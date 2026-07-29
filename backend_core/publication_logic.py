from __future__ import annotations

import json
import os
from typing import Any

from backend_core.drainage_logic import (
    apply_admin_overrides_to_payload,
    load_admin_history_state,
    load_admin_overrides_state,
    load_drainage_profiles,
    save_admin_overrides_state,
)
from backend_core.legacy_core import (
    ADMIN_USERNAME,
    APP_ENV,
    APP_ENV_LABEL,
    APP_NAME,
    PUBLIC_PAYLOAD_PATH,
    ROOT,
    append_admin_history_entry,
    build_prediction_payload,
    current_jakarta_timestamp,
    insert_prediction_run,
    is_staging_environment,
    parse_optional_timestamp,
    serialize_payload,
)
from backend_core.sqlite_store import get_latest_publication_snapshot, insert_publication_snapshot

BUNDLED_PUBLIC_PAYLOAD_PATH = ROOT / "frontend-public" / "data" / "east-jakarta-predictions.json"


def _load_json_payload(path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return None


def _extract_payload_horizon_days(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0

    forecast_days = payload.get("forecastDays")
    if isinstance(forecast_days, list) and forecast_days:
        offsets: list[int] = []
        for item in forecast_days:
            try:
                offsets.append(int(item.get("dayOffset")))
            except Exception:
                continue
        if offsets:
            return max(offsets)

    meta = payload.get("meta", {})
    try:
        return int(meta.get("forecastHorizonDays") or 0)
    except Exception:
        return 0


def _expected_runtime_horizon_days() -> int:
    try:
        config_path = ROOT / "operational_multiclass_config.json"
        if not config_path.exists():
            return 1

        config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        horizons = config_payload.get("horizons")
        if isinstance(horizons, dict) and horizons:
            parsed_keys = []
            for key in horizons.keys():
                try:
                    parsed_keys.append(int(key))
                except Exception:
                    continue
            if parsed_keys:
                return max(parsed_keys)

        return int(config_payload.get("forecast_horizon_days") or 1)
    except Exception:
        return 1


def _is_payload_legacy_for_runtime(payload: dict[str, Any] | None) -> bool:
    expected_horizon_days = _expected_runtime_horizon_days()
    if expected_horizon_days <= 1:
        return False

    payload_horizon_days = _extract_payload_horizon_days(payload)
    if payload_horizon_days < expected_horizon_days:
        return True

    forecast_days = payload.get("forecastDays") if isinstance(payload, dict) else None
    if not isinstance(forecast_days, list) or not forecast_days:
        return True

    return False


def _persist_runtime_public_payload(payload: dict[str, Any]) -> None:
    try:
        PUBLIC_PAYLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_PAYLOAD_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _build_live_payload_with_snapshot_fallback() -> tuple[dict[str, Any], str]:
    try:
        payload = build_prediction_payload()
        return payload, "live_model"
    except Exception as error:  # pragma: no cover - defensive fallback for deploy/runtime mismatch
        fallback_payload = _load_json_payload(BUNDLED_PUBLIC_PAYLOAD_PATH)
        if fallback_payload is None:
            raise error

        fallback_payload.setdefault("meta", {})
        fallback_payload["meta"]["liveBuildStatus"] = "bundled_snapshot_fallback"
        fallback_payload["meta"]["liveBuildError"] = str(error)
        fallback_payload["meta"]["publicPayloadSource"] = (
            fallback_payload["meta"].get("publicPayloadSource") or "bundled_snapshot_fallback"
        )
        fallback_payload["meta"]["publicPayloadSourceLabel"] = (
            fallback_payload["meta"].get("publicPayloadSourceLabel")
            or "Snapshot bundel fallback"
        )
        return fallback_payload, "bundled_snapshot_fallback"


def _enrich_runtime_meta(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("meta", {})
    meta = payload["meta"]
    now = current_jakarta_timestamp()

    # Runtime environment should reflect the active server, even when the
    # payload came from a bundled fallback snapshot generated elsewhere.
    meta["appName"] = meta.get("appName") or APP_NAME
    meta["deploymentEnvironment"] = APP_ENV
    meta["deploymentEnvironmentLabel"] = APP_ENV_LABEL
    meta["isStaging"] = is_staging_environment()

    if not meta.get("serverGeneratedAt"):
        meta["serverGeneratedAt"] = str(meta.get("updatedAt") or now.isoformat())
    if not meta.get("serverCurrentDate"):
        meta["serverCurrentDate"] = now.strftime("%Y-%m-%d")
    if not meta.get("runtimeClockSource"):
        meta["runtimeClockSource"] = (
            "fixed_env"
            if any(str(os.getenv(key, "")).strip() for key in ("FLOODGIS_FIXED_NOW", "FLOODGIS_REFERENCE_NOW"))
            else "system_clock"
        )

    observation_timestamp = parse_optional_timestamp(meta.get("latestObservationDate"))
    forecast_timestamp = parse_optional_timestamp(meta.get("forecastTargetDate"))
    observation_age_days = meta.get("observationAgeDays")
    if observation_age_days in (None, "") and observation_timestamp is not None:
        observation_age_days = max(0, int((now.date() - observation_timestamp.date()).days))
        meta["observationAgeDays"] = observation_age_days

    warnings: list[str] = list(meta.get("freshnessWarnings") or [])
    if observation_timestamp is not None and observation_timestamp.date() > now.date():
        warning = "Tanggal observasi terakhir berada di masa depan dibanding jam server."
        if warning not in warnings:
            warnings.append(warning)
    if forecast_timestamp is not None and forecast_timestamp.date() < now.date():
        warning = "Target prediksi sudah lewat dari tanggal server saat payload dibuka."
        if warning not in warnings:
            warnings.append(warning)
    if observation_timestamp is not None and forecast_timestamp is not None:
        if forecast_timestamp.date() < observation_timestamp.date():
            warning = "Target prediksi lebih awal daripada observasi terakhir."
            if warning not in warnings:
                warnings.append(warning)

    if warnings:
        meta["freshnessWarnings"] = warnings

    if not meta.get("freshnessStatus"):
        freshness_status = "ok"
        if observation_age_days is not None and int(observation_age_days) > int(meta.get("staleDataThresholdDays") or 3):
            freshness_status = "stale"
        if warnings:
            freshness_status = "warning"
        meta["freshnessStatus"] = freshness_status

    return payload


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
    publication_payload: dict[str, Any] | None = None
    latest_snapshot = _migrate_publication_snapshot_to_sqlite_if_needed(live_payload)
    if latest_snapshot is None and PUBLIC_PAYLOAD_PATH.exists():
        try:
            publication_payload = json.loads(PUBLIC_PAYLOAD_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            publication_payload = None
        latest_snapshot = _build_publication_snapshot_from_payload(publication_payload, live_payload)

    return {
        "hasPublishedSnapshot": latest_snapshot is not None,
        "publishedAt": latest_snapshot.get("publishedAt") if latest_snapshot else None,
        "payloadUpdatedAt": latest_snapshot.get("payloadUpdatedAt") if latest_snapshot else None,
        "publishedDistrictCount": int(latest_snapshot.get("publishedDistrictCount") or 0) if latest_snapshot else 0,
        "sourceLabel": latest_snapshot.get("sourceLabel") if latest_snapshot else "Snapshot publik terakhir",
        "generatedFromLiveAt": (
            latest_snapshot.get("generatedFromLiveAt")
            if latest_snapshot
            else live_payload.get("meta", {}).get("updatedAt") if live_payload else None
        ),
    }


def load_public_prediction_payload() -> dict[str, Any]:
    if PUBLIC_PAYLOAD_PATH.exists():
        try:
            payload = json.loads(PUBLIC_PAYLOAD_PATH.read_text(encoding="utf-8"))
            if not _is_payload_legacy_for_runtime(payload):
                payload.setdefault("meta", {})
                payload["meta"]["publicPayloadSource"] = (
                    payload["meta"].get("publicPayloadSource") or "published_snapshot"
                )
                payload["meta"]["publicPayloadSourceLabel"] = (
                    payload["meta"].get("publicPayloadSourceLabel") or "Snapshot publik aktif"
                )
                return _enrich_runtime_meta(payload)
        except (json.JSONDecodeError, OSError):
            pass

    payload, fallback_mode = _build_live_payload_with_snapshot_fallback()
    payload.setdefault("meta", {})
    if fallback_mode == "live_model":
        payload["meta"]["publicPayloadSource"] = "runtime_live_autofix"
        payload["meta"]["publicPayloadSourceLabel"] = "Payload live backend 3 hari"
    else:
        payload["meta"]["publicPayloadSource"] = "bundled_snapshot_fallback"
        payload["meta"]["publicPayloadSourceLabel"] = "Snapshot bundel 3 hari"
    _persist_runtime_public_payload(payload)
    return _enrich_runtime_meta(payload)


def build_admin_live_preview_response() -> dict[str, Any]:
    live_payload, preview_mode = _build_live_payload_with_snapshot_fallback()
    overrides_state = load_admin_overrides_state()
    apply_admin_overrides_to_payload(live_payload, overrides_state, load_drainage_profiles())
    live_payload = _enrich_runtime_meta(live_payload)
    live_payload.setdefault("meta", {})
    live_payload["meta"]["adminPreviewMode"] = (
        "live_draft" if preview_mode == "live_model" else "bundled_snapshot_draft"
    )
    live_payload["meta"]["publicPayloadSourceLabel"] = (
        "Draft live admin" if preview_mode == "live_model" else "Draft snapshot bundel admin"
    )

    overrides_for_client = {
        entry.get("districtName"): {
            "districtName": entry.get("districtName"),
            "drainageCondition": entry.get("drainageCondition"),
            "updatedAt": entry.get("updatedAt"),
        }
        for entry in overrides_state.get("districts", {}).values()
        if entry.get("districtName")
    }

    return {
        "status": "ok",
        "payload": live_payload,
        "overrides": overrides_for_client,
        "publication": summarize_publication_state(live_payload),
        "history": load_admin_history_state().get("entries", []),
    }


def publish_admin_snapshot() -> dict[str, Any]:
    live_payload, publish_mode = _build_live_payload_with_snapshot_fallback()
    overrides_state = load_admin_overrides_state()
    apply_admin_overrides_to_payload(live_payload, overrides_state, load_drainage_profiles())
    live_payload = _enrich_runtime_meta(live_payload)
    cleared_override_count = len(overrides_state.get("districts", {}))
    live_payload.setdefault("meta", {})
    now = current_jakarta_timestamp().isoformat()
    live_payload["meta"]["publishedAt"] = now
    live_payload["meta"]["publishedBy"] = ADMIN_USERNAME or "Admin lokal"
    live_payload["meta"]["publicPayloadSource"] = (
        "admin_publish" if publish_mode == "live_model" else "admin_publish_bundled_snapshot"
    )
    live_payload["meta"]["publicPayloadSourceLabel"] = (
        "Dipublish dari panel admin"
        if publish_mode == "live_model"
        else "Dipublish dari snapshot bundel admin"
    )
    live_payload["meta"]["publishedOverrideResetCount"] = cleared_override_count
    live_payload["meta"]["adminOverrideCount"] = 0
    PUBLIC_PAYLOAD_PATH.write_bytes(serialize_payload(live_payload))
    insert_prediction_run(live_payload, "admin_publish")
    insert_publication_snapshot(
        {
            "publishedAt": now,
            "payloadUpdatedAt": live_payload["meta"].get("updatedAt"),
            "publishedDistrictCount": len(live_payload.get("districts", [])),
            "sourceLabel": live_payload["meta"].get("publicPayloadSourceLabel"),
            "generatedFromLiveAt": live_payload["meta"].get("updatedAt"),
            "publishedBy": live_payload["meta"].get("publishedBy"),
            "overrideResetCount": cleared_override_count,
        }
    )

    save_admin_overrides_state(
        {
            "updatedAt": now,
            "districts": {},
        }
    )
    append_admin_history_entry(
        action_type="publish",
        title="Publish ke homepage",
        description=(
            f"{len(live_payload.get('districts', []))} kecamatan dipublish ke halaman publik. "
            f"{cleared_override_count} draft override direset otomatis setelah publish."
        ),
    )
    return live_payload


__all__ = [
    "_build_publication_snapshot_from_payload",
    "_migrate_publication_snapshot_to_sqlite_if_needed",
    "build_admin_live_preview_response",
    "load_public_prediction_payload",
    "publish_admin_snapshot",
    "summarize_publication_state",
]
