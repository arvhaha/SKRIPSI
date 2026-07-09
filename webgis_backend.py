from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
from base64 import b64decode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from tensorflow.keras.models import Model, load_model


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATASET_PATH = ROOT / "Master_Data_Spasial_Jaktim_1990_sekarang.csv"
TEMPLATE_PATH = DATA_DIR / "east-jakarta-predictions.json"
DRAINAGE_PATH = DATA_DIR / "drainase_jaktim_template_backend.csv"
MODEL_PATH = ROOT / "model_bilstm_4class_jaktim.h5"
XGB_PATH = ROOT / "model_xgboost_4class_jaktim.pkl"
SCALER_PATH = ROOT / "scaler_4class_jaktim.pkl"
FEATURE_COLUMNS_PATH = ROOT / "daftar_kolom_fitur_4class.pkl"
MODEL_CONFIG_PATH = ROOT / "operational_multiclass_config.json"
LATEST_MULTICLASS_SUMMARY_PATH = ROOT / "artifacts" / "latest_multiclass_training_summary.json"
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
DEFAULT_TIME_STEPS = 5
CLASS_LABELS = [
    "Cerah (<5 mm)",
    "Hujan Ringan (5-20 mm)",
    "Hujan Sedang (20-50 mm)",
    "Hujan Lebat/Ekstrem (>=50 mm)",
]
CLASS_RANGE_LABELS = ["<5 mm", "5-20 mm", "20-50 mm", ">=50 mm"]
CLASS_SEVERITY_SCORES = [0.05, 0.35, 0.65, 0.95]
APP_NAME = os.getenv("APP_NAME", "FloodGIS Jakarta Timur").strip() or "FloodGIS Jakarta Timur"
APP_ENV = os.getenv("APP_ENV", "local").strip().lower() or "local"
APP_ENV_LABEL = os.getenv("APP_ENV_LABEL", APP_ENV.upper()).strip() or APP_ENV.upper()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()


@dataclass(frozen=True)
class ModelBundle:
    lstm: Any
    extractor: Model
    xgb: Any
    scaler: Any
    feature_columns: list[str]
    time_steps: int
    ensemble_mode: str
    ensemble_rule: dict[str, Any]
    decision_rule: dict[str, Any]


@dataclass(frozen=True)
class DrainageProfile:
    condition: str
    score: float | None
    confidence_label: str
    confidence_score: float
    source_type: str
    source_name: str
    note: str
    manual_condition: str | None
    manual_score: float | None
    suggested_condition: str | None
    suggested_score: float | None


def normalize_name(value: str) -> str:
    return "".join((value or "").lower().split())


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def is_blank_value(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""


def condition_to_default_score(condition: str | None) -> float | None:
    mapping = {
        "Baik": 30.0,
        "Sedang": 50.0,
        "Buruk": 70.0,
    }
    return mapping.get((condition or "").strip())


def score_to_condition(score: float | None) -> str:
    if score is None:
        return "Tidak diketahui"
    if score >= 67:
        return "Buruk"
    if score >= 34:
        return "Sedang"
    return "Baik"


def confidence_weight(label: str, score: float) -> float:
    caps = {
        "Tinggi": 1.0,
        "Sedang": 0.75,
        "Rendah": 0.35,
        "Manual estimasi": 0.45,
        "Tidak tersedia": 0.0,
    }
    base_weight = clamp(score / 100.0)
    return min(base_weight, caps.get(label, base_weight))


def serialize_payload(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def is_staging_environment() -> bool:
    return APP_ENV == "staging"


def is_admin_auth_configured() -> bool:
    return bool(ADMIN_USERNAME) and bool(ADMIN_PASSWORD)


def is_admin_auth_misconfigured() -> bool:
    return bool(ADMIN_USERNAME) != bool(ADMIN_PASSWORD)


def is_admin_page_locked() -> bool:
    if is_admin_auth_misconfigured():
        return True
    return APP_ENV == "production" and not is_admin_auth_configured()


def is_protected_admin_html_path(path: str) -> bool:
    normalized_path = (path or "").strip().lower()
    return normalized_path.startswith("/admin") and normalized_path.endswith(".html")


def validate_admin_basic_auth_header(header_value: str | None) -> bool:
    if not is_admin_auth_configured():
        return False

    if not header_value or not header_value.startswith("Basic "):
        return False

    try:
        decoded_value = b64decode(header_value[6:].strip()).decode("utf-8")
    except (BinasciiError, UnicodeDecodeError):
        return False

    username, separator, password = decoded_value.partition(":")
    if separator != ":":
        return False

    return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(
        password, ADMIN_PASSWORD
    )


@lru_cache(maxsize=1)
def load_template_payload() -> dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


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
        loaded = json.loads(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
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


@lru_cache(maxsize=1)
def load_latest_multiclass_summary() -> dict[str, Any] | None:
    if not LATEST_MULTICLASS_SUMMARY_PATH.exists():
        return None
    try:
        return json.loads(LATEST_MULTICLASS_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@lru_cache(maxsize=1)
def load_drainage_profiles() -> dict[str, DrainageProfile]:
    if not DRAINAGE_PATH.exists():
        return {}

    df = pd.read_csv(DRAINAGE_PATH, sep=";")
    profiles: dict[str, DrainageProfile] = {}

    for _, row in df.iterrows():
        district_name = str(row.get("Kecamatan", "")).strip()
        if not district_name:
            continue

        manual_condition = None if is_blank_value(row.get("Kondisi_Drainase_Manual")) else str(
            row.get("Kondisi_Drainase_Manual")
        ).strip()
        manual_score = None if is_blank_value(row.get("Skor_Drainase_Manual")) else float(
            row.get("Skor_Drainase_Manual")
        )
        suggested_condition = (
            None
            if is_blank_value(row.get("Kondisi_Drainase_Saran"))
            else str(row.get("Kondisi_Drainase_Saran")).strip()
        )
        suggested_score = (
            None
            if is_blank_value(row.get("Skor_Drainase_Saran"))
            else float(row.get("Skor_Drainase_Saran"))
        )

        if manual_score is None and manual_condition:
            manual_score = condition_to_default_score(manual_condition)
        if manual_condition is None and manual_score is not None:
            manual_condition = score_to_condition(manual_score)

        uses_manual = manual_condition is not None or manual_score is not None

        if uses_manual:
            final_condition = manual_condition or suggested_condition or "Tidak diketahui"
            final_score = manual_score if manual_score is not None else suggested_score
            source_type = "manual"
        else:
            final_condition = suggested_condition or "Tidak diketahui"
            final_score = suggested_score
            source_type = "derived"

        if final_score is None:
            final_score = condition_to_default_score(final_condition)

        confidence_label_value = (
            "Tidak tersedia"
            if is_blank_value(row.get("Confidence_Drainase"))
            else str(row.get("Confidence_Drainase")).strip()
        )
        confidence_score_value = (
            0.0
            if is_blank_value(row.get("Skor_Confidence_Drainase"))
            else float(row.get("Skor_Confidence_Drainase"))
        )

        if uses_manual and confidence_score_value == 0.0:
            confidence_label_value = "Manual estimasi"
            confidence_score_value = 45.0

        note_parts = []
        if not is_blank_value(row.get("Catatan_Manual")):
            note_parts.append(str(row.get("Catatan_Manual")).strip())
        if not is_blank_value(row.get("Catatan")):
            note_parts.append(str(row.get("Catatan")).strip())

        profiles[normalize_name(district_name)] = DrainageProfile(
            condition=final_condition,
            score=final_score,
            confidence_label=confidence_label_value,
            confidence_score=confidence_score_value,
            source_type=source_type,
            source_name=str(row.get("Sumber_Data", DRAINAGE_PATH.name)).strip() or DRAINAGE_PATH.name,
            note=" ".join(note_parts).strip(),
            manual_condition=manual_condition,
            manual_score=manual_score,
            suggested_condition=suggested_condition,
            suggested_score=suggested_score,
        )

    return profiles


def load_source_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    return df.dropna().copy()


def parse_optional_timestamp(value: Any) -> pd.Timestamp | None:
    if is_blank_value(value):
        return None

    try:
        return pd.Timestamp(value)
    except (TypeError, ValueError):
        return None


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


def probability_to_level(probability: float) -> dict[str, Any]:
    if probability < 0.20:
        return {
            "riskCategory": "Cerah",
            "webgisLevel": 1,
            "webgisColor": "Hijau",
            "webgisLevelLabel": "Level 1: Hijau",
            "webgisDescription": "Cerah / Sangat Ringan",
        }

    if probability < 0.50:
        return {
            "riskCategory": "Ringan",
            "webgisLevel": 2,
            "webgisColor": "Kuning",
            "webgisLevelLabel": "Level 2: Kuning",
            "webgisDescription": "Hujan Ringan",
        }

    if probability < 0.80:
        return {
            "riskCategory": "Sedang",
            "webgisLevel": 3,
            "webgisColor": "Oranye",
            "webgisLevelLabel": "Level 3: Oranye",
            "webgisDescription": "Hujan Sedang",
        }

    return {
        "riskCategory": "Lebat/Ekstrem",
        "webgisLevel": 4,
        "webgisColor": "Merah",
        "webgisLevelLabel": "Level 4: Merah",
        "webgisDescription": "Hujan Lebat/Ekstrem",
    }


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


def apply_drainage_adjustment(
    base_score: float,
    drainage_profile: DrainageProfile | None,
) -> tuple[float, float]:
    if drainage_profile is None or drainage_profile.score is None:
        return base_score, 0.0

    if drainage_profile.condition in {"Tidak diketahui", "Tidak tersedia"}:
        return base_score, 0.0

    severity = (float(drainage_profile.score) - 50.0) / 50.0
    weight = confidence_weight(
        drainage_profile.confidence_label,
        drainage_profile.confidence_score,
    )
    adjustment = 0.10 * severity * weight
    adjusted_score = clamp(base_score + adjustment)
    return adjusted_score, adjustment


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

    return payload


def recommendation_for_level(level: int) -> str:
    if level == 1:
        return "Pertahankan pemantauan rutin dan pemeliharaan preventif."

    if level == 2:
        return "Lakukan monitoring berkala dan pembersihan saluran lokal."

    if level == 3:
        return "Siapkan pemantauan intensif pada saluran dan area rawan genangan."

    return "Aktifkan kesiapsiagaan tinggi dan pantau titik genangan prioritas."


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
            fallback_payload = copy.deepcopy(template_district)
            fallback_payload["summary"] = (
                "Backend tidak menemukan data historis untuk kecamatan ini, "
                "sehingga payload bawaan dipertahankan."
            )
            if drainage_profile is not None:
                fallback_payload["drainageCondition"] = drainage_profile.condition
                fallback_payload["drainageConfidence"] = drainage_profile.confidence_label
                fallback_payload["drainageNote"] = drainage_profile.note
            generated_districts.append(fallback_payload)
            continue

        generated_districts.append(
            build_district_payload(
                bundle=bundle,
                template_district=template_district,
                district_frame=district_frame,
                drainage_profile=drainage_profile,
            )
        )

    now = pd.Timestamp.now(tz=JAKARTA_TZ)
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
    meta: dict[str, Any] = {}
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
    meta.update(
        {
            "appName": APP_NAME,
            "deploymentEnvironment": APP_ENV,
            "deploymentEnvironmentLabel": APP_ENV_LABEL,
            "isStaging": is_staging_environment(),
            "datasetId": "jaktim-hybrid-backend-v4-4class",
            "model": "Hybrid Bi-LSTM + XGBoost 4 Class (gated ensemble, chronological split)",
            "updatedAt": now.isoformat(),
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
    )
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


class FloodGISRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/health":
            self.respond_json({"status": "ok"})
            return

        if parsed_path.path == "/api/predictions":
            try:
                payload = build_prediction_payload()
            except Exception as error:  # pragma: no cover - defensive response
                self.respond_json(
                    {
                        "status": "error",
                        "message": "Backend gagal menghitung prediksi.",
                        "detail": str(error),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self.respond_json(payload)
            return

        if is_protected_admin_html_path(parsed_path.path):
            if self.enforce_admin_page_access():
                return

        if parsed_path.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def enforce_admin_page_access(self) -> bool:
        if is_admin_page_locked():
            self.respond_text(
                (
                    "Halaman admin dinonaktifkan sampai proteksi admin dikonfigurasi. "
                    "Atur ADMIN_USERNAME dan ADMIN_PASSWORD di environment deployment."
                ),
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return True

        if not is_admin_auth_configured():
            return False

        if validate_admin_basic_auth_header(self.headers.get("Authorization")):
            return False

        body = (
            "Autentikasi admin diperlukan untuk membuka halaman ini.\n"
        ).encode("utf-8")
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="FloodGIS Admin"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True

    def respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = serialize_payload(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def respond_text(self, message: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve FloodGIS static files and prediction API.")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host binding for the server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port binding for the server.",
    )
    parser.add_argument(
        "--export-static-json",
        action="store_true",
        help="Bangun payload terbaru lalu simpan ke data/east-jakarta-predictions.json.",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Jalankan tugas sekali lalu keluar tanpa menyalakan server.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.export_static_json:
        payload = build_prediction_payload()
        TEMPLATE_PATH.write_bytes(serialize_payload(payload))
        print(f"Payload statis berhasil diekspor ke {TEMPLATE_PATH}")

    if args.no_serve:
        return

    server = ThreadingHTTPServer((args.host, args.port), FloodGISRequestHandler)
    print(f"FloodGIS backend aktif di http://{args.host}:{args.port}/")
    print(f"Endpoint API prediksi: http://{args.host}:{args.port}/api/predictions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
