from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

import pandas as pd

from backend_core.path_config import APP_ENV, APP_ENV_LABEL, APP_NAME, DATA_DIR, DATASET_PATH, ROOT


REFRESH_SCRIPT_PATH = ROOT / "refresh_public_predictions.py"
DEFAULT_REFRESH_TIMEOUT_SECONDS = int(os.getenv("FLOODGIS_REFRESH_TIMEOUT_SECONDS", "900"))
AUTO_REFRESH_ENABLED = os.getenv("FLOODGIS_AUTO_REFRESH_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
AUTO_REFRESH_TIMEZONE = os.getenv("FLOODGIS_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
AUTO_REFRESH_SOURCE_LAG_DAYS = max(0, int(os.getenv("FLOODGIS_SOURCE_LAG_DAYS", "1")))
AUTO_REFRESH_COOLDOWN_SECONDS = max(
    60,
    int(os.getenv("FLOODGIS_AUTO_REFRESH_COOLDOWN_SECONDS", "1800")),
)
AUTO_REFRESH_STATE_PATH = DATA_DIR / "auto_refresh_state.json"


def _read_auto_refresh_state() -> Dict[str, Any]:
    if not AUTO_REFRESH_STATE_PATH.exists():
        return {}

    try:
        return json.loads(AUTO_REFRESH_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_auto_refresh_state(state: Dict[str, Any]) -> None:
    AUTO_REFRESH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTO_REFRESH_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_state_timestamp(value: Any) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(AUTO_REFRESH_TIMEZONE))

    return parsed


def _get_latest_dataset_observation_date() -> datetime.date | None:
    if not DATASET_PATH.exists():
        return None

    try:
        dataset = pd.read_csv(DATASET_PATH, sep=";", usecols=["Tanggal"])
    except Exception:
        return None

    if dataset.empty:
        return None

    try:
        parsed_dates = pd.to_datetime(
            dataset["Tanggal"],
            format="%d/%m/%Y",
            dayfirst=True,
            errors="coerce",
        ).dropna()
    except Exception:
        return None

    if parsed_dates.empty:
        return None

    return parsed_dates.max().date()


def _get_target_observation_date() -> datetime.date:
    now = datetime.now(ZoneInfo(AUTO_REFRESH_TIMEZONE))
    return now.date() - timedelta(days=AUTO_REFRESH_SOURCE_LAG_DAYS)


def _should_auto_refresh(force: bool = False) -> tuple[bool, Dict[str, Any]]:
    latest_dataset_date = _get_latest_dataset_observation_date()
    target_observation_date = _get_target_observation_date()
    now = datetime.now(ZoneInfo(AUTO_REFRESH_TIMEZONE))
    state = _read_auto_refresh_state()

    details: Dict[str, Any] = {
        "enabled": AUTO_REFRESH_ENABLED,
        "latestDatasetDate": latest_dataset_date.isoformat() if latest_dataset_date else None,
        "targetObservationDate": target_observation_date.isoformat(),
        "cooldownSeconds": AUTO_REFRESH_COOLDOWN_SECONDS,
    }

    if not AUTO_REFRESH_ENABLED and not force:
        details["reason"] = "auto_refresh_disabled"
        return False, details

    is_stale = latest_dataset_date is None or latest_dataset_date < target_observation_date
    details["isStale"] = is_stale

    if not is_stale and not force:
        details["reason"] = "dataset_already_fresh"
        return False, details

    last_attempt_at = _parse_state_timestamp(state.get("lastAttemptAt"))
    if not force and last_attempt_at is not None:
        elapsed_seconds = max(0, int((now - last_attempt_at).total_seconds()))
        details["secondsSinceLastAttempt"] = elapsed_seconds
        if elapsed_seconds < AUTO_REFRESH_COOLDOWN_SECONDS:
            details["reason"] = "cooldown_active"
            return False, details

    details["reason"] = "stale_dataset_requires_refresh" if is_stale else "forced_refresh"
    return True, details


def refresh_live_prediction_sources() -> Dict[str, Any]:
    command = [
        sys.executable,
        str(REFRESH_SCRIPT_PATH),
        "--app-environment",
        APP_ENV,
        "--app-environment-label",
        APP_ENV_LABEL,
        "--app-name",
        APP_NAME,
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=DEFAULT_REFRESH_TIMEOUT_SECONDS,
        env=os.environ.copy(),
    )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        raise RuntimeError(
            stderr
            or stdout
            or f"Runner refresh berhenti dengan exit code {completed.returncode}."
        )

    return {
        "status": "ok",
        "message": "Sumber data, draft admin, dan payload homepage berhasil direfresh otomatis dari backend.",
        "stdout": stdout,
    }


def ensure_live_prediction_sources_fresh(
    *,
    trigger: str = "runtime_request",
    force: bool = False,
    raise_on_error: bool = False,
) -> Dict[str, Any]:
    should_refresh, details = _should_auto_refresh(force=force)
    if not should_refresh:
        return {
            "status": "skipped",
            "trigger": trigger,
            **details,
        }

    started_at = datetime.now(ZoneInfo(AUTO_REFRESH_TIMEZONE)).isoformat()
    state = {
        "lastAttemptAt": started_at,
        "lastAttemptTrigger": trigger,
        "lastAttemptStatus": "running",
        "targetObservationDate": details.get("targetObservationDate"),
        "latestDatasetDateBefore": details.get("latestDatasetDate"),
    }
    _write_auto_refresh_state(state)

    try:
        result = refresh_live_prediction_sources()
        latest_dataset_date = _get_latest_dataset_observation_date()
        finished_at = datetime.now(ZoneInfo(AUTO_REFRESH_TIMEZONE)).isoformat()
        _write_auto_refresh_state(
            {
                **state,
                "lastAttemptStatus": "success",
                "lastSuccessAt": finished_at,
                "latestDatasetDateAfter": latest_dataset_date.isoformat() if latest_dataset_date else None,
                "lastMessage": result.get("message"),
            }
        )
        return {
            "status": "ok",
            "trigger": trigger,
            "message": result.get("message"),
            "latestDatasetDateAfter": latest_dataset_date.isoformat() if latest_dataset_date else None,
            **details,
        }
    except Exception as error:
        finished_at = datetime.now(ZoneInfo(AUTO_REFRESH_TIMEZONE)).isoformat()
        _write_auto_refresh_state(
            {
                **state,
                "lastAttemptStatus": "error",
                "lastErrorAt": finished_at,
                "lastError": str(error),
            }
        )
        if raise_on_error:
            raise
        return {
            "status": "error",
            "trigger": trigger,
            "message": str(error),
            **details,
        }
