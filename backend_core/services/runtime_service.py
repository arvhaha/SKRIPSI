from pathlib import Path
from typing import Any, Dict, List

from backend_core.legacy_core import (
    APP_ENV,
    APP_NAME,
    ADMIN_OVERRIDES_PATH,
    DATASET_PATH,
    DRAINAGE_PATH,
    PUBLIC_PAYLOAD_PATH,
    TEMPLATE_PAYLOAD_PATH,
    current_jakarta_timestamp,
    get_allowed_cors_origins,
    is_admin_auth_configured,
)
from backend_core.sqlite_store import get_sqlite_db_path


def get_application_name() -> str:
    return APP_NAME


def get_cors_origins() -> List[str]:
    return list(get_allowed_cors_origins())


def get_runtime_health_payload() -> Dict[str, Any]:
    now = current_jakarta_timestamp()
    db_path = get_sqlite_db_path()
    db_parent = db_path.parent

    return {
        "status": "ok",
        "appName": get_application_name(),
        "appEnvironment": APP_ENV,
        "serverTime": now.isoformat(),
        "serverDate": now.strftime("%Y-%m-%d"),
        "sqliteDbPath": str(db_path),
        "sqliteDbExists": Path(db_path).exists(),
        "sqliteDbDirectory": str(db_parent),
        "sqliteDbDirectoryWritableHint": db_parent.exists() or db_parent == Path("/app/data"),
        "publicSnapshotPath": str(PUBLIC_PAYLOAD_PATH),
        "publicSnapshotExists": PUBLIC_PAYLOAD_PATH.exists(),
        "datasetPath": str(DATASET_PATH),
        "datasetExists": Path(DATASET_PATH).exists(),
        "drainagePath": str(DRAINAGE_PATH),
        "drainageExists": Path(DRAINAGE_PATH).exists(),
        "templatePath": str(TEMPLATE_PAYLOAD_PATH),
        "templateExists": Path(TEMPLATE_PAYLOAD_PATH).exists(),
        "adminOverrideFilePath": str(ADMIN_OVERRIDES_PATH),
        "adminApiProtected": is_admin_auth_configured(),
        "corsOrigins": get_cors_origins(),
    }
