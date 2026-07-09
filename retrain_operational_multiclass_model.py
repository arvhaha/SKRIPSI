from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import MinMaxScaler
from sklearn.utils.class_weight import compute_class_weight, compute_sample_weight

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import tensorflow as tf
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Bidirectional, Dense, Dropout, Input, LSTM
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "Master_Data_Spasial_Jaktim_1990_sekarang.csv"
ARTIFACTS_DIR = ROOT / "artifacts"
LATEST_SUMMARY_PATH = ARTIFACTS_DIR / "latest_multiclass_training_summary.json"
MODEL_CONFIG_PATH = ROOT / "operational_multiclass_config.json"
MODEL_PATH = ROOT / "model_bilstm_4class_jaktim.h5"
XGB_PATH = ROOT / "model_xgboost_4class_jaktim.pkl"
SCALER_PATH = ROOT / "scaler_4class_jaktim.pkl"
FEATURE_COLUMNS_PATH = ROOT / "daftar_kolom_fitur_4class.pkl"
TIME_STEPS = 5
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
SEED = 42
CLASS_NAMES = [
    "0_Cerah (<5mm)",
    "1_Ringan (5-20mm)",
    "2_Sedang (20-50mm)",
    "3_Lebat/Ekstrem (>=50mm)",
]
LSTM_CONFIG = {
    "units_1": 64,
    "units_2": 32,
    "dropout": 0.20,
    "dense_units": 16,
    "learning_rate": 0.0010,
    "batch_size": 64,
}
XGB_CANDIDATES = [
    {
        "name": "XGB_1",
        "max_depth": 4,
        "learning_rate": 0.05,
        "n_estimators": 250,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1,
    },
    {
        "name": "XGB_2",
        "max_depth": 5,
        "learning_rate": 0.05,
        "n_estimators": 350,
        "subsample": 0.9,
        "colsample_bytree": 0.8,
        "min_child_weight": 2,
    },
    {
        "name": "XGB_3",
        "max_depth": 6,
        "learning_rate": 0.03,
        "n_estimators": 450,
        "subsample": 0.8,
        "colsample_bytree": 0.9,
        "min_child_weight": 2,
    },
    {
        "name": "XGB_4",
        "max_depth": 4,
        "learning_rate": 0.08,
        "n_estimators": 220,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "min_child_weight": 1,
    },
]
EXTREME_THRESHOLD_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
EXTREME_MARGIN_GRID = [0.00, 0.02, 0.05, 0.08, 0.10, 0.15]
CLASS_2_THRESHOLD_GRID = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
CLASS_3_THRESHOLD_GRID = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
CLASS_2_MARGIN_GRID = [0.00, 0.02, 0.05]
CLASS_3_MARGIN_GRID = [0.00, 0.02, 0.05]


@dataclass(frozen=True)
class DatasetBundle:
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    scaler: MinMaxScaler
    feature_columns: list[str]
    split_summary: dict[str, Any]
    class_distribution_total: dict[str, int]


def klasifikasi_hujan_4_kelas(curah_hujan: float) -> int:
    if curah_hujan < 5:
        return 0
    if curah_hujan <= 20:
        return 1
    if curah_hujan <= 50:
        return 2
    return 3


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


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def engineer_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    grouped_rain = df.groupby("Kecamatan")["Curah Hujan (mm)"]

    df["Hujan_3Hari_Kumulatif"] = grouped_rain.transform(
        lambda values: values.rolling(window=3, min_periods=1).mean()
    )
    df["Hujan_7Hari_Kumulatif"] = grouped_rain.transform(
        lambda values: values.rolling(window=7, min_periods=1).sum()
    )
    df["Hujan_7Hari_Maksimum"] = grouped_rain.transform(
        lambda values: values.rolling(window=7, min_periods=1).max()
    )

    for lag in (1, 2, 3, 7):
        df[f"Hujan_Lag_{lag}"] = grouped_rain.transform(lambda values, lag=lag: values.shift(lag))

    df["HariHujan_Beruntun"] = grouped_rain.transform(compute_rain_streak)
    df["Bulan"] = df["Tanggal"].dt.month
    df["HariDalamTahun"] = df["Tanggal"].dt.dayofyear
    df["Bulan_Sin"] = np.sin(2 * np.pi * df["Bulan"] / 12)
    df["Bulan_Cos"] = np.cos(2 * np.pi * df["Bulan"] / 12)
    df["HariTahun_Sin"] = np.sin(2 * np.pi * df["HariDalamTahun"] / 366)
    df["HariTahun_Cos"] = np.cos(2 * np.pi * df["HariDalamTahun"] / 366)

    lag_columns = [f"Hujan_Lag_{lag}" for lag in (1, 2, 3, 7)]
    df[lag_columns] = df[lag_columns].fillna(0.0)
    df["HariHujan_Beruntun"] = df["HariHujan_Beruntun"].fillna(0.0)
    return df


def normalize_start_date(start_date: str | pd.Timestamp | None) -> pd.Timestamp | None:
    if start_date is None or start_date == "":
        return None
    timestamp = pd.Timestamp(start_date)
    if pd.isna(timestamp):
        return None
    return timestamp.normalize()


def prepare_feature_frame(start_date: str | pd.Timestamp | None = None) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(DATASET_PATH, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    df = df.dropna().sort_values(by=["Kecamatan", "Tanggal"]).reset_index(drop=True)

    normalized_start_date = normalize_start_date(start_date)
    if normalized_start_date is not None:
        df = df[df["Tanggal"] >= normalized_start_date].copy()
        if df.empty:
            raise ValueError(
                f"Tidak ada data setelah filter start_date={normalized_start_date.date().isoformat()}."
            )
        df = df.reset_index(drop=True)

    df = engineer_temporal_features(df)
    df["Label"] = df["Curah Hujan (mm)"].apply(klasifikasi_hujan_4_kelas).astype(np.int8)

    district_order = sorted(df["Kecamatan"].unique().tolist())
    df_dummy = pd.get_dummies(pd.Categorical(df["Kecamatan"], categories=district_order), prefix="Kec")
    df = pd.concat([df, df_dummy], axis=1)

    feature_columns = [
        "Curah Hujan (mm)",
        "Hujan_3Hari_Kumulatif",
        "Hujan_7Hari_Kumulatif",
        "Hujan_7Hari_Maksimum",
        "Hujan_Lag_1",
        "Hujan_Lag_2",
        "Hujan_Lag_3",
        "Hujan_Lag_7",
        "HariHujan_Beruntun",
        "Suhu Rata-rata (C)",
        "Kelembapan Rata-rata (%)",
        "Kecepatan Angin Max (km/h)",
        "Bulan_Sin",
        "Bulan_Cos",
        "HariTahun_Sin",
        "HariTahun_Cos",
    ] + list(df_dummy.columns)

    return df, feature_columns


def compute_split_points(row_count: int) -> tuple[int, int]:
    if row_count <= TIME_STEPS + 2:
        raise ValueError(
            f"Jumlah baris {row_count} terlalu sedikit untuk time_steps={TIME_STEPS} "
            "dan split train/val/test kronologis."
        )

    train_end = max(TIME_STEPS + 30, int(row_count * TRAIN_RATIO))
    val_end = max(train_end + 30, int(row_count * (TRAIN_RATIO + VAL_RATIO)))
    train_end = min(train_end, row_count - 2)
    val_end = min(val_end, row_count - 1)

    if val_end <= train_end:
        val_end = min(row_count - 1, train_end + 1)

    return train_end, val_end


def prepare_dataset(start_date: str | pd.Timestamp | None = None) -> DatasetBundle:
    df, feature_columns = prepare_feature_frame(start_date=start_date)
    district_frames: dict[str, pd.DataFrame] = {}
    split_boundaries: dict[str, dict[str, Any]] = {}
    training_rows: list[pd.DataFrame] = []

    for district_name in sorted(df["Kecamatan"].unique().tolist()):
        district_frame = (
            df[df["Kecamatan"] == district_name].sort_values("Tanggal").reset_index(drop=True).copy()
        )
        train_end, val_end = compute_split_points(len(district_frame))
        district_frames[district_name] = district_frame
        split_boundaries[district_name] = {
            "row_count": int(len(district_frame)),
            "train_end_index": int(train_end),
            "val_end_index": int(val_end),
            "train_end_date": district_frame.iloc[train_end - 1]["Tanggal"],
            "val_end_date": district_frame.iloc[val_end - 1]["Tanggal"],
            "test_start_date": district_frame.iloc[val_end]["Tanggal"],
        }
        training_rows.append(district_frame.iloc[:train_end][feature_columns])

    scaler = MinMaxScaler()
    scaler.fit(pd.concat(training_rows, ignore_index=True))

    X_splits: dict[str, list[np.ndarray]] = {"train": [], "val": [], "test": []}
    y_splits: dict[str, list[int]] = {"train": [], "val": [], "test": []}

    for district_name, district_frame in district_frames.items():
        boundary = split_boundaries[district_name]
        scaled_values = scaler.transform(district_frame[feature_columns]).astype(np.float32)
        labels = district_frame["Label"].to_numpy(dtype=np.int8)

        for target_index in range(TIME_STEPS, len(district_frame)):
            window = scaled_values[target_index - TIME_STEPS : target_index]
            label = int(labels[target_index])

            if target_index < boundary["train_end_index"]:
                split_name = "train"
            elif target_index < boundary["val_end_index"]:
                split_name = "val"
            else:
                split_name = "test"

            X_splits[split_name].append(window)
            y_splits[split_name].append(label)

    X_train = np.array(X_splits["train"], dtype=np.float32)
    X_val = np.array(X_splits["val"], dtype=np.float32)
    X_test = np.array(X_splits["test"], dtype=np.float32)
    y_train = np.array(y_splits["train"], dtype=np.int8)
    y_val = np.array(y_splits["val"], dtype=np.int8)
    y_test = np.array(y_splits["test"], dtype=np.int8)

    split_summary = {
        "strategy": "chronological_per_district",
        "train_ratio": TRAIN_RATIO,
        "val_ratio": VAL_RATIO,
        "time_steps": TIME_STEPS,
        "sequence_counts": {
            "train": int(len(X_train)),
            "val": int(len(X_val)),
            "test": int(len(X_test)),
        },
        "district_boundaries": split_boundaries,
    }

    class_distribution_total = {
        str(int(label)): int(count)
        for label, count in zip(*np.unique(df["Label"].to_numpy(dtype=np.int8), return_counts=True))
    }

    return DatasetBundle(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        scaler=scaler,
        feature_columns=feature_columns,
        split_summary=split_summary,
        class_distribution_total=class_distribution_total,
    )


def build_lstm_model(input_shape: tuple[int, int], feature_layer_name: str) -> Model:
    return build_lstm_model_with_loss(
        input_shape=input_shape,
        feature_layer_name=feature_layer_name,
        loss_mode="cross_entropy",
        focal_alpha=None,
        focal_gamma=2.0,
    )


def build_sparse_focal_loss(
    alpha: np.ndarray | None = None,
    gamma: float = 2.0,
):
    alpha_tensor = None
    if alpha is not None:
        alpha_tensor = tf.constant(alpha, dtype=tf.float32)

    def focal_loss(y_true: tf.Tensor, y_pred: tf.Tensor) -> tf.Tensor:
        y_true_flat = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        y_pred = tf.clip_by_value(
            y_pred,
            tf.keras.backend.epsilon(),
            1.0 - tf.keras.backend.epsilon(),
        )
        sample_indices = tf.stack([tf.range(tf.shape(y_true_flat)[0]), y_true_flat], axis=1)
        p_t = tf.gather_nd(y_pred, sample_indices)
        cross_entropy = -tf.math.log(p_t)
        modulating_factor = tf.pow(1.0 - p_t, gamma)

        if alpha_tensor is None:
            weighted_loss = modulating_factor * cross_entropy
        else:
            alpha_factor = tf.gather(alpha_tensor, y_true_flat)
            weighted_loss = alpha_factor * modulating_factor * cross_entropy

        return tf.reduce_mean(weighted_loss)

    focal_loss.__name__ = "sparse_focal_loss"
    return focal_loss


def build_lstm_model_with_loss(
    input_shape: tuple[int, int],
    feature_layer_name: str,
    loss_mode: str = "cross_entropy",
    focal_alpha: np.ndarray | None = None,
    focal_gamma: float = 2.0,
) -> Model:
    input_layer = Input(shape=input_shape)
    x = Bidirectional(LSTM(units=LSTM_CONFIG["units_1"], return_sequences=True))(input_layer)
    x = Dropout(LSTM_CONFIG["dropout"])(x)
    x = Bidirectional(LSTM(units=LSTM_CONFIG["units_2"], return_sequences=False))(x)
    x = Dropout(LSTM_CONFIG["dropout"])(x)
    feature_layer = Dense(
        units=LSTM_CONFIG["dense_units"],
        activation="relu",
        name=feature_layer_name,
    )(x)
    output_layer = Dense(units=4, activation="softmax")(feature_layer)

    if loss_mode == "focal":
        loss_fn = build_sparse_focal_loss(alpha=focal_alpha, gamma=focal_gamma)
    else:
        loss_fn = "sparse_categorical_crossentropy"

    model = Model(inputs=input_layer, outputs=output_layer)
    model.compile(
        optimizer=Adam(learning_rate=LSTM_CONFIG["learning_rate"]),
        loss=loss_fn,
        metrics=["accuracy"],
    )
    return model


def soft_class_weights(y_train: np.ndarray) -> dict[int, float]:
    classes = np.unique(y_train)
    raw_weights = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
    return {int(label): float(math.sqrt(weight)) for label, weight in zip(classes, raw_weights)}


def partial_smote_strategy(y_values: np.ndarray) -> tuple[dict[int, int], dict[int, int], int | None]:
    labels, counts = np.unique(y_values, return_counts=True)
    distribution = {int(label): int(count) for label, count in zip(labels, counts)}
    majority_count = max(distribution.values())
    target_class_2 = max(distribution.get(2, 0), int(majority_count * 0.40))
    target_class_3 = max(distribution.get(3, 0), int(majority_count * 0.10))

    sampling_strategy: dict[int, int] = {}
    if distribution.get(2, 0) < target_class_2:
        sampling_strategy[2] = target_class_2
    if distribution.get(3, 0) < target_class_3:
        sampling_strategy[3] = target_class_3

    if not sampling_strategy:
        return distribution, sampling_strategy, None

    min_count = min(distribution[class_label] for class_label in sampling_strategy)
    k_neighbors = max(1, min(5, min_count - 1))
    return distribution, sampling_strategy, k_neighbors


def apply_manual_smote(
    X: np.ndarray,
    y: np.ndarray,
    sampling_strategy: dict[int, int],
    k_neighbors: int | None,
    random_state: int = SEED,
) -> tuple[np.ndarray, np.ndarray]:
    if not sampling_strategy:
        return X.astype(np.float32), y.astype(np.int8)

    rng = np.random.default_rng(random_state)
    X_resampled = [X.astype(np.float32)]
    y_resampled = [y.astype(np.int8)]

    for class_label, target_count in sampling_strategy.items():
        X_class = X[y == class_label].astype(np.float32)
        current_count = int(len(X_class))

        if current_count >= target_count or current_count == 0:
            continue

        synthetic_count = int(target_count - current_count)

        if current_count == 1:
            noise = rng.normal(loc=0.0, scale=1e-5, size=(synthetic_count, X.shape[1])).astype(np.float32)
            synthetic_samples = X_class[0] + noise
        else:
            neighbor_count = min(current_count, (k_neighbors or 1) + 1)
            nn_model = NearestNeighbors(n_neighbors=neighbor_count)
            nn_model.fit(X_class)
            neighbor_indices = nn_model.kneighbors(X_class, return_distance=False)

            synthetic_rows: list[np.ndarray] = []
            for _ in range(synthetic_count):
                source_index = int(rng.integers(0, current_count))
                candidate_neighbors = neighbor_indices[source_index][1:]
                if len(candidate_neighbors) == 0:
                    neighbor_index = source_index
                else:
                    neighbor_index = int(rng.choice(candidate_neighbors))

                interpolation = float(rng.random())
                synthetic_sample = X_class[source_index] + interpolation * (
                    X_class[neighbor_index] - X_class[source_index]
                )
                synthetic_rows.append(synthetic_sample.astype(np.float32))

            synthetic_samples = np.vstack(synthetic_rows).astype(np.float32)

        X_resampled.append(synthetic_samples)
        y_resampled.append(np.full(synthetic_count, class_label, dtype=np.int8))

    return (
        np.vstack(X_resampled).astype(np.float32),
        np.concatenate(y_resampled).astype(np.int8),
    )


def summarize_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    class_names: list[str],
) -> dict[str, Any]:
    report = classification_report(
        y_true,
        y_pred,
        target_names=class_names,
        zero_division=0,
        output_dict=True,
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(report["macro avg"]["precision"]),
        "macro_recall": float(report["macro avg"]["recall"]),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "critical_recall": float(report["3_Lebat/Ekstrem (>=50mm)"]["recall"]),
        "critical_precision": float(report["3_Lebat/Ekstrem (>=50mm)"]["precision"]),
        "critical_f1": float(report["3_Lebat/Ekstrem (>=50mm)"]["f1-score"]),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1, 2, 3]).tolist(),
        "predicted_class_distribution": {
            str(class_index): int(np.sum(y_pred == class_index)) for class_index in range(4)
        },
        "true_class_distribution": {
            str(class_index): int(np.sum(y_true == class_index)) for class_index in range(4)
        },
        "sample_predictions": [
            {
                "true_class": int(y_true[index]),
                "pred_class": int(y_pred[index]),
                "probabilities": [round(float(probability), 4) for probability in y_prob[index]],
            }
            for index in range(min(10, len(y_true)))
        ],
    }


def apply_extreme_decision_rule(
    probabilities: np.ndarray,
    extreme_threshold: float,
    extreme_margin: float,
) -> np.ndarray:
    predictions = np.argmax(probabilities, axis=1).astype(np.int8)

    for index, row_probabilities in enumerate(probabilities):
        if predictions[index] != 3:
            continue

        fallback_index = int(np.argmax(row_probabilities[:3]))
        fallback_probability = float(row_probabilities[fallback_index])
        extreme_probability = float(row_probabilities[3])

        if extreme_probability < extreme_threshold or extreme_probability < (fallback_probability + extreme_margin):
            predictions[index] = np.int8(fallback_index)

    return predictions


def apply_gated_ensemble_rule(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    class_2_threshold: float,
    class_3_threshold: float,
    class_2_margin: float,
    class_3_margin: float,
) -> np.ndarray:
    if lstm_probabilities.shape != xgb_probabilities.shape:
        raise ValueError(
            "Shape probabilitas LSTM dan XGBoost harus sama untuk gated ensemble. "
            f"Diterima {lstm_probabilities.shape} vs {xgb_probabilities.shape}."
        )

    predictions = np.argmax(lstm_probabilities, axis=1).astype(np.int8)

    for index, xgb_row in enumerate(xgb_probabilities):
        strongest_low_class_probability = float(np.max(xgb_row[:2]))
        strongest_non_extreme_probability = float(np.max(xgb_row[:3]))

        if float(xgb_row[3]) >= class_3_threshold and float(xgb_row[3]) >= (
            strongest_non_extreme_probability + class_3_margin
        ):
            predictions[index] = np.int8(3)
            continue

        if predictions[index] in (0, 1) and float(xgb_row[2]) >= class_2_threshold and float(xgb_row[2]) >= (
            strongest_low_class_probability + class_2_margin
        ):
            predictions[index] = np.int8(2)

    return predictions


def compose_operational_probabilities(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    predictions: np.ndarray,
) -> np.ndarray:
    if lstm_probabilities.shape != xgb_probabilities.shape:
        raise ValueError(
            "Shape probabilitas LSTM dan XGBoost harus sama untuk komposisi probabilitas. "
            f"Diterima {lstm_probabilities.shape} vs {xgb_probabilities.shape}."
        )

    combined = lstm_probabilities.astype(np.float32).copy()
    base_predictions = np.argmax(lstm_probabilities, axis=1).astype(np.int8)

    for index, predicted_class in enumerate(predictions.astype(np.int8)):
        if predicted_class == base_predictions[index]:
            continue

        row = combined[index].copy()
        target_probability = max(float(row[predicted_class]), float(xgb_probabilities[index, predicted_class]))
        target_probability = min(max(target_probability, 1e-6), 0.95)

        other_indices = [class_index for class_index in range(row.shape[0]) if class_index != predicted_class]
        other_sum = float(np.sum(row[other_indices]))

        if other_sum <= 1e-8:
            row[:] = np.float32((1.0 - target_probability) / max(1, len(other_indices)))
            row[predicted_class] = np.float32(target_probability)
            combined[index] = row
            continue

        scaling_factor = (1.0 - target_probability) / other_sum
        row[other_indices] = row[other_indices] * scaling_factor
        row[predicted_class] = np.float32(target_probability)
        combined[index] = row.astype(np.float32)

    return combined


def model_selection_score(metrics: dict[str, Any]) -> float:
    return (
        0.45 * float(metrics["accuracy"])
        + 0.20 * float(metrics["macro_f1"])
        + 0.15 * float(metrics["macro_recall"])
        + 0.10 * float(metrics["critical_recall"])
        + 0.05 * float(metrics["critical_precision"])
        + 0.05 * float(metrics["critical_f1"])
    )


def extreme_rule_score(metrics: dict[str, Any]) -> float:
    return (
        0.45 * float(metrics["critical_f1"])
        + 0.25 * float(metrics["critical_precision"])
        + 0.15 * float(metrics["critical_recall"])
        + 0.10 * float(metrics["macro_f1"])
        + 0.05 * float(metrics["macro_recall"])
    )


def tune_gated_ensemble_rule(
    y_true: np.ndarray,
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    baseline_lstm_predictions = np.argmax(lstm_probabilities, axis=1).astype(np.int8)
    baseline_lstm_metrics = summarize_metrics(
        y_true,
        baseline_lstm_predictions,
        lstm_probabilities,
        CLASS_NAMES,
    )
    baseline_xgb_predictions = np.argmax(xgb_probabilities, axis=1).astype(np.int8)
    baseline_xgb_metrics = summarize_metrics(
        y_true,
        baseline_xgb_predictions,
        xgb_probabilities,
        CLASS_NAMES,
    )

    best_metrics = baseline_lstm_metrics
    best_rule = {
        "enabled": False,
        "class_2_threshold": 1.0,
        "class_3_threshold": 1.0,
        "class_2_margin": 0.0,
        "class_3_margin": 0.0,
        "selection_score": round(model_selection_score(baseline_lstm_metrics), 6),
        "description": "Argmax LSTM murni tanpa override selektif dari XGBoost.",
    }
    best_score = model_selection_score(baseline_lstm_metrics)
    evaluations = [
        {
            "enabled": False,
            "class_2_threshold": 1.0,
            "class_3_threshold": 1.0,
            "class_2_margin": 0.0,
            "class_3_margin": 0.0,
            "selection_score": round(best_score, 6),
            "accuracy": round(float(baseline_lstm_metrics["accuracy"]), 6),
            "macro_recall": round(float(baseline_lstm_metrics["macro_recall"]), 6),
            "macro_f1": round(float(baseline_lstm_metrics["macro_f1"]), 6),
            "critical_recall": round(float(baseline_lstm_metrics["critical_recall"]), 6),
            "critical_precision": round(float(baseline_lstm_metrics["critical_precision"]), 6),
            "critical_f1": round(float(baseline_lstm_metrics["critical_f1"]), 6),
        }
    ]

    for class_2_threshold in CLASS_2_THRESHOLD_GRID:
        for class_3_threshold in CLASS_3_THRESHOLD_GRID:
            for class_2_margin in CLASS_2_MARGIN_GRID:
                for class_3_margin in CLASS_3_MARGIN_GRID:
                    gated_predictions = apply_gated_ensemble_rule(
                        lstm_probabilities,
                        xgb_probabilities,
                        class_2_threshold=class_2_threshold,
                        class_3_threshold=class_3_threshold,
                        class_2_margin=class_2_margin,
                        class_3_margin=class_3_margin,
                    )
                    operational_probabilities = compose_operational_probabilities(
                        lstm_probabilities,
                        xgb_probabilities,
                        gated_predictions,
                    )
                    tuned_metrics = summarize_metrics(
                        y_true,
                        gated_predictions,
                        operational_probabilities,
                        CLASS_NAMES,
                    )
                    current_score = model_selection_score(tuned_metrics)

                    evaluations.append(
                        {
                            "enabled": True,
                            "class_2_threshold": class_2_threshold,
                            "class_3_threshold": class_3_threshold,
                            "class_2_margin": class_2_margin,
                            "class_3_margin": class_3_margin,
                            "selection_score": round(current_score, 6),
                            "accuracy": round(float(tuned_metrics["accuracy"]), 6),
                            "macro_recall": round(float(tuned_metrics["macro_recall"]), 6),
                            "macro_f1": round(float(tuned_metrics["macro_f1"]), 6),
                            "critical_recall": round(float(tuned_metrics["critical_recall"]), 6),
                            "critical_precision": round(float(tuned_metrics["critical_precision"]), 6),
                            "critical_f1": round(float(tuned_metrics["critical_f1"]), 6),
                        }
                    )

                    is_better = current_score > best_score + 1e-12
                    same_score = abs(current_score - best_score) <= 1e-12

                    if is_better or (
                        same_score
                        and float(tuned_metrics["accuracy"]) > float(best_metrics["accuracy"])
                    ):
                        best_score = current_score
                        best_metrics = tuned_metrics
                        best_rule = {
                            "enabled": True,
                            "class_2_threshold": class_2_threshold,
                            "class_3_threshold": class_3_threshold,
                            "class_2_margin": class_2_margin,
                            "class_3_margin": class_3_margin,
                            "selection_score": round(current_score, 6),
                            "description": (
                                "LSTM menjadi prediksi dasar. XGBoost hanya boleh override "
                                "ke kelas 2 atau 3 saat probabilitas laten cukup kuat."
                            ),
                        }

    return best_rule, best_metrics, baseline_lstm_metrics, baseline_xgb_metrics, evaluations


def tune_extreme_decision_rule(
    y_true: np.ndarray,
    probabilities: np.ndarray,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    baseline_predictions = np.argmax(probabilities, axis=1).astype(np.int8)
    baseline_metrics = summarize_metrics(y_true, baseline_predictions, probabilities, CLASS_NAMES)
    best_metrics = baseline_metrics
    best_rule = {
        "enabled": False,
        "extreme_threshold": 0.0,
        "extreme_margin": 0.0,
        "selection_score": round(extreme_rule_score(baseline_metrics), 6),
        "description": "Argmax murni tanpa penurunan kelas 3.",
    }
    best_score = extreme_rule_score(baseline_metrics)
    evaluations = [
        {
            "enabled": False,
            "extreme_threshold": 0.0,
            "extreme_margin": 0.0,
            "selection_score": round(best_score, 6),
            "critical_precision": round(float(baseline_metrics["critical_precision"]), 6),
            "critical_recall": round(float(baseline_metrics["critical_recall"]), 6),
            "critical_f1": round(float(baseline_metrics["critical_f1"]), 6),
            "macro_f1": round(float(baseline_metrics["macro_f1"]), 6),
        }
    ]

    for threshold in EXTREME_THRESHOLD_GRID:
        for margin in EXTREME_MARGIN_GRID:
            tuned_predictions = apply_extreme_decision_rule(probabilities, threshold, margin)
            tuned_metrics = summarize_metrics(y_true, tuned_predictions, probabilities, CLASS_NAMES)
            current_score = extreme_rule_score(tuned_metrics)

            evaluations.append(
                {
                    "enabled": True,
                    "extreme_threshold": threshold,
                    "extreme_margin": margin,
                    "selection_score": round(current_score, 6),
                    "critical_precision": round(float(tuned_metrics["critical_precision"]), 6),
                    "critical_recall": round(float(tuned_metrics["critical_recall"]), 6),
                    "critical_f1": round(float(tuned_metrics["critical_f1"]), 6),
                    "macro_f1": round(float(tuned_metrics["macro_f1"]), 6),
                }
            )

            is_better = current_score > best_score + 1e-12
            same_score = abs(current_score - best_score) <= 1e-12

            if is_better or (
                same_score
                and float(tuned_metrics["critical_precision"]) > float(best_metrics["critical_precision"])
            ):
                best_score = current_score
                best_metrics = tuned_metrics
                best_rule = {
                    "enabled": True,
                    "extreme_threshold": threshold,
                    "extreme_margin": margin,
                    "selection_score": round(current_score, 6),
                    "description": (
                        "Kelas 3 hanya dipertahankan jika probabilitasnya cukup tinggi "
                        "dan menang dengan margin yang aman."
                    ),
                }

    return best_rule, best_metrics, baseline_metrics, evaluations


def build_xgb_model(config: dict[str, Any]) -> xgb.XGBClassifier:
    xgb_params = {key: value for key, value in config.items() if key != "name"}
    return xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=4,
        eval_metric="mlogloss",
        random_state=SEED,
        **xgb_params,
    )


def tune_xgb_candidates(
    X_train_features: np.ndarray,
    y_train: np.ndarray,
    X_val_features: np.ndarray,
    y_val: np.ndarray,
    lstm_val_probabilities: np.ndarray,
) -> tuple[xgb.XGBClassifier, dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    train_distribution, sampling_strategy, k_neighbors = partial_smote_strategy(y_train)
    X_train_balanced, y_train_balanced = apply_manual_smote(
        X_train_features,
        y_train,
        sampling_strategy,
        k_neighbors,
        random_state=SEED,
    )
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_train_balanced)

    best_model: xgb.XGBClassifier | None = None
    best_candidate_summary: dict[str, Any] | None = None
    best_rule: dict[str, Any] | None = None
    best_score = -1.0
    candidate_rows: list[dict[str, Any]] = []

    for config in XGB_CANDIDATES:
        candidate_model = build_xgb_model(config)
        candidate_model.fit(
            X_train_balanced,
            y_train_balanced,
            sample_weight=sample_weights,
        )

        xgb_val_probabilities = candidate_model.predict_proba(X_val_features)
        best_candidate_rule, tuned_metrics, lstm_metrics, xgb_argmax_metrics, rule_evaluations = (
            tune_gated_ensemble_rule(
                y_val,
                lstm_val_probabilities,
                xgb_val_probabilities,
            )
        )
        candidate_score = model_selection_score(tuned_metrics)

        candidate_summary = {
            "name": config["name"],
            "params": {key: value for key, value in config.items() if key != "name"},
            "selection_score": round(candidate_score, 6),
            "ensemble_rule": best_candidate_rule,
            "decision_rule": {
                "enabled": bool(best_candidate_rule["enabled"]),
                "extreme_threshold": float(best_candidate_rule["class_3_threshold"]),
                "extreme_margin": float(best_candidate_rule["class_3_margin"]),
                "description": "Alias backward-compatible untuk gate kelas 3 pada mode gated ensemble.",
            },
            "val_metrics_after_rule": {
                "accuracy": round(float(tuned_metrics["accuracy"]), 6),
                "macro_recall": round(float(tuned_metrics["macro_recall"]), 6),
                "macro_f1": round(float(tuned_metrics["macro_f1"]), 6),
                "critical_recall": round(float(tuned_metrics["critical_recall"]), 6),
                "critical_precision": round(float(tuned_metrics["critical_precision"]), 6),
                "critical_f1": round(float(tuned_metrics["critical_f1"]), 6),
            },
            "val_metrics_lstm_argmax": {
                "accuracy": round(float(lstm_metrics["accuracy"]), 6),
                "macro_recall": round(float(lstm_metrics["macro_recall"]), 6),
                "macro_f1": round(float(lstm_metrics["macro_f1"]), 6),
                "critical_recall": round(float(lstm_metrics["critical_recall"]), 6),
                "critical_precision": round(float(lstm_metrics["critical_precision"]), 6),
                "critical_f1": round(float(lstm_metrics["critical_f1"]), 6),
            },
            "val_metrics_argmax": {
                "accuracy": round(float(xgb_argmax_metrics["accuracy"]), 6),
                "macro_recall": round(float(xgb_argmax_metrics["macro_recall"]), 6),
                "macro_f1": round(float(xgb_argmax_metrics["macro_f1"]), 6),
                "critical_recall": round(float(xgb_argmax_metrics["critical_recall"]), 6),
                "critical_precision": round(float(xgb_argmax_metrics["critical_precision"]), 6),
                "critical_f1": round(float(xgb_argmax_metrics["critical_f1"]), 6),
            },
            "rule_grid_top5": sorted(
                rule_evaluations,
                key=lambda item: (
                    item["selection_score"],
                    item.get("accuracy", 0.0),
                    item["critical_precision"],
                    item["critical_f1"],
                    item["macro_f1"],
                ),
                reverse=True,
            )[:5],
        }
        candidate_rows.append(candidate_summary)

        is_better = candidate_score > best_score + 1e-12
        same_score = abs(candidate_score - best_score) <= 1e-12

        if is_better or (
            same_score
            and candidate_summary["val_metrics_after_rule"]["accuracy"]
            > (best_candidate_summary or {}).get("val_metrics_after_rule", {}).get("accuracy", -1.0)
        ):
            best_model = candidate_model
            best_candidate_summary = candidate_summary
            best_rule = best_candidate_rule
            best_score = candidate_score

    if best_model is None or best_candidate_summary is None or best_rule is None:
        raise RuntimeError("Tidak ada kandidat XGBoost yang berhasil dipilih.")

    smote_summary = {
        "distribution_before": train_distribution,
        "sampling_strategy": sampling_strategy,
        "k_neighbors": k_neighbors,
        "distribution_after": {
            str(int(label)): int(count)
            for label, count in zip(*np.unique(y_train_balanced, return_counts=True))
        },
    }
    return best_model, best_candidate_summary, best_rule, candidate_rows, smote_summary


def build_focal_alpha_vector(class_weights: dict[int, float]) -> np.ndarray:
    alpha = np.array([float(class_weights.get(class_index, 1.0)) for class_index in range(4)], dtype=np.float32)
    alpha_sum = float(alpha.sum())
    if alpha_sum <= 0.0:
        return np.full(4, 0.25, dtype=np.float32)
    return (alpha / alpha_sum).astype(np.float32)


def run_training(
    *,
    start_date: str | pd.Timestamp | None = None,
    time_steps: int | None = None,
    loss_mode: str = "cross_entropy",
    focal_gamma: float = 2.0,
    output_prefix: str = "retrain_multiclass",
    persist_operational: bool = False,
    save_models: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    global TIME_STEPS

    original_time_steps = TIME_STEPS
    selected_time_steps = int(time_steps or TIME_STEPS)
    normalized_loss_mode = str(loss_mode).strip().lower() or "cross_entropy"
    if normalized_loss_mode not in {"cross_entropy", "focal"}:
        raise ValueError("loss_mode harus 'cross_entropy' atau 'focal'.")

    normalized_start_date = normalize_start_date(start_date)
    TIME_STEPS = selected_time_steps

    np.random.seed(SEED)
    tf.random.set_seed(SEED)
    tf.keras.backend.clear_session()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_output_prefix = (output_prefix or "retrain_multiclass").strip().replace(" ", "_")
    run_dir = ARTIFACTS_DIR / f"{safe_output_prefix}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        if verbose:
            if normalized_start_date is None:
                print("Menyiapkan dataset 4 class dari source penuh...")
            else:
                print(
                    "Menyiapkan dataset 4 class dari source mulai "
                    f"{normalized_start_date.date().isoformat()}..."
                )

        dataset = prepare_dataset(start_date=normalized_start_date)

        if verbose:
            print(f"Train: {dataset.X_train.shape} | Val: {dataset.X_val.shape} | Test: {dataset.X_test.shape}")
            print(f"Jumlah fitur per time step: {dataset.X_train.shape[2]}")
            print(f"Distribusi label total: {dataset.class_distribution_total}")
            print("Split data: kronologis per kecamatan, scaler fit hanya pada periode train.")

        class_weights = soft_class_weights(dataset.y_train)
        focal_alpha = build_focal_alpha_vector(class_weights) if normalized_loss_mode == "focal" else None

        if verbose:
            print(f"Class weights LSTM: {class_weights}")
            if focal_alpha is not None:
                print(f"Focal alpha: {[round(float(value), 6) for value in focal_alpha]}")

        model_lstm = build_lstm_model_with_loss(
            (dataset.X_train.shape[1], dataset.X_train.shape[2]),
            feature_layer_name="feature_layer",
            loss_mode=normalized_loss_mode,
            focal_alpha=focal_alpha,
            focal_gamma=float(focal_gamma),
        )
        early_stop = EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True)
        reduce_lr = ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=4,
            min_lr=0.00001,
            verbose=1,
        )

        if verbose:
            print(
                "\nMelatih Bi-LSTM 4 class dengan fitur temporal tambahan "
                f"(time_steps={TIME_STEPS}, loss={normalized_loss_mode})..."
            )

        history = model_lstm.fit(
            dataset.X_train,
            dataset.y_train,
            validation_data=(dataset.X_val, dataset.y_val),
            epochs=55,
            batch_size=LSTM_CONFIG["batch_size"],
            class_weight=class_weights,
            callbacks=[early_stop, reduce_lr],
            verbose=2,
        )

        if verbose:
            print("\nMengekstrak fitur laten...")

        feature_extractor = Model(
            inputs=model_lstm.input,
            outputs=model_lstm.get_layer("feature_layer").output,
        )
        X_train_features = feature_extractor.predict(dataset.X_train, verbose=0)
        X_val_features = feature_extractor.predict(dataset.X_val, verbose=0)
        X_test_features = feature_extractor.predict(dataset.X_test, verbose=0)
        lstm_val_probabilities = model_lstm.predict(dataset.X_val, verbose=0)
        lstm_test_probabilities = model_lstm.predict(dataset.X_test, verbose=0)

        if verbose:
            print("\nMenjalankan XGBoost candidates + SMOTE parsial pada fitur laten...")

        xgb_model, best_candidate, best_rule, candidate_rows, smote_summary = tune_xgb_candidates(
            X_train_features,
            dataset.y_train,
            X_val_features,
            dataset.y_val,
            lstm_val_probabilities,
        )

        if verbose:
            print(f"Kandidat XGBoost terpilih: {best_candidate['name']}")
            print(f"Gate ensemble terpilih: {best_rule}")

        xgb_test_probabilities = xgb_model.predict_proba(X_test_features)
        y_pred_lstm = np.argmax(lstm_test_probabilities, axis=1).astype(np.int8)
        metrics_lstm_argmax = summarize_metrics(
            dataset.y_test,
            y_pred_lstm,
            lstm_test_probabilities,
            CLASS_NAMES,
        )
        y_pred_argmax = np.argmax(xgb_test_probabilities, axis=1).astype(np.int8)
        metrics_argmax = summarize_metrics(dataset.y_test, y_pred_argmax, xgb_test_probabilities, CLASS_NAMES)
        y_pred_final = apply_gated_ensemble_rule(
            lstm_test_probabilities,
            xgb_test_probabilities,
            class_2_threshold=float(best_rule["class_2_threshold"]),
            class_3_threshold=float(best_rule["class_3_threshold"]),
            class_2_margin=float(best_rule["class_2_margin"]),
            class_3_margin=float(best_rule["class_3_margin"]),
        )
        operational_probabilities = compose_operational_probabilities(
            lstm_test_probabilities,
            xgb_test_probabilities,
            y_pred_final,
        )
        metrics_final = summarize_metrics(dataset.y_test, y_pred_final, operational_probabilities, CLASS_NAMES)

        summary = {
            "dataset_path": str(DATASET_PATH),
            "run_timestamp": timestamp,
            "window_start_date": (
                normalized_start_date.date().isoformat() if normalized_start_date is not None else None
            ),
            "loss_mode": normalized_loss_mode,
            "focal_gamma": float(focal_gamma) if normalized_loss_mode == "focal" else None,
            "focal_alpha": (
                [float(value) for value in focal_alpha.tolist()] if focal_alpha is not None else None
            ),
            "sequence_count": int(
                len(dataset.X_train) + len(dataset.X_val) + len(dataset.X_test)
            ),
            "time_steps": TIME_STEPS,
            "feature_count": int(dataset.X_train.shape[2]),
            "feature_columns": dataset.feature_columns,
            "split_summary": dataset.split_summary,
            "class_distribution_total": dataset.class_distribution_total,
            "class_distribution_train": {
                str(int(label)): int(count)
                for label, count in zip(*np.unique(dataset.y_train, return_counts=True))
            },
            "class_distribution_val": {
                str(int(label)): int(count)
                for label, count in zip(*np.unique(dataset.y_val, return_counts=True))
            },
            "class_distribution_test": {
                str(int(label)): int(count)
                for label, count in zip(*np.unique(dataset.y_test, return_counts=True))
            },
            "class_weights_lstm": {str(label): value for label, value in class_weights.items()},
            "lstm_config": LSTM_CONFIG,
            "smote_summary": smote_summary,
            "ensemble_mode": "gated_lstm_xgb_override",
            "xgb_candidate_rows": candidate_rows,
            "best_xgb_candidate": best_candidate,
            "ensemble_rule": best_rule,
            "decision_rule": {
                "enabled": bool(best_rule["enabled"]),
                "extreme_threshold": float(best_rule["class_3_threshold"]),
                "extreme_margin": float(best_rule["class_3_margin"]),
                "description": "Alias backward-compatible untuk gate kelas 3 pada mode gated ensemble.",
            },
            "metrics_lstm_argmax": metrics_lstm_argmax,
            "metrics_argmax": metrics_argmax,
            "metrics": metrics_final,
            "training_history": {
                key: [float(value) for value in values]
                for key, values in history.history.items()
            },
        }

        operational_config = {
            "time_steps": TIME_STEPS,
            "feature_columns": dataset.feature_columns,
            "training_window_start_date": (
                normalized_start_date.date().isoformat() if normalized_start_date is not None else None
            ),
            "loss_mode": normalized_loss_mode,
            "ensemble_mode": "gated_lstm_xgb_override",
            "ensemble_rule": best_rule,
            "decision_rule": {
                "enabled": bool(best_rule["enabled"]),
                "extreme_threshold": float(best_rule["class_3_threshold"]),
                "extreme_margin": float(best_rule["class_3_margin"]),
                "description": "Alias backward-compatible untuk gate kelas 3 pada mode gated ensemble.",
            },
            "model_notes": {
                "split_strategy": "chronological_per_district",
                "scaler_fit_scope": "train_only",
                "smote_scope": "latent_features_partial_classes_2_and_3",
                "ensemble_strategy": "lstm_base_with_xgb_selective_override",
            },
        }

        summary_path = run_dir / "training_summary.json"
        local_model_config_path = run_dir / "operational_multiclass_config.json"
        local_model_path = run_dir / MODEL_PATH.name
        local_xgb_path = run_dir / XGB_PATH.name
        local_scaler_path = run_dir / SCALER_PATH.name
        local_feature_columns_path = run_dir / FEATURE_COLUMNS_PATH.name

        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(summary), handle, ensure_ascii=False, indent=2)
        with local_model_config_path.open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(operational_config), handle, ensure_ascii=False, indent=2)

        if save_models:
            model_lstm.save(local_model_path)
            joblib.dump(xgb_model, local_xgb_path)
            joblib.dump(dataset.scaler, local_scaler_path)
            joblib.dump(dataset.feature_columns, local_feature_columns_path)

        if persist_operational:
            with LATEST_SUMMARY_PATH.open("w", encoding="utf-8") as handle:
                json.dump(to_jsonable(summary), handle, ensure_ascii=False, indent=2)
            with MODEL_CONFIG_PATH.open("w", encoding="utf-8") as handle:
                json.dump(to_jsonable(operational_config), handle, ensure_ascii=False, indent=2)

            if save_models:
                model_lstm.save(MODEL_PATH)
                joblib.dump(xgb_model, XGB_PATH)
                joblib.dump(dataset.scaler, SCALER_PATH)
                joblib.dump(dataset.feature_columns, FEATURE_COLUMNS_PATH)

        result = {
            "summary": summary,
            "run_dir": run_dir,
            "summary_path": summary_path,
            "operational_config_path": local_model_config_path,
            "model_path": local_model_path if save_models else None,
            "xgb_path": local_xgb_path if save_models else None,
            "scaler_path": local_scaler_path if save_models else None,
            "feature_columns_path": local_feature_columns_path if save_models else None,
        }

        if verbose:
            print("\nRingkasan metrik 4 class setelah gate final:")
            print(
                json.dumps(
                    {
                        "accuracy": round(float(metrics_final["accuracy"]), 4),
                        "macro_recall": round(float(metrics_final["macro_recall"]), 4),
                        "macro_f1": round(float(metrics_final["macro_f1"]), 4),
                        "critical_recall": round(float(metrics_final["critical_recall"]), 4),
                        "critical_precision": round(float(metrics_final["critical_precision"]), 4),
                        "critical_f1": round(float(metrics_final["critical_f1"]), 4),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            print(f"\nRingkasan training disimpan di: {summary_path}")
            if save_models:
                print(
                    f"Artefak model run disimpan ke: {local_model_path}, {local_xgb_path}, "
                    f"{local_scaler_path}, {local_feature_columns_path}"
                )
            if persist_operational:
                print(f"Artefak operasional aktif diperbarui di: {MODEL_PATH}, {XGB_PATH}, {SCALER_PATH}")

        return result
    finally:
        TIME_STEPS = original_time_steps
        tf.keras.backend.clear_session()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrain operational 4-class hybrid model.")
    parser.add_argument("--start-date", default=None, help="Filter data mulai tanggal YYYY-MM-DD.")
    parser.add_argument("--time-steps", type=int, default=TIME_STEPS, help="Panjang window sequence.")
    parser.add_argument(
        "--loss-mode",
        choices=["cross_entropy", "focal"],
        default="cross_entropy",
        help="Loss untuk training LSTM.",
    )
    parser.add_argument(
        "--focal-gamma",
        type=float,
        default=2.0,
        help="Nilai gamma untuk focal loss.",
    )
    parser.add_argument(
        "--output-prefix",
        default="retrain_multiclass",
        help="Prefix nama folder artifacts untuk run ini.",
    )
    parser.add_argument(
        "--no-persist-operational",
        action="store_true",
        help="Jangan timpa artefak operasional aktif.",
    )
    parser.add_argument(
        "--no-save-models",
        action="store_true",
        help="Lewati penyimpanan artefak model per-run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_training(
        start_date=args.start_date,
        time_steps=args.time_steps,
        loss_mode=args.loss_mode,
        focal_gamma=args.focal_gamma,
        output_prefix=args.output_prefix,
        persist_operational=not args.no_persist_operational,
        save_models=not args.no_save_models,
        verbose=True,
    )


if __name__ == "__main__":
    main()
