from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import retrain_operational_multiclass_model as final_model


CUTOFFS = [
    {"label": "2003plus", "start_date": "2003-01-01"},
    {"label": "2004plus", "start_date": "2004-01-01"},
    {"label": "2005plus", "start_date": "2005-01-01"},
    {"label": "2006plus", "start_date": "2006-01-01"},
    {"label": "2007plus", "start_date": "2007-01-01"},
]

CONFIGS = [
    {"config_label": "ts7_ce", "time_steps": 7, "loss_mode": "cross_entropy"},
    {"config_label": "ts5_ce", "time_steps": 5, "loss_mode": "cross_entropy"},
    {"config_label": "ts3_ce", "time_steps": 3, "loss_mode": "cross_entropy"},
    {"config_label": "ts3_focal", "time_steps": 3, "loss_mode": "focal"},
]


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


def build_row(combo: dict[str, Any], run_result: dict[str, Any]) -> dict[str, Any]:
    summary = run_result["summary"]
    metrics = summary["metrics"]
    return {
        "cutoff_label": str(combo["label"]),
        "start_date": str(combo["start_date"]),
        "config_label": str(combo["config_label"]),
        "time_steps": int(combo["time_steps"]),
        "loss_mode": str(combo["loss_mode"]),
        "selection_score": round(float(final_model.model_selection_score(metrics)), 6),
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


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = final_model.ARTIFACTS_DIR / f"cutoff_around_2005_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    combinations: list[dict[str, Any]] = []
    for cutoff in CUTOFFS:
        for config in CONFIGS:
            combinations.append({**cutoff, **config})

    rows: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []

    print("Mulai sweep cutoff sekitar 2005.")
    print(f"Total kombinasi: {len(combinations)}")
    print(f"Folder eksperimen: {experiment_dir}")

    for index, combo in enumerate(combinations, start=1):
        print(
            f"\n[{index}/{len(combinations)}] "
            f"cutoff={combo['label']} start={combo['start_date']} "
            f"config={combo['config_label']} "
            f"time_steps={combo['time_steps']} loss={combo['loss_mode']}"
        )

        try:
            run_result = final_model.run_training(
                start_date=combo["start_date"],
                time_steps=int(combo["time_steps"]),
                loss_mode=str(combo["loss_mode"]),
                output_prefix=(
                    f"cutoff_{combo['label']}_{combo['config_label']}"
                ),
                persist_operational=False,
                save_models=True,
                verbose=True,
            )
            row = build_row(combo, run_result)
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
        except Exception as error:  # pragma: no cover - runner safety
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

    best_by_cutoff: dict[str, dict[str, Any]] = {}
    for cutoff in CUTOFFS:
        cutoff_rows = [row for row in rows if row["cutoff_label"] == cutoff["label"]]
        if not cutoff_rows:
            continue
        best_by_cutoff[cutoff["label"]] = sorted(cutoff_rows, key=ranking_key, reverse=True)[0]

    best_overall = sorted(rows, key=ranking_key, reverse=True)[0] if rows else None

    with (experiment_dir / "best_by_cutoff.json").open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(best_by_cutoff), handle, ensure_ascii=False, indent=2)
    with (experiment_dir / "best_overall.json").open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(best_overall), handle, ensure_ascii=False, indent=2)

    print("\nSweep cutoff selesai.")
    print("Best by cutoff:")
    print(json.dumps(best_by_cutoff, ensure_ascii=False, indent=2))
    print("\nBest overall:")
    print(json.dumps(best_overall, ensure_ascii=False, indent=2))
    print(f"\nCSV: {experiment_dir / 'search_results.csv'}")
    print(f"Best cutoff summary: {experiment_dir / 'best_by_cutoff.json'}")
    print(f"Best overall summary: {experiment_dir / 'best_overall.json'}")


if __name__ == "__main__":
    main()
