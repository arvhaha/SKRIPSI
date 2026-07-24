from typing import Any, Dict

from backend_core.prediction_logic import build_prediction_payload, load_geojson_payload
from backend_core.publication_logic import build_admin_live_preview_response
from backend_core.services.publication_service import get_public_snapshot_payload


def get_live_prediction_payload() -> Dict[str, Any]:
    return build_prediction_payload()


def get_public_prediction_payload() -> Dict[str, Any]:
    return get_public_snapshot_payload()


def get_admin_live_preview_payload() -> Dict[str, Any]:
    return build_admin_live_preview_response()


def get_geojson_payload() -> Dict[str, Any]:
    return load_geojson_payload()
