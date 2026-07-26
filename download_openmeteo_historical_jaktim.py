from __future__ import annotations

import argparse
import json
import re
import ssl
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from backend_core.path_config import DATASET_PATH

try:
    import certifi
except ImportError:  # pragma: no cover - optional dependency fallback
    certifi = None

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = DATASET_PATH
API_URL = "https://archive-api.open-meteo.com/v1/archive"
END_DATE_RANGE_PATTERN = re.compile(
    r"Parameter 'end_date' is out of allowed range from \d{4}-\d{2}-\d{2} to (\d{4}-\d{2}-\d{2})"
)
DAILY_FIELDS = [
    "precipitation_sum",
    "temperature_2m_mean",
    "relative_humidity_2m_mean",
    "wind_speed_10m_max",
]

DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "Matraman": (-6.2010, 106.8640),
    "Pulo Gadung": (-6.1930, 106.8900),
    "Jatinegara": (-6.2250, 106.8750),
    "Duren Sawit": (-6.2300, 106.9170),
    "Kramat Jati": (-6.2730, 106.8680),
    "Makasar": (-6.2690, 106.8900),
    "Pasar Rebo": (-6.3150, 106.8580),
    "Ciracas": (-6.3260, 106.8770),
    "Cipayung": (-6.3170, 106.9010),
    "Cakung": (-6.1850, 106.9400),
}


def build_ssl_context() -> ssl.SSLContext:
    """Prefer certifi bundle to avoid broken Windows store certs in some envs."""
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unduh data historis cuaca 10 kecamatan Jakarta Timur dari Open-Meteo."
    )
    parser.add_argument(
        "--start-date",
        default="1990-01-01",
        help="Tanggal awal dalam format YYYY-MM-DD. Default: 1990-01-01",
    )
    parser.add_argument(
        "--end-date",
        default=get_archive_safe_end_date(),
        help=(
            "Tanggal akhir dalam format YYYY-MM-DD. "
            f"Default aman archive: {get_archive_safe_end_date()}"
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Lokasi file CSV output. Default: {DEFAULT_OUTPUT}",
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
    return parser.parse_args()


def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Tanggal '{value}' harus format YYYY-MM-DD.") from exc
    return value


def get_archive_safe_end_date(today: date | None = None) -> str:
    current_date = today or date.today()
    return (current_date - timedelta(days=1)).isoformat()


def clamp_archive_end_date(end_date: str, today: date | None = None) -> tuple[str, bool]:
    validated_end_date = validate_date(end_date)
    latest_safe_end_date = get_archive_safe_end_date(today=today)
    if validated_end_date > latest_safe_end_date:
        return latest_safe_end_date, True
    return validated_end_date, False


def extract_archive_max_end_date(error_detail: str) -> str | None:
    match = END_DATE_RANGE_PATTERN.search(error_detail)
    if match:
        return match.group(1)
    return None


def build_url(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    timezone: str,
    model: str,
) -> str:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_FIELDS),
        "timezone": timezone,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    if model.strip():
        params["models"] = model.strip()
    return f"{API_URL}?{urlencode(params)}"


def fetch_json(
    url: str,
    timeout: int,
    max_retries: int,
    sleep_seconds: float,
    rate_limit_wait: float,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "skripsi-open-meteo-fetcher/1.0",
        "Accept": "application/json",
    }
    ssl_context = build_ssl_context()

    for attempt in range(1, max_retries + 1):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=timeout, context=ssl_context) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                retry_after_header = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    retry_after_value = float(retry_after_header) if retry_after_header else 0.0
                except ValueError:
                    retry_after_value = 0.0
                wait_seconds = max(rate_limit_wait, retry_after_value, sleep_seconds * attempt * 2)
                print(
                    f"   [WARN] Kena rate limit (429). Retry {attempt}/{max_retries} dalam {wait_seconds:.1f} detik..."
                )
                time.sleep(wait_seconds)
                continue
            detail = exc.read().decode("utf-8", errors="ignore")
            max_end_date = extract_archive_max_end_date(detail)
            if max_end_date:
                raise RuntimeError(
                    "Open-Meteo archive belum menyediakan tanggal yang diminta. "
                    f"Tanggal maksimum yang diizinkan saat ini: {max_end_date}.\n"
                    f"URL: {url}\nDetail: {detail}"
                ) from exc
            raise RuntimeError(
                f"HTTP {exc.code} saat memanggil Open-Meteo.\nURL: {url}\nDetail: {detail}"
            ) from exc
        except URLError as exc:
            if attempt < max_retries:
                wait_seconds = sleep_seconds * attempt
                print(
                    f"   [WARN] Koneksi bermasalah. Retry {attempt}/{max_retries} dalam {wait_seconds:.1f} detik..."
                )
                time.sleep(wait_seconds)
                continue
            raise RuntimeError(f"Gagal menghubungi Open-Meteo.\nURL: {url}\nError: {exc}") from exc

    raise RuntimeError("Request gagal setelah seluruh retry dicoba.")


def convert_series(values: list[Any], digits: int) -> list[float | None]:
    converted: list[float | None] = []
    for value in values:
        if value is None:
            converted.append(None)
        else:
            converted.append(round(float(value), digits))
    return converted


def build_dataframe(kecamatan: str, payload: dict[str, Any]) -> pd.DataFrame:
    daily = payload.get("daily")
    if not daily:
        raise ValueError(f"Respons API untuk {kecamatan} tidak memiliki blok 'daily'.")

    dates = daily.get("time", [])
    rainfall = convert_series(daily.get("precipitation_sum", []), 1)
    temperature = convert_series(daily.get("temperature_2m_mean", []), 1)
    humidity_raw = daily.get("relative_humidity_2m_mean", [])
    humidity = [None if value is None else int(round(float(value))) for value in humidity_raw]
    wind = convert_series(daily.get("wind_speed_10m_max", []), 1)

    lengths = {len(dates), len(rainfall), len(temperature), len(humidity), len(wind)}
    if len(lengths) != 1:
        raise ValueError(f"Panjang data harian untuk {kecamatan} tidak konsisten: {lengths}")

    frame = pd.DataFrame(
        {
            "Tanggal": pd.to_datetime(dates, format="%Y-%m-%d").strftime("%d/%m/%Y"),
            "Kecamatan": kecamatan,
            "Curah Hujan (mm)": rainfall,
            "Suhu Rata-rata (C)": temperature,
            "Kelembapan Rata-rata (%)": humidity,
            "Kecepatan Angin Max (km/h)": wind,
        }
    )
    return frame


def download_all_districts(args: argparse.Namespace) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(DISTRICT_COORDS)

    for index, (kecamatan, (lat, lon)) in enumerate(DISTRICT_COORDS.items(), start=1):
        print(f"[{index}/{total}] Mengunduh data {kecamatan} ({lat}, {lon})...")
        url = build_url(
            latitude=lat,
            longitude=lon,
            start_date=args.start_date,
            end_date=args.end_date,
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
        frames.append(build_dataframe(kecamatan, payload))
        if index < total:
            time.sleep(args.sleep_seconds)

    dataset = pd.concat(frames, ignore_index=True)
    dataset["Tanggal_sort"] = pd.to_datetime(dataset["Tanggal"], format="%d/%m/%Y")
    dataset = dataset.sort_values(["Tanggal_sort", "Kecamatan"]).drop(columns=["Tanggal_sort"])
    dataset = dataset.reset_index(drop=True)
    return dataset


def main() -> None:
    args = parse_args()
    args.start_date = validate_date(args.start_date)
    args.end_date, end_date_was_clamped = clamp_archive_end_date(args.end_date)

    if args.start_date > args.end_date:
        raise ValueError("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Mulai unduh data Open-Meteo untuk 10 kecamatan Jakarta Timur...")
    print(f"Periode: {args.start_date} s.d. {args.end_date}")
    if end_date_was_clamped:
        print(
            "[INFO] Tanggal akhir otomatis dimundurkan ke tanggal aman archive "
            f"({args.end_date}) karena data hari ini belum tentu tersedia."
        )
    if args.model.strip():
        print(f"Model API: {args.model.strip()}")

    dataset = download_all_districts(args)
    dataset.to_csv(output_path, sep=";", index=False)

    print(f"Selesai. Total baris: {len(dataset):,}".replace(",", "."))
    print(f"File tersimpan di: {output_path}")


if __name__ == "__main__":
    main()
