from __future__ import annotations

import argparse
import json
import os
import pickle
import calendar
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.preprocessing import MinMaxScaler

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import tensorflow as tf
from tensorflow.keras import callbacks, layers, models


XML_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MISSING_MARKERS = {"", "8888", "8888.0", "9999", "9999.0"}
RAIN_THRESHOLD_MM = 0.5
HYDRO_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "Mei": 5,
    "Jun": 6,
    "Jul": 7,
    "Agu": 8,
    "Sep": 9,
    "Okt": 10,
    "Nov": 11,
    "Des": 12,
}


@dataclass
class DataSummary:
    source_kind: str
    source_path: str
    total_rows: int
    valid_rows: int
    missing_rows: int
    first_date: str
    last_date: str
    first_valid_date: str
    last_valid_date: str


@dataclass
class CandidateConfig:
    name: str
    window_size: int
    feature_columns: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Latih model LSTM untuk prediksi curah hujan harian dari data BMKG."
    )
    parser.add_argument(
        "--excel",
        default=r"c:\Users\Vino\Documents\DATA SKRIPSI\7_24 sampe 3_26.xlsx",
        help="Path ke file Excel gabungan BMKG. Dipakai sebagai fallback.",
    )
    parser.add_argument(
        "--source-dir",
        default=r"c:\Users\Vino\Documents\DATA SKRIPSI\bmkg",
        help="Folder file bulanan BMKG. Jika ada, ini diprioritaskan karena datanya lebih lengkap.",
    )
    parser.add_argument(
        "--hydro-excel",
        default=r"c:\Users\Vino\Documents\DATA SKRIPSI\data curah hujan hidro.xlsx",
        help="Path ke file hidro historis format tahun x bulan.",
    )
    parser.add_argument(
        "--candidate-windows",
        nargs="+",
        type=int,
        default=[7, 14, 30],
        help="Daftar panjang window harian yang akan dicoba.",
    )
    parser.add_argument(
        "--mode",
        choices=["direct", "pretrain-finetune"],
        default="pretrain-finetune",
        help="Strategi training. pretrain-finetune memakai hidro untuk pretraining dan BMKG sebagai target.",
    )
    parser.add_argument(
        "--selection-metric",
        choices=["rmse", "mae", "rain_accuracy"],
        default="rmse",
        help="Metrik validasi untuk memilih kandidat model terbaik.",
    )
    parser.add_argument(
        "--max-gap-days",
        type=int,
        default=10,
        help="Batas gap tanggal agar sequence masih dianggap satu segmen.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Jumlah epoch maksimum tiap kandidat model.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Ukuran batch training.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed random untuk reproducibility.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/lstm_curah_hujan",
        help="Folder output artefak model.",
    )
    return parser.parse_args()


def load_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    shared_strings: list[str] = []
    for item in root.findall("main:si", XML_NS):
        text = "".join(node.text or "" for node in item.iterfind(".//main:t", XML_NS))
        shared_strings.append(text)
    return shared_strings


def read_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", XML_NS)
    inline_node = cell.find("main:is", XML_NS)

    if value_node is not None and value_node.text is not None:
        value = value_node.text
        if cell_type == "s":
            return shared_strings[int(value)]
        return value

    if inline_node is not None:
        return "".join(node.text or "" for node in inline_node.iterfind(".//main:t", XML_NS))

    return ""


def extract_column_letters(cell_ref: str) -> str:
    return "".join(char for char in cell_ref if char.isalpha())


def parse_rainfall_value(raw_value: str) -> float | None:
    cleaned = "" if raw_value is None else str(raw_value).strip()
    if cleaned in MISSING_MARKERS:
        return None
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def read_monthly_bmkg_folder(folder_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for file_path in sorted(folder_path.glob("*.xlsx")):
        with ZipFile(file_path) as archive:
            shared_strings = load_shared_strings(archive)
            worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            xml_rows = worksheet.findall(".//main:sheetData/main:row", XML_NS)

            for row in xml_rows:
                values: dict[str, str] = {}
                for cell in row.findall("main:c", XML_NS):
                    cell_ref = cell.attrib.get("r", "")
                    column = extract_column_letters(cell_ref)
                    values[column] = read_cell_text(cell, shared_strings).strip()

                date_text = values.get("A", "")
                rr_raw = values.get("B", "")
                date_value = pd.to_datetime(
                    date_text, format="%d-%m-%Y", dayfirst=True, errors="coerce"
                )
                if pd.isna(date_value):
                    continue

                rows.append(
                    {
                        "source_file": file_path.name,
                        "source_type": "bmkg_monthly",
                        "date": date_value.normalize(),
                        "rr_raw": rr_raw,
                    }
                )

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def read_combined_bmkg_workbook(path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    with ZipFile(path) as archive:
        shared_strings = load_shared_strings(archive)
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        xml_rows = worksheet.findall(".//main:sheetData/main:row", XML_NS)

        for row in xml_rows:
            values: dict[str, str] = {}
            for cell in row.findall("main:c", XML_NS):
                cell_ref = cell.attrib.get("r", "")
                column = extract_column_letters(cell_ref)
                values[column] = read_cell_text(cell, shared_strings).strip()

            source_file = values.get("A", "")
            date_text = values.get("B", "")
            rr_raw = values.get("C", "")
            if not source_file or not date_text:
                continue

            date_value = pd.to_datetime(
                date_text, format="%d-%m-%Y", dayfirst=True, errors="coerce"
            )
            if pd.isna(date_value):
                continue

            rows.append(
                {
                    "source_file": source_file,
                    "source_type": "bmkg_combined",
                    "date": date_value.normalize(),
                    "rr_raw": rr_raw,
                }
            )

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def read_hydro_workbook(path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    with ZipFile(path) as archive:
        shared_strings = load_shared_strings(archive)
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        xml_rows = worksheet.findall(".//main:sheetData/main:row", XML_NS)

        current_year: int | None = None
        month_columns: dict[int, int] = {}

        for row in xml_rows:
            values: dict[int, str] = {}
            for cell in row.findall("main:c", XML_NS):
                cell_ref = cell.attrib.get("r", "")
                column_idx = column_index(cell_ref)
                values[column_idx] = read_cell_text(cell, shared_strings).strip()

            if values.get(0) == "Tanggal":
                month_columns = {
                    idx: HYDRO_MONTHS[value]
                    for idx, value in values.items()
                    if value in HYDRO_MONTHS
                }
                try:
                    current_year = int(float(values.get(13, "")))
                except ValueError:
                    current_year = None
                continue

            if current_year is None:
                continue

            try:
                day_number = int(float(values.get(0, "")))
            except ValueError:
                continue

            for column_idx, month_number in month_columns.items():
                if day_number > calendar.monthrange(current_year, month_number)[1]:
                    continue

                rr_raw = values.get(column_idx, "")
                if rr_raw == "":
                    continue

                rows.append(
                    {
                        "source_file": path.name,
                        "source_type": "hydro",
                        "date": pd.Timestamp(date(current_year, month_number, day_number)),
                        "rr_raw": rr_raw,
                    }
                )

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def column_index(cell_ref: str) -> int:
    letters = extract_column_letters(cell_ref)
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def resolve_source_dataframe(
    excel_path: Path, source_dir: Path, hydro_excel_path: Path
) -> tuple[pd.DataFrame, str, str]:
    frames: list[pd.DataFrame] = []
    source_labels: list[str] = []

    if hydro_excel_path.exists():
        frames.append(read_hydro_workbook(hydro_excel_path))
        source_labels.append(str(hydro_excel_path))

    if source_dir.exists() and any(source_dir.glob("*.xlsx")):
        frames.append(read_monthly_bmkg_folder(source_dir))
        source_labels.append(str(source_dir))
    elif excel_path.exists():
        frames.append(read_combined_bmkg_workbook(excel_path))
        source_labels.append(str(excel_path))

    frames = [frame for frame in frames if not frame.empty]
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.sort_values(["date", "source_type"]).reset_index(drop=True)
        source_kind = " + ".join(combined["source_type"].dropna().unique().tolist())
        return combined, source_kind, " | ".join(source_labels)

    raise FileNotFoundError(
        "Sumber data tidak ditemukan. "
        f"Folder BMKG: {source_dir} | File gabungan: {excel_path} | File hidro: {hydro_excel_path}"
    )


def rainfall_category(value_mm: float) -> str:
    if value_mm < RAIN_THRESHOLD_MM:
        return "Tidak Hujan"
    if value_mm < 20:
        return "Hujan Ringan"
    if value_mm < 50:
        return "Hujan Sedang"
    if value_mm < 100:
        return "Hujan Lebat"
    return "Hujan Sangat Lebat"


def prepare_daily_dataset(
    raw_df: pd.DataFrame, source_kind: str, source_path: str, max_gap_days: int
) -> tuple[pd.DataFrame, DataSummary]:
    if raw_df.empty:
        raise ValueError("Sumber data tidak mengandung baris data harian yang bisa dibaca.")

    df = raw_df.copy()
    df["rr_mm"] = df["rr_raw"].map(parse_rainfall_value)

    valid_mask = df["rr_mm"].notna()
    if not valid_mask.any():
        raise ValueError("Tidak ada nilai curah hujan valid pada sumber data ini.")

    first_valid_date = df.loc[valid_mask, "date"].min()
    last_valid_date = df.loc[valid_mask, "date"].max()

    daily = (
        df[df["rr_mm"].notna()]
        .groupby("date", as_index=False)
        .agg(
            rr_mm=("rr_mm", "mean"),
            source_file=("source_file", "last"),
            source_type=("source_type", "last"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["was_missing"] = 0
    daily["rr_mm_filled"] = daily["rr_mm"].clip(lower=0.0)
    daily["rr_log"] = np.log1p(daily["rr_mm_filled"])
    daily["rain_flag_actual"] = (daily["rr_mm"].fillna(0.0) >= RAIN_THRESHOLD_MM).astype(int)
    daily["gap_days"] = daily["date"].diff().dt.days.fillna(1).clip(lower=1).astype(np.float32)
    daily["segment_id"] = (daily["gap_days"] > max_gap_days).cumsum().astype(int)
    daily.loc[daily.groupby("segment_id").head(1).index, "gap_days"] = 1.0

    day_of_year = daily["date"].dt.dayofyear.astype(np.float32)
    month_number = daily["date"].dt.month.astype(np.float32)
    daily["sin_dayofyear"] = np.sin(2 * np.pi * day_of_year / 366.0)
    daily["cos_dayofyear"] = np.cos(2 * np.pi * day_of_year / 366.0)
    daily["sin_month"] = np.sin(2 * np.pi * month_number / 12.0)
    daily["cos_month"] = np.cos(2 * np.pi * month_number / 12.0)
    daily["source_hydro"] = (daily["source_type"] == "hydro").astype(int)
    daily["source_bmkg"] = daily["source_type"].str.startswith("bmkg").astype(int)

    grouped = daily.groupby("segment_id", group_keys=False)["rr_mm_filled"]
    daily["baseline_prev1"] = grouped.shift(1).fillna(0.0)
    daily["baseline_median30"] = grouped.apply(
        lambda series: series.shift(1).rolling(30, min_periods=1).median()
    ).fillna(0.0)
    daily["rolling_mean7"] = grouped.apply(
        lambda series: series.shift(1).rolling(7, min_periods=1).mean()
    ).fillna(0.0)
    daily["rolling_max7"] = grouped.apply(
        lambda series: series.shift(1).rolling(7, min_periods=1).max()
    ).fillna(0.0)
    daily["rolling_median30"] = daily["baseline_median30"]
    daily["rolling_std7"] = grouped.apply(
        lambda series: series.shift(1).rolling(7, min_periods=2).std()
    ).fillna(0.0)

    dry_streaks: list[int] = []
    wet_streaks: list[int] = []
    for _, segment in daily.groupby("segment_id"):
        dry_count = 0
        wet_count = 0
        segment_dry: list[int] = []
        segment_wet: list[int] = []
        for is_rain in segment["rain_flag_actual"].to_numpy():
            segment_dry.append(dry_count)
            segment_wet.append(wet_count)
            if is_rain:
                wet_count += 1
                dry_count = 0
            else:
                dry_count += 1
                wet_count = 0
        dry_streaks.extend(segment_dry)
        wet_streaks.extend(segment_wet)

    daily["dry_streak"] = dry_streaks
    daily["wet_streak"] = wet_streaks

    segment_lengths = daily.groupby("segment_id").size().to_dict()
    daily["segment_length"] = daily["segment_id"].map(segment_lengths).astype(int)

    daily = (
        daily.sort_values("date")
        .reset_index(drop=True)
    )

    summary = DataSummary(
        source_kind=source_kind,
        source_path=source_path,
        total_rows=int(len(raw_df)),
        valid_rows=int(valid_mask.sum()),
        missing_rows=int((~valid_mask).sum()),
        first_date=str(raw_df["date"].min().date()),
        last_date=str(raw_df["date"].max().date()),
        first_valid_date=str(first_valid_date.date()),
        last_valid_date=str(last_valid_date.date()),
    )

    return daily, summary


def build_candidate_configs(candidate_windows: list[int]) -> list[CandidateConfig]:
    feature_sets = {
        "minimal": [
            "rr_log",
            "gap_days",
            "sin_dayofyear",
            "cos_dayofyear",
            "sin_month",
            "cos_month",
        ],
        "context": [
            "rr_log",
            "gap_days",
            "rolling_mean7",
            "rolling_max7",
            "rolling_median30",
            "rolling_std7",
            "dry_streak",
            "wet_streak",
            "sin_dayofyear",
            "cos_dayofyear",
            "sin_month",
            "cos_month",
            "source_hydro",
            "source_bmkg",
        ],
    }

    return [
        CandidateConfig(
            name=f"{feature_set_name}_window_{window_size}",
            window_size=window_size,
            feature_columns=feature_columns,
        )
        for window_size in candidate_windows
        for feature_set_name, feature_columns in feature_sets.items()
    ]


def build_sequences(
    daily_df: pd.DataFrame, candidate: CandidateConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    feature_matrix = daily_df.loc[:, candidate.feature_columns].to_numpy(dtype=np.float32)
    target_vector = daily_df["rr_log"].to_numpy(dtype=np.float32)
    date_vector = daily_df["date"].dt.strftime("%Y-%m-%d").to_numpy()
    observed_target_mask = daily_df["rr_mm"].notna().to_numpy()
    segment_vector = daily_df["segment_id"].to_numpy()

    inputs: list[np.ndarray] = []
    targets: list[float] = []
    target_dates: list[str] = []
    target_indices: list[int] = []

    for end_idx in range(candidate.window_size, len(daily_df)):
        if not observed_target_mask[end_idx]:
            continue
        if segment_vector[end_idx] != segment_vector[end_idx - candidate.window_size]:
            continue
        inputs.append(feature_matrix[end_idx - candidate.window_size : end_idx])
        targets.append(target_vector[end_idx])
        target_dates.append(date_vector[end_idx])
        target_indices.append(end_idx)

    if not inputs:
        raise ValueError("Data tidak cukup untuk membentuk sequence LSTM.")

    return (
        np.asarray(inputs, dtype=np.float32),
        np.asarray(targets, dtype=np.float32).reshape(-1, 1),
        np.asarray(target_dates),
        np.asarray(target_indices),
    )


def sequential_split(sample_count: int) -> tuple[int, int]:
    train_end = max(int(sample_count * 0.70), 1)
    val_end = max(int(sample_count * 0.85), train_end + 1)
    val_end = min(val_end, sample_count - 1)
    return train_end, val_end


def scale_features_and_target(
    X: np.ndarray, y: np.ndarray, train_end: int
) -> tuple[np.ndarray, np.ndarray, MinMaxScaler, MinMaxScaler]:
    feature_scaler = MinMaxScaler()
    X_train_flat = X[:train_end].reshape(-1, X.shape[-1])
    feature_scaler.fit(X_train_flat)
    X_scaled = feature_scaler.transform(X.reshape(-1, X.shape[-1])).reshape(X.shape)

    target_scaler = MinMaxScaler()
    target_scaler.fit(y[:train_end])
    y_scaled = target_scaler.transform(y)

    return X_scaled.astype(np.float32), y_scaled.astype(np.float32), feature_scaler, target_scaler


def build_lstm_model(window_size: int, num_features: int) -> tf.keras.Model:
    model = models.Sequential(
        [
            layers.Input(shape=(window_size, num_features)),
            layers.LSTM(64, return_sequences=True),
            layers.Dropout(0.15),
            layers.LSTM(32),
            layers.Dense(24, activation="relu"),
            layers.Dense(1),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="mse",
        metrics=["mae"],
    )
    return model


def inverse_target(values_scaled: np.ndarray, target_scaler: MinMaxScaler) -> np.ndarray:
    values_log = target_scaler.inverse_transform(values_scaled.reshape(-1, 1)).reshape(-1)
    rainfall_mm = np.expm1(values_log)
    return np.clip(rainfall_mm, a_min=0.0, a_max=None)


def compute_metrics(actual_mm: np.ndarray, predicted_mm: np.ndarray) -> dict[str, float]:
    actual_rain = actual_mm >= RAIN_THRESHOLD_MM
    predicted_rain = predicted_mm >= RAIN_THRESHOLD_MM

    return {
        "mae_mm": float(mean_absolute_error(actual_mm, predicted_mm)),
        "rmse_mm": float(root_mean_squared_error(actual_mm, predicted_mm)),
        "rain_accuracy": float((actual_rain == predicted_rain).mean()),
    }


def metric_score(metrics: dict[str, float], selection_metric: str) -> tuple[float, float]:
    if selection_metric == "rain_accuracy":
        return (-metrics["rain_accuracy"], metrics["rmse_mm"])
    if selection_metric == "mae":
        return (metrics["mae_mm"], metrics["rmse_mm"])
    return (metrics["rmse_mm"], metrics["mae_mm"])


def choose_postprocess_threshold(
    actual_val_mm: np.ndarray,
    predicted_val_mm_raw: np.ndarray,
    selection_metric: str,
) -> tuple[float, dict[str, float]]:
    best_threshold = 0.0
    best_metrics = compute_metrics(actual_val_mm, predicted_val_mm_raw)
    best_score = metric_score(best_metrics, selection_metric)

    for threshold in np.arange(0.0, 10.25, 0.25):
        predicted = np.where(predicted_val_mm_raw >= threshold, predicted_val_mm_raw, 0.0)
        metrics = compute_metrics(actual_val_mm, predicted)
        score = metric_score(metrics, selection_metric)
        if score < best_score:
            best_threshold = float(threshold)
            best_metrics = metrics
            best_score = score

    return best_threshold, best_metrics


def train_candidate(
    daily_df: pd.DataFrame,
    candidate: CandidateConfig,
    epochs: int,
    batch_size: int,
    seed: int,
    selection_metric: str,
) -> dict[str, object]:
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)

    X, y, target_dates, target_indices = build_sequences(daily_df, candidate)
    sample_count = len(X)
    train_end, val_end = sequential_split(sample_count)

    X_scaled, y_scaled, feature_scaler, target_scaler = scale_features_and_target(
        X=X, y=y, train_end=train_end
    )

    X_train, X_val, X_test = (
        X_scaled[:train_end],
        X_scaled[train_end:val_end],
        X_scaled[val_end:],
    )
    y_train, y_val, y_test = (
        y_scaled[:train_end],
        y_scaled[train_end:val_end],
        y_scaled[val_end:],
    )

    val_dates = target_dates[train_end:val_end]
    test_dates = target_dates[val_end:]
    val_indices = target_indices[train_end:val_end]
    test_indices = target_indices[val_end:]

    if len(X_val) == 0 or len(X_test) == 0:
        raise ValueError("Split train/validation/test menghasilkan subset kosong.")

    train_actual_mm = inverse_target(y_train, target_scaler)
    sample_weights = 1.0 + 2.5 * (train_actual_mm >= RAIN_THRESHOLD_MM).astype(np.float32)

    model = build_lstm_model(candidate.window_size, len(candidate.feature_columns))
    training_callbacks = [
        callbacks.EarlyStopping(
            monitor="val_loss",
            patience=12,
            restore_best_weights=True,
            verbose=0,
        ),
        callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            patience=6,
            factor=0.5,
            min_lr=1e-5,
            verbose=0,
        ),
    ]

    history = model.fit(
        X_train,
        y_train,
        validation_data=(X_val, y_val),
        sample_weight=sample_weights,
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
        callbacks=training_callbacks,
    )

    y_val_pred_scaled = model.predict(X_val, verbose=0).reshape(-1, 1)
    y_test_pred_scaled = model.predict(X_test, verbose=0).reshape(-1, 1)

    y_val_actual_mm = inverse_target(y_val, target_scaler)
    y_test_actual_mm = inverse_target(y_test, target_scaler)
    y_val_pred_mm_raw = inverse_target(y_val_pred_scaled, target_scaler)
    y_test_pred_mm_raw = inverse_target(y_test_pred_scaled, target_scaler)

    threshold_mm, val_metrics = choose_postprocess_threshold(
        actual_val_mm=y_val_actual_mm,
        predicted_val_mm_raw=y_val_pred_mm_raw,
        selection_metric=selection_metric,
    )
    y_test_pred_mm = np.where(y_test_pred_mm_raw >= threshold_mm, y_test_pred_mm_raw, 0.0)
    test_metrics = compute_metrics(y_test_actual_mm, y_test_pred_mm)

    baseline_prev1_val = daily_df.loc[val_indices, "baseline_prev1"].to_numpy(dtype=np.float32)
    baseline_prev1_test = daily_df.loc[test_indices, "baseline_prev1"].to_numpy(dtype=np.float32)
    baseline_median30_val = daily_df.loc[val_indices, "baseline_median30"].to_numpy(dtype=np.float32)
    baseline_median30_test = daily_df.loc[test_indices, "baseline_median30"].to_numpy(dtype=np.float32)

    return {
        "candidate": candidate,
        "model": model,
        "feature_scaler": feature_scaler,
        "target_scaler": target_scaler,
        "history": history.history,
        "train_samples": int(len(X_train)),
        "validation_samples": int(len(X_val)),
        "test_samples": int(len(X_test)),
        "threshold_mm": threshold_mm,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "val_dates": val_dates,
        "test_dates": test_dates,
        "test_indices": test_indices,
        "test_actual_mm": y_test_actual_mm,
        "test_pred_mm_raw": y_test_pred_mm_raw,
        "test_pred_mm": y_test_pred_mm,
        "baseline_prev1_test": baseline_prev1_test,
        "baseline_median30_test": baseline_median30_test,
        "baseline_prev1_val_metrics": compute_metrics(y_val_actual_mm, baseline_prev1_val),
        "baseline_prev1_test_metrics": compute_metrics(y_test_actual_mm, baseline_prev1_test),
        "baseline_median30_val_metrics": compute_metrics(y_val_actual_mm, baseline_median30_val),
        "baseline_median30_test_metrics": compute_metrics(y_test_actual_mm, baseline_median30_test),
        "last_window_scaled": X_scaled[-1:],
    }


def train_pretrain_finetune_candidate(
    pretrain_daily_df: pd.DataFrame,
    target_daily_df: pd.DataFrame,
    candidate: CandidateConfig,
    epochs: int,
    batch_size: int,
    seed: int,
    selection_metric: str,
) -> dict[str, object]:
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)

    X_pre, y_pre, _, _ = build_sequences(pretrain_daily_df, candidate)
    X, y, target_dates, target_indices = build_sequences(target_daily_df, candidate)
    sample_count = len(X)
    train_end, val_end = sequential_split(sample_count)

    feature_scaler = MinMaxScaler()
    feature_scaler.fit(
        np.concatenate(
            [
                X_pre.reshape(-1, X_pre.shape[-1]),
                X[:train_end].reshape(-1, X.shape[-1]),
            ],
            axis=0,
        )
    )
    target_scaler = MinMaxScaler()
    target_scaler.fit(np.concatenate([y_pre, y[:train_end]], axis=0))

    def scale_x(values: np.ndarray) -> np.ndarray:
        return feature_scaler.transform(values.reshape(-1, values.shape[-1])).reshape(
            values.shape
        ).astype(np.float32)

    X_pre_scaled = scale_x(X_pre)
    y_pre_scaled = target_scaler.transform(y_pre).astype(np.float32)
    X_scaled = scale_x(X)
    y_scaled = target_scaler.transform(y).astype(np.float32)

    X_train, X_val, X_test = (
        X_scaled[:train_end],
        X_scaled[train_end:val_end],
        X_scaled[val_end:],
    )
    y_train, y_val, y_test = (
        y_scaled[:train_end],
        y_scaled[train_end:val_end],
        y_scaled[val_end:],
    )

    val_dates = target_dates[train_end:val_end]
    test_dates = target_dates[val_end:]
    val_indices = target_indices[train_end:val_end]
    test_indices = target_indices[val_end:]

    model = build_lstm_model(candidate.window_size, len(candidate.feature_columns))

    pretrain_actual_mm = inverse_target(y_pre_scaled, target_scaler)
    pretrain_weights = 1.0 + 1.5 * (
        pretrain_actual_mm >= RAIN_THRESHOLD_MM
    ).astype(np.float32)
    pretrain_history = model.fit(
        X_pre_scaled,
        y_pre_scaled,
        sample_weight=pretrain_weights,
        epochs=max(20, epochs // 2),
        batch_size=max(batch_size, 32),
        verbose=0,
        callbacks=[
            callbacks.EarlyStopping(
                monitor="loss",
                patience=5,
                restore_best_weights=True,
                verbose=0,
            )
        ],
    )

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.0005),
        loss="mse",
        metrics=["mae"],
    )

    train_actual_mm = inverse_target(y_train, target_scaler)
    sample_weights = 1.0 + 2.5 * (train_actual_mm >= RAIN_THRESHOLD_MM).astype(np.float32)
    finetune_history = model.fit(
        X_train,
        y_train,
        validation_data=(X_val, y_val),
        sample_weight=sample_weights,
        epochs=epochs,
        batch_size=batch_size,
        verbose=0,
        callbacks=[
            callbacks.EarlyStopping(
                monitor="val_loss",
                patience=12,
                restore_best_weights=True,
                verbose=0,
            ),
            callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                patience=6,
                factor=0.5,
                min_lr=1e-5,
                verbose=0,
            ),
        ],
    )

    y_val_pred_scaled = model.predict(X_val, verbose=0).reshape(-1, 1)
    y_test_pred_scaled = model.predict(X_test, verbose=0).reshape(-1, 1)

    y_val_actual_mm = inverse_target(y_val, target_scaler)
    y_test_actual_mm = inverse_target(y_test, target_scaler)
    y_val_pred_mm_raw = inverse_target(y_val_pred_scaled, target_scaler)
    y_test_pred_mm_raw = inverse_target(y_test_pred_scaled, target_scaler)

    threshold_mm, val_metrics = choose_postprocess_threshold(
        actual_val_mm=y_val_actual_mm,
        predicted_val_mm_raw=y_val_pred_mm_raw,
        selection_metric=selection_metric,
    )
    y_test_pred_mm = np.where(y_test_pred_mm_raw >= threshold_mm, y_test_pred_mm_raw, 0.0)
    test_metrics = compute_metrics(y_test_actual_mm, y_test_pred_mm)

    baseline_prev1_val = target_daily_df.loc[val_indices, "baseline_prev1"].to_numpy(
        dtype=np.float32
    )
    baseline_prev1_test = target_daily_df.loc[test_indices, "baseline_prev1"].to_numpy(
        dtype=np.float32
    )
    baseline_median30_val = target_daily_df.loc[
        val_indices, "baseline_median30"
    ].to_numpy(dtype=np.float32)
    baseline_median30_test = target_daily_df.loc[
        test_indices, "baseline_median30"
    ].to_numpy(dtype=np.float32)

    history = {
        f"pretrain_{key}": value for key, value in pretrain_history.history.items()
    }
    history.update(
        {f"finetune_{key}": value for key, value in finetune_history.history.items()}
    )

    return {
        "candidate": candidate,
        "model": model,
        "feature_scaler": feature_scaler,
        "target_scaler": target_scaler,
        "history": history,
        "train_samples": int(len(X_train)),
        "validation_samples": int(len(X_val)),
        "test_samples": int(len(X_test)),
        "pretrain_samples": int(len(X_pre_scaled)),
        "threshold_mm": threshold_mm,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "val_dates": val_dates,
        "test_dates": test_dates,
        "test_indices": test_indices,
        "test_actual_mm": y_test_actual_mm,
        "test_pred_mm_raw": y_test_pred_mm_raw,
        "test_pred_mm": y_test_pred_mm,
        "baseline_prev1_test": baseline_prev1_test,
        "baseline_median30_test": baseline_median30_test,
        "baseline_prev1_val_metrics": compute_metrics(y_val_actual_mm, baseline_prev1_val),
        "baseline_prev1_test_metrics": compute_metrics(y_test_actual_mm, baseline_prev1_test),
        "baseline_median30_val_metrics": compute_metrics(y_val_actual_mm, baseline_median30_val),
        "baseline_median30_test_metrics": compute_metrics(
            y_test_actual_mm, baseline_median30_test
        ),
        "last_window_scaled": X_scaled[-1:],
    }


def save_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def validation_score(metrics: dict[str, float], selection_metric: str) -> tuple[float, float]:
    return metric_score(metrics, selection_metric)


def main() -> None:
    args = parse_args()
    excel_path = Path(args.excel)
    source_dir = Path(args.source_dir)
    hydro_excel_path = Path(args.hydro_excel)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    use_pretrain = (
        args.mode == "pretrain-finetune"
        and hydro_excel_path.exists()
        and (source_dir.exists() and any(source_dir.glob("*.xlsx")))
    )

    if use_pretrain:
        hydro_raw_df = read_hydro_workbook(hydro_excel_path)
        target_raw_df = read_monthly_bmkg_folder(source_dir)
        raw_df = pd.concat([hydro_raw_df, target_raw_df], ignore_index=True)
        source_kind = "hydro_pretrain + bmkg_finetune"
        source_path = f"{hydro_excel_path} | {source_dir}"
        cleaned_daily_df, summary = prepare_daily_dataset(
            raw_df, source_kind, source_path, args.max_gap_days
        )
        pretrain_daily_df, _ = prepare_daily_dataset(
            hydro_raw_df, "hydro", str(hydro_excel_path), args.max_gap_days
        )
        target_daily_df, _ = prepare_daily_dataset(
            target_raw_df, "bmkg_monthly", str(source_dir), args.max_gap_days
        )
        forecast_daily_df = target_daily_df
    else:
        raw_df, source_kind, source_path = resolve_source_dataframe(
            excel_path, source_dir, hydro_excel_path
        )
        cleaned_daily_df, summary = prepare_daily_dataset(
            raw_df, source_kind, source_path, args.max_gap_days
        )
        target_daily_df = cleaned_daily_df
        pretrain_daily_df = None
        forecast_daily_df = target_daily_df

    candidate_configs = build_candidate_configs(args.candidate_windows)

    best_result: dict[str, object] | None = None
    candidate_reports: list[dict[str, object]] = []

    for candidate in candidate_configs:
        if use_pretrain:
            result = train_pretrain_finetune_candidate(
                pretrain_daily_df=pretrain_daily_df,
                target_daily_df=target_daily_df,
                candidate=candidate,
                epochs=args.epochs,
                batch_size=args.batch_size,
                seed=args.seed,
                selection_metric=args.selection_metric,
            )
        else:
            result = train_candidate(
                daily_df=target_daily_df,
                candidate=candidate,
                epochs=args.epochs,
                batch_size=args.batch_size,
                seed=args.seed,
                selection_metric=args.selection_metric,
            )

        candidate_report = {
            "name": candidate.name,
            "window_size": candidate.window_size,
            "feature_columns": candidate.feature_columns,
            "training_mode": args.mode if use_pretrain else "direct",
            "pretrain_samples": result.get("pretrain_samples", 0),
            "train_samples": result["train_samples"],
            "validation_samples": result["validation_samples"],
            "test_samples": result["test_samples"],
            "postprocess_threshold_mm": result["threshold_mm"],
            "validation_metrics": result["val_metrics"],
            "test_metrics": result["test_metrics"],
        }
        candidate_reports.append(candidate_report)

        current_score = validation_score(result["val_metrics"], args.selection_metric)
        if best_result is None:
            best_result = result
        else:
            best_score = validation_score(best_result["val_metrics"], args.selection_metric)
            if current_score < best_score:
                best_result = result

    if best_result is None:
        raise RuntimeError("Tidak ada kandidat model yang berhasil dilatih.")

    selected_candidate: CandidateConfig = best_result["candidate"]
    next_day_pred_scaled = best_result["model"].predict(best_result["last_window_scaled"], verbose=0)
    next_day_pred_mm_raw = float(
        inverse_target(next_day_pred_scaled.reshape(-1, 1), best_result["target_scaler"])[0]
    )
    next_day_pred_mm = (
        next_day_pred_mm_raw
        if next_day_pred_mm_raw >= best_result["threshold_mm"]
        else 0.0
    )
    next_day_date = (forecast_daily_df["date"].max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    predictions_df = pd.DataFrame(
        {
            "date": best_result["test_dates"],
            "actual_rr_mm": np.round(best_result["test_actual_mm"], 3),
            "predicted_rr_mm_raw": np.round(best_result["test_pred_mm_raw"], 3),
            "predicted_rr_mm": np.round(best_result["test_pred_mm"], 3),
            "baseline_prev1_rr_mm": np.round(best_result["baseline_prev1_test"], 3),
            "baseline_median30_rr_mm": np.round(best_result["baseline_median30_test"], 3),
        }
    )
    predictions_df["actual_category"] = predictions_df["actual_rr_mm"].map(rainfall_category)
    predictions_df["predicted_category"] = predictions_df["predicted_rr_mm"].map(rainfall_category)

    cleaned_export = cleaned_daily_df[
        [
            "date",
            "source_file",
            "source_type",
            "segment_id",
            "gap_days",
            "rr_mm",
            "was_missing",
            "rr_mm_filled",
            "baseline_prev1",
            "baseline_median30",
            "rain_flag_actual",
        ]
    ].copy()

    model_path = output_dir / "lstm_curah_hujan.keras"
    scalers_path = output_dir / "preprocessing.pkl"
    metrics_path = output_dir / "metrics.json"
    forecast_path = output_dir / "next_day_forecast.json"
    cleaned_path = output_dir / "curah_hujan_cleaned.csv"
    predictions_path = output_dir / "test_predictions.csv"
    history_path = output_dir / "training_history.csv"

    best_result["model"].save(model_path)
    with scalers_path.open("wb") as handle:
        pickle.dump(
            {
                "source_kind": summary.source_kind,
                "source_path": summary.source_path,
                "training_mode": args.mode if use_pretrain else "direct",
                "feature_scaler": best_result["feature_scaler"],
                "target_scaler": best_result["target_scaler"],
                "feature_columns": selected_candidate.feature_columns,
                "window_size": selected_candidate.window_size,
                "max_gap_days": args.max_gap_days,
                "selection_metric": args.selection_metric,
                "postprocess_threshold_mm": best_result["threshold_mm"],
                "rain_threshold_mm": RAIN_THRESHOLD_MM,
            },
            handle,
        )

    cleaned_export.to_csv(cleaned_path, index=False)
    predictions_df.to_csv(predictions_path, index=False)
    pd.DataFrame(
        {key: pd.Series(value) for key, value in best_result["history"].items()}
    ).to_csv(history_path, index=False)

    save_json(
        metrics_path,
        {
            "data_summary": asdict(summary),
            "selected_model": {
                "name": selected_candidate.name,
                "training_mode": args.mode if use_pretrain else "direct",
                "selection_metric": args.selection_metric,
                "window_size": selected_candidate.window_size,
                "feature_columns": selected_candidate.feature_columns,
                "postprocess_threshold_mm": best_result["threshold_mm"],
                "max_gap_days": args.max_gap_days,
                "pretrain_samples": best_result.get("pretrain_samples", 0),
                "train_samples": best_result["train_samples"],
                "validation_samples": best_result["validation_samples"],
                "test_samples": best_result["test_samples"],
            },
            "candidate_results": candidate_reports,
            "baseline_metrics": {
                "previous_day_validation": best_result["baseline_prev1_val_metrics"],
                "previous_day_test": best_result["baseline_prev1_test_metrics"],
                "median30_validation": best_result["baseline_median30_val_metrics"],
                "median30_test": best_result["baseline_median30_test_metrics"],
            },
            "test_metrics": best_result["test_metrics"],
        },
    )

    save_json(
        forecast_path,
        {
            "forecast_date": next_day_date,
            "predicted_rr_mm_raw": round(next_day_pred_mm_raw, 3),
            "predicted_rr_mm": round(next_day_pred_mm, 3),
            "predicted_category": rainfall_category(next_day_pred_mm),
            "rain_threshold_mm": RAIN_THRESHOLD_MM,
            "postprocess_threshold_mm": round(float(best_result["threshold_mm"]), 3),
        },
    )

    print("\nRingkasan data:")
    print(json.dumps(asdict(summary), indent=2))
    print("\nModel terpilih:")
    print(
        json.dumps(
            {
                "name": selected_candidate.name,
                "training_mode": args.mode if use_pretrain else "direct",
                "selection_metric": args.selection_metric,
                "window_size": selected_candidate.window_size,
                "postprocess_threshold_mm": best_result["threshold_mm"],
            },
            indent=2,
        )
    )
    print("\nMetrik data uji:")
    print(json.dumps(best_result["test_metrics"], indent=2))
    print("\nArtefak tersimpan di:")
    print(output_dir.resolve())


if __name__ == "__main__":
    main()
