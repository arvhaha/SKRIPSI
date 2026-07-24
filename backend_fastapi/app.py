from pathlib import Path
from typing import Any, Dict, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from backend_core.schemas import (
    AdminOverrideRequest,
    AdminOverrideResponse,
    GenericStatusResponse,
    HealthResponse,
    PublicationStateResponse,
    PublishResponse,
)
from backend_core.services.admin_service import (
    publish_public_snapshot,
    save_drainage_override,
)
from backend_core.services.auth_service import (
    get_admin_access_state,
    is_same_origin_admin_referer,
    validate_basic_auth,
)
from backend_core.services.prediction_service import (
    get_admin_live_preview_payload,
    get_geojson_payload,
    get_public_prediction_payload,
)
from backend_core.services.prediction_history_service import (
    get_prediction_run_by_id,
    get_prediction_run_history,
)
from backend_core.services.publication_service import get_publication_summary
from backend_core.services.runtime_service import (
    get_application_name,
    get_cors_origins,
    get_runtime_health_payload,
)


app = FastAPI(
    title=f"{get_application_name()} FastAPI",
    version="0.1.0",
    description="FastAPI backend FloodGIS yang memakai service layer bersama di atas logika inti backend.",
)

ROOT = Path(__file__).resolve().parent.parent

allowed_origins = get_cors_origins()
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
        allow_credentials="*" not in allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def enforce_admin_api_access(
    authorization: Optional[str] = Header(default=None),
    referer: Optional[str] = Header(default=None),
    host: Optional[str] = Header(default=None),
) -> None:
    access_state = get_admin_access_state()

    if access_state["isLocked"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "API admin dinonaktifkan sampai proteksi admin dikonfigurasi. "
                "Atur ADMIN_USERNAME dan ADMIN_PASSWORD di environment deployment."
            ),
        )

    if not access_state["isConfigured"]:
        return

    if validate_basic_auth(authorization):
        return

    if is_same_origin_admin_referer(referer, host):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autentikasi admin diperlukan untuk mengakses API admin.",
        headers={"WWW-Authenticate": 'Basic realm="FloodGIS Admin"'},
    )


def build_admin_html_response(authorization: Optional[str]) -> Union[FileResponse, PlainTextResponse]:
    access_state = get_admin_access_state()

    if access_state["isLocked"]:
        return PlainTextResponse(
            (
                "Halaman admin dinonaktifkan sampai proteksi admin dikonfigurasi. "
                "Atur ADMIN_USERNAME dan ADMIN_PASSWORD di environment deployment."
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if access_state["isConfigured"] and not validate_basic_auth(authorization):
        return PlainTextResponse(
            "Autentikasi admin diperlukan untuk membuka halaman ini.\n",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="FloodGIS Admin"'},
        )

    return FileResponse(ROOT / "admin.html")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
        },
        headers=exc.headers or None,
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**get_runtime_health_payload())


@app.get("/api/predictions")
def get_predictions() -> Dict[str, Any]:
    return get_public_prediction_payload()


@app.get("/api/geojson")
def get_geojson() -> Dict[str, Any]:
    return get_geojson_payload()


@app.get("/api/admin/publication", response_model=PublicationStateResponse, dependencies=[Depends(enforce_admin_api_access)])
def get_admin_publication_state() -> PublicationStateResponse:
    summary = get_publication_summary()
    return PublicationStateResponse(**summary)


@app.get("/api/admin/predictions/live", dependencies=[Depends(enforce_admin_api_access)])
def get_admin_live_predictions() -> Dict[str, Any]:
    return get_admin_live_preview_payload()


@app.get("/api/admin/prediction-runs", dependencies=[Depends(enforce_admin_api_access)])
def get_admin_prediction_runs(limit: int = 20) -> Dict[str, Any]:
    return get_prediction_run_history(limit=limit)


@app.get("/api/admin/prediction-runs/{run_id}", dependencies=[Depends(enforce_admin_api_access)])
def get_admin_prediction_run_detail(run_id: int) -> Dict[str, Any]:
    run_detail = get_prediction_run_by_id(run_id)
    if run_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run prediksi tidak ditemukan.",
        )
    return run_detail


@app.post(
    "/api/admin/overrides",
    response_model=AdminOverrideResponse,
    dependencies=[Depends(enforce_admin_api_access)],
)
def save_admin_override(payload: AdminOverrideRequest) -> AdminOverrideResponse:
    try:
        result = save_drainage_override(
            district_name=payload.districtName,
            drainage_condition=payload.drainageCondition,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menyimpan draft admin ke file override. {error}",
        ) from error

    return AdminOverrideResponse(**result)


@app.post(
    "/api/admin/publish",
    response_model=PublishResponse,
    dependencies=[Depends(enforce_admin_api_access)],
)
def publish_admin_predictions() -> PublishResponse:
    try:
        published_payload = publish_public_snapshot()
    except Exception as error:  # pragma: no cover - defensive response
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot publik gagal dipublish dari panel admin. {error}",
        ) from error

    return PublishResponse(
        status="ok",
        message=(
            "Snapshot publik berhasil dipublish dari panel admin. "
            f"{published_payload.get('meta', {}).get('publishedOverrideResetCount', 0)} draft override direset."
        ),
        publishedAt=published_payload.get("meta", {}).get("publishedAt"),
    )


@app.get("/", include_in_schema=False, response_model=None)
def serve_root() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/admin.html", include_in_schema=False, response_model=None)
def serve_admin_page(authorization: Optional[str] = Header(default=None)) -> Union[FileResponse, PlainTextResponse]:
    return build_admin_html_response(authorization)


@app.get("/{asset_path:path}", include_in_schema=False, response_model=None)
def serve_static_asset(asset_path: str, authorization: Optional[str] = Header(default=None)) -> FileResponse:
    normalized_path = asset_path.strip().lstrip("/")
    candidate_path = (ROOT / normalized_path).resolve()

    try:
        candidate_path.relative_to(ROOT)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File tidak ditemukan.") from error

    if normalized_path == "admin.html":
        response = build_admin_html_response(authorization)
        if isinstance(response, FileResponse):
            return response
        raise HTTPException(
            status_code=response.status_code,
            detail=response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body),
            headers=dict(response.headers),
        )

    if not candidate_path.exists() or not candidate_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File tidak ditemukan.")

    return FileResponse(candidate_path)
