from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from backend_core.path_config import (
    ADMIN_HISTORY_PATH,
    ADMIN_OVERRIDES_PATH,
    BUNDLED_DATASET_PATH,
    BUNDLED_DISTRICT_GEOJSON_PATH,
    BUNDLED_DRAINAGE_CLEAN_PATH,
    BUNDLED_DRAINAGE_SUMMARY_PATH,
    BUNDLED_DRAINAGE_TEMPLATE_PATH,
    BUNDLED_PUBLIC_PAYLOAD_PATH,
    BUNDLED_TEMPLATE_PAYLOAD_PATH,
    DATASET_PATH,
    DATA_DIR,
    DISTRICT_GEOJSON_PATH,
    DRAINAGE_PATH,
    FRONTEND_PUBLIC_GEOJSON_PATH,
    FRONTEND_PUBLIC_SNAPSHOT_PATH,
    PUBLIC_PAYLOAD_PATH,
    RUNTIME_DATA_DIR,
    TEMPLATE_PAYLOAD_PATH,
)


def _copy_if_missing(source_path: Path, target_path: Path) -> None:
    if target_path.exists() or not source_path.exists():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def _get_latest_dataset_date(path: Path) -> pd.Timestamp | None:
    if not path.exists():
        return None

    try:
        dataset = pd.read_csv(path, sep=";", usecols=["Tanggal"])
        if dataset.empty:
            return None
        return pd.to_datetime(dataset["Tanggal"], format="%d/%m/%Y", dayfirst=True).max()
    except Exception:
        return None


def _copy_dataset_if_source_newer(source_path: Path, target_path: Path) -> None:
    if not source_path.exists():
        return

    source_latest = _get_latest_dataset_date(source_path)
    target_latest = _get_latest_dataset_date(target_path)

    if target_latest is not None and source_latest is not None and target_latest >= source_latest:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def _write_json_if_missing(target_path: Path, payload: dict[str, Any]) -> None:
    if target_path.exists():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_template_from_snapshot(snapshot_path: Path) -> dict[str, Any] | None:
    if not snapshot_path.exists():
        return None

    try:
        source_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    template_districts: list[dict[str, str]] = []
    seen_districts: set[str] = set()

    for district in source_payload.get("districts", []):
        district_name = str(district.get("name") or "").strip()
        if not district_name:
            continue

        district_key = "".join(district_name.lower().split())
        if district_key in seen_districts:
            continue

        template_districts.append(
            {
                "name": district_name,
                "label": str(district.get("label") or district_name.title()).strip(),
            }
        )
        seen_districts.add(district_key)

    return {
        "meta": {
            "templateType": "district_seed",
            "districtCount": len(template_districts),
        },
        "forecastDays": [],
        "districts": template_districts,
    }


def ensure_runtime_data_files() -> None:
    if RUNTIME_DATA_DIR == DATA_DIR:
        RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Static sources needed to build live predictions on Railway should live in
    # the writable runtime directory so refresh/publish use one consistent set.
    _copy_dataset_if_source_newer(BUNDLED_DATASET_PATH, DATASET_PATH)
    _copy_if_missing(BUNDLED_DRAINAGE_TEMPLATE_PATH, DRAINAGE_PATH)
    _copy_if_missing(BUNDLED_TEMPLATE_PAYLOAD_PATH, TEMPLATE_PAYLOAD_PATH)
    _copy_if_missing(BUNDLED_DISTRICT_GEOJSON_PATH, DISTRICT_GEOJSON_PATH)

    # Nice-to-have helper files for ops/debugging.
    _copy_if_missing(BUNDLED_DRAINAGE_CLEAN_PATH, DATA_DIR / BUNDLED_DRAINAGE_CLEAN_PATH.name)
    _copy_if_missing(BUNDLED_DRAINAGE_SUMMARY_PATH, DATA_DIR / BUNDLED_DRAINAGE_SUMMARY_PATH.name)

    # Seed public snapshot from bundled data only when the runtime volume does
    # not yet have a published snapshot.
    if not PUBLIC_PAYLOAD_PATH.exists():
        _copy_if_missing(BUNDLED_PUBLIC_PAYLOAD_PATH, PUBLIC_PAYLOAD_PATH)
        _copy_if_missing(FRONTEND_PUBLIC_SNAPSHOT_PATH, PUBLIC_PAYLOAD_PATH)

    if not DISTRICT_GEOJSON_PATH.exists():
        _copy_if_missing(FRONTEND_PUBLIC_GEOJSON_PATH, DISTRICT_GEOJSON_PATH)

    if not TEMPLATE_PAYLOAD_PATH.exists():
        template_payload = _build_template_from_snapshot(PUBLIC_PAYLOAD_PATH)
        if template_payload is None:
            template_payload = _build_template_from_snapshot(FRONTEND_PUBLIC_SNAPSHOT_PATH)
        if template_payload is not None:
            _write_json_if_missing(TEMPLATE_PAYLOAD_PATH, template_payload)

    _write_json_if_missing(ADMIN_OVERRIDES_PATH, {"updatedAt": None, "districts": {}})
    _write_json_if_missing(ADMIN_HISTORY_PATH, {"updatedAt": None, "entries": []})
