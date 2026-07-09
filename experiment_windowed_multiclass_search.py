from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import retrain_operational_multiclass_model as final_model


WINDOWS = [
    {"label": "2005plus", "start_date": "2005-01-01"},
    {"label": "2010plus", "start_date": "2010-01-01"},
]
TIME_STEPS_OPTIONS = [3, 5, 7]
LOSS_MODES = ["cross_entropy", "focal"]


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return final_model.to_jsonable(value)


def build_result_row(
    *,
    window_label: str,
    start_date: str,
    time_steps: int,
    loss_mode: str,
    run_result: dict[str, Any],
) -> dict[str, Any]:
    summary = run_result["summary"]
    metrics = summary["metrics"]
    selection_score = final_model.model_selection_score(metrics)

    return {
        "window_label": window_label,
        "start_date": start_date,
        "time_steps": int(time_steps),
        "loss_mode": loss_mode,
        "selection_score": round(float(selection_score), 6),
        "accuracy": round(float(metrics["accuracy"]), 6),
        "macro_recall": round(float(metrics["macro_recall"]), 6),
        "macro_f1": round(float(metrics["macro_f1"]), 6),
        "critical_recall": round(float(metrics["critical_recall"]), 6),
        "critical_precision": round(float(metrics["critical_precision"]), 6),
        "critical_f1": round(float(metrics["critical_f1"]), 6),
        "best_xgb_name": summary["best_xgb_candidate"]["name"],
        "best_gate_class_2_threshold": round(float(summary["ensemble_rule"]["class_2_threshold"]), 6),
        "best_gate_class_3_threshold": round(float(summary["ensemble_rule"]["class_3_threshold"]), 6),
        "best_gate_class_2_margin": round(float(summary["ensemble_rule"]["class_2_margin"]), 6),
        "best_gate_class_3_margin": round(float(summary["ensemble_rule"]["class_3_margin"]), 6),
        "sequence_count": int(summary["sequence_count"]),
        "train_sequences": int(summary["split_summary"]["sequence_counts"]["train"]),
        "val_sequences": int(summary["split_summary"]["sequence_counts"]["val"]),
        "test_sequences": int(summary["split_summary"]["sequence_counts"]["test"]),
        "class3_total": int(summary["class_distribution_total"].get("3", 0)),
        "class3_test": int(summary["class_distribution_test"].get("3", 0)),
        "run_dir": str(run_result["run_dir"]),
        "summary_path": str(run_result["summary_path"]),
    }


def ranking_key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(row["selection_score"]),
        float(row["critical_f1"]),
        float(row["critical_precision"]),
        float(row["macro_f1"]),
        float(row["accuracy"]),
    )


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = final_model.ARTIFACTS_DIR / f"windowed_multiclass_search_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    combinations: list[dict[str, Any]] = []
    for window in WINDOWS:
        for time_steps in TIME_STEPS_OPTIONS:
            for loss_mode in LOSS_MODES:
                combinations.append(
                    {
                        "window_label": window["label"],
                        "start_date": window["start_date"],
                        "time_steps": time_steps,
                        "loss_mode": loss_mode,
                    }
                )

    rows: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []

    print("Mulai eksperimen pencarian model terbaik untuk window 2005+ dan 2010+.")
    print(f"Total kombinasi: {len(combinations)}")
    print(f"Folder ringkasan eksperimen: {experiment_dir}")

    for index, combo in enumerate(combinations, start=1):
        print(
            f"\n[{index}/{len(combinations)}] "
            f"window={combo['window_label']} start={combo['start_date']} "
            f"time_steps={combo['time_steps']} loss={combo['loss_mode']}"
        )
        try:
            run_result = final_model.run_training(
                start_date=combo["start_date"],
                time_steps=int(combo["time_steps"]),
                loss_mode=str(combo["loss_mode"]),
                output_prefix=(
                    f"window_search_{combo['window_label']}_"
                    f"ts{combo['time_steps']}_{combo['loss_mode']}"
                ),
                persist_operational=False,
                save_models=True,
                verbose=True,
            )

            row = build_result_row(
                window_label=str(combo["window_label"]),
                start_date=str(combo["start_date"]),
                time_steps=int(combo["time_steps"]),
                loss_mode=str(combo["loss_mode"]),
                run_result=run_result,
            )
            rows.append(row)
            raw_results.append(
                {
                    "combo": combo,
                    "result_row": row,
                    "run_dir": str(run_result["run_dir"]),
                    "summary_path": str(run_result["summary_path"]),
                    "summary": run_result["summary"],
                }
            )
        except Exception as error:  # pragma: no cover - experiment runner safety
            print(f"Run gagal: {combo} -> {error}")
            failed_runs.append(
                {
                    "combo": combo,
                    "error": str(error),
                }
            )

        rows_sorted = sorted(rows, key=ranking_key, reverse=True)
        write_rows_csv(experiment_dir / "search_results.csv", rows_sorted)
        with (experiment_dir / "search_results.json").open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(raw_results), handle, ensure_ascii=False, indent=2)
        with (experiment_dir / "failed_runs.json").open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(failed_runs), handle, ensure_ascii=False, indent=2)

    best_by_window: dict[str, dict[str, Any]] = {}
    for window in WINDOWS:
        window_rows = [row for row in rows if row["window_label"] == window["label"]]
        if not window_rows:
            continue
        best_by_window[window["label"]] = sorted(window_rows, key=ranking_key, reverse=True)[0]

    with (experiment_dir / "best_by_window.json").open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(best_by_window), handle, ensure_ascii=False, indent=2)

    print("\nEksperimen selesai.")
    print("Model terbaik per window:")
    print(json.dumps(best_by_window, ensure_ascii=False, indent=2))
    print(f"\nCSV hasil lengkap: {experiment_dir / 'search_results.csv'}")
    print(f"JSON hasil lengkap: {experiment_dir / 'search_results.json'}")
    print(f"Ringkasan terbaik per window: {experiment_dir / 'best_by_window.json'}")


if __name__ == "__main__":
    main()
