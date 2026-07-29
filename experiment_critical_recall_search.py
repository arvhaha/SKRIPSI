from __future__ import annotations

import argparse
import csv
import gc
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import tensorflow as tf

import retrain_operational_multiclass_model as final_model


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"


SCORE_PROFILES: dict[str, dict[str, float]] = {
    "baseline": {
        "accuracy": 0.45,
        "macro_f1": 0.20,
        "macro_recall": 0.15,
        "critical_recall": 0.10,
        "critical_precision": 0.05,
        "critical_f1": 0.05,
    },
    "critical_balanced": {
        "accuracy": 0.28,
        "macro_f1": 0.18,
        "macro_recall": 0.14,
        "critical_recall": 0.22,
        "critical_precision": 0.08,
        "critical_f1": 0.10,
    },
    "critical_aggressive": {
        "accuracy": 0.18,
        "macro_f1": 0.15,
        "macro_recall": 0.12,
        "critical_recall": 0.30,
        "critical_precision": 0.10,
        "critical_f1": 0.15,
    },
}


SMOTE_PROFILES: dict[str, dict[str, float]] = {
    "baseline": {"class_2_ratio": 0.40, "class_3_ratio": 0.10},
    "boost_c3": {"class_2_ratio": 0.45, "class_3_ratio": 0.18},
    "aggressive_c3": {"class_2_ratio": 0.50, "class_3_ratio": 0.25},
}


GATE_PROFILES: dict[str, dict[str, list[float]]] = {
    "baseline": {
        "class_2_thresholds": [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65],
        "class_3_thresholds": [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65],
        "class_2_margins": [0.00, 0.02, 0.05],
        "class_3_margins": [0.00, 0.02, 0.05],
    },
    "early_warning": {
        "class_2_thresholds": [0.30, 0.35, 0.40, 0.45, 0.50],
        "class_3_thresholds": [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
        "class_2_margins": [0.00, 0.02, 0.05],
        "class_3_margins": [0.00, 0.02, 0.05],
    },
    "very_early_warning": {
        "class_2_thresholds": [0.25, 0.30, 0.35, 0.40, 0.45],
        "class_3_thresholds": [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45],
        "class_2_margins": [0.00, 0.02, 0.05],
        "class_3_margins": [0.00, 0.02, 0.05],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eksperimen terfokus untuk meningkatkan critical recall kelas Lebat/Ekstrem.",
    )
    parser.add_argument("--start-date", default="2005-01-01")
    parser.add_argument("--time-steps", nargs="+", type=int, default=[3])
    parser.add_argument("--loss-modes", nargs="+", default=["focal"])
    parser.add_argument("--focal-gammas", nargs="+", type=float, default=[2.0, 3.0])
    parser.add_argument("--horizons", nargs="+", type=int, default=[1])
    parser.add_argument(
        "--score-profiles",
        nargs="+",
        default=["baseline", "critical_balanced", "critical_aggressive"],
    )
    parser.add_argument(
        "--smote-profiles",
        nargs="+",
        default=["baseline", "boost_c3", "aggressive_c3"],
    )
    parser.add_argument(
        "--gate-profiles",
        nargs="+",
        default=["baseline", "early_warning", "very_early_warning"],
    )
    parser.add_argument("--max-runs", type=int, default=0)
    return parser.parse_args()


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


def build_selection_score_fn(weights: dict[str, float]) -> Callable[[dict[str, Any]], float]:
    def score(metrics: dict[str, Any]) -> float:
        return sum(float(weights[key]) * float(metrics[key]) for key in weights)

    return score


def build_smote_fn(class_2_ratio: float, class_3_ratio: float) -> Callable[[Any], tuple[dict[int, int], dict[int, int], int | None]]:
    def strategy(y_values: Any) -> tuple[dict[int, int], dict[int, int], int | None]:
        labels, counts = final_model.np.unique(y_values, return_counts=True)
        distribution = {int(label): int(count) for label, count in zip(labels, counts)}
        majority_count = max(distribution.values())
        target_class_2 = max(distribution.get(2, 0), int(majority_count * class_2_ratio))
        target_class_3 = max(distribution.get(3, 0), int(majority_count * class_3_ratio))

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

    return strategy


def competition_score(row: dict[str, Any]) -> float:
    return (
        0.35 * float(row["critical_recall"])
        + 0.20 * float(row["critical_f1"])
        + 0.10 * float(row["critical_precision"])
        + 0.15 * float(row["accuracy"])
        + 0.10 * float(row["macro_f1"])
        + 0.10 * float(row["macro_recall"])
    )


def ranking_key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(row["competition_score"]),
        float(row["critical_recall"]),
        float(row["critical_f1"]),
        float(row["accuracy"]),
        float(row["macro_f1"]),
    )


@contextmanager
def patched_experiment_context(
    *,
    score_profile: str,
    smote_profile: str,
    gate_profile: str,
):
    original_model_selection_score = final_model.model_selection_score
    original_partial_smote_strategy = final_model.partial_smote_strategy
    original_class_2_threshold_grid = list(final_model.CLASS_2_THRESHOLD_GRID)
    original_class_3_threshold_grid = list(final_model.CLASS_3_THRESHOLD_GRID)
    original_class_2_margin_grid = list(final_model.CLASS_2_MARGIN_GRID)
    original_class_3_margin_grid = list(final_model.CLASS_3_MARGIN_GRID)

    score_weights = SCORE_PROFILES[score_profile]
    smote_weights = SMOTE_PROFILES[smote_profile]
    gate_values = GATE_PROFILES[gate_profile]

    final_model.model_selection_score = build_selection_score_fn(score_weights)
    final_model.partial_smote_strategy = build_smote_fn(
        class_2_ratio=float(smote_weights["class_2_ratio"]),
        class_3_ratio=float(smote_weights["class_3_ratio"]),
    )
    final_model.CLASS_2_THRESHOLD_GRID = list(gate_values["class_2_thresholds"])
    final_model.CLASS_3_THRESHOLD_GRID = list(gate_values["class_3_thresholds"])
    final_model.CLASS_2_MARGIN_GRID = list(gate_values["class_2_margins"])
    final_model.CLASS_3_MARGIN_GRID = list(gate_values["class_3_margins"])

    try:
        yield
    finally:
        final_model.model_selection_score = original_model_selection_score
        final_model.partial_smote_strategy = original_partial_smote_strategy
        final_model.CLASS_2_THRESHOLD_GRID = original_class_2_threshold_grid
        final_model.CLASS_3_THRESHOLD_GRID = original_class_3_threshold_grid
        final_model.CLASS_2_MARGIN_GRID = original_class_2_margin_grid
        final_model.CLASS_3_MARGIN_GRID = original_class_3_margin_grid


def build_result_row(combo: dict[str, Any], run_result: dict[str, Any]) -> dict[str, Any]:
    summary = run_result["summary"]
    metrics = summary["metrics"]
    row = {
        "horizon_days": int(combo["horizon_days"]),
        "start_date": str(combo["start_date"]),
        "time_steps": int(combo["time_steps"]),
        "loss_mode": str(combo["loss_mode"]),
        "focal_gamma": float(combo["focal_gamma"]) if combo["loss_mode"] == "focal" else None,
        "score_profile": str(combo["score_profile"]),
        "smote_profile": str(combo["smote_profile"]),
        "gate_profile": str(combo["gate_profile"]),
        "selection_score": round(float(final_model.model_selection_score(metrics)), 6),
        "competition_score": round(float(competition_score(metrics)), 6),
        "accuracy": round(float(metrics["accuracy"]), 6),
        "macro_recall": round(float(metrics["macro_recall"]), 6),
        "macro_f1": round(float(metrics["macro_f1"]), 6),
        "critical_recall": round(float(metrics["critical_recall"]), 6),
        "critical_precision": round(float(metrics["critical_precision"]), 6),
        "critical_f1": round(float(metrics["critical_f1"]), 6),
        "best_xgb_name": summary["best_xgb_candidate"]["name"],
        "class_2_threshold": round(float(summary["ensemble_rule"]["class_2_threshold"]), 6),
        "class_3_threshold": round(float(summary["ensemble_rule"]["class_3_threshold"]), 6),
        "class_2_margin": round(float(summary["ensemble_rule"]["class_2_margin"]), 6),
        "class_3_margin": round(float(summary["ensemble_rule"]["class_3_margin"]), 6),
        "sequence_count": int(summary["sequence_count"]),
        "class3_total": int(summary["class_distribution_total"].get("3", 0)),
        "class3_test": int(summary["class_distribution_test"].get("3", 0)),
        "run_dir": str(run_result["run_dir"]),
        "summary_path": str(run_result["summary_path"]),
    }
    return row


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_combinations(args: argparse.Namespace) -> list[dict[str, Any]]:
    combinations: list[dict[str, Any]] = []
    for horizon_days in args.horizons:
        for time_steps in args.time_steps:
            for loss_mode in args.loss_modes:
                gamma_values = args.focal_gammas if str(loss_mode).strip().lower() == "focal" else [0.0]
                for focal_gamma in gamma_values:
                    for score_profile in args.score_profiles:
                        for smote_profile in args.smote_profiles:
                            for gate_profile in args.gate_profiles:
                                combinations.append(
                                    {
                                        "horizon_days": int(horizon_days),
                                        "start_date": str(args.start_date),
                                        "time_steps": int(time_steps),
                                        "loss_mode": str(loss_mode),
                                        "focal_gamma": float(focal_gamma),
                                        "score_profile": str(score_profile),
                                        "smote_profile": str(smote_profile),
                                        "gate_profile": str(gate_profile),
                                    }
                                )
    if int(args.max_runs) > 0:
        return combinations[: int(args.max_runs)]
    return combinations


def main() -> None:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = ARTIFACTS_DIR / f"critical_recall_search_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    combinations = build_combinations(args)
    rows: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []

    print("=" * 88)
    print("CRITICAL RECALL SEARCH")
    print("=" * 88)
    print(f"Jumlah kombinasi: {len(combinations)}")
    print(f"Folder eksperimen: {experiment_dir}")

    for index, combo in enumerate(combinations, start=1):
        print(
            f"\n[{index}/{len(combinations)}] "
            f"H+{combo['horizon_days']} start={combo['start_date']} "
            f"ts={combo['time_steps']} loss={combo['loss_mode']} "
            f"gamma={combo['focal_gamma']} score={combo['score_profile']} "
            f"smote={combo['smote_profile']} gate={combo['gate_profile']}"
        )
        try:
            with patched_experiment_context(
                score_profile=combo["score_profile"],
                smote_profile=combo["smote_profile"],
                gate_profile=combo["gate_profile"],
            ):
                run_result = final_model.run_training(
                    start_date=combo["start_date"],
                    time_steps=int(combo["time_steps"]),
                    horizon_days=int(combo["horizon_days"]),
                    loss_mode=str(combo["loss_mode"]),
                    focal_gamma=float(combo["focal_gamma"]),
                    output_prefix=(
                        "critical_search"
                        f"_h{combo['horizon_days']}"
                        f"_ts{combo['time_steps']}"
                        f"_{combo['loss_mode']}"
                        f"_g{str(combo['focal_gamma']).replace('.', 'p')}"
                        f"_{combo['score_profile']}"
                        f"_{combo['smote_profile']}"
                        f"_{combo['gate_profile']}"
                    ),
                    persist_operational=False,
                    save_models=True,
                    verbose=True,
                )

            row = build_result_row(combo, run_result)
            rows.append(row)
            raw_results.append(
                {
                    "combo": combo,
                    "row": row,
                    "summary": run_result["summary"],
                }
            )
            print(
                json.dumps(
                    {
                        "competition_score": row["competition_score"],
                        "accuracy": row["accuracy"],
                        "macro_f1": row["macro_f1"],
                        "critical_recall": row["critical_recall"],
                        "critical_precision": row["critical_precision"],
                        "critical_f1": row["critical_f1"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception as error:  # pragma: no cover - safety for long runner
            print(f"Run gagal: {combo} -> {error}")
            failed_runs.append({"combo": combo, "error": str(error)})
        finally:
            tf.keras.backend.clear_session()
            gc.collect()

        rows_sorted = sorted(rows, key=ranking_key, reverse=True)
        write_rows_csv(experiment_dir / "search_results.csv", rows_sorted)
        with (experiment_dir / "search_results.json").open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(raw_results), handle, ensure_ascii=False, indent=2)
        with (experiment_dir / "failed_runs.json").open("w", encoding="utf-8") as handle:
            json.dump(to_jsonable(failed_runs), handle, ensure_ascii=False, indent=2)

    best_overall = sorted(rows, key=ranking_key, reverse=True)[0] if rows else None
    best_by_horizon: dict[str, dict[str, Any]] = {}
    for horizon_days in args.horizons:
        horizon_rows = [row for row in rows if int(row["horizon_days"]) == int(horizon_days)]
        if horizon_rows:
            best_by_horizon[str(int(horizon_days))] = sorted(horizon_rows, key=ranking_key, reverse=True)[0]

    with (experiment_dir / "best_overall.json").open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(best_overall), handle, ensure_ascii=False, indent=2)
    with (experiment_dir / "best_by_horizon.json").open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(best_by_horizon), handle, ensure_ascii=False, indent=2)

    print("\nEksperimen selesai.")
    print("Best overall:")
    print(json.dumps(to_jsonable(best_overall), ensure_ascii=False, indent=2))
    print("\nBest by horizon:")
    print(json.dumps(to_jsonable(best_by_horizon), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
