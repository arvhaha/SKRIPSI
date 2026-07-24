from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from backend_core.drainage_logic import save_admin_override
from backend_core.legacy_core import (
    ROOT,
    is_admin_auth_configured,
    is_admin_page_locked,
    is_protected_admin_html_path,
    resolve_cors_allow_origin,
    serialize_payload,
    validate_admin_basic_auth_header,
)
from backend_core.prediction_logic import load_geojson_payload
from backend_core.publication_logic import (
    build_admin_live_preview_response,
    load_public_prediction_payload,
    publish_admin_snapshot,
)


class FloodGISRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def should_attach_cors_headers(self) -> bool:
        request_path = urlparse(self.path).path
        return request_path.startswith("/api/")

    def append_cors_headers(self) -> None:
        allow_origin = resolve_cors_allow_origin(self.headers.get("Origin"))
        if not allow_origin:
            return

        self.send_header("Access-Control-Allow-Origin", allow_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if allow_origin != "*":
            self.send_header("Vary", "Origin")

    def end_headers(self) -> None:
        if self.should_attach_cors_headers():
            self.append_cors_headers()
        super().end_headers()

    def do_OPTIONS(self) -> None:
        request_path = urlparse(self.path).path
        if request_path.startswith("/api/") and self.headers.get("Origin"):
            if not resolve_cors_allow_origin(self.headers.get("Origin")):
                self.respond_text(
                    "Origin frontend belum diizinkan oleh backend.",
                    status=HTTPStatus.FORBIDDEN,
                )
                return

        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/api/health":
            self.respond_json({"status": "ok"})
            return

        if parsed_path.path.startswith("/api/admin/"):
            if self.enforce_admin_api_access():
                return

        if parsed_path.path == "/api/admin/predictions/live":
            try:
                payload = build_admin_live_preview_response()
            except Exception as error:  # pragma: no cover
                self.respond_json(
                    {
                        "status": "error",
                        "message": "Backend gagal membangun draft admin.",
                        "detail": str(error),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self.respond_json(payload)
            return

        if parsed_path.path == "/api/predictions":
            try:
                payload = load_public_prediction_payload()
            except Exception as error:  # pragma: no cover
                self.respond_json(
                    {
                        "status": "error",
                        "message": "Backend gagal memuat payload publik.",
                        "detail": str(error),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self.respond_json(payload)
            return

        if parsed_path.path == "/api/geojson":
            try:
                payload = load_geojson_payload()
            except Exception as error:  # pragma: no cover
                self.respond_json(
                    {
                        "status": "error",
                        "message": "Backend gagal memuat GeoJSON wilayah.",
                        "detail": str(error),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self.respond_json(payload)
            return

        if is_protected_admin_html_path(parsed_path.path):
            if self.enforce_admin_page_access():
                return

        if parsed_path.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self) -> None:
        parsed_path = urlparse(self.path)
        if not parsed_path.path.startswith("/api/admin/"):
            self.respond_json(
                {
                    "status": "error",
                    "message": "Endpoint POST tidak tersedia.",
                },
                status=HTTPStatus.NOT_FOUND,
            )
            return

        if self.enforce_admin_api_access():
            return

        if parsed_path.path == "/api/admin/overrides":
            self.handle_save_admin_override()
            return

        if parsed_path.path == "/api/admin/publish":
            self.handle_publish_admin_snapshot()
            return

        self.respond_json(
            {
                "status": "error",
                "message": "Endpoint admin tidak ditemukan.",
            },
            status=HTTPStatus.NOT_FOUND,
        )

    def enforce_admin_page_access(self) -> bool:
        if is_admin_page_locked():
            self.respond_text(
                (
                    "Halaman admin dinonaktifkan sampai proteksi admin dikonfigurasi. "
                    "Atur ADMIN_USERNAME dan ADMIN_PASSWORD di environment deployment."
                ),
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return True

        if not is_admin_auth_configured():
            return False

        if validate_admin_basic_auth_header(self.headers.get("Authorization")):
            return False

        body = "Autentikasi admin diperlukan untuk membuka halaman ini.\n".encode("utf-8")
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="FloodGIS Admin"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True

    def enforce_admin_api_access(self) -> bool:
        if is_admin_page_locked():
            self.respond_json(
                {
                    "status": "error",
                    "message": (
                        "API admin dinonaktifkan sampai proteksi admin dikonfigurasi. "
                        "Atur ADMIN_USERNAME dan ADMIN_PASSWORD di environment deployment."
                    ),
                },
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return True

        if not is_admin_auth_configured():
            return False

        if validate_admin_basic_auth_header(self.headers.get("Authorization")):
            return False

        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="FloodGIS Admin API"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        body = serialize_payload(
            {
                "status": "error",
                "message": "Autentikasi admin diperlukan untuk mengakses API admin.",
            }
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def read_json_body(self) -> dict[str, Any]:
        content_length_header = self.headers.get("Content-Length", "0")
        try:
            content_length = max(0, int(content_length_header))
        except ValueError as error:
            raise ValueError("Header Content-Length tidak valid.") from error

        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        if not raw_body:
            return {}

        try:
            loaded = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Body JSON tidak valid.") from error

        if not isinstance(loaded, dict):
            raise ValueError("Body request harus berupa objek JSON.")

        return loaded

    def handle_save_admin_override(self) -> None:
        try:
            request_payload = self.read_json_body()
            result = save_admin_override(
                district_name=request_payload.get("districtName"),
                drainage_condition_value=request_payload.get("drainageCondition"),
            )
        except ValueError as error:
            self.respond_json(
                {
                    "status": "error",
                    "message": str(error),
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        except OSError as error:
            self.respond_json(
                {
                    "status": "error",
                    "message": "Gagal menyimpan draft admin ke file override.",
                    "detail": str(error),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.respond_json(
            {
                "status": result["status"],
                "message": result["message"],
                "districtName": result["districtName"],
                "districtLabel": result["districtLabel"],
                "hasOverride": result["hasOverride"],
                "drainageCondition": result["drainageCondition"],
            }
        )

    def handle_publish_admin_snapshot(self) -> None:
        try:
            published_payload = publish_admin_snapshot()
        except Exception as error:  # pragma: no cover
            self.respond_json(
                {
                    "status": "error",
                    "message": "Snapshot publik gagal dipublish dari panel admin.",
                    "detail": str(error),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.respond_json(
            {
                "status": "ok",
                "message": (
                    "Snapshot publik berhasil dipublish dari panel admin. "
                    f"{published_payload.get('meta', {}).get('publishedOverrideResetCount', 0)} draft override direset."
                ),
                "publishedAt": published_payload.get("meta", {}).get("publishedAt"),
            }
        )

    def respond_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = serialize_payload(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def respond_text(self, message: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
