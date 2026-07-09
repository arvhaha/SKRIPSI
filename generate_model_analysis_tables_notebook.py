from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
NOTEBOOK_PATH = ROOT / "ANALISIS_TABEL_MODEL_FINAL.ipynb"

BASELINE_SUMMARY_PATH = (
    ARTIFACTS_DIR / "operational_backup_before_2005plus_20260705_234502" / "latest_multiclass_training_summary.json"
)
BEST_2005_SUMMARY_PATH = ARTIFACTS_DIR / "cutoff_2005plus_ts3_focal_20260705_222007" / "training_summary.json"
WINDOWED_SEARCH_CSV_PATH = ARTIFACTS_DIR / "windowed_multiclass_search_20260705_161003" / "search_results.csv"
CUTOFF_SEARCH_CSV_PATH = ARTIFACTS_DIR / "cutoff_around_2005_20260705_202618" / "search_results.csv"
TIME_STEPS_SWEEP_CSV_PATH = ARTIFACTS_DIR / "time_steps_gated_sweep_20260630_202306" / "time_steps_sweep_results.csv"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def selection_score(metrics: dict[str, Any]) -> float:
    return (
        0.45 * float(metrics["accuracy"])
        + 0.20 * float(metrics["macro_f1"])
        + 0.15 * float(metrics["macro_recall"])
        + 0.10 * float(metrics["critical_recall"])
        + 0.05 * float(metrics["critical_precision"])
        + 0.05 * float(metrics["critical_f1"])
    )


def first_test_start_date(summary: dict[str, Any]) -> str:
    boundaries = summary["split_summary"]["district_boundaries"]
    first_boundary = next(iter(boundaries.values()))
    return str(first_boundary["test_start_date"]).replace("T00:00:00", "")


def round_float_columns(df: pd.DataFrame, digits: int = 6) -> pd.DataFrame:
    rounded = df.copy()
    float_columns = rounded.select_dtypes(include=["float", "float32", "float64"]).columns
    for column in float_columns:
        rounded[column] = rounded[column].round(digits)
    return rounded


def best_window_row(windowed_results: pd.DataFrame, window_label: str) -> pd.Series:
    subset = windowed_results[windowed_results["window_label"] == window_label].copy()
    if subset.empty:
        raise ValueError(f"Tidak ada hasil untuk window_label={window_label}.")
    return subset.sort_values(["selection_score", "accuracy"], ascending=[False, False]).iloc[0]


def build_main_model_compare(windowed_results: pd.DataFrame) -> pd.DataFrame:
    baseline_summary = load_json(BASELINE_SUMMARY_PATH)
    best_2005_summary = load_json(BEST_2005_SUMMARY_PATH)
    best_2010 = best_window_row(windowed_results, "2010plus")

    rows = [
        {
            "Model": "Baseline Full Data (1990+)",
            "Window Data": "1990-sekarang",
            "Time Steps": int(baseline_summary["time_steps"]),
            "Loss": baseline_summary.get("loss_mode", "cross_entropy"),
            "Selection Score": selection_score(baseline_summary["metrics"]),
            "Accuracy": float(baseline_summary["metrics"]["accuracy"]),
            "Macro Recall": float(baseline_summary["metrics"]["macro_recall"]),
            "Macro F1": float(baseline_summary["metrics"]["macro_f1"]),
            "Critical Recall": float(baseline_summary["metrics"]["critical_recall"]),
            "Critical Precision": float(baseline_summary["metrics"]["critical_precision"]),
            "Critical F1": float(baseline_summary["metrics"]["critical_f1"]),
            "Test Start": first_test_start_date(baseline_summary),
            "Kelas 3 Test": int(baseline_summary["class_distribution_test"]["3"]),
        },
        {
            "Model": "Best 2005+",
            "Window Data": "2005-sekarang",
            "Time Steps": int(best_2005_summary["time_steps"]),
            "Loss": best_2005_summary.get("loss_mode", "cross_entropy"),
            "Selection Score": selection_score(best_2005_summary["metrics"]),
            "Accuracy": float(best_2005_summary["metrics"]["accuracy"]),
            "Macro Recall": float(best_2005_summary["metrics"]["macro_recall"]),
            "Macro F1": float(best_2005_summary["metrics"]["macro_f1"]),
            "Critical Recall": float(best_2005_summary["metrics"]["critical_recall"]),
            "Critical Precision": float(best_2005_summary["metrics"]["critical_precision"]),
            "Critical F1": float(best_2005_summary["metrics"]["critical_f1"]),
            "Test Start": first_test_start_date(best_2005_summary),
            "Kelas 3 Test": int(best_2005_summary["class_distribution_test"]["3"]),
        },
        {
            "Model": "Best 2010+",
            "Window Data": "2010-sekarang",
            "Time Steps": int(best_2010["time_steps"]),
            "Loss": str(best_2010["loss_mode"]),
            "Selection Score": float(best_2010["selection_score"]),
            "Accuracy": float(best_2010["accuracy"]),
            "Macro Recall": float(best_2010["macro_recall"]),
            "Macro F1": float(best_2010["macro_f1"]),
            "Critical Recall": float(best_2010["critical_recall"]),
            "Critical Precision": float(best_2010["critical_precision"]),
            "Critical F1": float(best_2010["critical_f1"]),
            "Test Start": "2024-01-07",
            "Kelas 3 Test": int(best_2010["class3_test"]),
        },
    ]
    return round_float_columns(pd.DataFrame(rows), digits=6)


def build_cutoff_best_table(cutoff_results: pd.DataFrame) -> pd.DataFrame:
    best_rows = (
        cutoff_results.sort_values("selection_score", ascending=False)
        .groupby("cutoff_label", sort=False)
        .head(1)
        .copy()
    )
    cutoff_order = ["2003plus", "2004plus", "2005plus", "2006plus", "2007plus"]
    best_rows["order_key"] = best_rows["cutoff_label"].map({label: index for index, label in enumerate(cutoff_order)})
    best_rows = best_rows.sort_values("order_key").drop(columns=["order_key"])

    table = best_rows.rename(
        columns={
            "cutoff_label": "Cutoff",
            "start_date": "Start Date",
            "config_label": "Config Terbaik",
            "time_steps": "Time Steps",
            "loss_mode": "Loss",
            "selection_score": "Selection Score",
            "accuracy": "Accuracy",
            "macro_recall": "Macro Recall",
            "macro_f1": "Macro F1",
            "critical_recall": "Critical Recall",
            "critical_precision": "Critical Precision",
            "critical_f1": "Critical F1",
            "class3_test": "Kelas 3 Test",
            "sequence_count": "Total Sequence",
        }
    )[
        [
            "Cutoff",
            "Start Date",
            "Config Terbaik",
            "Time Steps",
            "Loss",
            "Selection Score",
            "Accuracy",
            "Macro Recall",
            "Macro F1",
            "Critical Recall",
            "Critical Precision",
            "Critical F1",
            "Kelas 3 Test",
            "Total Sequence",
        ]
    ]
    return round_float_columns(table, digits=6)


def build_cutoff_full_table(cutoff_results: pd.DataFrame) -> pd.DataFrame:
    table = cutoff_results.rename(
        columns={
            "cutoff_label": "Cutoff",
            "start_date": "Start Date",
            "config_label": "Config",
            "time_steps": "Time Steps",
            "loss_mode": "Loss",
            "selection_score": "Selection Score",
            "accuracy": "Accuracy",
            "macro_recall": "Macro Recall",
            "macro_f1": "Macro F1",
            "critical_recall": "Critical Recall",
            "critical_precision": "Critical Precision",
            "critical_f1": "Critical F1",
            "class3_test": "Kelas 3 Test",
        }
    )[
        [
            "Cutoff",
            "Start Date",
            "Config",
            "Time Steps",
            "Loss",
            "Selection Score",
            "Accuracy",
            "Macro Recall",
            "Macro F1",
            "Critical Recall",
            "Critical Precision",
            "Critical F1",
            "Kelas 3 Test",
        ]
    ]
    return round_float_columns(table, digits=6)


def build_time_steps_baseline_table() -> pd.DataFrame:
    time_steps_results = pd.read_csv(TIME_STEPS_SWEEP_CSV_PATH)
    table = time_steps_results.copy()
    table["selection_score"] = (
        0.45 * table["gated_accuracy"]
        + 0.20 * table["gated_macro_f1"]
        + 0.15 * table["gated_macro_recall"]
        + 0.10 * table["gated_critical_recall"]
        + 0.05 * table["gated_critical_precision"]
        + 0.05 * table["gated_critical_f1"]
    )
    table = table.rename(
        columns={
            "time_steps": "Time Steps",
            "selection_score": "Selection Score",
            "gated_accuracy": "Hybrid Accuracy",
            "gated_macro_recall": "Hybrid Macro Recall",
            "gated_macro_f1": "Hybrid Macro F1",
            "gated_critical_recall": "Hybrid Critical Recall",
            "gated_critical_precision": "Hybrid Critical Precision",
            "gated_critical_f1": "Hybrid Critical F1",
            "lstm_accuracy": "LSTM Accuracy",
            "lstm_macro_f1": "LSTM Macro F1",
            "xgb_accuracy": "XGB Accuracy",
            "xgb_macro_f1": "XGB Macro F1",
            "best_xgb_name": "Best XGB",
            "class_2_threshold": "Gate C2",
            "class_3_threshold": "Gate C3",
        }
    )[
        [
            "Time Steps",
            "Selection Score",
            "Hybrid Accuracy",
            "Hybrid Macro Recall",
            "Hybrid Macro F1",
            "Hybrid Critical Recall",
            "Hybrid Critical Precision",
            "Hybrid Critical F1",
            "LSTM Accuracy",
            "LSTM Macro F1",
            "XGB Accuracy",
            "XGB Macro F1",
            "Best XGB",
            "Gate C2",
            "Gate C3",
        ]
    ]
    return round_float_columns(table.sort_values("Time Steps"), digits=6)


def build_time_steps_2005_ce_table(cutoff_results: pd.DataFrame) -> pd.DataFrame:
    table = cutoff_results[
        (cutoff_results["cutoff_label"] == "2005plus")
        & (cutoff_results["loss_mode"] == "cross_entropy")
    ].copy()
    table = table.rename(
        columns={
            "config_label": "Config",
            "time_steps": "Time Steps",
            "selection_score": "Selection Score",
            "accuracy": "Accuracy",
            "macro_recall": "Macro Recall",
            "macro_f1": "Macro F1",
            "critical_recall": "Critical Recall",
            "critical_precision": "Critical Precision",
            "critical_f1": "Critical F1",
        }
    )[
        [
            "Config",
            "Time Steps",
            "Selection Score",
            "Accuracy",
            "Macro Recall",
            "Macro F1",
            "Critical Recall",
            "Critical Precision",
            "Critical F1",
        ]
    ]
    return round_float_columns(table.sort_values("Time Steps"), digits=6)


def build_window_loss_compare(windowed_results: pd.DataFrame) -> pd.DataFrame:
    working = windowed_results.copy()
    working["window_label"] = working["window_label"].map(
        {"2005plus": "2005+", "2010plus": "2010+"}
    )
    best_by_window_loss = (
        working.sort_values("selection_score", ascending=False)
        .groupby(["window_label", "loss_mode"], sort=False)
        .head(1)
        .copy()
    )

    rows: list[dict[str, Any]] = []
    for window_label in ["2005+", "2010+"]:
        ce_row = best_by_window_loss[
            (best_by_window_loss["window_label"] == window_label)
            & (best_by_window_loss["loss_mode"] == "cross_entropy")
        ].iloc[0]
        focal_row = best_by_window_loss[
            (best_by_window_loss["window_label"] == window_label)
            & (best_by_window_loss["loss_mode"] == "focal")
        ].iloc[0]
        rows.append(
            {
                "Window": window_label,
                "Best CE Config": ce_row["time_steps"],
                "CE Selection Score": ce_row["selection_score"],
                "CE Accuracy": ce_row["accuracy"],
                "CE Critical Recall": ce_row["critical_recall"],
                "CE Critical Precision": ce_row["critical_precision"],
                "Best Focal Config": focal_row["time_steps"],
                "Focal Selection Score": focal_row["selection_score"],
                "Focal Accuracy": focal_row["accuracy"],
                "Focal Critical Recall": focal_row["critical_recall"],
                "Focal Critical Precision": focal_row["critical_precision"],
                "Delta Focal-CE": focal_row["selection_score"] - ce_row["selection_score"],
            }
        )
    return round_float_columns(pd.DataFrame(rows), digits=6)


def build_ts3_loss_cutoff_compare(cutoff_results: pd.DataFrame) -> pd.DataFrame:
    working = cutoff_results[cutoff_results["config_label"].isin(["ts3_ce", "ts3_focal"])].copy()

    rows: list[dict[str, Any]] = []
    for cutoff_label in ["2003plus", "2004plus", "2005plus", "2006plus", "2007plus"]:
        ce_row = working[
            (working["cutoff_label"] == cutoff_label)
            & (working["config_label"] == "ts3_ce")
        ].iloc[0]
        focal_row = working[
            (working["cutoff_label"] == cutoff_label)
            & (working["config_label"] == "ts3_focal")
        ].iloc[0]
        rows.append(
            {
                "Cutoff": cutoff_label,
                "CE Selection Score": ce_row["selection_score"],
                "Focal Selection Score": focal_row["selection_score"],
                "Delta Focal-CE": focal_row["selection_score"] - ce_row["selection_score"],
                "CE Accuracy": ce_row["accuracy"],
                "Focal Accuracy": focal_row["accuracy"],
                "CE Critical Recall": ce_row["critical_recall"],
                "Focal Critical Recall": focal_row["critical_recall"],
                "CE Critical Precision": ce_row["critical_precision"],
                "Focal Critical Precision": focal_row["critical_precision"],
            }
        )

    return round_float_columns(pd.DataFrame(rows), digits=6)


def build_family_compare(summary_path: Path, label_suffix: str) -> pd.DataFrame:
    summary = load_json(summary_path)
    rows = [
        {
            "Model Family": f"LSTM only ({label_suffix})",
            "Accuracy": float(summary["metrics_lstm_argmax"]["accuracy"]),
            "Macro Recall": float(summary["metrics_lstm_argmax"]["macro_recall"]),
            "Macro F1": float(summary["metrics_lstm_argmax"]["macro_f1"]),
            "Critical Recall": float(summary["metrics_lstm_argmax"]["critical_recall"]),
            "Critical Precision": float(summary["metrics_lstm_argmax"]["critical_precision"]),
            "Critical F1": float(summary["metrics_lstm_argmax"]["critical_f1"]),
        },
        {
            "Model Family": f"XGBoost only ({label_suffix})",
            "Accuracy": float(summary["metrics_argmax"]["accuracy"]),
            "Macro Recall": float(summary["metrics_argmax"]["macro_recall"]),
            "Macro F1": float(summary["metrics_argmax"]["macro_f1"]),
            "Critical Recall": float(summary["metrics_argmax"]["critical_recall"]),
            "Critical Precision": float(summary["metrics_argmax"]["critical_precision"]),
            "Critical F1": float(summary["metrics_argmax"]["critical_f1"]),
        },
        {
            "Model Family": f"Hybrid gated ({label_suffix})",
            "Accuracy": float(summary["metrics"]["accuracy"]),
            "Macro Recall": float(summary["metrics"]["macro_recall"]),
            "Macro F1": float(summary["metrics"]["macro_f1"]),
            "Critical Recall": float(summary["metrics"]["critical_recall"]),
            "Critical Precision": float(summary["metrics"]["critical_precision"]),
            "Critical F1": float(summary["metrics"]["critical_f1"]),
        },
    ]
    return round_float_columns(pd.DataFrame(rows), digits=6)


def dataframe_output(df: pd.DataFrame) -> dict[str, Any]:
    html = df.to_html(index=False, border=0)
    text = df.to_string(index=False)
    return {
        "output_type": "display_data",
        "data": {
            "text/plain": text,
            "text/html": html,
        },
        "metadata": {},
    }


def markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source,
    }


def code_cell(source: str, execution_count: int | None = None, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": execution_count,
        "source": source,
        "outputs": outputs or [],
    }


def build_notebook() -> dict[str, Any]:
    baseline_summary = load_json(BASELINE_SUMMARY_PATH)
    best_2005_summary = load_json(BEST_2005_SUMMARY_PATH)
    cutoff_results = pd.read_csv(CUTOFF_SEARCH_CSV_PATH)
    windowed_results = pd.read_csv(WINDOWED_SEARCH_CSV_PATH)

    table_model_compare = build_main_model_compare(windowed_results)
    table_cutoff_best = build_cutoff_best_table(cutoff_results)
    table_cutoff_full = build_cutoff_full_table(cutoff_results)
    table_time_steps_baseline = build_time_steps_baseline_table()
    table_time_steps_2005_ce = build_time_steps_2005_ce_table(cutoff_results)
    table_window_loss = build_window_loss_compare(windowed_results)
    table_cutoff_ts3_loss = build_ts3_loss_cutoff_compare(cutoff_results)
    table_family_final = build_family_compare(BEST_2005_SUMMARY_PATH, "Final 2005+")
    table_family_baseline = build_family_compare(BASELINE_SUMMARY_PATH, "Baseline Full Data")

    setup_code = f"""from pathlib import Path
import json
import pandas as pd

ROOT = Path.cwd()
ARTIFACTS_DIR = ROOT / "artifacts"

BASELINE_SUMMARY_PATH = ARTIFACTS_DIR / "operational_backup_before_2005plus_20260705_234502" / "latest_multiclass_training_summary.json"
BEST_2005_SUMMARY_PATH = ARTIFACTS_DIR / "cutoff_2005plus_ts3_focal_20260705_222007" / "training_summary.json"
WINDOWED_SEARCH_CSV_PATH = ARTIFACTS_DIR / "windowed_multiclass_search_20260705_161003" / "search_results.csv"
CUTOFF_SEARCH_CSV_PATH = ARTIFACTS_DIR / "cutoff_around_2005_20260705_202618" / "search_results.csv"
TIME_STEPS_SWEEP_CSV_PATH = ARTIFACTS_DIR / "time_steps_gated_sweep_20260630_202306" / "time_steps_sweep_results.csv"

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def selection_score(metrics: dict):
    return (
        0.45 * float(metrics["accuracy"])
        + 0.20 * float(metrics["macro_f1"])
        + 0.15 * float(metrics["macro_recall"])
        + 0.10 * float(metrics["critical_recall"])
        + 0.05 * float(metrics["critical_precision"])
        + 0.05 * float(metrics["critical_f1"])
    )

def first_test_start_date(summary: dict) -> str:
    first_boundary = next(iter(summary["split_summary"]["district_boundaries"].values()))
    return str(first_boundary["test_start_date"]).replace("T00:00:00", "")

def round_float_columns(df: pd.DataFrame, digits: int = 6) -> pd.DataFrame:
    rounded = df.copy()
    float_columns = rounded.select_dtypes(include=["float", "float32", "float64"]).columns
    for column in float_columns:
        rounded[column] = rounded[column].round(digits)
    return rounded

baseline_summary = load_json(BASELINE_SUMMARY_PATH)
best_2005_summary = load_json(BEST_2005_SUMMARY_PATH)
cutoff_results = pd.read_csv(CUTOFF_SEARCH_CSV_PATH)
windowed_results = pd.read_csv(WINDOWED_SEARCH_CSV_PATH)
time_steps_results = pd.read_csv(TIME_STEPS_SWEEP_CSV_PATH)

table_model_compare = {table_model_compare.to_dict(orient="list")}
table_model_compare = pd.DataFrame(table_model_compare)

table_cutoff_best = {table_cutoff_best.to_dict(orient="list")}
table_cutoff_best = pd.DataFrame(table_cutoff_best)

table_cutoff_full = {table_cutoff_full.to_dict(orient="list")}
table_cutoff_full = pd.DataFrame(table_cutoff_full)

table_time_steps_baseline = {table_time_steps_baseline.to_dict(orient="list")}
table_time_steps_baseline = pd.DataFrame(table_time_steps_baseline)

table_time_steps_2005_ce = {table_time_steps_2005_ce.to_dict(orient="list")}
table_time_steps_2005_ce = pd.DataFrame(table_time_steps_2005_ce)

table_window_loss = {table_window_loss.to_dict(orient="list")}
table_window_loss = pd.DataFrame(table_window_loss)

table_cutoff_ts3_loss = {table_cutoff_ts3_loss.to_dict(orient="list")}
table_cutoff_ts3_loss = pd.DataFrame(table_cutoff_ts3_loss)

table_family_final = {table_family_final.to_dict(orient="list")}
table_family_final = pd.DataFrame(table_family_final)

table_family_baseline = {table_family_baseline.to_dict(orient="list")}
table_family_baseline = pd.DataFrame(table_family_baseline)
"""

    notebook = {
        "cells": [
            markdown_cell(
            """# Analisis Tabel Model Final

Notebook ini merangkum seluruh tabel penting untuk skripsi dalam satu file:

- perbandingan model utama `full-data vs 2005+ vs 2010+`
- hasil sweep cutoff `2003+` sampai `2007+`
- hasil eksperimen `time_steps`
- perbandingan `cross_entropy` vs `focal`
- perbandingan keluarga model `LSTM only vs XGBoost only vs Hybrid gated`

Semua angka diambil dari artefak hasil eksperimen yang sudah ada di folder `artifacts/`.
"""
            ),
            markdown_cell(
            """## Sumber Artefak

- Baseline full-data: `artifacts/operational_backup_before_2005plus_20260705_234502/latest_multiclass_training_summary.json`
- Best 2005+: `artifacts/cutoff_2005plus_ts3_focal_20260705_222007/training_summary.json`
- Best 2010+: diambil dari baris terbaik `window_label=2010plus` pada `artifacts/windowed_multiclass_search_20260705_161003/search_results.csv`
- Sweep cutoff sekitar 2005: `artifacts/cutoff_around_2005_20260705_202618/search_results.csv`
- Sweep window 2005 vs 2010: `artifacts/windowed_multiclass_search_20260705_161003/search_results.csv`
- Sweep time steps baseline: `artifacts/time_steps_gated_sweep_20260630_202306/time_steps_sweep_results.csv`
"""
            ),
            code_cell(setup_code, execution_count=1, outputs=[]),
            markdown_cell("## 1. Perbandingan Model Utama\nTabel ini membandingkan baseline full-data, model terbaik window `2005+`, dan model terbaik window `2010+`."),
            code_cell(
            'table_model_compare',
            execution_count=2,
            outputs=[dataframe_output(table_model_compare)],
            ),
            markdown_cell(
            """Catatan:

- Baseline full-data masih menjadi pembanding utama karena itu model operasional sebelum cutoff diubah.
- Window `2005+` adalah kandidat final yang sedang dipakai untuk web.
- Window `2010+` dipakai untuk membuktikan bahwa memotong data terlalu agresif justru menurunkan performa.
"""
            ),
            markdown_cell("## 2. Sweep Cutoff 2003+ sampai 2007+\nTabel pertama menampilkan konfigurasi terbaik pada setiap cutoff. Tabel kedua menampilkan seluruh kombinasi yang diuji."),
            code_cell(
            'table_cutoff_best',
            execution_count=3,
            outputs=[dataframe_output(table_cutoff_best)],
            ),
            code_cell(
            'table_cutoff_full',
            execution_count=4,
            outputs=[dataframe_output(table_cutoff_full)],
            ),
            markdown_cell(
            """Interpretasi singkat:

- `2005+` muncul sebagai cutoff terbaik secara keseluruhan.
- `2006+` dan `2007+` masih cukup kompetitif, tetapi kalah pada `selection score`.
- `2003+` dan `2004+` punya akurasi lumayan, tetapi performa kelas ekstrem jauh lebih lemah.
"""
            ),
            markdown_cell("## 3. Eksperimen Time Steps\nBagian ini dibagi dua: sweep `time_steps` baseline full-data, lalu perbandingan `time_steps` untuk cutoff `2005+` pada loss `cross_entropy`."),
            code_cell(
            'table_time_steps_baseline',
            execution_count=5,
            outputs=[dataframe_output(table_time_steps_baseline)],
            ),
            code_cell(
            'table_time_steps_2005_ce',
            execution_count=6,
            outputs=[dataframe_output(table_time_steps_2005_ce)],
            ),
            markdown_cell(
            """Interpretasi singkat:

- Pada baseline full-data, perubahan `time_steps` memberi trade-off kuat antara akurasi umum dan kemampuan menangkap kelas ekstrem.
- Pada cutoff `2005+`, `time_steps=3` tetap kompetitif dan menjadi dasar model final ketika dipadukan dengan `focal loss`.
"""
            ),
            markdown_cell("## 4. Cross Entropy vs Focal\nTabel pertama membandingkan `best CE` vs `best focal` pada window `2005+` dan `2010+`. Tabel kedua membandingkan `ts3_ce` vs `ts3_focal` untuk cutoff `2003+` sampai `2007+`."),
            code_cell(
            'table_window_loss',
            execution_count=7,
            outputs=[dataframe_output(table_window_loss)],
            ),
            code_cell(
            'table_cutoff_ts3_loss',
            execution_count=8,
            outputs=[dataframe_output(table_cutoff_ts3_loss)],
            ),
            markdown_cell(
            """Interpretasi singkat:

- `Focal loss` tidak selalu menang di semua cutoff.
- Namun pada cutoff `2005+`, kombinasi `ts3 + focal` memberikan trade-off yang paling kuat dan akhirnya menjadi model final.
- Dengan kata lain, `focal` di sini berguna bukan karena selalu paling tinggi akurasinya, tetapi karena paling seimbang untuk metrik makro dan kelas ekstrem.
"""
            ),
            markdown_cell("## 5. Model Pembanding: LSTM vs XGBoost vs Hybrid\nTabel ini memperlihatkan trade-off antar keluarga model pada model final terpilih dan pada baseline full-data."),
            code_cell(
            'table_family_final',
            execution_count=9,
            outputs=[dataframe_output(table_family_final)],
            ),
            code_cell(
            'table_family_baseline',
            execution_count=10,
            outputs=[dataframe_output(table_family_baseline)],
            ),
            markdown_cell(
            """## 6. Ringkasan Akhir

- Baseline full-data masih berguna sebagai pembanding, tetapi bukan lagi model terbaik.
- Sweep cutoff menunjukkan `2005+` adalah cutoff paling kuat di antara `2003+` sampai `2007+`.
- Sweep loss menunjukkan `focal` membantu ketika dipadukan dengan cutoff `2005+` dan `time_steps=3`.
- Model final operasional yang dipilih untuk web dan skripsi adalah:

`window 2005+ / time_steps 3 / focal / Hybrid BiLSTM + XGBoost gated ensemble`
"""
            ),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.x",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return notebook


def main() -> None:
    notebook = build_notebook()
    NOTEBOOK_PATH.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Notebook berhasil dibuat: {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()
