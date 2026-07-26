from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from download_openmeteo_historical_jaktim import (
    DEFAULT_OUTPUT,
    DISTRICT_COORDS,
    build_dataframe,
    build_url,
    clamp_archive_end_date,
    fetch_json,
    get_archive_safe_end_date,
    validate_date,
)


DATE_FORMAT = "%d/%m/%Y"
EXPECTED_COLUMNS = [
    "Tanggal",
    "Kecamatan",
    "Curah Hujan (mm)",
    "Suhu Rata-rata (C)",
    "Kelembapan Rata-rata (%)",
    "Kecepatan Angin Max (km/h)",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update incremental dataset Open-Meteo Jakarta Timur, lalu merge ke "
            "Master_Data_Spasial_Jaktim_1990_sekarang.csv."
        )
    )
    parser.add_argument(
        "--dataset-path",
        default=str(DEFAULT_OUTPUT),
        help=f"Lokasi file CSV dataset utama. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help=(
            "Opsional: tanggal awal update format YYYY-MM-DD. "
            "Kalau kosong, script mulai dari tanggal terakhir dataset dikurangi backfill."
        ),
    )
    parser.add_argument(
        "--end-date",
        default=get_archive_safe_end_date(),
        help=(
            "Tanggal akhir update format YYYY-MM-DD. "
            f"Default aman archive: {get_archive_safe_end_date()}"
        ),
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=3,
        help=(
            "Jumlah hari mundur dari tanggal terakhir dataset untuk di-fetch ulang "
            "agar revisi data harian ikut tertangkap. Default: 3"
        ),
    )
    parser.add_argument(
        "--timezone",
        default="Asia/Jakarta",
        help="Timezone yang dipakai API. Default: Asia/Jakarta",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Jeda antar request untuk mengurangi risiko rate limit. Default: 1.0",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Jumlah maksimum retry saat request gagal. Default: 5",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout request dalam detik. Default: 60",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Opsional: model Open-Meteo, misalnya era5. Kosongkan jika tidak perlu.",
    )
    parser.add_argument(
        "--rate-limit-wait",
        type=float,
        default=65.0,
        help="Waktu tunggu default saat kena HTTP 429, dalam detik. Default: 65",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Unduh dan hitung hasil merge tanpa menulis ulang file dataset.",
    )
    return parser.parse_args()


def build_empty_dataset() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def load_existing_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"[INFO] Dataset belum ada di {path}. Script akan membuat file baru.")
        return build_empty_dataset()

    dataset = pd.read_csv(path, sep=";")
    missing_columns = [column for column in EXPECTED_COLUMNS if column not in dataset.columns]
    if missing_columns:
        raise ValueError(
            f"Dataset {path} tidak memiliki kolom wajib: {', '.join(missing_columns)}"
        )

    return dataset[EXPECTED_COLUMNS].copy()


def resolve_start_date(existing_dataset: pd.DataFrame, explicit_start_date: str, backfill_days: int) -> str:
    if explicit_start_date.strip():
        return validate_date(explicit_start_date.strip())

    if existing_dataset.empty:
        return "1990-01-01"

    latest_date = pd.to_datetime(
        existing_dataset["Tanggal"], format=DATE_FORMAT, dayfirst=True
    ).max()
    start_date = latest_date.date() - timedelta(days=max(0, backfill_days))
    return start_date.isoformat()


def download_incremental_dataset(args: argparse.Namespace, start_date: str, end_date: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(DISTRICT_COORDS)

    for index, (district_name, (latitude, longitude)) in enumerate(DISTRICT_COORDS.items(), start=1):
        print(f"[{index}/{total}] Mengunduh update {district_name} dari {start_date} s.d. {end_date}...")
        url = build_url(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            timezone=args.timezone,
            model=args.model,
        )
        payload = fetch_json(
            url=url,
            timeout=args.timeout,
            max_retries=args.max_retries,
            sleep_seconds=args.sleep_seconds,
            rate_limit_wait=args.rate_limit_wait,
        )
        frames.append(build_dataframe(district_name, payload))
        if index < total:
            time.sleep(args.sleep_seconds)

    dataset = pd.concat(frames, ignore_index=True)
    dataset = dataset[EXPECTED_COLUMNS].copy()
    return dataset


def merge_datasets(existing_dataset: pd.DataFrame, incremental_dataset: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([existing_dataset, incremental_dataset], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Tanggal", "Kecamatan"], keep="last")
    combined["Tanggal_sort"] = pd.to_datetime(combined["Tanggal"], format=DATE_FORMAT, dayfirst=True)
    combined = combined.sort_values(["Tanggal_sort", "Kecamatan"]).drop(columns=["Tanggal_sort"])
    combined = combined.reset_index(drop=True)
    return combined


def main() -> None:
    args = parse_args()
    requested_end_date = validate_date(args.end_date)
    args.end_date, end_date_was_clamped = clamp_archive_end_date(requested_end_date)

    dataset_path = Path(args.dataset_path).resolve()
    dataset_path.parent.mkdir(parents=True, exist_ok=True)

    existing_dataset = load_existing_dataset(dataset_path)
    start_date = resolve_start_date(existing_dataset, args.start_date, args.backfill_days)

    if start_date > args.end_date:
        raise ValueError(
            f"Tanggal awal update ({start_date}) tidak boleh lebih besar dari tanggal akhir ({args.end_date})."
        )

    print(f"[INFO] Dataset target: {dataset_path}")
    print(f"[INFO] Periode update incremental: {start_date} s.d. {args.end_date}")
    if end_date_was_clamped:
        print(
            "[INFO] Tanggal akhir update otomatis dimundurkan dari "
            f"{requested_end_date} ke {args.end_date} karena archive Open-Meteo "
            "belum tentu menyediakan data hari ini."
        )

    incremental_dataset = download_incremental_dataset(args, start_date, args.end_date)
    merged_dataset = merge_datasets(existing_dataset, incremental_dataset)

    latest_before = (
        pd.to_datetime(existing_dataset["Tanggal"], format=DATE_FORMAT, dayfirst=True).max().strftime("%Y-%m-%d")
        if not existing_dataset.empty
        else "-"
    )
    latest_after = (
        pd.to_datetime(merged_dataset["Tanggal"], format=DATE_FORMAT, dayfirst=True).max().strftime("%Y-%m-%d")
        if not merged_dataset.empty
        else "-"
    )

    print(f"[INFO] Baris lama : {len(existing_dataset):,}")
    print(f"[INFO] Baris update: {len(incremental_dataset):,}")
    print(f"[INFO] Baris akhir: {len(merged_dataset):,}")
    print(f"[INFO] Tanggal terbaru sebelum update: {latest_before}")
    print(f"[INFO] Tanggal terbaru sesudah update: {latest_after}")

    if args.dry_run:
        print("[INFO] Dry-run aktif. Dataset tidak ditulis ke file.")
        return

    merged_dataset.to_csv(dataset_path, sep=";", index=False)
    print(f"[OK] Dataset berhasil diperbarui: {dataset_path}")


if __name__ == "__main__":
    main()
