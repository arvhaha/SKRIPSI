from typing import Any, Optional

from backend_core.legacy_core import (
    is_admin_auth_configured,
    is_admin_page_locked,
    validate_admin_basic_auth_header,
)


def get_admin_access_state() -> dict[str, Any]:
    return {
        "isLocked": is_admin_page_locked(),
        "isConfigured": is_admin_auth_configured(),
    }


def validate_basic_auth(authorization_header: Optional[str]) -> bool:
    return validate_admin_basic_auth_header(authorization_header)
