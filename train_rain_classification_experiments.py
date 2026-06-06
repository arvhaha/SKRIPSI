from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional dependency in some environments.
    XGBClassifier = None


RAIN_THRESHOLDS = [0.5, 1.0, 5.0, 10.0, 20.0]
CATEGORY_BINS = [-np.inf, 0.5, 20.0, 50.0, 100.0, np.inf]
CATEGORY_LABELS = ["Tidak Hujan", "Ringan", "Sedang", "Lebat", "Sangat Lebat"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eksperimen klasifikasi hujan dari fitur turunan curah hujan."
    )
    parser.add_argument(
        "--cleaned-data",
        default="artifacts/lstm_curah_hujan/curah_hujan_cleaned.csv",
        help="CSV data bersih dari pipeline LSTM.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/rain_classification",
        help="Folder output hasil eksperimen klasifikasi.",
    )
    return parser.parse_args()


def add_grouped_feature(
    df: pd.DataFrame, column_name: str, values: pd.Series | pd.DataFrame
) -> None:
    df[column_name] = values.reset_index(level=0, drop=True).fillna(0.0).to_numpy()


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df = df.sort_values("date").reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["source_bmkg"] = (df["source_type"] == "bmkg_monthly").astype(int)
    df["source_hydro"] = (df["source_type"] == "hydro").astype(int)
    df["rr_log"] = np.log1p(df["rr_mm"].clip(lower=0))
    df["dayofyear"] = df["date"].dt.dayofyear
    df["month"] = df["date"].dt.month

    hydro_df = df[df["source_type"] == "hydro"].copy()
    if not hydro_df.empty:
        for threshold in RAIN_THRESHOLDS:
            hydro_df[f"rain_ge_{threshold}"] = (
                hydro_df["rr_mm"] >= threshold
            ).astype(float)

        climatology_rows: list[dict[str, float]] = []
        for dayofyear in range(1, 367):
            day_distance = np.minimum(
                (hydro_df["dayofyear"] - dayofyear).abs(),
                366 - (hydro_df["dayofyear"] - dayofyear).abs(),
            )
            local_window = hydro_df[day_distance <= 7]
            row: dict[str, float] = {
                "dayofyear": dayofyear,
                "clim_mean_rr_15d": float(local_window["rr_mm"].mean()),
                "clim_median_rr_15d": float(local_window["rr_mm"].median()),
                "clim_p90_rr_15d": float(local_window["rr_mm"].quantile(0.9)),
            }
            for threshold in RAIN_THRESHOLDS:
                row[f"clim_prob_ge_{threshold}_15d"] = float(
                    local_window[f"rain_ge_{threshold}"].mean()
                )
            climatology_rows.append(row)

        df = df.merge(pd.DataFrame(climatology_rows), on="dayofyear", how="left")

        month_climatology = (
            hydro_df.groupby("month")["rr_mm"]
            .agg(
                clim_month_mean="mean",
                clim_month_median="median",
                clim_month_p90=lambda values: values.quantile(0.9),
            )
            .reset_index()
        )
        for threshold in RAIN_THRESHOLDS:
            monthly_probability = (
                hydro_df.groupby("month")
                .apply(
                    lambda group, threshold=threshold: (
                        group["rr_mm"] >= threshold
                    ).mean(),
                    include_groups=False,
                )
                .reset_index(name=f"clim_month_prob_ge_{threshold}")
            )
            month_climatology = month_climatology.merge(
                monthly_probability, on="month", how="left"
            )
        df = df.merge(month_climatology, on="month", how="left")

    grouped = df.groupby("segment_id", group_keys=True)["rr_mm"]
    rain_grouped = df.assign(rain05=(df["rr_mm"] >= 0.5).astype(float)).groupby(
        "segment_id", group_keys=True
    )["rain05"]

    for lag in [1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 30, 45, 60]:
        add_grouped_feature(df, f"lag_{lag}", grouped.shift(lag))

    for window in [3, 5, 7, 10, 14, 21, 30, 45, 60]:
        add_grouped_feature(
            df,
            f"roll_mean_{window}",
            grouped.apply(lambda series: series.shift(1).rolling(window, min_periods=1).mean()),
        )
        add_grouped_feature(
            df,
            f"roll_sum_{window}",
            grouped.apply(lambda series: series.shift(1).rolling(window, min_periods=1).sum()),
        )
        add_grouped_feature(
            df,
            f"roll_max_{window}",
            grouped.apply(lambda series: series.shift(1).rolling(window, min_periods=1).max()),
        )
        add_grouped_feature(
            df,
            f"rain_days_{window}",
            rain_grouped.apply(
                lambda series: series.shift(1).rolling(window, min_periods=1).sum()
            ),
        )

    for window in [7, 14, 30, 60]:
        add_grouped_feature(
            df,
            f"roll_std_{window}",
            grouped.apply(lambda series: series.shift(1).rolling(window, min_periods=2).std()),
        )

    day_of_year = df["date"].dt.dayofyear.astype(float)
    month = df["date"].dt.month.astype(float)
    df["sin_dayofyear"] = np.sin(2 * np.pi * day_of_year / 366.0)
    df["cos_dayofyear"] = np.cos(2 * np.pi * day_of_year / 366.0)
    df["sin_month"] = np.sin(2 * np.pi * month / 12.0)
    df["cos_month"] = np.cos(2 * np.pi * month / 12.0)

    climatology_columns = [
        column
        for column in df.columns
        if column.startswith("clim_")
    ]
    lag_columns = [column for column in df.columns if column.startswith("lag_")]
    rolling_columns = [
        column
        for column in df.columns
        if column.startswith(("roll_", "rain_days_"))
    ]

    feature_columns = [
        "gap_days",
        "source_bmkg",
        "source_hydro",
        "sin_dayofyear",
        "cos_dayofyear",
        "sin_month",
        "cos_month",
        "baseline_prev1",
        "baseline_median30",
    ]
    feature_columns.extend(climatology_columns)
    feature_columns.extend(lag_columns)
    feature_columns.extend(rolling_columns)
    feature_columns = list(dict.fromkeys(feature_columns))
    return df, feature_columns


def split_bmkg(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bmkg_indices = df.index[df["source_type"] == "bmkg_monthly"].to_numpy()
    train_end = int(len(bmkg_indices) * 0.70)
    val_end = int(len(bmkg_indices) * 0.85)
    return bmkg_indices[:train_end], bmkg_indices[train_end:val_end], bmkg_indices[val_end:]


def probability_thresholds(model, X_val: pd.DataFrame) -> np.ndarray | None:
    if not hasattr(model, "predict_proba"):
        return None
    proba = model.predict_proba(X_val)
    if proba.ndim != 2 or proba.shape[1] < 2:
        return None
    return proba[:, 1]


def choose_threshold(
    y_val: np.ndarray, val_scores: np.ndarray | None, strategy: str
) -> float:
    if val_scores is None:
        return 0.5

    best_threshold = 0.5
    best_score = (-1.0, -1.0)
    for threshold in np.arange(0.05, 0.96, 0.05):
        pred = (val_scores >= threshold).astype(int)
        metrics = binary_metrics(y_val, pred)
        if strategy == "balanced_accuracy":
            score = (metrics["balanced_accuracy"], metrics["f1"], metrics["accuracy"])
        elif strategy == "f1":
            score = (metrics["f1"], metrics["balanced_accuracy"], metrics["accuracy"])
        else:
            score = (metrics["accuracy"], metrics["f1"], metrics["balanced_accuracy"])
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
    return best_threshold


def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def model_factories(y_train: np.ndarray) -> dict[str, object]:
    negative = max(int((y_train == 0).sum()), 1)
    positive = max(int((y_train == 1).sum()), 1)
    scale_pos_weight = negative / positive

    models: dict[str, object] = {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=400,
            max_depth=6,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=500,
            max_depth=8,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        ),
        "random_forest_shallow": RandomForestClassifier(
            n_estimators=300,
            max_depth=4,
            min_samples_leaf=6,
            class_weight="balanced",
            random_state=43,
            n_jobs=1,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=120,
            learning_rate=0.03,
            max_depth=2,
            random_state=44,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=8,
            l2_regularization=1.0,
            random_state=45,
        ),
    }
    if XGBClassifier is not None:
        models["xgboost"] = XGBClassifier(
            n_estimators=250,
            max_depth=2,
            learning_rate=0.025,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=3.0,
            reg_alpha=0.5,
            objective="binary:logistic",
            eval_metric="logloss",
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            n_jobs=1,
        )
    return models


def run_binary_experiments(
    df: pd.DataFrame, feature_columns: list[str], output_dir: Path
) -> pd.DataFrame:
    bmkg_train_idx, bmkg_val_idx, bmkg_test_idx = split_bmkg(df)
    hydro_idx = df.index[df["source_type"] == "hydro"].to_numpy()
    training_modes = {
        "bmkg_only": bmkg_train_idx,
        "hydro_plus_bmkg": np.concatenate([hydro_idx, bmkg_train_idx]),
    }

    rows: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    best_model_payload: dict[str, object] | None = None

    for threshold_mm in RAIN_THRESHOLDS:
        df[f"target_rain_{threshold_mm}"] = (df["rr_mm"] >= threshold_mm).astype(int)
        y_val = df.loc[bmkg_val_idx, f"target_rain_{threshold_mm}"].to_numpy()
        y_test = df.loc[bmkg_test_idx, f"target_rain_{threshold_mm}"].to_numpy()

        for mode_name, train_idx in training_modes.items():
            X_train = df.loc[train_idx, feature_columns]
            X_val = df.loc[bmkg_val_idx, feature_columns]
            X_test = df.loc[bmkg_test_idx, feature_columns]
            y_train = df.loc[train_idx, f"target_rain_{threshold_mm}"].to_numpy()

            class_rate = float(y_test.mean())
            majority_pred = np.full_like(y_test, int(class_rate >= 0.5))
            rows.append(
                {
                    "target": f"rain_ge_{threshold_mm:g}mm",
                    "training_mode": mode_name,
                    "model": "majority_baseline",
                    "probability_threshold": np.nan,
                    "positive_rate_test": class_rate,
                    **binary_metrics(y_test, majority_pred),
                }
            )

            for model_name, model in model_factories(y_train).items():
                model.fit(X_train, y_train)
                val_scores = probability_thresholds(model, X_val)

                for selection_strategy in ["accuracy", "balanced_accuracy", "f1"]:
                    best_threshold = choose_threshold(
                        y_val, val_scores, selection_strategy
                    )
                    test_scores = probability_thresholds(model, X_test)
                    if test_scores is None:
                        y_pred = model.predict(X_test)
                    else:
                        y_pred = (test_scores >= best_threshold).astype(int)
                    metrics = binary_metrics(y_test, y_pred)
                    row = {
                        "target": f"rain_ge_{threshold_mm:g}mm",
                        "training_mode": mode_name,
                        "model": model_name,
                        "selection_strategy": selection_strategy,
                        "probability_threshold": best_threshold,
                        "positive_rate_test": class_rate,
                        **metrics,
                    }
                    rows.append(row)

                    if row["target"] == "rain_ge_0.5mm":
                        best_key = (
                            metrics["balanced_accuracy"],
                            metrics["f1"],
                            metrics["accuracy"],
                        )
                        current_best_key = (
                            -1.0,
                            -1.0,
                            -1.0,
                        )
                        if best_model_payload is not None:
                            current_best_key = best_model_payload["score"]
                        if best_key > current_best_key:
                            best_model_payload = {
                                "score": best_key,
                                "model": model,
                                "threshold": best_threshold,
                                "metadata": row,
                                "feature_columns": feature_columns,
                            }

                    prediction_frames.append(
                        pd.DataFrame(
                        {
                            "date": df.loc[bmkg_test_idx, "date"].dt.strftime("%Y-%m-%d"),
                            "threshold_mm": threshold_mm,
                            "training_mode": mode_name,
                            "model": model_name,
                            "selection_strategy": selection_strategy,
                            "actual_rr_mm": df.loc[bmkg_test_idx, "rr_mm"].to_numpy(),
                            "actual": y_test,
                            "predicted": y_pred,
                            "probability": test_scores
                            if test_scores is not None
                            else np.nan,
                        }
                        )
                    )

    summary = pd.DataFrame(rows).sort_values(
        ["accuracy", "f1", "balanced_accuracy"], ascending=False
    )
    summary.to_csv(output_dir / "binary_classification_summary.csv", index=False)
    if prediction_frames:
        pd.concat(prediction_frames, ignore_index=True).to_csv(
            output_dir / "binary_test_predictions.csv", index=False
        )
    if best_model_payload is not None:
        model_path = output_dir / "best_rain_0_5mm_classifier.pkl"
        with model_path.open("wb") as handle:
            pickle.dump(
                {
                    "model": best_model_payload["model"],
                    "probability_threshold": best_model_payload["threshold"],
                    "feature_columns": best_model_payload["feature_columns"],
                    "metadata": best_model_payload["metadata"],
                },
                handle,
            )
        (output_dir / "best_rain_0_5mm_classifier.json").write_text(
            json.dumps(best_model_payload["metadata"], indent=2), encoding="utf-8"
        )
    return summary


def run_category_experiment(
    df: pd.DataFrame, feature_columns: list[str], output_dir: Path
) -> pd.DataFrame:
    bmkg_train_idx, bmkg_val_idx, bmkg_test_idx = split_bmkg(df)
    hydro_idx = df.index[df["source_type"] == "hydro"].to_numpy()
    train_idx = np.concatenate([hydro_idx, bmkg_train_idx])

    df["rain_category_id"] = pd.cut(
        df["rr_mm"],
        bins=CATEGORY_BINS,
        labels=False,
        right=False,
    ).astype(int)

    X_train = df.loc[train_idx, feature_columns]
    X_test = df.loc[bmkg_test_idx, feature_columns]
    y_train = df.loc[train_idx, "rain_category_id"].to_numpy()
    y_test = df.loc[bmkg_test_idx, "rain_category_id"].to_numpy()

    models: dict[str, object] = {
        "random_forest": RandomForestClassifier(
            n_estimators=500,
            max_depth=7,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=500,
            max_depth=9,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        ),
    }
    if XGBClassifier is not None:
        models["xgboost"] = XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.03,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=1,
        )

    rows = []
    for model_name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        rows.append(
            {
                "target": "rain_category_5class",
                "training_mode": "hydro_plus_bmkg",
                "model": model_name,
                "accuracy": float(accuracy_score(y_test, y_pred)),
                "balanced_accuracy": float(balanced_accuracy_score(y_test, y_pred)),
                "macro_f1": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
            }
        )

    summary = pd.DataFrame(rows).sort_values(["accuracy", "macro_f1"], ascending=False)
    summary.to_csv(output_dir / "category_classification_summary.csv", index=False)
    return summary


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.cleaned_data)
    df, feature_columns = build_features(df)
    feature_payload = {"feature_columns": feature_columns}
    (output_dir / "feature_columns.json").write_text(
        json.dumps(feature_payload, indent=2), encoding="utf-8"
    )

    binary_summary = run_binary_experiments(df, feature_columns, output_dir)
    category_summary = run_category_experiment(df, feature_columns, output_dir)

    print("\nTop binary classification results:")
    print(binary_summary.head(15).to_string(index=False))
    print("\nCategory classification results:")
    print(category_summary.to_string(index=False))
    print(f"\nArtifacts saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
