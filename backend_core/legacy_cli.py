from __future__ import annotations

import argparse
import os
import shutil
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend_core.drainage_logic import (
    apply_admin_overrides_to_payload,
    load_admin_overrides_state,
    load_drainage_profiles,
)
from backend_core.legacy_http import FloodGISRequestHandler
from backend_core.legacy_core import PUBLIC_PAYLOAD_PATH, current_jakarta_timestamp, insert_prediction_run, serialize_payload
from backend_core.path_config import DISTRICT_GEOJSON_PATH, ROOT
from backend_core.prediction_logic import build_prediction_payload
from backend_core.sqlite_store import insert_publication_snapshot


def _sync_runtime_file_to_static_target(
    source_path: Path,
    target_path: Path,
    *,
    require_existing_root: bool = False,
) -> bool:
    if not source_path.exists():
        return False

    if require_existing_root and not target_path.parents[1].exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return True


def _sync_public_runtime_payloads() -> list[str]:
    synced_paths: list[str] = []
    sync_plan = (
        (PUBLIC_PAYLOAD_PATH, ROOT / "frontend-public" / "data" / PUBLIC_PAYLOAD_PATH.name, False),
        (PUBLIC_PAYLOAD_PATH, ROOT / "frontend-react" / "dist" / "data" / PUBLIC_PAYLOAD_PATH.name, True),
        (DISTRICT_GEOJSON_PATH, ROOT / "frontend-public" / "data" / DISTRICT_GEOJSON_PATH.name, False),
        (DISTRICT_GEOJSON_PATH, ROOT / "frontend-react" / "dist" / "data" / DISTRICT_GEOJSON_PATH.name, True),
    )

    for source_path, target_path, require_existing_root in sync_plan:
        if _sync_runtime_file_to_static_target(
            source_path,
            target_path,
            require_existing_root=require_existing_root,
        ):
            synced_paths.append(str(target_path))

    return synced_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve FloodGIS static files and prediction API.")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host binding for the server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port binding for the server.",
    )
    parser.add_argument(
        "--export-static-json",
        action="store_true",
        help="Bangun payload terbaru lalu simpan ke data/east-jakarta-predictions.json.",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Jalankan tugas sekali lalu keluar tanpa menyalakan server.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.export_static_json:
        payload = build_prediction_payload()
        apply_admin_overrides_to_payload(payload, load_admin_overrides_state(), load_drainage_profiles())
        payload.setdefault("meta", {})
        published_at = current_jakarta_timestamp().isoformat()
        payload["meta"]["publishedAt"] = published_at
        payload["meta"]["publishedBy"] = "Scheduler backend"
        payload["meta"]["publicPayloadSource"] = "scheduled_auto_publish"
        payload["meta"]["publicPayloadSourceLabel"] = "Diperbarui otomatis backend"
        payload["meta"]["publishedOverrideResetCount"] = 0
        PUBLIC_PAYLOAD_PATH.write_bytes(serialize_payload(payload))
        synced_static_paths = _sync_public_runtime_payloads()
        insert_prediction_run(payload, "scheduled_export")
        insert_publication_snapshot(
            {
                "publishedAt": published_at,
                "payloadUpdatedAt": payload["meta"].get("updatedAt"),
                "publishedDistrictCount": len(payload.get("districts", [])),
                "sourceLabel": payload["meta"].get("publicPayloadSourceLabel"),
                "generatedFromLiveAt": payload["meta"].get("updatedAt"),
                "publishedBy": payload["meta"].get("publishedBy"),
                "overrideResetCount": 0,
            }
        )
        print(f"Payload statis berhasil diekspor ke {PUBLIC_PAYLOAD_PATH}")
        if synced_static_paths:
            print("Snapshot frontend statis ikut disinkronkan ke:")
            for synced_path in synced_static_paths:
                print(f"- {synced_path}")

    if args.no_serve:
        return

    server = ThreadingHTTPServer((args.host, args.port), FloodGISRequestHandler)
    print(f"FloodGIS backend aktif di http://{args.host}:{args.port}/")
    print(f"Endpoint API prediksi: http://{args.host}:{args.port}/api/predictions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()
