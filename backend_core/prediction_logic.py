from __future__ import annotations

import copy
import os
from functools import lru_cache
from typing import Any

import joblib
import numpy as np
import pandas as pd
from tensorflow.keras.models import Model, load_model

from backend_core.drainage_logic import load_drainage_profiles
from backend_core.legacy_core import (
    APP_ENV,
    APP_ENV_LABEL,
    APP_NAME,
    CLASS_LABELS,
    CLASS_RANGE_LABELS,
    CLASS_SEVERITY_SCORES,
    DEFAULT_TIME_STEPS,
    DISTRICT_GEOJSON_PATH,
    FEATURE_COLUMNS_PATH,
    MODEL_CONFIG_PATH,
    MODEL_PATH,
    XGB_PATH,
    DrainageProfile,
    ModelBundle,
    apply_drainage_adjustment,
    current_jakarta_timestamp,
    is_staging_environment,
    load_latest_multiclass_summary,
    load_template_payload,
    normalize_name,
    parse_optional_timestamp,
    probability_to_level,
    DATASET_PATH,
    SCALER_PATH,
)


@lru_cache(maxsize=1)
def load_geojson_payload() -> dict[str, Any]:
    return json_loads_file(DISTRICT_GEOJSON_PATH)


@lru_cache(maxsize=1)
def load_operational_model_config() -> dict[str, Any]:
    default_config = {
        "time_steps": DEFAULT_TIME_STEPS,
        "ensemble_mode": "xgb_extreme_threshold",
        "ensemble_rule": {
            "enabled": False,
            "class_2_threshold": 1.0,
            "class_3_threshold": 1.0,
            "class_2_margin": 0.0,
            "class_3_margin": 0.0,
        },
        "decision_rule": {
            "enabled": False,
            "extreme_threshold": 0.0,
            "extreme_margin": 0.0,
        },
    }

    if not MODEL_CONFIG_PATH.exists():
        return default_config

    try:
        loaded = json_loads_file(MODEL_CONFIG_PATH)
    except Exception:
        return default_config

    decision_rule = loaded.get("decision_rule", {})
    ensemble_rule = loaded.get("ensemble_rule", {})
    return {
        "time_steps": int(loaded.get("time_steps", DEFAULT_TIME_STEPS)),
        "ensemble_mode": str(loaded.get("ensemble_mode", "xgb_extreme_threshold")),
        "ensemble_rule": {
            "enabled": bool(ensemble_rule.get("enabled", False)),
            "class_2_threshold": float(ensemble_rule.get("class_2_threshold", 1.0)),
            "class_3_threshold": float(ensemble_rule.get("class_3_threshold", 1.0)),
            "class_2_margin": float(ensemble_rule.get("class_2_margin", 0.0)),
            "class_3_margin": float(ensemble_rule.get("class_3_margin", 0.0)),
            "description": str(ensemble_rule.get("description", "")),
            "selection_score": float(ensemble_rule.get("selection_score", 0.0)),
        },
        "decision_rule": {
            "enabled": bool(decision_rule.get("enabled", False)),
            "extreme_threshold": float(decision_rule.get("extreme_threshold", 0.0)),
            "extreme_margin": float(decision_rule.get("extreme_margin", 0.0)),
            "description": str(decision_rule.get("description", "")),
        },
    }


@lru_cache(maxsize=1)
def load_model_bundle() -> ModelBundle:
    config = load_operational_model_config()
    lstm = load_model(MODEL_PATH, compile=False)
    extractor = Model(inputs=lstm.input, outputs=lstm.get_layer("feature_layer").output)
    xgb = joblib.load(XGB_PATH)
    scaler = joblib.load(SCALER_PATH)
    feature_columns = list(joblib.load(FEATURE_COLUMNS_PATH))
    decision_rule = dict(config.get("decision_rule", {}))
    ensemble_rule = dict(config.get("ensemble_rule", {}))
    return ModelBundle(
        lstm=lstm,
        extractor=extractor,
        xgb=xgb,
        scaler=scaler,
        feature_columns=feature_columns,
        time_steps=int(config.get("time_steps", DEFAULT_TIME_STEPS)),
        ensemble_mode=str(config.get("ensemble_mode", "xgb_extreme_threshold")),
        ensemble_rule=ensemble_rule,
        decision_rule=decision_rule,
    )


def load_source_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    return df.dropna().copy()


def compute_rain_streak(series: pd.Series) -> pd.Series:
    streak_values: list[float] = []
    current_streak = 0.0
    for value in series.fillna(0.0).tolist():
        if float(value) > 0.0:
            current_streak += 1.0
        else:
            current_streak = 0.0
        streak_values.append(current_streak)
    return pd.Series(streak_values, index=series.index, dtype="float32")


def build_sequence_frame(
    district_frame: pd.DataFrame,
    district_name: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    sequence_frame = district_frame.sort_values("Tanggal").copy()
    rain_series = sequence_frame["Curah Hujan (mm)"]

    sequence_frame["Hujan_3Hari_Kumulatif"] = rain_series.rolling(window=3, min_periods=1).mean()
    sequence_frame["Hujan_7Hari_Kumulatif"] = rain_series.rolling(window=7, min_periods=1).sum()
    sequence_frame["Hujan_7Hari_Maksimum"] = rain_series.rolling(window=7, min_periods=1).max()
    for lag in (1, 2, 3, 7):
        sequence_frame[f"Hujan_Lag_{lag}"] = rain_series.shift(lag)
    sequence_frame["HariHujan_Beruntun"] = compute_rain_streak(rain_series)

    sequence_frame["Bulan"] = sequence_frame["Tanggal"].dt.month
    sequence_frame["HariDalamTahun"] = sequence_frame["Tanggal"].dt.dayofyear
    sequence_frame["Bulan_Sin"] = np.sin(2 * np.pi * sequence_frame["Bulan"] / 12)
    sequence_frame["Bulan_Cos"] = np.cos(2 * np.pi * sequence_frame["Bulan"] / 12)
    sequence_frame["HariTahun_Sin"] = np.sin(2 * np.pi * sequence_frame["HariDalamTahun"] / 366)
    sequence_frame["HariTahun_Cos"] = np.cos(2 * np.pi * sequence_frame["HariDalamTahun"] / 366)
    for lag_column in ("Hujan_Lag_1", "Hujan_Lag_2", "Hujan_Lag_3", "Hujan_Lag_7"):
        sequence_frame[lag_column] = sequence_frame[lag_column].fillna(0.0)
    sequence_frame["HariHujan_Beruntun"] = sequence_frame["HariHujan_Beruntun"].fillna(0.0)

    normalized_name = normalize_name(district_name)
    for feature_name in feature_columns:
        if feature_name.startswith("Kec_"):
            sequence_frame[feature_name] = float(
                normalize_name(feature_name[4:]) == normalized_name
            )

    missing_columns = [name for name in feature_columns if name not in sequence_frame.columns]
    if missing_columns:
        raise KeyError(f"Kolom fitur tidak lengkap untuk inference: {missing_columns}")

    return sequence_frame


def extract_class_probabilities(latent_features: np.ndarray, xgb_model: Any) -> np.ndarray:
    probabilities = xgb_model.predict_proba(latent_features)
    if probabilities.ndim != 2 or probabilities.shape[0] == 0:
        raise ValueError("Output probabilitas XGBoost tidak valid.")
    if probabilities.shape[1] != 4:
        raise ValueError(
            f"Backend mengharapkan 4 probabilitas kelas, tetapi menerima shape {probabilities.shape}."
        )
    return probabilities[0]


def extract_lstm_class_probabilities(inference_input: np.ndarray, lstm_model: Any) -> np.ndarray:
    probabilities = lstm_model.predict(inference_input, verbose=0)
    if probabilities.ndim != 2 or probabilities.shape[0] == 0:
        raise ValueError("Output probabilitas LSTM tidak valid.")
    if probabilities.shape[1] != 4:
        raise ValueError(
            f"Backend mengharapkan 4 probabilitas kelas dari LSTM, tetapi menerima shape {probabilities.shape}."
        )
    return probabilities[0]


def class_probabilities_to_risk_score(probabilities: np.ndarray) -> float:
    return float(np.dot(probabilities, np.array(CLASS_SEVERITY_SCORES, dtype=np.float32)))


def apply_extreme_decision_rule(
    probabilities: np.ndarray,
    extreme_threshold: float,
    extreme_margin: float,
) -> int:
    predicted_index = int(np.argmax(probabilities))
    if predicted_index != 3:
        return predicted_index

    fallback_index = int(np.argmax(probabilities[:3]))
    fallback_probability = float(probabilities[fallback_index])
    extreme_probability = float(probabilities[3])

    if extreme_probability < extreme_threshold or extreme_probability < (fallback_probability + extreme_margin):
        return fallback_index

    return predicted_index


def apply_gated_ensemble_rule(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    ensemble_rule: dict[str, Any],
) -> tuple[int, str]:
    predicted_index = int(np.argmax(lstm_probabilities))

    if not bool(ensemble_rule.get("enabled", False)):
        return predicted_index, "lstm_base"

    class_2_threshold = float(ensemble_rule.get("class_2_threshold", 1.0))
    class_3_threshold = float(ensemble_rule.get("class_3_threshold", 1.0))
    class_2_margin = float(ensemble_rule.get("class_2_margin", 0.0))
    class_3_margin = float(ensemble_rule.get("class_3_margin", 0.0))

    strongest_low_class_probability = float(np.max(xgb_probabilities[:2]))
    strongest_non_extreme_probability = float(np.max(xgb_probabilities[:3]))

    if float(xgb_probabilities[3]) >= class_3_threshold and float(xgb_probabilities[3]) >= (
        strongest_non_extreme_probability + class_3_margin
    ):
        return 3, "xgb_override_class_3"

    if predicted_index in (0, 1) and float(xgb_probabilities[2]) >= class_2_threshold and float(
        xgb_probabilities[2]
    ) >= (strongest_low_class_probability + class_2_margin):
        return 2, "xgb_override_class_2"

    return predicted_index, "lstm_base"


def compose_operational_probabilities(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    predicted_class_index: int,
) -> np.ndarray:
    combined = lstm_probabilities.astype(np.float32).copy()
    base_prediction = int(np.argmax(lstm_probabilities))
    safe_prediction = max(0, min(int(predicted_class_index), len(combined) - 1))

    if safe_prediction == base_prediction:
        return combined

    target_probability = max(float(combined[safe_prediction]), float(xgb_probabilities[safe_prediction]))
    target_probability = min(max(target_probability, 1e-6), 0.95)

    other_indices = [class_index for class_index in range(len(combined)) if class_index != safe_prediction]
    other_sum = float(np.sum(combined[other_indices]))

    if other_sum <= 1e-8:
        combined[:] = np.float32((1.0 - target_probability) / max(1, len(other_indices)))
        combined[safe_prediction] = np.float32(target_probability)
        return combined

    scaling_factor = (1.0 - target_probability) / other_sum
    combined[other_indices] = combined[other_indices] * scaling_factor
    combined[safe_prediction] = np.float32(target_probability)
    return combined.astype(np.float32)


def class_index_to_rainfall_info(class_index: int) -> dict[str, Any]:
    safe_index = max(0, min(int(class_index), len(CLASS_LABELS) - 1))
    return {
        "predictedRainfallClassIndex": safe_index,
        "predictedRainfallLabel": CLASS_LABELS[safe_index],
        "predictedRainfallRange": CLASS_RANGE_LABELS[safe_index],
    }


def recommendation_for_level(level: int) -> str:
    if level == 1:
        return "Pertahankan pemantauan rutin dan pemeliharaan preventif."
    if level == 2:
        return "Lakukan monitoring berkala dan pembersihan saluran lokal."
    if level == 3:
        return "Siapkan pemantauan intensif pada saluran dan area rawan genangan."
    return "Aktifkan kesiapsiagaan tinggi dan pantau titik genangan prioritas."


def build_district_payload(
    bundle: ModelBundle,
    template_district: dict[str, Any],
    district_frame: pd.DataFrame,
    drainage_profile: DrainageProfile | None,
) -> dict[str, Any]:
    district_name = str(district_frame["Kecamatan"].iloc[0])
    sequence_frame = build_sequence_frame(district_frame, district_name, bundle.feature_columns)

    if len(sequence_frame) < bundle.time_steps:
        raise ValueError(
            f"Data {district_name} hanya memiliki {len(sequence_frame)} baris, "
            f"minimal {bundle.time_steps} untuk inference."
        )

    latest_window = sequence_frame.tail(bundle.time_steps).copy()
    scaled_window = bundle.scaler.transform(latest_window[bundle.feature_columns])
    inference_input = np.array([scaled_window], dtype=np.float32)

    lstm_probabilities = extract_lstm_class_probabilities(inference_input, bundle.lstm)
    latent_features = bundle.extractor.predict(inference_input, verbose=0)
    xgb_probabilities = extract_class_probabilities(latent_features, bundle.xgb)

    if bundle.ensemble_mode == "gated_lstm_xgb_override":
        predicted_class_index, decision_source = apply_gated_ensemble_rule(
            lstm_probabilities,
            xgb_probabilities,
            bundle.ensemble_rule,
        )
        class_probabilities = compose_operational_probabilities(
            lstm_probabilities,
            xgb_probabilities,
            predicted_class_index,
        )
    else:
        predicted_class_index = apply_extreme_decision_rule(
            xgb_probabilities,
            float(bundle.decision_rule.get("extreme_threshold", 0.0)),
            float(bundle.decision_rule.get("extreme_margin", 0.0)),
        )
        class_probabilities = xgb_probabilities.astype(np.float32).copy()
        decision_source = "xgb_threshold_rule"

    predicted_class_probability = float(class_probabilities[predicted_class_index])
    extreme_probability = float(class_probabilities[3])
    base_risk_score = class_probabilities_to_risk_score(class_probabilities)
    adjusted_risk_score, drainage_adjustment = apply_drainage_adjustment(
        base_risk_score,
        drainage_profile,
    )
    predicted_class_probability_percent = round(predicted_class_probability * 100, 1)
    extreme_probability_percent = round(extreme_probability * 100, 1)
    adjusted_risk_score_percent = round(adjusted_risk_score * 100, 1)
    level_info = probability_to_level(adjusted_risk_score)
    rainfall_info = class_index_to_rainfall_info(predicted_class_index)

    latest_row = sequence_frame.iloc[-1]
    forecast_date = (pd.Timestamp(latest_row["Tanggal"]) + pd.Timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    payload = copy.deepcopy(template_district)
    payload.update(level_info)
    payload.update(rainfall_info)

    payload["predictedRainfallMm"] = None
    payload["riskScore"] = round(adjusted_risk_score, 4)
    payload["riskScorePercent"] = adjusted_risk_score_percent
    payload["baseModelRiskScore"] = round(base_risk_score, 4)
    payload["predictedClassProbability"] = round(predicted_class_probability, 4)
    payload["predictedClassProbabilityPercent"] = predicted_class_probability_percent
    payload["probabilityWaspada"] = round(extreme_probability, 4)
    payload["probabilityWaspadaPercent"] = extreme_probability_percent
    payload["classProbabilities"] = {
        "cerah": round(float(class_probabilities[0]), 4),
        "ringan": round(float(class_probabilities[1]), 4),
        "sedang": round(float(class_probabilities[2]), 4),
        "lebat_ekstrem": round(float(class_probabilities[3]), 4),
    }
    payload["baseLstmClassProbabilities"] = {
        "cerah": round(float(lstm_probabilities[0]), 4),
        "ringan": round(float(lstm_probabilities[1]), 4),
        "sedang": round(float(lstm_probabilities[2]), 4),
        "lebat_ekstrem": round(float(lstm_probabilities[3]), 4),
    }
    payload["latentXgbClassProbabilities"] = {
        "cerah": round(float(xgb_probabilities[0]), 4),
        "ringan": round(float(xgb_probabilities[1]), 4),
        "sedang": round(float(xgb_probabilities[2]), 4),
        "lebat_ekstrem": round(float(xgb_probabilities[3]), 4),
    }
    payload["decisionSource"] = decision_source
    payload["forecastLabel"] = f"Prediksi {forecast_date}"
    payload["actualStatusFromNotebookTest"] = ""
    payload["rainfallDisplayNote"] = (
        "Model 4 class memprediksi rentang/intensitas curah hujan, bukan angka mm presisi."
    )
    payload["drainageCondition"] = (
        drainage_profile.condition if drainage_profile is not None else payload.get("drainageCondition", "Tidak tersedia")
    )
    payload["drainageScore"] = (
        round(float(drainage_profile.score), 1)
        if drainage_profile is not None and drainage_profile.score is not None
        else None
    )
    payload["drainageConfidence"] = (
        drainage_profile.confidence_label if drainage_profile is not None else "Tidak tersedia"
    )
    payload["drainageConfidenceScore"] = (
        round(float(drainage_profile.confidence_score), 1) if drainage_profile is not None else 0.0
    )
    payload["drainageAdjustmentApplied"] = round(drainage_adjustment, 4)
    payload["drainageAdjustmentPercent"] = round(drainage_adjustment * 100, 1)
    payload["drainageDataSourceType"] = (
        drainage_profile.source_type if drainage_profile is not None else "template"
    )
    payload["drainageDataSourceName"] = (
        drainage_profile.source_name if drainage_profile is not None else "Template WebGIS"
    )
    payload["drainageSuggestedCondition"] = (
        drainage_profile.suggested_condition if drainage_profile is not None else None
    )
    payload["drainageSuggestedScore"] = (
        round(float(drainage_profile.suggested_score), 1)
        if drainage_profile is not None and drainage_profile.suggested_score is not None
        else None
    )
    payload["drainageManualCondition"] = (
        drainage_profile.manual_condition if drainage_profile is not None else None
    )
    payload["drainageManualScore"] = (
        round(float(drainage_profile.manual_score), 1)
        if drainage_profile is not None and drainage_profile.manual_score is not None
        else None
    )
    payload["drainageNote"] = drainage_profile.note if drainage_profile is not None else ""

    if drainage_profile is None or abs(drainage_adjustment) < 0.0001:
        drainage_summary = "tanpa penyesuaian berarti dari layer drainase"
    else:
        adjustment_sign = "+" if drainage_adjustment > 0 else ""
        drainage_summary = (
            f"dengan penyesuaian drainase {adjustment_sign}{drainage_adjustment * 100:.1f} poin "
            f"(kondisi {payload['drainageCondition']}, confidence {payload['drainageConfidence']})"
        )

    payload["summary"] = (
        f"Backend memproses {bundle.time_steps} hari terakhir data {payload['label']} hingga "
        f"{pd.Timestamp(latest_row['Tanggal']).strftime('%Y-%m-%d')} dan memprediksi "
        f"kelas {payload['predictedRainfallLabel']} dengan confidence "
        f"{predicted_class_probability_percent:.1f}% serta probabilitas kelas lebat/ekstrem "
        f"{extreme_probability_percent:.1f}% lewat keputusan {decision_source} {drainage_summary}, sehingga skor risiko akhir "
        f"menjadi {adjusted_risk_score_percent:.1f}% "
        f"({payload['webgisLevelLabel']}: {payload['webgisDescription']})."
    )
    payload["recommendation"] = recommendation_for_level(int(payload["webgisLevel"]))
    payload["latestObservationDate"] = pd.Timestamp(latest_row["Tanggal"]).strftime("%Y-%m-%d")
    payload["latestObservedRainfallMm"] = round(float(latest_row["Curah Hujan (mm)"]), 1)
    payload["recentThreeDayAverageMm"] = round(float(latest_row["Hujan_3Hari_Kumulatif"]), 1)
    payload["latestObservedTemperatureC"] = round(float(latest_row["Suhu Rata-rata (C)"]), 1)
    payload["latestObservedHumidityPercent"] = round(
        float(latest_row["Kelembapan Rata-rata (%)"]),
        1,
    )

    return payload


def build_unavailable_district_payload(
    template_district: dict[str, Any],
    drainage_profile: DrainageProfile | None,
    message: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(template_district)

    payload["predictedRainfallMm"] = None
    payload["drainageCondition"] = (
        drainage_profile.condition if drainage_profile is not None else "Tidak tersedia"
    )
    payload["riskCategory"] = "Tidak tersedia"
    payload["riskScore"] = None
    payload["probabilityWaspada"] = None
    payload["probabilityWaspadaPercent"] = None
    payload["webgisLevel"] = 0
    payload["webgisColor"] = "Abu-abu"
    payload["webgisLevelLabel"] = "Data tidak tersedia"
    payload["webgisDescription"] = "Data historis belum tersedia"
    payload["forecastLabel"] = "Prediksi tidak tersedia"
    payload["actualStatusFromNotebookTest"] = ""
    payload["rainfallDisplayNote"] = (
        "Prediksi tidak dapat dibentuk karena data historis kecamatan belum tersedia."
    )
    payload["summary"] = message
    payload["recommendation"] = (
        "Lengkapi data historis kecamatan terlebih dahulu sebelum hasil dibagikan ke publik."
    )
    payload["riskScorePercent"] = None
    payload["baseModelRiskScore"] = None
    payload["drainageScore"] = (
        round(float(drainage_profile.score), 1)
        if drainage_profile is not None and drainage_profile.score is not None
        else None
    )
    payload["drainageConfidence"] = (
        drainage_profile.confidence_label if drainage_profile is not None else "Tidak tersedia"
    )
    payload["drainageConfidenceScore"] = (
        round(float(drainage_profile.confidence_score), 1) if drainage_profile is not None else 0.0
    )
    payload["drainageAdjustmentApplied"] = 0.0
    payload["drainageAdjustmentPercent"] = 0.0
    payload["drainageDataSourceType"] = (
        drainage_profile.source_type if drainage_profile is not None else "missing_source_data"
    )
    payload["drainageDataSourceName"] = (
        drainage_profile.source_name if drainage_profile is not None else "Data sumber tidak tersedia"
    )
    payload["drainageSuggestedCondition"] = (
        drainage_profile.suggested_condition if drainage_profile is not None else None
    )
    payload["drainageSuggestedScore"] = (
        round(float(drainage_profile.suggested_score), 1)
        if drainage_profile is not None and drainage_profile.suggested_score is not None
        else None
    )
    payload["drainageManualCondition"] = (
        drainage_profile.manual_condition if drainage_profile is not None else None
    )
    payload["drainageManualScore"] = (
        round(float(drainage_profile.manual_score), 1)
        if drainage_profile is not None and drainage_profile.manual_score is not None
        else None
    )
    payload["drainageNote"] = drainage_profile.note if drainage_profile is not None else ""
    payload["latestObservationDate"] = None
    payload["latestObservedRainfallMm"] = None
    payload["recentThreeDayAverageMm"] = None
    payload["predictedRainfallClassIndex"] = None
    payload["predictedRainfallLabel"] = "Data tidak tersedia"
    payload["predictedRainfallRange"] = "Data tidak tersedia"
    payload["predictedClassProbability"] = None
    payload["predictedClassProbabilityPercent"] = None
    payload["classProbabilities"] = {}
    payload["baseLstmClassProbabilities"] = {}
    payload["latentXgbClassProbabilities"] = {}
    payload["decisionSource"] = "missing_source_data"
    payload["latestObservedTemperatureC"] = None
    payload["latestObservedHumidityPercent"] = None
    payload["hasAdminOverride"] = False
    payload["hasAdminDrainageOverride"] = False
    payload["adminOverrideUpdatedAt"] = None

    return payload


def build_prediction_payload() -> dict[str, Any]:
    template_payload = copy.deepcopy(load_template_payload())
    bundle = load_model_bundle()
    drainage_profiles = load_drainage_profiles()
    source_df = load_source_dataset()
    districts_by_key = {
        normalize_name(name): frame.copy()
        for name, frame in source_df.groupby("Kecamatan", sort=False)
    }

    generated_districts: list[dict[str, Any]] = []
    for template_district in template_payload.get("districts", []):
        district_key = normalize_name(str(template_district.get("name", "")))
        district_frame = districts_by_key.get(district_key)
        drainage_profile = drainage_profiles.get(district_key)

        if district_frame is None:
            generated_districts.append(
                build_unavailable_district_payload(
                    template_district=template_district,
                    drainage_profile=drainage_profile,
                    message=(
                        "Backend tidak menemukan data historis untuk kecamatan ini, "
                        "sehingga prediksi baru belum dapat dibentuk."
                    ),
                )
            )
            continue

        try:
            generated_districts.append(
                build_district_payload(
                    bundle=bundle,
                    template_district=template_district,
                    district_frame=district_frame,
                    drainage_profile=drainage_profile,
                )
            )
        except ValueError as error:
            generated_districts.append(
                build_unavailable_district_payload(
                    template_district=template_district,
                    drainage_profile=drainage_profile,
                    message=str(error),
                )
            )
            continue
        except Exception as error:  # pragma: no cover
            generated_districts.append(
                build_unavailable_district_payload(
                    template_district=template_district,
                    drainage_profile=drainage_profile,
                    message=(
                        "Terjadi kegagalan saat membentuk prediksi kecamatan ini dari backend. "
                        f"Detail: {error}"
                    ),
                )
            )
            continue

    now = current_jakarta_timestamp()
    latest_observation_dates = [
        parsed_value
        for parsed_value in (
            parse_optional_timestamp(district.get("latestObservationDate"))
            for district in generated_districts
        )
        if parsed_value is not None
    ]
    forecast_target_dates = [
        parsed_value
        for parsed_value in (
            parse_optional_timestamp(
                str(district.get("forecastLabel", "")).replace("Prediksi ", "", 1).strip()
            )
            for district in generated_districts
        )
        if parsed_value is not None
    ]
    latest_observation_date = max(latest_observation_dates) if latest_observation_dates else None
    forecast_target_date = max(forecast_target_dates) if forecast_target_dates else None
    observation_age_days = (
        max(0, int((now.date() - latest_observation_date.date()).days))
        if latest_observation_date is not None
        else None
    )
    freshness_warnings: list[str] = []
    if latest_observation_date is not None and latest_observation_date.date() > now.date():
        freshness_warnings.append("Tanggal observasi terakhir berada di masa depan dibanding jam server.")
    if forecast_target_date is not None and forecast_target_date.date() < now.date():
        freshness_warnings.append("Target prediksi sudah lewat dari tanggal server saat payload dibuka.")
    if forecast_target_date is not None and latest_observation_date is not None:
        if forecast_target_date.date() < latest_observation_date.date():
            freshness_warnings.append("Target prediksi lebih awal daripada observasi terakhir.")

    freshness_status = "ok"
    if observation_age_days is not None and observation_age_days > 3:
        freshness_status = "stale"
    if freshness_warnings:
        freshness_status = "warning"
    latest_multiclass_summary = load_latest_multiclass_summary()
    if latest_multiclass_summary:
        multiclass_metrics = latest_multiclass_summary.get("metrics", {})
        model_accuracy_note = (
            "Evaluasi retrain 4 class terakhir menghasilkan "
            f"akurasi {multiclass_metrics.get('accuracy', 0.0) * 100:.2f}%, "
            f"macro recall {multiclass_metrics.get('macro_recall', 0.0) * 100:.2f}%, "
            f"dan recall kelas lebat/ekstrem {multiclass_metrics.get('critical_recall', 0.0) * 100:.2f}%. "
            "Gunakan sebagai pendukung visualisasi, bukan peringatan operasional final."
        )
    else:
        model_accuracy_note = (
            "Prediksi kelas curah hujan berasal dari pipeline multiclass classification. "
            "Gunakan sebagai pendukung visualisasi, bukan peringatan operasional final."
        )

    meta: dict[str, Any] = {
        "appName": APP_NAME,
        "deploymentEnvironment": APP_ENV,
        "deploymentEnvironmentLabel": APP_ENV_LABEL,
        "isStaging": is_staging_environment(),
        "datasetId": "jaktim-hybrid-backend-v4-4class",
        "model": "Hybrid Bi-LSTM + XGBoost 4 Class (gated ensemble, chronological split)",
        "updatedAt": now.isoformat(),
        "serverGeneratedAt": now.isoformat(),
        "serverCurrentDate": now.strftime("%Y-%m-%d"),
        "runtimeClockSource": "fixed_env"
        if any(str(os.getenv(key, "")).strip() for key in ("FLOODGIS_FIXED_NOW", "FLOODGIS_REFERENCE_NOW"))
        else "system_clock",
        "latestObservationDate": (
            latest_observation_date.strftime("%Y-%m-%d")
            if latest_observation_date is not None
            else None
        ),
        "forecastTargetDate": (
            forecast_target_date.strftime("%Y-%m-%d")
            if forecast_target_date is not None
            else None
        ),
        "observationAgeDays": observation_age_days,
        "freshnessStatus": freshness_status,
        "freshnessWarnings": freshness_warnings,
        "staleDataThresholdDays": 3,
        "refreshInterval": "Setiap permintaan API / saat halaman dimuat",
        "rainfallSource": (
            "Master_Data_Spasial_Jaktim_1990_sekarang.csv - "
            f"jendela {bundle.time_steps} hari terakhir per kecamatan"
        ),
        "drainageSource": "drainase_jaktim_template_backend.csv - manual override + saran otomatis + confidence data",
        "forecastHorizonDays": 1,
        "modelAccuracyNote": model_accuracy_note,
        "conversionNote": (
            "Backend menghitung probabilitas 4 kelas curah hujan dari data historis "
            f"{bundle.time_steps} hari terakhir. LSTM menjadi prediksi dasar, lalu XGBoost "
            "pada fitur laten hanya boleh melakukan override selektif ke kelas sedang atau "
            "lebat/ekstrem saat sinyalnya cukup kuat, sebelum skor risiko dasar digeser "
            "terbatas oleh layer drainase dan confidence data."
        ),
        "drainageAdjustmentNote": (
            "Layer drainase tidak mengubah prediksi hujan mentah. Layer ini hanya "
            "menggeser skor risiko akhir dalam skala kecil-menengah sesuai kondisi "
            "drainase dan tingkat kepercayaan datanya."
        ),
        "modelDecisionRule": {
            "ensembleMode": bundle.ensemble_mode,
            "class2Threshold": round(float(bundle.ensemble_rule.get("class_2_threshold", 1.0)), 4),
            "class3Threshold": round(float(bundle.ensemble_rule.get("class_3_threshold", 1.0)), 4),
            "class2Margin": round(float(bundle.ensemble_rule.get("class_2_margin", 0.0)), 4),
            "class3Margin": round(float(bundle.ensemble_rule.get("class_3_margin", 0.0)), 4),
        },
    }
    if latest_multiclass_summary:
        multiclass_metrics = latest_multiclass_summary.get("metrics", {})
        meta.update(
            {
                "modelAccuracyFromNotebook": round(float(multiclass_metrics.get("accuracy", 0.0)), 4),
                "modelMacroRecall": round(float(multiclass_metrics.get("macro_recall", 0.0)), 4),
                "modelMacroF1": round(float(multiclass_metrics.get("macro_f1", 0.0)), 4),
                "modelCriticalRecall": round(float(multiclass_metrics.get("critical_recall", 0.0)), 4),
                "modelCriticalPrecision": round(
                    float(multiclass_metrics.get("critical_precision", 0.0)), 4
                ),
                "modelLastRetrainedAt": latest_multiclass_summary.get("run_timestamp"),
            }
        )

    return {
        "meta": meta,
        "forecastDays": [],
        "districts": generated_districts,
    }


def json_loads_file(path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "apply_gated_ensemble_rule",
    "build_district_payload",
    "build_prediction_payload",
    "build_sequence_frame",
    "compose_operational_probabilities",
    "load_geojson_payload",
    "load_model_bundle",
    "load_source_dataset",
]
