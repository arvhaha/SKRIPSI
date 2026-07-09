from __future__ import annotations

import json
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NOTEBOOK_PATH = ROOT / "MODEL_FINAL_SKRIPSI_4CLASS.ipynb"


def markdown_cell(source: str) -> dict:
    normalized = textwrap.dedent(source).strip("\n")
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": normalized.splitlines(keepends=True),
    }


def code_cell(source: str) -> dict:
    normalized = textwrap.dedent(source).strip("\n")
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": normalized.splitlines(keepends=True),
    }


def build_notebook() -> dict:
    cells = [
        markdown_cell(
            """
            # Model Final Skripsi - Hybrid 4 Class Global

            Ini adalah **jalur final utama** yang dipakai untuk skripsi dan integrasi WebGIS.

            Model final:

            - pendekatan: **Hybrid BiLSTM + XGBoost**
            - target: **4 kelas curah hujan BMKG**
            - cakupan: **seluruh Jakarta Timur**
            - fitur spasial: **`Kecamatan` tetap dipakai sebagai fitur dummy**
            - split data: **kronologis per kecamatan**
            - imbalance handling: **class weight + SMOTE parsial di latent feature**
            - mode keputusan final: **gated ensemble**
            - deployment path: **backend membaca artefak dari retrain operasional**

            Notebook ini dibuat supaya kamu punya **satu tempat utama** buat lihat:

            - model final yang dipakai
            - hasil metrik terakhir
            - fitur dan split data
            - kandidat XGBoost yang dipilih
            - confusion matrix
            - source code training yang penting
            - cara rerun model dan refresh backend
            """
        ),
        markdown_cell(
            """
            ## Cell 1 - Import dan Setup
            """
        ),
        code_cell(
            """
            import importlib
            import inspect
            import json
            import subprocess
            import sys
            from pathlib import Path

            import matplotlib.pyplot as plt
            import pandas as pd
            import seaborn as sns
            from IPython.display import Markdown, display

            import retrain_operational_multiclass_model as final_model
            final_model = importlib.reload(final_model)

            sns.set_theme(style="whitegrid", palette="deep")
            plt.rcParams["figure.figsize"] = (10, 5)
            """
        ),
        markdown_cell(
            """
            ## Cell 2 - Path Artefak Final
            """
        ),
        code_cell(
            """
            ROOT = Path(".").resolve()
            SUMMARY_PATH = ROOT / "artifacts" / "latest_multiclass_training_summary.json"
            CONFIG_PATH = ROOT / "operational_multiclass_config.json"
            MODEL_PATH = ROOT / "model_bilstm_4class_jaktim.h5"
            XGB_PATH = ROOT / "model_xgboost_4class_jaktim.pkl"
            SCALER_PATH = ROOT / "scaler_4class_jaktim.pkl"
            FEATURE_PATH = ROOT / "daftar_kolom_fitur_4class.pkl"

            artifact_status_df = pd.DataFrame(
                [
                    {"artifact": "summary_json", "path": str(SUMMARY_PATH), "exists": SUMMARY_PATH.exists()},
                    {"artifact": "config_json", "path": str(CONFIG_PATH), "exists": CONFIG_PATH.exists()},
                    {"artifact": "lstm_model", "path": str(MODEL_PATH), "exists": MODEL_PATH.exists()},
                    {"artifact": "xgb_model", "path": str(XGB_PATH), "exists": XGB_PATH.exists()},
                    {"artifact": "scaler", "path": str(SCALER_PATH), "exists": SCALER_PATH.exists()},
                    {"artifact": "feature_columns", "path": str(FEATURE_PATH), "exists": FEATURE_PATH.exists()},
                ]
            )
            display(artifact_status_df)
            """
        ),
        markdown_cell(
            """
            ## Cell 3 - Identitas Model Final
            """
        ),
        code_cell(
            """
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

            final_identity_df = pd.DataFrame(
                [
                    {
                        "Pendekatan": "Hybrid BiLSTM + XGBoost",
                        "Mode": "Global seluruh Jakarta Timur",
                        "Target": "4 kelas BMKG",
                        "Time Steps": summary["time_steps"],
                        "Feature Count": summary["feature_count"],
                        "Split": summary["split_summary"]["strategy"],
                        "Kecamatan Sebagai Fitur": "Ya",
                        "Ensemble Mode": config.get("ensemble_mode", "xgb_extreme_threshold"),
                        "Gate Aktif": config.get("ensemble_rule", {}).get("enabled", False),
                    }
                ]
            )
            display(final_identity_df)
            """
        ),
        markdown_cell(
            """
            ## Cell 4 - Kenapa Ini Yang Jadi Final
            """
        ),
        code_cell(
            """
            reasons = [
                "Model no_kecamatan turun lebih jauh dan gagal menangkap kelas ekstrem.",
                "Model regression tidak konsisten untuk kelas hujan lebat/ekstrem.",
                "Model two-stage tidak mengungguli model 4 class langsung.",
                "Model global 4 class paling masuk akal untuk tujuan skripsi dan jalur WebGIS.",
                "Mode gated ensemble dipilih karena menjaga akurasi lebih baik daripada hybrid XGBoost penuh, tanpa membuang total kelas ekstrem seperti LSTM murni.",
            ]

            display(Markdown("\\n".join([f"- {reason}" for reason in reasons])))
            """
        ),
        markdown_cell(
            """
            ## Cell 5 - Fitur, Split, dan Distribusi Kelas
            """
        ),
        code_cell(
            """
            display(pd.DataFrame({"feature": summary["feature_columns"]}))

            split_df = pd.DataFrame([summary["split_summary"]])
            display(split_df[["strategy", "train_ratio", "val_ratio", "time_steps"]])

            distribution_df = pd.DataFrame(
                [
                    {"split": "total", **summary["class_distribution_total"]},
                    {"split": "train", **summary["class_distribution_train"]},
                    {"split": "val", **summary["class_distribution_val"]},
                    {"split": "test", **summary["class_distribution_test"]},
                ]
            ).fillna(0)
            display(distribution_df)
            """
        ),
        markdown_cell(
            """
            ## Cell 6 - Konfigurasi Training Final
            """
        ),
        code_cell(
            """
            print("LSTM config")
            display(pd.DataFrame([summary["lstm_config"]]))

            print("\\nClass weights LSTM")
            display(pd.DataFrame([summary["class_weights_lstm"]]))

            print("\\nSMOTE summary")
            display(pd.DataFrame([summary["smote_summary"]]))

            print("\\nEnsemble rule final")
            display(pd.DataFrame([summary["ensemble_rule"]]))
            """
        ),
        markdown_cell(
            """
            ## Cell 7 - Kandidat XGBoost dan Gate Terpilih
            """
        ),
        code_cell(
            """
            candidates_df = pd.DataFrame(
                [
                    {
                        "name": row["name"],
                        "selection_score": row["selection_score"],
                        "gated_val_acc": row["val_metrics_after_rule"]["accuracy"],
                        "gated_val_macro_f1": row["val_metrics_after_rule"]["macro_f1"],
                        "lstm_val_acc": row["val_metrics_lstm_argmax"]["accuracy"],
                        "xgb_val_acc": row["val_metrics_argmax"]["accuracy"],
                        "gated_val_critical_recall": row["val_metrics_after_rule"]["critical_recall"],
                    }
                    for row in summary["xgb_candidate_rows"]
                ]
            ).sort_values(
                by=["selection_score", "gated_val_acc", "gated_val_macro_f1"],
                ascending=False,
            )
            display(candidates_df)

            print("\\nBest XGBoost candidate")
            display(
                pd.DataFrame(
                    [
                        {
                            "name": summary["best_xgb_candidate"]["name"],
                            "selection_score": summary["best_xgb_candidate"]["selection_score"],
                            "gated_val_acc": summary["best_xgb_candidate"]["val_metrics_after_rule"]["accuracy"],
                            "gated_val_macro_f1": summary["best_xgb_candidate"]["val_metrics_after_rule"]["macro_f1"],
                            "lstm_val_acc": summary["best_xgb_candidate"]["val_metrics_lstm_argmax"]["accuracy"],
                            "xgb_val_acc": summary["best_xgb_candidate"]["val_metrics_argmax"]["accuracy"],
                        }
                    ]
                )
            )
            """
        ),
        markdown_cell(
            """
            ## Cell 8 - Metrik Final dan Pembanding Mode Prediksi
            """
        ),
        code_cell(
            """
            metrics_compare_df = pd.DataFrame(
                [
                    {
                        "stage": "final_gated_ensemble",
                        "accuracy": summary["metrics"]["accuracy"],
                        "macro_precision": summary["metrics"]["macro_precision"],
                        "macro_recall": summary["metrics"]["macro_recall"],
                        "macro_f1": summary["metrics"]["macro_f1"],
                        "critical_precision": summary["metrics"]["critical_precision"],
                        "critical_recall": summary["metrics"]["critical_recall"],
                        "critical_f1": summary["metrics"]["critical_f1"],
                    },
                    {
                        "stage": "lstm_argmax_only",
                        "accuracy": summary["metrics_lstm_argmax"]["accuracy"],
                        "macro_precision": summary["metrics_lstm_argmax"]["macro_precision"],
                        "macro_recall": summary["metrics_lstm_argmax"]["macro_recall"],
                        "macro_f1": summary["metrics_lstm_argmax"]["macro_f1"],
                        "critical_precision": summary["metrics_lstm_argmax"]["critical_precision"],
                        "critical_recall": summary["metrics_lstm_argmax"]["critical_recall"],
                        "critical_f1": summary["metrics_lstm_argmax"]["critical_f1"],
                    },
                    {
                        "stage": "xgb_argmax_only",
                        "accuracy": summary["metrics_argmax"]["accuracy"],
                        "macro_precision": summary["metrics_argmax"]["macro_precision"],
                        "macro_recall": summary["metrics_argmax"]["macro_recall"],
                        "macro_f1": summary["metrics_argmax"]["macro_f1"],
                        "critical_precision": summary["metrics_argmax"]["critical_precision"],
                        "critical_recall": summary["metrics_argmax"]["critical_recall"],
                        "critical_f1": summary["metrics_argmax"]["critical_f1"],
                    },
                ]
            )
            display(metrics_compare_df)
            """
        ),
        markdown_cell(
            """
            ## Cell 9 - Interpretasi Trade-off
            """
        ),
        code_cell(
            """
            tradeoff_notes = [
                "Gated ensemble adalah model final yang dipakai di backend.",
                "LSTM-only biasanya memberi accuracy lebih tinggi, tetapi bisa gagal total di kelas ekstrem.",
                "XGBoost-only lebih sensitif ke kelas ekstrem, tetapi accuracy total cenderung turun.",
                "Gated ensemble dipilih sebagai kompromi: accuracy tetap naik dari hybrid lama, sambil menjaga deteksi kelas ekstrem tetap hidup.",
            ]

            display(Markdown("\\n".join([f"- {note}" for note in tradeoff_notes])))
            """
        ),
        markdown_cell(
            """
            ## Cell 10 - Confusion Matrix Final
            """
        ),
        code_cell(
            """
            confusion_df = pd.DataFrame(
                summary["metrics"]["confusion_matrix"],
                index=final_model.CLASS_NAMES,
                columns=final_model.CLASS_NAMES,
            )
            display(confusion_df)

            plt.figure(figsize=(8, 6))
            sns.heatmap(confusion_df, annot=True, fmt="d", cmap="Blues")
            plt.title("Confusion Matrix - Model Final 4 Class")
            plt.xlabel("Predicted")
            plt.ylabel("Actual")
            plt.tight_layout()
            plt.show()
            """
        ),
        markdown_cell(
            """
            ## Cell 11 - Kurva Training LSTM
            """
        ),
        code_cell(
            """
            history_df = pd.DataFrame(summary["training_history"])

            fig, axes = plt.subplots(1, 2, figsize=(12, 4))
            axes[0].plot(history_df.index + 1, history_df["loss"], label="train_loss")
            axes[0].plot(history_df.index + 1, history_df["val_loss"], label="val_loss")
            axes[0].set_title("Loss History")
            axes[0].set_xlabel("Epoch")
            axes[0].legend()

            axes[1].plot(history_df.index + 1, history_df["accuracy"], label="train_acc")
            axes[1].plot(history_df.index + 1, history_df["val_accuracy"], label="val_acc")
            axes[1].set_title("Accuracy History")
            axes[1].set_xlabel("Epoch")
            axes[1].legend()

            plt.tight_layout()
            plt.show()
            """
        ),
        markdown_cell(
            """
            ## Cell 12 - Source Code Pembentukan Data
            """
        ),
        code_cell(
            """
            print(inspect.getsource(final_model.prepare_feature_frame))
            print(inspect.getsource(final_model.prepare_dataset))
            """
        ),
        markdown_cell(
            """
            ## Cell 13 - Source Code Model dan Balancing
            """
        ),
        code_cell(
            """
            print(inspect.getsource(final_model.build_lstm_model))
            print(inspect.getsource(final_model.soft_class_weights))
            print(inspect.getsource(final_model.partial_smote_strategy))
            print(inspect.getsource(final_model.apply_manual_smote))
            print(inspect.getsource(final_model.apply_gated_ensemble_rule))
            print(inspect.getsource(final_model.compose_operational_probabilities))
            """
        ),
        markdown_cell(
            """
            ## Cell 14 - Source Code Seleksi XGBoost dan Tuning Gate
            """
        ),
        code_cell(
            """
            print(inspect.getsource(final_model.tune_gated_ensemble_rule))
            print(inspect.getsource(final_model.tune_xgb_candidates))
            """
        ),
        markdown_cell(
            """
            ## Cell 15 - Source Code Main Training Final
            """
        ),
        code_cell(
            """
            print(inspect.getsource(final_model.main))
            """
        ),
        markdown_cell(
            """
            ## Cell 16 - Cara Rerun Model Final

            Jalankan cell ini hanya kalau memang mau retrain ulang.
            """
        ),
        code_cell(
            """
            JALANKAN_RETRAIN = False

            if JALANKAN_RETRAIN:
                result = subprocess.run(
                    [sys.executable, "retrain_operational_multiclass_model.py"],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                print(result.stdout)
            else:
                print("Retrain dimatikan. Ubah JALANKAN_RETRAIN = True kalau mau menjalankan ulang.")
            """
        ),
        markdown_cell(
            """
            ## Cell 17 - Cara Refresh Output Backend WebGIS
            """
        ),
        code_cell(
            """
            print("Perintah terminal yang dipakai:")
            print("python retrain_operational_multiclass_model.py")
            print("python webgis_backend.py --export-static-json --no-serve")
            """
        ),
        markdown_cell(
            """
            ## Cell 18 - Kalimat Singkat Buat Sidang

            Kalau mau jelasin cepat:

            - model final yang digunakan adalah **Hybrid BiLSTM + XGBoost dengan gated ensemble**
            - targetnya **4 kelas curah hujan BMKG**
            - data diproses secara **kronologis per kecamatan**
            - fitur lokasi **tetap dipakai** karena eksperimen tanpa fitur kecamatan justru menurunkan performa
            - LSTM dipakai sebagai prediksi dasar, lalu XGBoost hanya mengoreksi ke kelas lebih tinggi saat sinyalnya cukup kuat
            - hasil model kemudian dihubungkan ke backend WebGIS melalui artefak operasional
            """
        ),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.11",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    notebook = build_notebook()
    NOTEBOOK_PATH.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Notebook berhasil dibuat: {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()
