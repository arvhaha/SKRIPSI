from __future__ import annotations

import argparse
import gc
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.models import Model

import retrain_operational_multiclass_model as final_model


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eksperimen sweep time_steps untuk model final gated ensemble 4 class.",
    )
    parser.add_argument(
        "--time-steps",
        nargs="+",
        type=int,
        default=[3, 7, 10],
        help="Daftar time_steps yang mau diuji. Baseline 5 dibaca dari latest summary.",
    )
    return parser.parse_args()


def compact_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "accuracy": round(float(metrics["accuracy"]), 6),
        "macro_precision": round(float(metrics["macro_precision"]), 6),
        "macro_recall": round(float(metrics["macro_recall"]), 6),
        "macro_f1": round(float(metrics["macro_f1"]), 6),
        "critical_precision": round(float(metrics["critical_precision"]), 6),
        "critical_recall": round(float(metrics["critical_recall"]), 6),
        "critical_f1": round(float(metrics["critical_f1"]), 6),
    }


def run_single_experiment(time_steps: int, run_dir: Path) -> dict[str, Any]:
    original_time_steps = final_model.TIME_STEPS
    final_model.TIME_STEPS = time_steps

    try:
        tf.keras.backend.clear_session()
        gc.collect()
        np.random.seed(final_model.SEED)
        tf.random.set_seed(final_model.SEED)

        dataset = final_model.prepare_dataset()
        class_weights = final_model.soft_class_weights(dataset.y_train)

        model_lstm = final_model.build_lstm_model(
            (dataset.X_train.shape[1], dataset.X_train.shape[2]),
            feature_layer_name="feature_layer",
        )
        early_stop = EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True)
        reduce_lr = ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=4,
            min_lr=0.00001,
            verbose=0,
        )

        history = model_lstm.fit(
            dataset.X_train,
            dataset.y_train,
            validation_data=(dataset.X_val, dataset.y_val),
            epochs=55,
            batch_size=final_model.LSTM_CONFIG["batch_size"],
            class_weight=class_weights,
            callbacks=[early_stop, reduce_lr],
            verbose=0,
        )

        feature_extractor = Model(
            inputs=model_lstm.input,
            outputs=model_lstm.get_layer("feature_layer").output,
        )
        X_train_features = feature_extractor.predict(dataset.X_train, verbose=0)
        X_val_features = feature_extractor.predict(dataset.X_val, verbose=0)
        X_test_features = feature_extractor.predict(dataset.X_test, verbose=0)
        lstm_val_probabilities = model_lstm.predict(dataset.X_val, verbose=0)
        lstm_test_probabilities = model_lstm.predict(dataset.X_test, verbose=0)

        xgb_model, best_candidate, best_rule, candidate_rows, smote_summary = final_model.tune_xgb_candidates(
            X_train_features,
            dataset.y_train,
            X_val_features,
            dataset.y_val,
            lstm_val_probabilities,
        )

        xgb_test_probabilities = xgb_model.predict_proba(X_test_features)
        y_pred_lstm = np.argmax(lstm_test_probabilities, axis=1).astype(np.int8)
        metrics_lstm_argmax = final_model.summarize_metrics(
            dataset.y_test,
            y_pred_lstm,
            lstm_test_probabilities,
            final_model.CLASS_NAMES,
        )

        y_pred_xgb = np.argmax(xgb_test_probabilities, axis=1).astype(np.int8)
        metrics_xgb_argmax = final_model.summarize_metrics(
            dataset.y_test,
            y_pred_xgb,
            xgb_test_probabilities,
            final_model.CLASS_NAMES,
        )

        y_pred_gated = final_model.apply_gated_ensemble_rule(
            lstm_test_probabilities,
            xgb_test_probabilities,
            class_2_threshold=float(best_rule["class_2_threshold"]),
            class_3_threshold=float(best_rule["class_3_threshold"]),
            class_2_margin=float(best_rule["class_2_margin"]),
            class_3_margin=float(best_rule["class_3_margin"]),
        )
        operational_probabilities = final_model.compose_operational_probabilities(
            lstm_test_probabilities,
            xgb_test_probabilities,
            y_pred_gated,
        )
        metrics_gated = final_model.summarize_metrics(
            dataset.y_test,
            y_pred_gated,
            operational_probabilities,
            final_model.CLASS_NAMES,
        )

        summary = {
            "time_steps": time_steps,
            "run_timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "feature_count": int(dataset.X_train.shape[2]),
            "sequence_count": int(len(dataset.X_train) + len(dataset.X_val) + len(dataset.X_test)),
            "split_summary": dataset.split_summary,
            "class_distribution_total": dataset.class_distribution_total,
            "class_weights_lstm": {str(label): value for label, value in class_weights.items()},
            "lstm_config": final_model.LSTM_CONFIG,
            "smote_summary": smote_summary,
            "best_xgb_candidate": best_candidate,
            "ensemble_rule": best_rule,
            "metrics_gated": metrics_gated,
            "metrics_lstm_argmax": metrics_lstm_argmax,
            "metrics_xgb_argmax": metrics_xgb_argmax,
            "training_history": {
                key: [float(value) for value in values]
                for key, values in history.history.items()
            },
            "xgb_candidate_rows": candidate_rows,
        }

        summary_path = run_dir / f"time_steps_{time_steps}_summary.json"
        summary_path.write_text(
            json.dumps(final_model.to_jsonable(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result_row = {
            "time_steps": time_steps,
            "summary_path": str(summary_path),
            "gated_accuracy": round(float(metrics_gated["accuracy"]), 6),
            "gated_macro_recall": round(float(metrics_gated["macro_recall"]), 6),
            "gated_macro_f1": round(float(metrics_gated["macro_f1"]), 6),
            "gated_critical_recall": round(float(metrics_gated["critical_recall"]), 6),
            "gated_critical_precision": round(float(metrics_gated["critical_precision"]), 6),
            "gated_critical_f1": round(float(metrics_gated["critical_f1"]), 6),
            "lstm_accuracy": round(float(metrics_lstm_argmax["accuracy"]), 6),
            "lstm_macro_f1": round(float(metrics_lstm_argmax["macro_f1"]), 6),
            "xgb_accuracy": round(float(metrics_xgb_argmax["accuracy"]), 6),
            "xgb_macro_f1": round(float(metrics_xgb_argmax["macro_f1"]), 6),
            "best_xgb_name": str(best_candidate["name"]),
            "class_2_threshold": round(float(best_rule["class_2_threshold"]), 6),
            "class_3_threshold": round(float(best_rule["class_3_threshold"]), 6),
            "class_2_margin": round(float(best_rule["class_2_margin"]), 6),
            "class_3_margin": round(float(best_rule["class_3_margin"]), 6),
        }
        return result_row
    finally:
        final_model.TIME_STEPS = original_time_steps
        tf.keras.backend.clear_session()
        gc.collect()


def load_baseline_row() -> dict[str, Any]:
    summary_path = ARTIFACTS_DIR / "latest_multiclass_training_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "time_steps": int(summary["time_steps"]),
        "summary_path": str(summary_path),
        "gated_accuracy": round(float(summary["metrics"]["accuracy"]), 6),
        "gated_macro_recall": round(float(summary["metrics"]["macro_recall"]), 6),
        "gated_macro_f1": round(float(summary["metrics"]["macro_f1"]), 6),
        "gated_critical_recall": round(float(summary["metrics"]["critical_recall"]), 6),
        "gated_critical_precision": round(float(summary["metrics"]["critical_precision"]), 6),
        "gated_critical_f1": round(float(summary["metrics"]["critical_f1"]), 6),
        "lstm_accuracy": round(float(summary["metrics_lstm_argmax"]["accuracy"]), 6),
        "lstm_macro_f1": round(float(summary["metrics_lstm_argmax"]["macro_f1"]), 6),
        "xgb_accuracy": round(float(summary["metrics_argmax"]["accuracy"]), 6),
        "xgb_macro_f1": round(float(summary["metrics_argmax"]["macro_f1"]), 6),
        "best_xgb_name": str(summary["best_xgb_candidate"]["name"]),
        "class_2_threshold": round(float(summary["ensemble_rule"]["class_2_threshold"]), 6),
        "class_3_threshold": round(float(summary["ensemble_rule"]["class_3_threshold"]), 6),
        "class_2_margin": round(float(summary["ensemble_rule"]["class_2_margin"]), 6),
        "class_3_margin": round(float(summary["ensemble_rule"]["class_3_margin"]), 6),
    }


def main() -> None:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ARTIFACTS_DIR / f"time_steps_gated_sweep_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("SWEEP TIME_STEPS - GATED ENSEMBLE 4 CLASS")
    print("=" * 80)
    print(f"Hasil eksperimen akan disimpan di: {run_dir}")

    rows: list[dict[str, Any]] = [load_baseline_row()]
    print(f"Baseline time_steps=5 dimuat dari latest summary.")

    for time_steps in args.time_steps:
        if time_steps == 5:
            print("Lewati time_steps=5 karena baseline sudah dimuat dari latest summary.")
            continue

        print(f"\nMenjalankan eksperimen time_steps={time_steps}...")
        row = run_single_experiment(time_steps, run_dir)
        rows.append(row)
        print(
            json.dumps(
                {
                    "time_steps": row["time_steps"],
                    "gated_accuracy": row["gated_accuracy"],
                    "gated_macro_f1": row["gated_macro_f1"],
                    "gated_critical_recall": row["gated_critical_recall"],
                    "best_xgb_name": row["best_xgb_name"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    results_df = pd.DataFrame(rows).sort_values(
        by=[
            "gated_accuracy",
            "gated_macro_f1",
            "gated_macro_recall",
            "gated_critical_recall",
            "gated_critical_precision",
        ],
        ascending=False,
    ).reset_index(drop=True)

    csv_path = run_dir / "time_steps_sweep_results.csv"
    json_path = run_dir / "time_steps_sweep_results.json"
    results_df.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps(results_df.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nPeringkat akhir:")
    print(results_df.to_string(index=False))
    print(f"\nCSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
