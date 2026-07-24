from typing import Any, Dict

from backend_core.drainage_logic import save_admin_override
from backend_core.services.publication_service import publish_snapshot


def save_drainage_override(district_name: str, drainage_condition: Any) -> Dict[str, Any]:
    return save_admin_override(district_name=district_name, drainage_condition_value=drainage_condition)


def publish_public_snapshot() -> Dict[str, Any]:
    return publish_snapshot()
