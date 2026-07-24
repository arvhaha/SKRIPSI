from typing import Any, Optional
from urllib.parse import urlparse

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


def is_same_origin_admin_referer(referer: Optional[str], host: Optional[str]) -> bool:
    referer_value = str(referer or "").strip()
    host_value = str(host or "").strip().lower()

    if not referer_value or not host_value:
        return False

    try:
        parsed = urlparse(referer_value)
    except ValueError:
        return False

    referer_host = str(parsed.netloc or "").strip().lower()
    referer_path = str(parsed.path or "").strip().lower()

    if not referer_host or referer_host != host_value:
        return False

    return referer_path.endswith("/admin.html")
