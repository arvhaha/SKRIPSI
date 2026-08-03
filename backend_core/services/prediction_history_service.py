from typing import Any, Optional

from backend_core.sqlite_store import (
    get_prediction_run_detail,
    list_district_prediction_history,
    list_prediction_runs,
)


def get_prediction_run_history(limit: int = 20) -> dict[str, Any]:
    return {
        "status": "ok",
        "runs": list_prediction_runs(limit=limit),
    }


def get_prediction_run_by_id(run_id: int) -> Optional[dict[str, Any]]:
    run_detail = get_prediction_run_detail(run_id)
    if run_detail is None:
        return None

    return {
        "status": "ok",
        "run": run_detail,
    }


def get_public_district_prediction_history(district_name: str, limit: int = 3) -> dict[str, Any]:
    return {
        "status": "ok",
        "districtName": district_name,
        "history": list_district_prediction_history(district_name=district_name, limit=limit),
    }
