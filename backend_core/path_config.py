from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUNDLED_DATA_DIR = ROOT / "data"

APP_ENV = os.getenv("APP_ENV", "local").strip().lower() or "local"
APP_ENV_LABEL = os.getenv("APP_ENV_LABEL", APP_ENV.upper()).strip() or APP_ENV.upper()
APP_NAME = os.getenv("APP_NAME", "FloodGIS Jakarta Timur").strip() or "FloodGIS Jakarta Timur"

DATASET_FILENAME = "Master_Data_Spasial_Jaktim_1990_sekarang.csv"
PUBLIC_PAYLOAD_FILENAME = "east-jakarta-predictions.json"
TEMPLATE_PAYLOAD_FILENAME = "east-jakarta-template.json"
DISTRICT_GEOJSON_FILENAME = "jkt.geojson"
DRAINAGE_TEMPLATE_FILENAME = "drainase_jaktim_template_backend.csv"
DRAINAGE_CLEAN_FILENAME = "drainase_jaktim_bersih.csv"
DRAINAGE_SUMMARY_FILENAME = "drainase_jaktim_ringkasan_kecamatan.csv"
ADMIN_OVERRIDES_FILENAME = "admin_overrides.json"
ADMIN_HISTORY_FILENAME = "admin_activity_history.json"


def _resolve_runtime_data_dir() -> Path:
    explicit_data_dir = os.getenv("FLOODGIS_DATA_DIR", "").strip()
    if explicit_data_dir:
        return Path(explicit_data_dir)

    explicit_db_path = os.getenv("FLOODGIS_DB_PATH", "").strip()
    if explicit_db_path:
        return Path(explicit_db_path).parent

    if APP_ENV in {"production", "staging"}:
        return Path("/app/data")

    return BUNDLED_DATA_DIR


RUNTIME_DATA_DIR = _resolve_runtime_data_dir()
USES_RUNTIME_DATASET = RUNTIME_DATA_DIR != BUNDLED_DATA_DIR or APP_ENV in {"production", "staging"}

BUNDLED_DATASET_PATH = ROOT / DATASET_FILENAME
BUNDLED_PUBLIC_PAYLOAD_PATH = BUNDLED_DATA_DIR / PUBLIC_PAYLOAD_FILENAME
BUNDLED_TEMPLATE_PAYLOAD_PATH = BUNDLED_DATA_DIR / TEMPLATE_PAYLOAD_FILENAME
BUNDLED_DISTRICT_GEOJSON_PATH = BUNDLED_DATA_DIR / DISTRICT_GEOJSON_FILENAME
BUNDLED_DRAINAGE_TEMPLATE_PATH = BUNDLED_DATA_DIR / DRAINAGE_TEMPLATE_FILENAME
BUNDLED_DRAINAGE_CLEAN_PATH = BUNDLED_DATA_DIR / DRAINAGE_CLEAN_FILENAME
BUNDLED_DRAINAGE_SUMMARY_PATH = BUNDLED_DATA_DIR / DRAINAGE_SUMMARY_FILENAME
FRONTEND_PUBLIC_SNAPSHOT_PATH = ROOT / "frontend-public" / "data" / PUBLIC_PAYLOAD_FILENAME
FRONTEND_PUBLIC_GEOJSON_PATH = ROOT / "frontend-public" / "data" / DISTRICT_GEOJSON_FILENAME

DATA_DIR = RUNTIME_DATA_DIR
DATASET_PATH = (RUNTIME_DATA_DIR / DATASET_FILENAME) if USES_RUNTIME_DATASET else BUNDLED_DATASET_PATH
PUBLIC_PAYLOAD_PATH = RUNTIME_DATA_DIR / PUBLIC_PAYLOAD_FILENAME
TEMPLATE_PAYLOAD_PATH = RUNTIME_DATA_DIR / TEMPLATE_PAYLOAD_FILENAME
DISTRICT_GEOJSON_PATH = RUNTIME_DATA_DIR / DISTRICT_GEOJSON_FILENAME
DRAINAGE_PATH = RUNTIME_DATA_DIR / DRAINAGE_TEMPLATE_FILENAME
ADMIN_OVERRIDES_PATH = RUNTIME_DATA_DIR / ADMIN_OVERRIDES_FILENAME
ADMIN_HISTORY_PATH = RUNTIME_DATA_DIR / ADMIN_HISTORY_FILENAME

