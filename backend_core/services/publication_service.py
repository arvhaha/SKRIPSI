from typing import Any, Dict, Optional

from backend_core.publication_logic import (
    load_public_prediction_payload,
    publish_admin_snapshot,
    summarize_publication_state,
)


def get_public_snapshot_payload() -> Dict[str, Any]:
    return load_public_prediction_payload()


def publish_snapshot() -> Dict[str, Any]:
    return publish_admin_snapshot()


def get_publication_summary(live_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return summarize_publication_state(live_payload)
