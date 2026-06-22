from __future__ import annotations

import argparse
import copy
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from tensorflow.keras.models import Model, load_model


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATASET_PATH = ROOT / "Master_Data_Spasial_Jaktim.csv"
TEMPLATE_PATH = DATA_DIR / "east-jakarta-predictions.json"
MODEL_PATH = ROOT / "model_bilstm_jaktim.h5"
XGB_PATH = ROOT / "model_xgboost_jaktim.pkl"
SCALER_PATH = ROOT / "scaler_jaktim.pkl"
FEATURE_COLUMNS_PATH = ROOT / "daftar_kolom_fitur.pkl"
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
TIME_STEPS = 5


@dataclass(frozen=True)
class ModelBundle:
    lstm: Any
    extractor: Model
    xgb: Any
    scaler: Any
    feature_columns: list[str]


def normalize_name(value: str) -> str:
    return "".join((value or "").lower().split())


def serialize_payload(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@lru_cache(maxsize=1)
def load_template_payload() -> dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_model_bundle() -> ModelBundle:
    lstm = load_model(MODEL_PATH, compile=False)
    extractor = Model(inputs=lstm.input, outputs=lstm.get_layer("feature_layer").output)
    xgb = joblib.load(XGB_PATH)
    scaler = joblib.load(SCALER_PATH)
    feature_columns = list(joblib.load(FEATURE_COLUMNS_PATH))
    return ModelBundle(
        lstm=lstm,
        extractor=extractor,
        xgb=xgb,
        scaler=scaler,
        feature_columns=feature_columns,
    )


def load_source_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    return df.dropna().copy()


def probability_to_level(probability: float) -> dict[str, Any]:
    if probability < 0.20:
        return {
            "riskCategory": "Rendah",
            "webgisLevel": 1,
            "webgisColor": "Hijau",
            "webgisLevelLabel": "Level 1: Hijau",
            "webgisDescription": "Aman / Curah Hujan Rendah",
        }

    if probability < 0.50:
        return {
            "riskCategory": "Sedang",
            "webgisLevel": 2,
            "webgisColor": "Kuning",
            "webgisLevelLabel": "Level 2: Kuning",
            "webgisDescription": "Siaga 3 / Potensi Hujan Sedang",
        }

    if probability < 0.80:
        return {
            "riskCategory": "Tinggi",
            "webgisLevel": 3,
            "webgisColor": "Oranye",
            "webgisLevelLabel": "Level 3: Oranye",
            "webgisDescription": "Siaga 2 / Hujan Lebat, Waspada",
        }

    return {
        "riskCategory": "Tinggi",
        "webgisLevel": 4,
        "webgisColor": "Merah",
        "webgisLevelLabel": "Level 4: Merah",
        "webgisDescription": "Siaga 1 / Badai Ekstrem, Awas Genangan!",
    }


def estimate_rainfall_mm(probability: float) -> int:
    if probability < 0.20:
        estimate = 5 + (probability / 0.20) * 25
    elif probability < 0.50:
        estimate = 30 + ((probability - 0.20) / 0.30) * 50
    elif probability < 0.80:
        estimate = 80 + ((probability - 0.50) / 0.30) * 100
    else:
        estimate = 180 + ((probability - 0.80) / 0.20) * 70

    return int(round(min(max(estimate, 5), 250)))


def build_sequence_frame(
    district_frame: pd.DataFrame,
    district_name: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    sequence_frame = district_frame.sort_values("Tanggal").copy()
    sequence_frame["Hujan_3Hari_Kumulatif"] = (
        sequence_frame["Curah Hujan (mm)"].rolling(window=3, min_periods=1).mean()
    )
    sequence_frame["Bulan"] = sequence_frame["Tanggal"].dt.month
    sequence_frame["Bulan_Sin"] = np.sin(2 * np.pi * sequence_frame["Bulan"] / 12)
    sequence_frame["Bulan_Cos"] = np.cos(2 * np.pi * sequence_frame["Bulan"] / 12)

    normalized_name = normalize_name(district_name)
    for feature_name in feature_columns:
        if feature_name.startswith("Kec_"):
            sequence_frame[feature_name] = float(
                normalize_name(feature_name[4:]) == normalized_name
            )

    missing_columns = [name for name in feature_columns if name not in sequence_frame.columns]
    if missing_columns:
        raise KeyError(f"Kolom fitur tidak lengkap untuk inference: {missing_columns}")

    return sequence_frame


def extract_alert_probability(latent_features: np.ndarray, xgb_model: Any) -> float:
    probabilities = xgb_model.predict_proba(latent_features)

    if probabilities.ndim != 2 or probabilities.shape[0] == 0:
        raise ValueError("Output probabilitas XGBoost tidak valid.")

    if probabilities.shape[1] == 1:
        return float(probabilities[0, 0])

    return float(probabilities[0, 1])


def build_district_payload(
    bundle: ModelBundle,
    template_district: dict[str, Any],
    district_frame: pd.DataFrame,
) -> dict[str, Any]:
    district_name = str(district_frame["Kecamatan"].iloc[0])
    sequence_frame = build_sequence_frame(district_frame, district_name, bundle.feature_columns)

    if len(sequence_frame) < TIME_STEPS:
        raise ValueError(
            f"Data {district_name} hanya memiliki {len(sequence_frame)} baris, "
            f"minimal {TIME_STEPS} untuk inference."
        )

    latest_window = sequence_frame.tail(TIME_STEPS).copy()
    scaled_window = bundle.scaler.transform(latest_window[bundle.feature_columns])
    inference_input = np.array([scaled_window], dtype=np.float32)

    latent_features = bundle.extractor.predict(inference_input, verbose=0)
    probability = extract_alert_probability(latent_features, bundle.xgb)
    probability_percent = round(probability * 100, 1)
    level_info = probability_to_level(probability)

    latest_row = sequence_frame.iloc[-1]
    forecast_date = (pd.Timestamp(latest_row["Tanggal"]) + pd.Timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    payload = copy.deepcopy(template_district)
    payload.update(level_info)

    payload["predictedRainfallMm"] = estimate_rainfall_mm(probability)
    payload["riskScore"] = round(probability, 4)
    payload["probabilityWaspada"] = round(probability, 4)
    payload["probabilityWaspadaPercent"] = probability_percent
    payload["forecastLabel"] = f"Prediksi {forecast_date}"
    payload["actualStatusFromNotebookTest"] = ""
    payload["rainfallDisplayNote"] = (
        "Angka curah hujan merupakan estimasi tampilan berbasis probabilitas model "
        "hybrid; backend tidak menghasilkan prediksi mm secara langsung."
    )
    payload["summary"] = (
        f"Backend memproses 5 hari terakhir data {payload['label']} hingga "
        f"{pd.Timestamp(latest_row['Tanggal']).strftime('%Y-%m-%d')} dan menghasilkan "
        f"probabilitas waspada {probability_percent:.1f}% "
        f"({payload['webgisLevelLabel']}: {payload['webgisDescription']})."
    )
    payload["recommendation"] = recommendation_for_level(int(payload["webgisLevel"]))
    payload["latestObservationDate"] = pd.Timestamp(latest_row["Tanggal"]).strftime("%Y-%m-%d")
    payload["latestObservedRainfallMm"] = round(float(latest_row["Curah Hujan (mm)"]), 1)
    payload["recentThreeDayAverageMm"] = round(float(latest_row["Hujan_3Hari_Kumulatif"]), 1)

    return payload


def recommendation_for_level(level: int) -> str:
    if level == 1:
        return "Pertahankan pemantauan rutin dan pemeliharaan preventif."

    if level == 2:
        return "Lakukan monitoring berkala dan pembersihan saluran lokal."

    if level == 3:
        return "Siapkan pemantauan intensif pada saluran dan area rawan genangan."

    return "Aktifkan kesiapsiagaan tinggi dan pantau titik genangan prioritas."


def build_prediction_payload() -> dict[str, Any]:
    template_payload = copy.deepcopy(load_template_payload())
    bundle = load_model_bundle()
    source_df = load_source_dataset()
    districts_by_key = {
        normalize_name(name): frame.copy()
        for name, frame in source_df.groupby("Kecamatan", sort=False)
    }

    generated_districts: list[dict[str, Any]] = []
    for template_district in template_payload.get("districts", []):
        district_key = normalize_name(str(template_district.get("name", "")))
        district_frame = districts_by_key.get(district_key)

        if district_frame is None:
            fallback_payload = copy.deepcopy(template_district)
            fallback_payload["summary"] = (
                "Backend tidak menemukan data historis untuk kecamatan ini, "
                "sehingga payload bawaan dipertahankan."
            )
            generated_districts.append(fallback_payload)
            continue

        generated_districts.append(
            build_district_payload(
                bundle=bundle,
                template_district=template_district,
                district_frame=district_frame,
            )
        )

    now = pd.Timestamp.now(tz=JAKARTA_TZ)
    meta = template_payload.get("meta", {})
    meta.update(
        {
            "datasetId": "jaktim-hybrid-backend-v1",
            "model": "Hybrid Bi-LSTM + XGBoost (backend live inference)",
            "updatedAt": now.isoformat(),
            "refreshInterval": "Setiap permintaan API / saat halaman dimuat",
            "rainfallSource": "Master_Data_Spasial_Jaktim.csv - jendela 5 hari terakhir per kecamatan",
            "drainageSource": "Template WebGIS statis per kecamatan",
            "forecastHorizonDays": 1,
            "modelAccuracyNote": (
                "Probabilitas waspada berasal dari pipeline binary classification. "
                "Gunakan sebagai pendukung visualisasi, bukan peringatan operasional final."
            ),
            "conversionNote": (
                "Backend menghitung probabilitas waspada tiap kecamatan dari data historis "
                "5 hari terakhir, lalu memetakan hasilnya ke skema warna dan ringkasan WebGIS."
            ),
        }
    )

    return {
        "meta": meta,
        "forecastDays": [],
        "districts": generated_districts,
    }


class FloodGISRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/health":
            self.respond_json({"status": "ok"})
            return

        if parsed_path.path == "/api/predictions":
            try:
                payload = build_prediction_payload()
            except Exception as error:  # pragma: no cover - defensive response
                self.respond_json(
                    {
                        "status": "error",
                        "message": "Backend gagal menghitung prediksi.",
                        "detail": str(error),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self.respond_json(payload)
            return

        if parsed_path.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = serialize_payload(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve FloodGIS static files and prediction API.")
    parser.add_argument("--host", default="127.0.0.1", help="Host binding for the local server.")
    parser.add_argument("--port", type=int, default=8000, help="Port binding for the local server.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), FloodGISRequestHandler)
    print(f"FloodGIS backend aktif di http://{args.host}:{args.port}/")
    print(f"Endpoint API prediksi: http://{args.host}:{args.port}/api/predictions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
