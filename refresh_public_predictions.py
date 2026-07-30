from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DEFAULT_TIMEZONE = "Asia/Jakarta"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Runner lintas platform untuk refresh data cuaca dan ekspor prediksi "
            "publik HydroGIS."
        )
    )
    parser.add_argument(
        "--app-environment",
        default="production",
        choices=["local", "staging", "production"],
        help="Environment aplikasi saat ekspor prediksi. Default: production",
    )
    parser.add_argument(
        "--app-environment-label",
        default="",
        help="Label environment yang dikirim ke frontend. Default: uppercase dari app-environment.",
    )
    parser.add_argument(
        "--app-name",
        default="FloodGIS Jakarta Timur",
        help="Nama aplikasi yang dikirim ke payload metadata.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone referensi untuk menentukan tanggal hari ini. Default: {DEFAULT_TIMEZONE}",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help=(
            "Tanggal akhir update dalam format YYYY-MM-DD. Kalau kosong, "
            "otomatis memakai tanggal hari ini dikurangi source-lag-days sesuai timezone."
        ),
    )
    parser.add_argument(
        "--source-lag-days",
        type=int,
        default=1,
        help=(
            "Jarak hari dari tanggal akses ke observasi sumber terakhir yang dianggap aman "
            "untuk diambil otomatis. Default: 1"
        ),
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=3,
        help="Jumlah hari mundur untuk re-fetch data sumber. Default: 3",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Jeda antar request Open-Meteo. Default: 1.0",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Jumlah retry request Open-Meteo. Default: 5",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout request Open-Meteo dalam detik. Default: 60",
    )
    parser.add_argument(
        "--rate-limit-wait",
        type=float,
        default=65.0,
        help="Waktu tunggu saat kena 429 dari Open-Meteo. Default: 65",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Opsional: nama model Open-Meteo, misalnya era5.",
    )
    parser.add_argument(
        "--skip-source-update",
        action="store_true",
        help="Lewati langkah update data sumber Open-Meteo.",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Lewati langkah ekspor data/east-jakarta-predictions.json.",
    )
    parser.add_argument(
        "--source-update-dry-run",
        action="store_true",
        help="Jalankan update sumber tanpa menulis ulang dataset utama.",
    )
    return parser.parse_args()


def resolve_end_date(timezone_name: str, explicit_value: str, source_lag_days: int) -> str:
    if explicit_value.strip():
        return explicit_value.strip()
    return (
        datetime.now(ZoneInfo(timezone_name)).date()
        - timedelta(days=max(0, int(source_lag_days)))
    ).isoformat()


def run_step(command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[RUN] {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    args = parse_args()
    end_date = resolve_end_date(args.timezone, args.end_date, args.source_lag_days)
    environment_label = args.app_environment_label.strip() or args.app_environment.upper()

    if not args.skip_source_update:
        source_command = [
            sys.executable,
            str(ROOT / "update_openmeteo_dataset_jaktim.py"),
            "--end-date",
            end_date,
            "--backfill-days",
            str(args.backfill_days),
            "--timezone",
            args.timezone,
            "--sleep-seconds",
            str(args.sleep_seconds),
            "--max-retries",
            str(args.max_retries),
            "--timeout",
            str(args.timeout),
            "--rate-limit-wait",
            str(args.rate_limit_wait),
        ]
        if args.model.strip():
            source_command.extend(["--model", args.model.strip()])
        if args.source_update_dry_run:
            source_command.append("--dry-run")
        run_step(source_command)

    if not args.skip_export:
        export_env = os.environ.copy()
        export_env["APP_ENV"] = args.app_environment
        export_env["APP_ENV_LABEL"] = environment_label
        export_env["APP_NAME"] = args.app_name

        export_command = [
            sys.executable,
            str(ROOT / "webgis_backend.py"),
            "--export-static-json",
            "--no-serve",
        ]
        run_step(export_command, env=export_env)

    print("[OK] Refresh publik selesai.")


if __name__ == "__main__":
    main()
