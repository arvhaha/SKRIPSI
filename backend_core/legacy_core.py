from __future__ import annotations

import copy
import json
import os
import secrets
from base64 import b64decode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from tensorflow.keras.models import Model, load_model
from backend_core.sqlite_store import (
    append_admin_history_entry as sqlite_append_admin_history_entry,
    get_latest_publication_snapshot,
    get_sqlite_db_path,
    insert_publication_snapshot,
    insert_prediction_run,
    load_admin_history_state as sqlite_load_admin_history_state,
    load_admin_overrides_state as sqlite_load_admin_overrides_state,
    replace_admin_history_state,
    replace_admin_overrides_state,
)


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATASET_PATH = ROOT / "Master_Data_Spasial_Jaktim_1990_sekarang.csv"
PUBLIC_PAYLOAD_PATH = DATA_DIR / "east-jakarta-predictions.json"
TEMPLATE_PAYLOAD_PATH = DATA_DIR / "east-jakarta-template.json"
DISTRICT_GEOJSON_PATH = DATA_DIR / "jkt.geojson"
DRAINAGE_PATH = DATA_DIR / "drainase_jaktim_template_backend.csv"
ADMIN_OVERRIDES_PATH = DATA_DIR / "admin_overrides.json"
ADMIN_HISTORY_PATH = DATA_DIR / "admin_activity_history.json"
SQLITE_DB_PATH = get_sqlite_db_path()
MODEL_PATH = ROOT / "model_bilstm_4class_jaktim.h5"
XGB_PATH = ROOT / "model_xgboost_4class_jaktim.pkl"
SCALER_PATH = ROOT / "scaler_4class_jaktim.pkl"
FEATURE_COLUMNS_PATH = ROOT / "daftar_kolom_fitur_4class.pkl"
MODEL_CONFIG_PATH = ROOT / "operational_multiclass_config.json"
LATEST_MULTICLASS_SUMMARY_PATH = ROOT / "artifacts" / "latest_multiclass_training_summary.json"
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
FIXED_NOW_ENV_KEYS = ("FLOODGIS_FIXED_NOW", "FLOODGIS_REFERENCE_NOW")
DEFAULT_TIME_STEPS = 5
CLASS_LABELS = [
    "Cerah (<5 mm)",
    "Hujan Ringan (5-20 mm)",
    "Hujan Sedang (20-50 mm)",
    "Hujan Lebat/Ekstrem (>=50 mm)",
]
CLASS_RANGE_LABELS = ["<5 mm", "5-20 mm", "20-50 mm", ">=50 mm"]
CLASS_SEVERITY_SCORES = [0.05, 0.35, 0.65, 0.95]
APP_NAME = os.getenv("APP_NAME", "FloodGIS Jakarta Timur").strip() or "FloodGIS Jakarta Timur"
APP_ENV = os.getenv("APP_ENV", "local").strip().lower() or "local"
APP_ENV_LABEL = os.getenv("APP_ENV_LABEL", APP_ENV.upper()).strip() or APP_ENV.upper()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").strip()
ADMIN_OVERRIDE_SOURCE_NAME = "Input admin FloodGIS"
ADMIN_OVERRIDE_CONFIDENCE_LABEL = "Override admin"
ADMIN_OVERRIDE_CONFIDENCE_SCORE = 60.0
ADMIN_HISTORY_LIMIT = 40
ALLOWED_DRAINAGE_CONDITIONS = ("Baik", "Sedang", "Buruk")
CORS_ALLOWED_ORIGINS = tuple(
    origin
    for origin in (
        normalize_origin
        for normalize_origin in (
            item.strip()
            for item in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        )
    )
    if origin
)


@dataclass(frozen=True)
class ModelBundle:
    lstm: Any
    extractor: Model
    xgb: Any
    scaler: Any
    feature_columns: list[str]
    time_steps: int
    ensemble_mode: str
    ensemble_rule: dict[str, Any]
    decision_rule: dict[str, Any]


@dataclass(frozen=True)
class DrainageProfile:
    condition: str
    score: float | None
    confidence_label: str
    confidence_score: float
    source_type: str
    source_name: str
    note: str
    manual_condition: str | None
    manual_score: float | None
    suggested_condition: str | None
    suggested_score: float | None


def normalize_name(value: str) -> str:
    return "".join((value or "").lower().split())


def normalize_template_text(value: Any) -> str:
    return str(value or "").strip()


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def is_blank_value(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""


def condition_to_default_score(condition: str | None) -> float | None:
    mapping = {
        "Baik": 30.0,
        "Sedang": 50.0,
        "Buruk": 70.0,
    }
    return mapping.get((condition or "").strip())


def score_to_condition(score: float | None) -> str:
    if score is None:
        return "Tidak diketahui"
    if score >= 67:
        return "Buruk"
    if score >= 34:
        return "Sedang"
    return "Baik"


def confidence_weight(label: str, score: float) -> float:
    caps = {
        "Tinggi": 1.0,
        "Sedang": 0.75,
        "Rendah": 0.35,
        "Manual estimasi": 0.45,
        "Override admin": 0.6,
        "Tidak tersedia": 0.0,
    }
    base_weight = clamp(score / 100.0)
    return min(base_weight, caps.get(label, base_weight))


def serialize_payload(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_clean_template_payload(source_payload: dict[str, Any]) -> dict[str, Any]:
    template_districts: list[dict[str, str]] = []
    seen_districts: set[str] = set()

    for district in source_payload.get("districts", []):
        district_name = normalize_template_text(district.get("name"))
        if not district_name:
            continue

        district_key = normalize_name(district_name)
        if district_key in seen_districts:
            continue

        district_label = normalize_template_text(district.get("label")) or district_name.title()
        template_districts.append(
            {
                "name": district_name,
                "label": district_label,
            }
        )
        seen_districts.add(district_key)

    return {
        "meta": {
            "appName": APP_NAME,
            "templateType": "district_seed",
            "districtCount": len(template_districts),
        },
        "forecastDays": [],
        "districts": template_districts,
    }


def normalize_origin(value: str | None) -> str:
    return str(value or "").strip().rstrip("/")


def get_allowed_cors_origins() -> tuple[str, ...]:
    if CORS_ALLOWED_ORIGINS:
        return CORS_ALLOWED_ORIGINS

    if FRONTEND_ORIGIN:
        return (normalize_origin(FRONTEND_ORIGIN),)

    return ()


def resolve_cors_allow_origin(request_origin: str | None) -> str | None:
    normalized_origin = normalize_origin(request_origin)
    if not normalized_origin:
        return None

    allowed_origins = get_allowed_cors_origins()
    if not allowed_origins:
        return normalized_origin

    if "*" in allowed_origins:
        return "*"

    if normalized_origin in allowed_origins:
        return normalized_origin

    return None


def is_staging_environment() -> bool:
    return APP_ENV == "staging"


def is_admin_auth_configured() -> bool:
    return bool(ADMIN_USERNAME) and bool(ADMIN_PASSWORD)


def is_admin_auth_misconfigured() -> bool:
    return bool(ADMIN_USERNAME) != bool(ADMIN_PASSWORD)


def is_admin_page_locked() -> bool:
    if is_admin_auth_misconfigured():
        return True
    return APP_ENV == "production" and not is_admin_auth_configured()


def is_protected_admin_html_path(path: str) -> bool:
    normalized_path = (path or "").strip().lower()
    return normalized_path.startswith("/admin") and normalized_path.endswith(".html")


def validate_admin_basic_auth_header(header_value: str | None) -> bool:
    if not is_admin_auth_configured():
        return False

    if not header_value or not header_value.startswith("Basic "):
        return False

    try:
        decoded_value = b64decode(header_value[6:].strip()).decode("utf-8")
    except (BinasciiError, UnicodeDecodeError):
        return False

    username, separator, password = decoded_value.partition(":")
    if separator != ":":
        return False

    return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(
        password, ADMIN_PASSWORD
    )


def load_template_payload() -> dict[str, Any]:
    candidate_paths = (TEMPLATE_PAYLOAD_PATH, PUBLIC_PAYLOAD_PATH)

    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue

        try:
            source_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        template_payload = build_clean_template_payload(source_payload)
        if not template_payload.get("districts"):
            continue

        if candidate_path != TEMPLATE_PAYLOAD_PATH:
            try:
                TEMPLATE_PAYLOAD_PATH.write_bytes(serialize_payload(template_payload))
            except OSError:
                pass

        return template_payload

    raise FileNotFoundError(
        "Template distrik FloodGIS tidak ditemukan. "
        "Pastikan east-jakarta-template.json atau east-jakarta-predictions.json tersedia."
    )


@lru_cache(maxsize=1)
def load_geojson_payload() -> dict[str, Any]:
    return json.loads(DISTRICT_GEOJSON_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_operational_model_config() -> dict[str, Any]:
    default_config = {
        "time_steps": DEFAULT_TIME_STEPS,
        "ensemble_mode": "xgb_extreme_threshold",
        "ensemble_rule": {
            "enabled": False,
            "class_2_threshold": 1.0,
            "class_3_threshold": 1.0,
            "class_2_margin": 0.0,
            "class_3_margin": 0.0,
        },
        "decision_rule": {
            "enabled": False,
            "extreme_threshold": 0.0,
            "extreme_margin": 0.0,
        },
    }

    if not MODEL_CONFIG_PATH.exists():
        return default_config

    try:
        loaded = json.loads(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config

    decision_rule = loaded.get("decision_rule", {})
    ensemble_rule = loaded.get("ensemble_rule", {})
    return {
        "time_steps": int(loaded.get("time_steps", DEFAULT_TIME_STEPS)),
        "ensemble_mode": str(loaded.get("ensemble_mode", "xgb_extreme_threshold")),
        "ensemble_rule": {
            "enabled": bool(ensemble_rule.get("enabled", False)),
            "class_2_threshold": float(ensemble_rule.get("class_2_threshold", 1.0)),
            "class_3_threshold": float(ensemble_rule.get("class_3_threshold", 1.0)),
            "class_2_margin": float(ensemble_rule.get("class_2_margin", 0.0)),
            "class_3_margin": float(ensemble_rule.get("class_3_margin", 0.0)),
            "description": str(ensemble_rule.get("description", "")),
            "selection_score": float(ensemble_rule.get("selection_score", 0.0)),
        },
        "decision_rule": {
            "enabled": bool(decision_rule.get("enabled", False)),
            "extreme_threshold": float(decision_rule.get("extreme_threshold", 0.0)),
            "extreme_margin": float(decision_rule.get("extreme_margin", 0.0)),
            "description": str(decision_rule.get("description", "")),
        },
    }


@lru_cache(maxsize=1)
def load_model_bundle() -> ModelBundle:
    from backend_core.prediction_logic import load_model_bundle as _impl

    return _impl()


@lru_cache(maxsize=1)
def load_latest_multiclass_summary() -> dict[str, Any] | None:
    if not LATEST_MULTICLASS_SUMMARY_PATH.exists():
        return None
    try:
        return json.loads(LATEST_MULTICLASS_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@lru_cache(maxsize=1)
def load_drainage_profiles() -> dict[str, DrainageProfile]:
    from backend_core.drainage_logic import load_drainage_profiles as _impl

    return _impl()


def load_source_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH, sep=";")
    df["Tanggal"] = pd.to_datetime(df["Tanggal"], format="%d/%m/%Y", dayfirst=True)
    return df.dropna().copy()


def parse_optional_timestamp(value: Any) -> pd.Timestamp | None:
    if is_blank_value(value):
        return None

    try:
        return pd.Timestamp(value)
    except (TypeError, ValueError):
        return None


def current_jakarta_timestamp() -> pd.Timestamp:
    for env_key in FIXED_NOW_ENV_KEYS:
        raw_value = str(os.getenv(env_key, "")).strip()
        if not raw_value:
            continue

        try:
            fixed_timestamp = pd.Timestamp(raw_value)
        except (TypeError, ValueError):
            continue

        if fixed_timestamp.tzinfo is None:
            return fixed_timestamp.tz_localize(JAKARTA_TZ)
        return fixed_timestamp.tz_convert(JAKARTA_TZ)

    return pd.Timestamp.now(tz=JAKARTA_TZ)


def normalize_optional_text(value: Any) -> str:
    return str(value or "").strip()


def sanitize_override_condition(value: Any) -> str | None:
    normalized_value = normalize_optional_text(value)
    if not normalized_value:
        return None

    for allowed_value in ALLOWED_DRAINAGE_CONDITIONS:
        if normalized_value.casefold() == allowed_value.casefold():
            return allowed_value

    raise ValueError(
        "Kondisi drainase override tidak valid. Gunakan salah satu: "
        + ", ".join(ALLOWED_DRAINAGE_CONDITIONS)
    )


def sanitize_field_note(value: Any) -> str:
    normalized_value = normalize_optional_text(value)
    return normalized_value[:800]


def _load_admin_overrides_json_state() -> dict[str, Any]:
    default_state = {"updatedAt": None, "districts": {}}
    if not ADMIN_OVERRIDES_PATH.exists():
        return default_state

    try:
        loaded_state = json.loads(ADMIN_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_state

    normalized_districts: dict[str, dict[str, Any]] = {}
    for key, entry in dict(loaded_state.get("districts", {})).items():
        if not isinstance(entry, dict):
            continue

        district_name = normalize_optional_text(entry.get("districtName") or key)
        if not district_name:
            continue

        normalized_key = normalize_name(district_name)
        try:
            drainage_condition = sanitize_override_condition(entry.get("drainageCondition"))
        except ValueError:
            drainage_condition = None

        updated_at = normalize_optional_text(entry.get("updatedAt"))

        if not drainage_condition:
            continue

        normalized_districts[normalized_key] = {
            "districtName": district_name,
            "drainageCondition": drainage_condition,
            "updatedAt": updated_at,
        }

    return {
        "updatedAt": loaded_state.get("updatedAt"),
        "districts": normalized_districts,
    }


def _write_admin_overrides_json_state(state: dict[str, Any]) -> None:
    serializable_districts: dict[str, Any] = {}
    districts = dict(state.get("districts", {}))

    for normalized_key, entry in sorted(
        districts.items(),
        key=lambda item: str(item[1].get("districtName", item[0])),
    ):
        serializable_districts[normalized_key] = {
            "districtName": entry.get("districtName"),
            "drainageCondition": entry.get("drainageCondition"),
            "updatedAt": entry.get("updatedAt"),
        }

    payload = {
        "updatedAt": state.get("updatedAt"),
        "districts": serializable_districts,
    }
    ADMIN_OVERRIDES_PATH.write_bytes(serialize_payload(payload))


def _load_admin_history_json_state() -> dict[str, Any]:
    default_state = {"updatedAt": None, "entries": []}
    if not ADMIN_HISTORY_PATH.exists():
        return default_state

    try:
        loaded_state = json.loads(ADMIN_HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_state

    raw_entries = loaded_state.get("entries", [])
    if not isinstance(raw_entries, list):
        raw_entries = []

    normalized_entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue

        timestamp = normalize_optional_text(entry.get("timestamp"))
        action_type = normalize_optional_text(entry.get("type"))
        title = normalize_optional_text(entry.get("title"))
        description = normalize_optional_text(entry.get("description"))
        district_name = normalize_optional_text(entry.get("districtName"))

        if not timestamp or not title:
            continue

        normalized_entries.append(
            {
                "timestamp": timestamp,
                "type": action_type or "activity",
                "title": title,
                "description": description,
                "districtName": district_name or None,
            }
        )

    return {
        "updatedAt": loaded_state.get("updatedAt"),
        "entries": normalized_entries[:ADMIN_HISTORY_LIMIT],
    }


def _write_admin_history_json_state(state: dict[str, Any]) -> None:
    entries = state.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    payload = {
        "updatedAt": state.get("updatedAt"),
        "entries": entries[:ADMIN_HISTORY_LIMIT],
    }
    ADMIN_HISTORY_PATH.write_bytes(serialize_payload(payload))


def _migrate_admin_overrides_json_to_sqlite_if_needed() -> None:
    sqlite_state = sqlite_load_admin_overrides_state()
    if sqlite_state.get("districts") or sqlite_state.get("updatedAt"):
        return

    json_state = _load_admin_overrides_json_state()
    if json_state.get("districts") or json_state.get("updatedAt"):
        replace_admin_overrides_state(json_state)


def _migrate_admin_history_json_to_sqlite_if_needed() -> None:
    sqlite_state = sqlite_load_admin_history_state(ADMIN_HISTORY_LIMIT)
    if sqlite_state.get("entries") or sqlite_state.get("updatedAt"):
        return

    json_state = _load_admin_history_json_state()
    if json_state.get("entries") or json_state.get("updatedAt"):
        replace_admin_history_state(json_state, ADMIN_HISTORY_LIMIT)


def load_admin_overrides_state() -> dict[str, Any]:
    _migrate_admin_overrides_json_to_sqlite_if_needed()
    state = sqlite_load_admin_overrides_state()
    _write_admin_overrides_json_state(state)
    return state


def save_admin_overrides_state(state: dict[str, Any]) -> None:
    replace_admin_overrides_state(state)
    _write_admin_overrides_json_state(state)


def load_admin_history_state() -> dict[str, Any]:
    _migrate_admin_history_json_to_sqlite_if_needed()
    state = sqlite_load_admin_history_state(ADMIN_HISTORY_LIMIT)
    _write_admin_history_json_state(state)
    return state


def save_admin_history_state(state: dict[str, Any]) -> None:
    replace_admin_history_state(state, ADMIN_HISTORY_LIMIT)
    _write_admin_history_json_state(state)


def append_admin_history_entry(
    action_type: str,
    title: str,
    description: str = "",
    district_name: str | None = None,
) -> None:
    timestamp = current_jakarta_timestamp().isoformat()
    _migrate_admin_history_json_to_sqlite_if_needed()
    sqlite_append_admin_history_entry(
        {
            "timestamp": timestamp,
            "type": normalize_optional_text(action_type) or "activity",
            "title": normalize_optional_text(title) or "Aktivitas admin",
            "description": normalize_optional_text(description),
            "districtName": normalize_optional_text(district_name) or None,
        },
        ADMIN_HISTORY_LIMIT,
        timestamp,
    )
    _write_admin_history_json_state(sqlite_load_admin_history_state(ADMIN_HISTORY_LIMIT))


def get_template_district_name_map() -> dict[str, str]:
    district_name_map: dict[str, str] = {}
    for district in load_template_payload().get("districts", []):
        district_name = normalize_optional_text(district.get("name"))
        if district_name:
            district_name_map[normalize_name(district_name)] = district_name
    return district_name_map


def get_template_district_label_map() -> dict[str, str]:
    district_label_map: dict[str, str] = {}
    for district in load_template_payload().get("districts", []):
        district_name = normalize_optional_text(district.get("name"))
        if not district_name:
            continue

        district_label = normalize_optional_text(district.get("label")) or district_name.title()
        district_label_map[normalize_name(district_name)] = district_label
    return district_label_map


def save_admin_override(district_name: str, drainage_condition_value: Any) -> dict[str, Any]:
    from backend_core.drainage_logic import save_admin_override as _impl

    return _impl(district_name, drainage_condition_value)


def build_override_drainage_profile(
    base_profile: DrainageProfile | None,
    override_entry: dict[str, Any],
) -> DrainageProfile | None:
    from backend_core.drainage_logic import build_override_drainage_profile as _impl

    return _impl(base_profile, override_entry)


def apply_drainage_profile_to_district_payload(
    district_payload: dict[str, Any],
    drainage_profile: DrainageProfile | None,
    override_entry: dict[str, Any] | None = None,
) -> None:
    from backend_core.drainage_logic import (
        apply_drainage_profile_to_district_payload as _impl,
    )

    _impl(district_payload, drainage_profile, override_entry)


def apply_admin_overrides_to_payload(
    payload: dict[str, Any],
    overrides_state: dict[str, Any],
    drainage_profiles: dict[str, DrainageProfile] | None = None,
) -> dict[str, Any]:
    from backend_core.drainage_logic import apply_admin_overrides_to_payload as _impl

    return _impl(payload, overrides_state, drainage_profiles)


def _build_publication_snapshot_from_payload(
    publication_payload: dict[str, Any] | None,
    live_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(publication_payload, dict):
        return None

    meta = publication_payload.get("meta", {})
    return {
        "publishedAt": meta.get("publishedAt"),
        "payloadUpdatedAt": meta.get("updatedAt"),
        "publishedDistrictCount": len(publication_payload.get("districts", [])),
        "sourceLabel": meta.get("publicPayloadSourceLabel") or "Snapshot publik terakhir",
        "generatedFromLiveAt": live_payload.get("meta", {}).get("updatedAt") if live_payload else None,
        "publishedBy": meta.get("publishedBy"),
        "overrideResetCount": meta.get("publishedOverrideResetCount") or 0,
    }


def _migrate_publication_snapshot_to_sqlite_if_needed(
    live_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    latest_snapshot = get_latest_publication_snapshot()
    if latest_snapshot is not None:
        return latest_snapshot

    if not PUBLIC_PAYLOAD_PATH.exists():
        return None

    try:
        publication_payload = json.loads(PUBLIC_PAYLOAD_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    snapshot = _build_publication_snapshot_from_payload(publication_payload, live_payload)
    if snapshot is None:
        return None

    if snapshot.get("publishedAt") or snapshot.get("payloadUpdatedAt") or snapshot.get("publishedDistrictCount"):
        insert_publication_snapshot(snapshot)

    return get_latest_publication_snapshot()


def summarize_publication_state(live_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend_core.publication_logic import summarize_publication_state as _impl

    return _impl(live_payload)


def load_public_prediction_payload() -> dict[str, Any]:
    from backend_core.publication_logic import load_public_prediction_payload as _impl

    return _impl()


def build_admin_live_preview_response() -> dict[str, Any]:
    from backend_core.publication_logic import build_admin_live_preview_response as _impl

    return _impl()


def publish_admin_snapshot() -> dict[str, Any]:
    from backend_core.publication_logic import publish_admin_snapshot as _impl

    return _impl()


def compute_rain_streak(series: pd.Series) -> pd.Series:
    streak_values: list[float] = []
    current_streak = 0.0
    for value in series.fillna(0.0).tolist():
        if float(value) > 0.0:
            current_streak += 1.0
        else:
            current_streak = 0.0
        streak_values.append(current_streak)
    return pd.Series(streak_values, index=series.index, dtype="float32")


def probability_to_level(probability: float) -> dict[str, Any]:
    if probability < 0.20:
        return {
            "riskCategory": "Cerah",
            "webgisLevel": 1,
            "webgisColor": "Hijau",
            "webgisLevelLabel": "Level 1: Sangat Rendah",
            "webgisDescription": "Cerah / Sangat Ringan",
        }

    if probability < 0.50:
        return {
            "riskCategory": "Ringan",
            "webgisLevel": 2,
            "webgisColor": "Kuning",
            "webgisLevelLabel": "Level 2: Ringan",
            "webgisDescription": "Hujan Ringan",
        }

    if probability < 0.80:
        return {
            "riskCategory": "Sedang",
            "webgisLevel": 3,
            "webgisColor": "Oranye",
            "webgisLevelLabel": "Level 3: Sedang",
            "webgisDescription": "Hujan Sedang",
        }

    return {
        "riskCategory": "Lebat/Ekstrem",
        "webgisLevel": 4,
        "webgisColor": "Merah",
        "webgisLevelLabel": "Level 4: Tinggi",
        "webgisDescription": "Hujan Lebat/Ekstrem",
    }


def build_sequence_frame(
    district_frame: pd.DataFrame,
    district_name: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    from backend_core.prediction_logic import build_sequence_frame as _impl

    return _impl(district_frame, district_name, feature_columns)


def extract_class_probabilities(latent_features: np.ndarray, xgb_model: Any) -> np.ndarray:
    probabilities = xgb_model.predict_proba(latent_features)

    if probabilities.ndim != 2 or probabilities.shape[0] == 0:
        raise ValueError("Output probabilitas XGBoost tidak valid.")

    if probabilities.shape[1] != 4:
        raise ValueError(
            f"Backend mengharapkan 4 probabilitas kelas, tetapi menerima shape {probabilities.shape}."
        )

    return probabilities[0]


def extract_lstm_class_probabilities(inference_input: np.ndarray, lstm_model: Any) -> np.ndarray:
    probabilities = lstm_model.predict(inference_input, verbose=0)

    if probabilities.ndim != 2 or probabilities.shape[0] == 0:
        raise ValueError("Output probabilitas LSTM tidak valid.")

    if probabilities.shape[1] != 4:
        raise ValueError(
            f"Backend mengharapkan 4 probabilitas kelas dari LSTM, tetapi menerima shape {probabilities.shape}."
        )

    return probabilities[0]


def class_probabilities_to_risk_score(probabilities: np.ndarray) -> float:
    return float(np.dot(probabilities, np.array(CLASS_SEVERITY_SCORES, dtype=np.float32)))


def apply_extreme_decision_rule(
    probabilities: np.ndarray,
    extreme_threshold: float,
    extreme_margin: float,
) -> int:
    predicted_index = int(np.argmax(probabilities))
    if predicted_index != 3:
        return predicted_index

    fallback_index = int(np.argmax(probabilities[:3]))
    fallback_probability = float(probabilities[fallback_index])
    extreme_probability = float(probabilities[3])

    if extreme_probability < extreme_threshold or extreme_probability < (fallback_probability + extreme_margin):
        return fallback_index

    return predicted_index


def apply_gated_ensemble_rule(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    ensemble_rule: dict[str, Any],
) -> tuple[int, str]:
    from backend_core.prediction_logic import apply_gated_ensemble_rule as _impl

    return _impl(lstm_probabilities, xgb_probabilities, ensemble_rule)


def compose_operational_probabilities(
    lstm_probabilities: np.ndarray,
    xgb_probabilities: np.ndarray,
    predicted_class_index: int,
) -> np.ndarray:
    from backend_core.prediction_logic import compose_operational_probabilities as _impl

    return _impl(lstm_probabilities, xgb_probabilities, predicted_class_index)


def class_index_to_rainfall_info(class_index: int) -> dict[str, Any]:
    safe_index = max(0, min(int(class_index), len(CLASS_LABELS) - 1))
    return {
        "predictedRainfallClassIndex": safe_index,
        "predictedRainfallLabel": CLASS_LABELS[safe_index],
        "predictedRainfallRange": CLASS_RANGE_LABELS[safe_index],
    }


def apply_drainage_adjustment(
    base_score: float,
    drainage_profile: DrainageProfile | None,
) -> tuple[float, float]:
    if drainage_profile is None or drainage_profile.score is None:
        return base_score, 0.0

    if drainage_profile.condition in {"Tidak diketahui", "Tidak tersedia"}:
        return base_score, 0.0

    severity = (float(drainage_profile.score) - 50.0) / 50.0
    weight = confidence_weight(
        drainage_profile.confidence_label,
        drainage_profile.confidence_score,
    )
    adjustment = 0.10 * severity * weight
    adjusted_score = clamp(base_score + adjustment)
    return adjusted_score, adjustment


def build_district_payload(
    bundle: ModelBundle,
    template_district: dict[str, Any],
    district_frame: pd.DataFrame,
    drainage_profile: DrainageProfile | None,
) -> dict[str, Any]:
    from backend_core.prediction_logic import build_district_payload as _impl

    return _impl(bundle, template_district, district_frame, drainage_profile)


def recommendation_for_level(level: int) -> str:
    if level == 1:
        return "Pertahankan pemantauan rutin dan pemeliharaan preventif."

    if level == 2:
        return "Lakukan monitoring berkala dan pembersihan saluran lokal."

    if level == 3:
        return "Siapkan pemantauan intensif pada saluran dan area rawan genangan."

    return "Aktifkan kesiapsiagaan tinggi dan pantau titik genangan prioritas."


def build_unavailable_district_payload(
    template_district: dict[str, Any],
    drainage_profile: DrainageProfile | None,
    message: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(template_district)

    payload["predictedRainfallMm"] = None
    payload["drainageCondition"] = (
        drainage_profile.condition if drainage_profile is not None else "Tidak tersedia"
    )
    payload["riskCategory"] = "Tidak tersedia"
    payload["riskScore"] = None
    payload["probabilityWaspada"] = None
    payload["probabilityWaspadaPercent"] = None
    payload["webgisLevel"] = 0
    payload["webgisColor"] = "Abu-abu"
    payload["webgisLevelLabel"] = "Data tidak tersedia"
    payload["webgisDescription"] = "Data historis belum tersedia"
    payload["forecastLabel"] = "Prediksi tidak tersedia"
    payload["actualStatusFromNotebookTest"] = ""
    payload["rainfallDisplayNote"] = (
        "Prediksi tidak dapat dibentuk karena data historis kecamatan belum tersedia."
    )
    payload["summary"] = message
    payload["recommendation"] = (
        "Lengkapi data historis kecamatan terlebih dahulu sebelum hasil dibagikan ke publik."
    )
    payload["riskScorePercent"] = None
    payload["baseModelRiskScore"] = None
    payload["drainageScore"] = (
        round(float(drainage_profile.score), 1)
        if drainage_profile is not None and drainage_profile.score is not None
        else None
    )
    payload["drainageConfidence"] = (
        drainage_profile.confidence_label if drainage_profile is not None else "Tidak tersedia"
    )
    payload["drainageConfidenceScore"] = (
        round(float(drainage_profile.confidence_score), 1) if drainage_profile is not None else 0.0
    )
    payload["drainageAdjustmentApplied"] = 0.0
    payload["drainageAdjustmentPercent"] = 0.0
    payload["drainageDataSourceType"] = (
        drainage_profile.source_type if drainage_profile is not None else "missing_source_data"
    )
    payload["drainageDataSourceName"] = (
        drainage_profile.source_name if drainage_profile is not None else "Data sumber tidak tersedia"
    )
    payload["drainageSuggestedCondition"] = (
        drainage_profile.suggested_condition if drainage_profile is not None else None
    )
    payload["drainageSuggestedScore"] = (
        round(float(drainage_profile.suggested_score), 1)
        if drainage_profile is not None and drainage_profile.suggested_score is not None
        else None
    )
    payload["drainageManualCondition"] = (
        drainage_profile.manual_condition if drainage_profile is not None else None
    )
    payload["drainageManualScore"] = (
        round(float(drainage_profile.manual_score), 1)
        if drainage_profile is not None and drainage_profile.manual_score is not None
        else None
    )
    payload["drainageNote"] = drainage_profile.note if drainage_profile is not None else ""
    payload["latestObservationDate"] = None
    payload["latestObservedRainfallMm"] = None
    payload["recentThreeDayAverageMm"] = None
    payload["predictedRainfallClassIndex"] = None
    payload["predictedRainfallLabel"] = "Data tidak tersedia"
    payload["predictedRainfallRange"] = "Data tidak tersedia"
    payload["predictedClassProbability"] = None
    payload["predictedClassProbabilityPercent"] = None
    payload["classProbabilities"] = {}
    payload["baseLstmClassProbabilities"] = {}
    payload["latentXgbClassProbabilities"] = {}
    payload["decisionSource"] = "missing_source_data"
    payload["latestObservedTemperatureC"] = None
    payload["latestObservedHumidityPercent"] = None
    payload["hasAdminOverride"] = False
    payload["hasAdminDrainageOverride"] = False
    payload["adminOverrideUpdatedAt"] = None

    return payload


def build_prediction_payload() -> dict[str, Any]:
    from backend_core.prediction_logic import build_prediction_payload as _impl

    return _impl()
