from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from backend_core.path_config import APP_ENV, APP_ENV_LABEL, APP_NAME, ROOT


REFRESH_SCRIPT_PATH = ROOT / "refresh_public_predictions.py"
DEFAULT_REFRESH_TIMEOUT_SECONDS = int(os.getenv("FLOODGIS_REFRESH_TIMEOUT_SECONDS", "900"))


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
        "message": "Sumber data dan payload prediksi berhasil direfresh dari backend.",
        "stdout": stdout,
    }

