from typing import Any, Dict

from backend_core.prediction_logic import build_prediction_payload, load_geojson_payload
from backend_core.publication_logic import build_admin_live_preview_response
from backend_core.services.publication_service import get_public_snapshot_payload
from backend_core.services.refresh_service import ensure_live_prediction_sources_fresh


def get_live_prediction_payload() -> Dict[str, Any]:
    ensure_live_prediction_sources_fresh(trigger="api_live_predictions")
    return build_prediction_payload()


def get_public_prediction_payload() -> Dict[str, Any]:
    ensure_live_prediction_sources_fresh(trigger="api_public_predictions")
    return get_public_snapshot_payload()


def get_admin_live_preview_payload() -> Dict[str, Any]:
    ensure_live_prediction_sources_fresh(trigger="api_admin_preview")
    return build_admin_live_preview_response()


def get_geojson_payload() -> Dict[str, Any]:
    return load_geojson_payload()
