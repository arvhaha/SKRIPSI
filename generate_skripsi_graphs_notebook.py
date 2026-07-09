from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Model

import retrain_operational_multiclass_model as final_model


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
SUMMARY_FINAL_PATH = ARTIFACTS_DIR / "latest_multiclass_training_summary.json"
WINDOW_SEARCH_PATH = ARTIFACTS_DIR / "windowed_multiclass_search_20260705_161003" / "search_results.csv"
CUTOFF_SEARCH_PATH = ARTIFACTS_DIR / "cutoff_around_2005_20260705_202618" / "search_results.csv"
TIME_STEPS_SEARCH_PATH = (
    ARTIFACTS_DIR / "time_steps_gated_sweep_20260630_202306" / "time_steps_sweep_results.csv"
)
NOTEBOOK_PATH = ROOT / "GRAFIK_SKRIPSI_FINAL.ipynb"
FIGURE_PREFIX = "skripsi_graphs"
CLASS_LABELS_SHORT = ["Cerah", "Ringan", "Sedang", "Lebat"]
CLASS_LABELS_FULL = final_model.CLASS_NAMES
METRIC_COLUMNS = [
    "accuracy",
    "macro_recall",
    "macro_f1",
    "critical_recall",
    "critical_precision",
    "critical_f1",
]
METRIC_LABELS = {
    "accuracy": "Accuracy",
    "macro_recall": "Macro Recall",
    "macro_f1": "Macro F1",
    "critical_recall": "Recall Kelas 3",
    "critical_precision": "Precision Kelas 3",
    "critical_f1": "F1 Kelas 3",
}
PLOT_COLORS = {
    "Cerah": "#94a3b8",
    "Ringan": "#60a5fa",
    "Sedang": "#f59e0b",
    "Lebat": "#ef4444",
    "Baseline Lama": "#64748b",
    "2005+ Final": "#0f766e",
    "2010+ Terbaik": "#7c3aed",
    "LSTM": "#2563eb",
    "XGBoost": "#dc2626",
    "Hybrid": "#0f766e",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_backup_summary() -> Path:
    backup_dirs = sorted(
        ARTIFACTS_DIR.glob("operational_backup_before_2005plus_*"),
        key=lambda path: path.name,
    )
    if not backup_dirs:
        raise FileNotFoundError("Folder backup model lama tidak ditemukan.")
    summary_path = backup_dirs[-1] / "latest_multiclass_training_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary backup tidak ditemukan: {summary_path}")
    return summary_path


def ensure_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ARTIFACTS_DIR / f"{FIGURE_PREFIX}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def save_fig(fig: plt.Figure, output_dir: Path, filename: str) -> Path:
    path = output_dir / filename
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def load_dataset() -> pd.DataFrame:
    dataset_path = ROOT / "Master_Data_Spasial_Jaktim_1990_sekarang.csv"
    df = pd.read_csv(dataset_path, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    df = df.sort_values(["Kecamatan", "Tanggal"]).reset_index(drop=True)
    df["Label"] = df["Curah Hujan (mm)"].apply(final_model.klasifikasi_hujan_4_kelas).astype(np.int8)
    return df


def plot_class_distribution(summary_final: dict[str, Any], output_dir: Path) -> Path:
    class_dist = summary_final["class_distribution_total"]
    labels = [CLASS_LABELS_SHORT[int(class_id)] for class_id in class_dist.keys()]
    counts = [int(value) for value in class_dist.values()]
    colors = [PLOT_COLORS[label] for label in labels]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(labels, counts, color=colors, edgecolor="#1e293b", linewidth=0.8)
    ax.set_title("Distribusi Kelas Target 4 Class", fontsize=14, fontweight="bold")
    ax.set_ylabel("Jumlah Data")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    for bar, count in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(counts) * 0.015,
            f"{count:,}".replace(",", "."),
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    return save_fig(fig, output_dir, "01_distribusi_kelas_asli.png")


def plot_smote_distribution(summary_final: dict[str, Any], output_dir: Path) -> Path:
    smote_summary = summary_final["smote_summary"]
    before = smote_summary["distribution_before"]
    after = smote_summary["distribution_after"]
    class_ids = [0, 1, 2, 3]
    labels = [CLASS_LABELS_SHORT[class_id] for class_id in class_ids]
    x = np.arange(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    before_values = [int(before.get(str(class_id), 0)) for class_id in class_ids]
    after_values = [int(after.get(str(class_id), 0)) for class_id in class_ids]
    bars_before = ax.bar(x - width / 2, before_values, width, label="Sebelum SMOTE", color="#94a3b8")
    bars_after = ax.bar(x + width / 2, after_values, width, label="Sesudah SMOTE", color="#0f766e")
    ax.set_title("Distribusi Kelas Train Sebelum dan Sesudah SMOTE", fontsize=14, fontweight="bold")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Jumlah Sequence Train")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False)
    for bars in (bars_before, bars_after):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(after_values) * 0.012,
                f"{int(bar.get_height()):,}".replace(",", "."),
                ha="center",
                va="bottom",
                fontsize=8,
            )
    fig.tight_layout()
    return save_fig(fig, output_dir, "02_distribusi_smote.png")


def plot_monthly_pattern(df: pd.DataFrame, output_dir: Path) -> Path:
    monthly = (
        df.assign(Bulan=df["Tanggal"].dt.month)
        .groupby("Bulan")
        .agg(
            rata_hujan=("Curah Hujan (mm)", "mean"),
            kejadian_sedang_ekstrem=("Label", lambda values: int(np.sum(np.asarray(values) >= 2))),
        )
        .reset_index()
    )
    month_labels = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

    fig, ax1 = plt.subplots(figsize=(10, 4.8))
    ax2 = ax1.twinx()
    ax1.plot(
        monthly["Bulan"],
        monthly["rata_hujan"],
        color="#2563eb",
        marker="o",
        linewidth=2.2,
        label="Rata-rata curah hujan",
    )
    ax2.bar(
        monthly["Bulan"],
        monthly["kejadian_sedang_ekstrem"],
        color="#f59e0b",
        alpha=0.28,
        width=0.65,
        label="Jumlah kelas Sedang+Lebat",
    )
    ax1.set_title("Pola Musiman Curah Hujan dan Kelas Sedang/Lebat", fontsize=14, fontweight="bold")
    ax1.set_xticks(range(1, 13), month_labels)
    ax1.set_ylabel("Rata-rata Curah Hujan (mm)", color="#2563eb")
    ax2.set_ylabel("Jumlah Kejadian Kelas 2-3", color="#b45309")
    ax1.grid(axis="y", linestyle="--", alpha=0.3)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", frameon=False)
    fig.tight_layout()
    return save_fig(fig, output_dir, "03_pola_musiman.png")


def plot_confusion_matrix(summary_final: dict[str, Any], output_dir: Path) -> Path:
    confusion = np.asarray(summary_final["metrics"]["confusion_matrix"], dtype=np.int32)
    row_sums = confusion.sum(axis=1, keepdims=True)
    normalized = np.divide(confusion, row_sums, out=np.zeros_like(confusion, dtype=np.float64), where=row_sums > 0)

    fig, ax = plt.subplots(figsize=(6.8, 5.8))
    image = ax.imshow(normalized, cmap="Blues", vmin=0.0, vmax=1.0)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Proporsi per kelas aktual")
    ax.set_xticks(range(4), CLASS_LABELS_SHORT)
    ax.set_yticks(range(4), CLASS_LABELS_SHORT)
    ax.set_xlabel("Prediksi")
    ax.set_ylabel("Aktual")
    ax.set_title("Confusion Matrix Model Final (Normalized)", fontsize=14, fontweight="bold")
    for row_idx in range(confusion.shape[0]):
        for col_idx in range(confusion.shape[1]):
            count = confusion[row_idx, col_idx]
            share = normalized[row_idx, col_idx] * 100.0
            text_color = "white" if normalized[row_idx, col_idx] >= 0.45 else "#0f172a"
            ax.text(
                col_idx,
                row_idx,
                f"{count}\n{share:.1f}%",
                ha="center",
                va="center",
                fontsize=9,
                color=text_color,
                fontweight="bold" if row_idx == col_idx else None,
            )
    fig.tight_layout()
    return save_fig(fig, output_dir, "04_confusion_matrix_final.png")


def plot_per_class_metrics(summary_final: dict[str, Any], output_dir: Path) -> Path:
    report = summary_final["metrics"]["classification_report"]
    labels = CLASS_LABELS_SHORT
    precision = [float(report[class_name]["precision"]) for class_name in CLASS_LABELS_FULL]
    recall = [float(report[class_name]["recall"]) for class_name in CLASS_LABELS_FULL]
    f1_scores = [float(report[class_name]["f1-score"]) for class_name in CLASS_LABELS_FULL]
    x = np.arange(len(labels))
    width = 0.24

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(x - width, precision, width, label="Precision", color="#2563eb")
    ax.bar(x, recall, width, label="Recall", color="#0f766e")
    ax.bar(x + width, f1_scores, width, label="F1-Score", color="#f59e0b")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Skor")
    ax.set_title("Precision, Recall, dan F1 per Kelas", fontsize=14, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False, ncols=3)
    fig.tight_layout()
    return save_fig(fig, output_dir, "05_metrics_per_kelas.png")


def plot_model_family_comparison(summary_final: dict[str, Any], output_dir: Path) -> Path:
    family_rows = pd.DataFrame(
        [
            {
                "model": "LSTM",
                "accuracy": float(summary_final["metrics_lstm_argmax"]["accuracy"]),
                "macro_f1": float(summary_final["metrics_lstm_argmax"]["macro_f1"]),
                "critical_recall": float(summary_final["metrics_lstm_argmax"]["critical_recall"]),
            },
            {
                "model": "XGBoost",
                "accuracy": float(summary_final["metrics_argmax"]["accuracy"]),
                "macro_f1": float(summary_final["metrics_argmax"]["macro_f1"]),
                "critical_recall": float(summary_final["metrics_argmax"]["critical_recall"]),
            },
            {
                "model": "Hybrid",
                "accuracy": float(summary_final["metrics"]["accuracy"]),
                "macro_f1": float(summary_final["metrics"]["macro_f1"]),
                "critical_recall": float(summary_final["metrics"]["critical_recall"]),
            },
        ]
    )
    metrics = ["accuracy", "macro_f1", "critical_recall"]
    metric_names = ["Accuracy", "Macro F1", "Recall Kelas 3"]
    x = np.arange(len(metrics))
    width = 0.23

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for index, row in family_rows.iterrows():
        ax.bar(
            x + (index - 1) * width,
            [float(row[metric]) for metric in metrics],
            width,
            label=str(row["model"]),
            color=PLOT_COLORS[str(row["model"])],
        )
    ax.set_xticks(x, metric_names)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Skor")
    ax.set_title("Perbandingan Keluarga Model pada Run Final", fontsize=14, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False, ncols=3)
    fig.tight_layout()
    return save_fig(fig, output_dir, "06_perbandingan_keluarga_model.png")


def plot_window_comparison(
    summary_baseline: dict[str, Any],
    summary_final: dict[str, Any],
    window_df: pd.DataFrame,
    output_dir: Path,
) -> Path:
    best_2010 = (
        window_df[window_df["window_label"] == "2010plus"]
        .sort_values(["selection_score", "accuracy"], ascending=[False, False])
        .iloc[0]
    )

    comparison = pd.DataFrame(
        [
            {
                "label": "Baseline Lama",
                "accuracy": float(summary_baseline["metrics"]["accuracy"]),
                "macro_f1": float(summary_baseline["metrics"]["macro_f1"]),
                "critical_recall": float(summary_baseline["metrics"]["critical_recall"]),
            },
            {
                "label": "2005+ Final",
                "accuracy": float(summary_final["metrics"]["accuracy"]),
                "macro_f1": float(summary_final["metrics"]["macro_f1"]),
                "critical_recall": float(summary_final["metrics"]["critical_recall"]),
            },
            {
                "label": "2010+ Terbaik",
                "accuracy": float(best_2010["accuracy"]),
                "macro_f1": float(best_2010["macro_f1"]),
                "critical_recall": float(best_2010["critical_recall"]),
            },
        ]
    )

    metrics = ["accuracy", "macro_f1", "critical_recall"]
    metric_names = ["Accuracy", "Macro F1", "Recall Kelas 3"]
    x = np.arange(len(metrics))
    width = 0.23

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    for index, row in comparison.iterrows():
        ax.bar(
            x + (index - 1) * width,
            [float(row[metric]) for metric in metrics],
            width,
            label=str(row["label"]),
            color=PLOT_COLORS[str(row["label"])],
        )
    ax.set_xticks(x, metric_names)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Skor")
    ax.set_title("Perbandingan Window Data Utama", fontsize=14, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    return save_fig(fig, output_dir, "07_perbandingan_window.png")


def plot_cutoff_sweep(cutoff_df: pd.DataFrame, output_dir: Path) -> Path:
    best_per_cutoff = (
        cutoff_df.sort_values(["cutoff_label", "selection_score", "accuracy"], ascending=[True, False, False])
        .groupby("cutoff_label", as_index=False)
        .first()
        .copy()
    )
    best_per_cutoff["year"] = best_per_cutoff["start_date"].str.slice(0, 4).astype(int)
    best_per_cutoff = best_per_cutoff.sort_values("year")

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.plot(best_per_cutoff["year"], best_per_cutoff["accuracy"], marker="o", linewidth=2.2, label="Accuracy")
    ax.plot(best_per_cutoff["year"], best_per_cutoff["macro_f1"], marker="o", linewidth=2.2, label="Macro F1")
    ax.plot(
        best_per_cutoff["year"],
        best_per_cutoff["critical_recall"],
        marker="o",
        linewidth=2.2,
        label="Recall Kelas 3",
    )
    ax.set_title("Sweep Cutoff Data 2003+ sampai 2007+", fontsize=14, fontweight="bold")
    ax.set_xlabel("Tahun Awal Data")
    ax.set_ylabel("Skor")
    ax.set_xticks(best_per_cutoff["year"].tolist())
    ax.set_ylim(0, max(0.7, float(best_per_cutoff[["accuracy", "macro_f1"]].to_numpy().max()) + 0.05))
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(frameon=False, ncols=3)

    best_row = best_per_cutoff.sort_values(["accuracy", "macro_f1"], ascending=[False, False]).iloc[0]
    ax.annotate(
        f"Best accuracy: {best_row['year']}\n{best_row['accuracy']:.3f}",
        xy=(best_row["year"], best_row["accuracy"]),
        xytext=(best_row["year"] + 0.15, min(0.85, best_row["accuracy"] + 0.08)),
        arrowprops={"arrowstyle": "->", "color": "#0f172a"},
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#cbd5e1"},
    )
    fig.tight_layout()
    return save_fig(fig, output_dir, "08_cutoff_sweep.png")


def plot_time_steps_comparison(cutoff_df: pd.DataFrame, output_dir: Path) -> Path:
    time_step_df = (
        cutoff_df[
            (cutoff_df["cutoff_label"] == "2005plus") & (cutoff_df["loss_mode"] == "cross_entropy")
        ]
        .sort_values("time_steps")
        .copy()
    )

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.plot(time_step_df["time_steps"], time_step_df["accuracy"], marker="o", linewidth=2.2, label="Accuracy")
    ax.plot(time_step_df["time_steps"], time_step_df["macro_f1"], marker="o", linewidth=2.2, label="Macro F1")
    ax.plot(
        time_step_df["time_steps"],
        time_step_df["critical_recall"],
        marker="o",
        linewidth=2.2,
        label="Recall Kelas 3",
    )
    ax.set_title("Pengaruh Time Steps pada Window 2005+ (Cross Entropy)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time Steps")
    ax.set_ylabel("Skor")
    ax.set_xticks(time_step_df["time_steps"].tolist())
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend(frameon=False, ncols=3)
    fig.tight_layout()
    return save_fig(fig, output_dir, "09_time_steps_2005_ce.png")


def plot_loss_comparison(window_df: pd.DataFrame, output_dir: Path) -> Path:
    fixed_df = (
        window_df[(window_df["time_steps"] == 3) & (window_df["window_label"].isin(["2005plus", "2010plus"]))]
        .sort_values(["window_label", "loss_mode"])
        .copy()
    )
    fixed_df["combo"] = fixed_df["window_label"] + "\n" + fixed_df["loss_mode"]
    x = np.arange(len(fixed_df))
    width = 0.24

    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(x - width, fixed_df["accuracy"], width, label="Accuracy", color="#2563eb")
    ax.bar(x, fixed_df["macro_f1"], width, label="Macro F1", color="#0f766e")
    ax.bar(x + width, fixed_df["critical_recall"], width, label="Recall Kelas 3", color="#f59e0b")
    ax.set_xticks(x, fixed_df["combo"].tolist())
    ax.set_ylabel("Skor")
    ax.set_ylim(0, 0.75)
    ax.set_title("Perbandingan Cross Entropy vs Focal (Time Steps = 3)", fontsize=14, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False, ncols=3)
    fig.tight_layout()
    return save_fig(fig, output_dir, "10_loss_compare_ts3.png")


def plot_training_curve(summary_final: dict[str, Any], output_dir: Path) -> Path:
    history = summary_final["training_history"]
    epochs = np.arange(1, len(history["loss"]) + 1)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(epochs, history["loss"], label="Train Loss", linewidth=2.0, color="#2563eb")
    axes[0].plot(epochs, history["val_loss"], label="Val Loss", linewidth=2.0, color="#ef4444")
    axes[0].set_title("Kurva Loss LSTM")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].grid(True, linestyle="--", alpha=0.3)
    axes[0].legend(frameon=False)

    axes[1].plot(epochs, history["accuracy"], label="Train Accuracy", linewidth=2.0, color="#0f766e")
    axes[1].plot(epochs, history["val_accuracy"], label="Val Accuracy", linewidth=2.0, color="#f59e0b")
    axes[1].set_title("Kurva Accuracy LSTM")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].grid(True, linestyle="--", alpha=0.3)
    axes[1].legend(frameon=False)

    fig.suptitle("Training Curve Model Final", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return save_fig(fig, output_dir, "11_training_curve.png")


def build_test_predictions_by_district(summary_final: dict[str, Any]) -> dict[str, pd.DataFrame]:
    start_date = summary_final.get("window_start_date")
    time_steps = int(summary_final["time_steps"])
    final_model.TIME_STEPS = time_steps

    feature_frame, feature_columns = final_model.prepare_feature_frame(start_date=start_date)
    scaler = joblib.load(ROOT / "scaler_4class_jaktim.pkl")
    lstm_model = tf.keras.models.load_model(ROOT / "model_bilstm_4class_jaktim.h5", compile=False)
    xgb_model = joblib.load(ROOT / "model_xgboost_4class_jaktim.pkl")
    feature_extractor = Model(
        inputs=lstm_model.input,
        outputs=lstm_model.get_layer("feature_layer").output,
    )
    ensemble_rule = summary_final["ensemble_rule"]

    results: dict[str, pd.DataFrame] = {}
    for district_name in sorted(feature_frame["Kecamatan"].unique().tolist()):
        district_frame = (
            feature_frame[feature_frame["Kecamatan"] == district_name]
            .sort_values("Tanggal")
            .reset_index(drop=True)
            .copy()
        )
        _, val_end = final_model.compute_split_points(len(district_frame))
        scaled_values = scaler.transform(district_frame[feature_columns]).astype(np.float32)

        metadata_rows: list[dict[str, Any]] = []
        windows: list[np.ndarray] = []
        for target_index in range(time_steps, len(district_frame)):
            if target_index < val_end:
                continue
            windows.append(scaled_values[target_index - time_steps : target_index])
            row = district_frame.iloc[target_index]
            metadata_rows.append(
                {
                    "Kecamatan": district_name,
                    "Tanggal": row["Tanggal"],
                    "Curah Hujan (mm)": float(row["Curah Hujan (mm)"]),
                    "ActualClass": int(row["Label"]),
                }
            )

        test_meta = pd.DataFrame(metadata_rows)
        X_test = np.asarray(windows, dtype=np.float32)
        lstm_probabilities = lstm_model.predict(X_test, verbose=0)
        latent_features = feature_extractor.predict(X_test, verbose=0)
        xgb_probabilities = xgb_model.predict_proba(latent_features)

        final_predictions = final_model.apply_gated_ensemble_rule(
            lstm_probabilities,
            xgb_probabilities,
            class_2_threshold=float(ensemble_rule["class_2_threshold"]),
            class_3_threshold=float(ensemble_rule["class_3_threshold"]),
            class_2_margin=float(ensemble_rule["class_2_margin"]),
            class_3_margin=float(ensemble_rule["class_3_margin"]),
        )
        operational_probabilities = final_model.compose_operational_probabilities(
            lstm_probabilities,
            xgb_probabilities,
            final_predictions,
        )

        test_meta["PredClass"] = final_predictions.astype(int)
        test_meta["PredConfidence"] = operational_probabilities.max(axis=1)
        test_meta["ProbSedang"] = operational_probabilities[:, 2]
        test_meta["ProbLebat"] = operational_probabilities[:, 3]
        test_meta["ProbSedangAtauLebat"] = operational_probabilities[:, 2] + operational_probabilities[:, 3]
        test_meta["ActualLabel"] = test_meta["ActualClass"].map(dict(enumerate(CLASS_LABELS_SHORT)))
        test_meta["PredLabel"] = test_meta["PredClass"].map(dict(enumerate(CLASS_LABELS_SHORT)))
        results[district_name] = test_meta

    return results


def select_representative_event_window(
    district_predictions: dict[str, pd.DataFrame],
    window_size: int = 35,
) -> tuple[str, pd.DataFrame]:
    best_choice: tuple[float, str, int] | None = None

    for district_name, frame in district_predictions.items():
        if len(frame) < window_size:
            continue

        for start_index in range(0, len(frame) - window_size + 1):
            window = frame.iloc[start_index : start_index + window_size].copy()
            actual_ge2 = int((window["ActualClass"] >= 2).sum())
            actual_ge3 = int((window["ActualClass"] == 3).sum())
            pred_ge2 = int((window["PredClass"] >= 2).sum())
            hit_ge2 = int(((window["ActualClass"] >= 2) & (window["PredClass"] >= 2)).sum())
            peak_rain = float(window["Curah Hujan (mm)"].max())
            mean_prob = float(window["ProbSedangAtauLebat"].mean())
            score = (
                actual_ge2 * 4.0
                + actual_ge3 * 6.0
                + hit_ge2 * 5.0
                + pred_ge2 * 1.5
                + peak_rain / 20.0
                + mean_prob
            )
            choice = (score, district_name, start_index)
            if best_choice is None or choice > best_choice:
                best_choice = choice

    if best_choice is None:
        fallback_district = sorted(district_predictions.keys())[0]
        return fallback_district, district_predictions[fallback_district].head(window_size).copy()

    _, district_name, start_index = best_choice
    frame = district_predictions[district_name]
    return district_name, frame.iloc[start_index : start_index + window_size].copy()


def plot_sample_actual_vs_predicted(summary_final: dict[str, Any], output_dir: Path) -> Path:
    district_predictions = build_test_predictions_by_district(summary_final)
    district_name, plot_frame = select_representative_event_window(district_predictions, window_size=35)
    plot_frame["Tanggal"] = pd.to_datetime(plot_frame["Tanggal"])

    fig, axes = plt.subplots(2, 1, figsize=(11.5, 7.0), sharex=True, height_ratios=[1.0, 1.2])
    axes[0].axhspan(0, 5, color="#e2e8f0", alpha=0.75, label="Cerah")
    axes[0].axhspan(5, 20, color="#dbeafe", alpha=0.6, label="Ringan")
    axes[0].axhspan(20, 50, color="#fef3c7", alpha=0.6, label="Sedang")
    axes[0].axhspan(50, max(60.0, float(plot_frame["Curah Hujan (mm)"].max()) + 5.0), color="#fee2e2", alpha=0.55, label="Lebat")
    axes[0].plot(
        plot_frame["Tanggal"],
        plot_frame["Curah Hujan (mm)"],
        color="#2563eb",
        linewidth=2.0,
        marker="o",
        markersize=4.0,
        label="Curah hujan aktual",
    )
    axes[0].axhline(5, color="#94a3b8", linestyle="--", linewidth=1.0)
    axes[0].axhline(20, color="#f59e0b", linestyle="--", linewidth=1.0)
    axes[0].axhline(50, color="#ef4444", linestyle="--", linewidth=1.0)
    axes[0].set_ylabel("Curah Hujan (mm)")
    axes[0].set_title(
        f"Contoh Output Model Final pada Window Hujan Aktif Kecamatan {district_name}",
        fontsize=14,
        fontweight="bold",
    )
    axes[0].grid(True, linestyle="--", alpha=0.25)
    axes[0].legend(frameon=False, loc="upper right")

    axes[1].step(
        plot_frame["Tanggal"],
        plot_frame["ActualClass"],
        where="mid",
        label="Aktual",
        color="#0f766e",
        linewidth=2.2,
    )
    axes[1].step(
        plot_frame["Tanggal"],
        plot_frame["PredClass"],
        where="mid",
        label="Prediksi",
        color="#dc2626",
        linewidth=1.8,
        alpha=0.85,
    )
    prob_axis = axes[1].twinx()
    prob_axis.plot(
        plot_frame["Tanggal"],
        plot_frame["ProbSedangAtauLebat"],
        color="#7c3aed",
        linewidth=2.0,
        alpha=0.8,
        label="Probabilitas Sedang+Lebat",
    )
    prob_axis.plot(
        plot_frame["Tanggal"],
        plot_frame["PredConfidence"],
        color="#f97316",
        linewidth=1.8,
        linestyle="--",
        marker="o",
        markersize=3.8,
        alpha=0.8,
        label="Confidence prediksi akhir",
    )
    prob_axis.set_ylim(0, 1.0)
    prob_axis.set_ylabel("Probabilitas")
    axes[1].set_yticks([0, 1, 2, 3], CLASS_LABELS_SHORT)
    axes[1].set_ylabel("Kelas")
    axes[1].set_xlabel("Tanggal")
    axes[1].grid(True, linestyle="--", alpha=0.25)
    lines_left, labels_left = axes[1].get_legend_handles_labels()
    lines_right, labels_right = prob_axis.get_legend_handles_labels()
    axes[1].legend(lines_left + lines_right, labels_left + labels_right, frameon=False, ncols=2, loc="upper left")
    date_start = plot_frame["Tanggal"].min().strftime("%d %b %Y")
    date_end = plot_frame["Tanggal"].max().strftime("%d %b %Y")
    fig.text(
        0.125,
        0.915,
        f"Window contoh: {date_start} sampai {date_end}",
        fontsize=9.5,
        color="#334155",
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    return save_fig(fig, output_dir, "12_contoh_actual_vs_predicted.png")


def plot_latent_feature_importance(output_dir: Path) -> Path:
    xgb_model = joblib.load(ROOT / "model_xgboost_4class_jaktim.pkl")
    importances = np.asarray(xgb_model.feature_importances_, dtype=float)
    top_n = min(12, len(importances))
    top_indices = np.argsort(importances)[-top_n:][::-1]
    top_values = importances[top_indices]
    top_labels = [f"Latent_{index + 1}" for index in top_indices]

    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.barh(top_labels[::-1], top_values[::-1], color="#7c3aed")
    ax.set_xlabel("Feature Importance")
    ax.set_title(
        "Feature Importance XGBoost pada Fitur Laten",
        fontsize=14,
        fontweight="bold",
    )
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    fig.tight_layout()
    return save_fig(fig, output_dir, "13_feature_importance_laten.png")


def build_notebook(
    output_dir: Path,
    summary_final: dict[str, Any],
    summary_baseline: dict[str, Any],
    best_2010_row: pd.Series,
    figure_paths: dict[str, Path],
) -> dict[str, Any]:
    rel = {name: path.relative_to(ROOT).as_posix() for name, path in figure_paths.items()}

    intro_lines = [
        "# Grafik Skripsi Model Final\n",
        "\n",
        "Notebook ini merangkum grafik-grafik utama untuk skripsi Web-GIS prediksi curah hujan 4 class BMKG.\n",
        "\n",
        f"- Model operasional final: `2005+ / time_steps={summary_final['time_steps']} / {summary_final['loss_mode']}`\n",
        f"- Accuracy final: `{float(summary_final['metrics']['accuracy']):.4f}`\n",
        f"- Macro F1 final: `{float(summary_final['metrics']['macro_f1']):.4f}`\n",
        f"- Recall kelas 3 final: `{float(summary_final['metrics']['critical_recall']):.4f}`\n",
        f"- Folder grafik: `{output_dir.relative_to(ROOT).as_posix()}`\n",
    ]

    overview_lines = [
        "## Ringkasan Model Utama\n",
        "\n",
        f"- Baseline lama: accuracy `{float(summary_baseline['metrics']['accuracy']):.4f}`, macro F1 `{float(summary_baseline['metrics']['macro_f1']):.4f}`, recall kelas 3 `{float(summary_baseline['metrics']['critical_recall']):.4f}`.\n",
        f"- Final 2005+: accuracy `{float(summary_final['metrics']['accuracy']):.4f}`, macro F1 `{float(summary_final['metrics']['macro_f1']):.4f}`, recall kelas 3 `{float(summary_final['metrics']['critical_recall']):.4f}`.\n",
        f"- 2010+ terbaik: accuracy `{float(best_2010_row['accuracy']):.4f}`, macro F1 `{float(best_2010_row['macro_f1']):.4f}`, recall kelas 3 `{float(best_2010_row['critical_recall']):.4f}`.\n",
    ]

    sections = [
        (
            "## 1. Distribusi Kelas Target\n\n"
            "Grafik ini penting untuk menjelaskan bahwa data 4 class sangat imbalanced, terutama pada kelas Lebat.\n\n"
            f"![Distribusi Kelas]({rel['class_distribution']})\n"
        ),
        (
            "## 2. Distribusi Sebelum dan Sesudah SMOTE\n\n"
            "Grafik ini menunjukkan kenapa SMOTE dipakai: kelas minoritas dinaikkan pada data train setelah ekstraksi fitur laten.\n\n"
            f"![SMOTE]({rel['smote_distribution']})\n"
        ),
        (
            "## 3. Pola Musiman Curah Hujan\n\n"
            "Visual ini membantu menjelaskan bahwa curah hujan dan kejadian kelas Sedang/Lebat punya pola musiman yang cukup jelas.\n\n"
            f"![Pola Musiman]({rel['monthly_pattern']})\n"
        ),
        (
            "## 4. Confusion Matrix Model Final\n\n"
            "Confusion matrix menunjukkan kelas mana yang paling sering tertukar. Ini grafik inti untuk pembahasan performa model.\n\n"
            f"![Confusion Matrix]({rel['confusion_matrix']})\n"
        ),
        (
            "## 5. Precision, Recall, dan F1 per Kelas\n\n"
            "Grafik ini menjelaskan bahwa performa per kelas tidak merata, dan kelas mayoritas biasanya lebih mudah dipelajari model.\n\n"
            f"![Per Class Metrics]({rel['per_class_metrics']})\n"
        ),
        (
            "## 6. Perbandingan Keluarga Model\n\n"
            "Grafik ini membandingkan LSTM saja, XGBoost saja, dan hybrid gated. Tujuannya menunjukkan alasan hybrid dipilih.\n\n"
            f"![Family Comparison]({rel['family_comparison']})\n"
        ),
        (
            "## 7. Perbandingan Window Data Utama\n\n"
            "Grafik ini menunjukkan kenapa window 2005+ lebih masuk akal dipilih dibanding baseline lama dan window 2010+.\n\n"
            f"![Window Comparison]({rel['window_comparison']})\n"
        ),
        (
            "## 8. Sweep Cutoff Tahun Awal Data\n\n"
            "Grafik ini penting untuk menunjukkan bahwa pemilihan 2005+ bukan asal pilih, tetapi hasil eksperimen cutoff beberapa tahun.\n\n"
            f"![Cutoff Sweep]({rel['cutoff_sweep']})\n"
        ),
        (
            "## 9. Pengaruh Time Steps\n\n"
            "Grafik ini menjelaskan efek panjang window input historis terhadap performa model pada window 2005+.\n\n"
            f"![Time Steps]({rel['time_steps_comparison']})\n"
        ),
        (
            "## 10. Cross Entropy vs Focal Loss\n\n"
            "Grafik ini menunjukkan bahwa pemilihan fungsi loss juga memengaruhi trade-off antara akurasi umum dan deteksi kelas ekstrem.\n\n"
            f"![Loss Comparison]({rel['loss_comparison']})\n"
        ),
        (
            "## 11. Training Curve LSTM\n\n"
            "Kurva ini dipakai untuk membaca apakah training berjalan stabil dan apakah ada indikasi overfitting berat.\n\n"
            f"![Training Curve]({rel['training_curve']})\n"
        ),
        (
            "## 12. Contoh Output pada Window Hujan Aktif\n\n"
            "Grafik ini sengaja difokuskan ke potongan waktu test yang lebih aktif hujan, supaya respons model terhadap event penting lebih mudah dilihat dan dijelaskan.\n\n"
            f"![Actual vs Predicted]({rel['sample_predictions']})\n"
        ),
        (
            "## 13. Feature Importance XGBoost pada Fitur Laten\n\n"
            "Karena XGBoost bekerja di atas fitur laten hasil LSTM, importance ini bersifat teknis dan tidak langsung seterjemah fitur input asli.\n\n"
            f"![Latent Feature Importance]({rel['latent_importance']})\n"
        ),
        (
            "## Penutup\n\n"
            "Paket grafik ini sudah cukup kuat untuk dipakai di bab hasil dan pembahasan. Kalau mau, langkah berikutnya paling pas adalah bikin versi narasi pembahasan per grafik supaya langsung siap masuk dokumen skripsi.\n"
        ),
    ]

    cells: list[dict[str, Any]] = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": intro_lines,
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": overview_lines,
        },
    ]
    for section in sections:
        cells.append({"cell_type": "markdown", "metadata": {}, "source": section.splitlines(keepends=True)})

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    summary_final = load_json(SUMMARY_FINAL_PATH)
    summary_baseline_path = find_latest_backup_summary()
    summary_baseline = load_json(summary_baseline_path)
    window_df = pd.read_csv(WINDOW_SEARCH_PATH)
    cutoff_df = pd.read_csv(CUTOFF_SEARCH_PATH)
    _ = pd.read_csv(TIME_STEPS_SEARCH_PATH)
    dataset = load_dataset()
    output_dir = ensure_output_dir()

    best_2010_row = (
        window_df[window_df["window_label"] == "2010plus"]
        .sort_values(["selection_score", "accuracy"], ascending=[False, False])
        .iloc[0]
    )

    figure_paths = {
        "class_distribution": plot_class_distribution(summary_final, output_dir),
        "smote_distribution": plot_smote_distribution(summary_final, output_dir),
        "monthly_pattern": plot_monthly_pattern(dataset, output_dir),
        "confusion_matrix": plot_confusion_matrix(summary_final, output_dir),
        "per_class_metrics": plot_per_class_metrics(summary_final, output_dir),
        "family_comparison": plot_model_family_comparison(summary_final, output_dir),
        "window_comparison": plot_window_comparison(summary_baseline, summary_final, window_df, output_dir),
        "cutoff_sweep": plot_cutoff_sweep(cutoff_df, output_dir),
        "time_steps_comparison": plot_time_steps_comparison(cutoff_df, output_dir),
        "loss_comparison": plot_loss_comparison(window_df, output_dir),
        "training_curve": plot_training_curve(summary_final, output_dir),
        "sample_predictions": plot_sample_actual_vs_predicted(summary_final, output_dir),
        "latent_importance": plot_latent_feature_importance(output_dir),
    }

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "output_dir": str(output_dir),
        "summary_final_path": str(SUMMARY_FINAL_PATH),
        "summary_baseline_path": str(summary_baseline_path),
        "figure_paths": {name: str(path) for name, path in figure_paths.items()},
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    notebook = build_notebook(output_dir, summary_final, summary_baseline, best_2010_row, figure_paths)
    NOTEBOOK_PATH.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Notebook tersimpan di: {NOTEBOOK_PATH}")
    print(f"Grafik tersimpan di: {output_dir}")


if __name__ == "__main__":
    main()
