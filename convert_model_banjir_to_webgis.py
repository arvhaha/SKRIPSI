import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NOTEBOOK_PATH = ROOT / "MODEL_BANJIR.ipynb"
OUTPUT_PATH = ROOT / "data" / "east-jakarta-predictions.json"
DATASET_ID = "model-banjir-ipynb-webgis-v1"


SIMULATION_PATTERN = re.compile(
    r"Hari ke-(?P<day>\d+)\s+\|\s+Probabilitas Badai:\s+"
    r"(?P<percent>\d+(?:\.\d+)?)%\s*\n"
    r"-> Warna Poligon WebGIS\s+:\s+Level\s+(?P<level>\d+):\s+"
    r"(?P<color>[A-Z]+)\s+\((?P<description>.*?)\)\s*\n"
    r"-> Kejadian Asli di BMKG:\s+(?P<actual>.+?)(?:\n\n|$)",
    re.DOTALL,
)


DEFAULT_DISTRICTS = [
    {"name": "CAKUNG", "label": "Cakung", "drainageCondition": "Buruk"},
    {"name": "CIPAYUNG", "label": "Cipayung", "drainageCondition": "Sedang"},
    {"name": "CIRACAS", "label": "Ciracas", "drainageCondition": "Sedang"},
    {"name": "DUREN SAWIT", "label": "Duren Sawit", "drainageCondition": "Buruk"},
    {"name": "JATINEGARA", "label": "Jatinegara", "drainageCondition": "Buruk"},
    {"name": "KRAMAT JATI", "label": "Kramat Jati", "drainageCondition": "Sedang"},
    {"name": "MAKASAR", "label": "Makasar", "drainageCondition": "Baik"},
    {"name": "MATRAMAN", "label": "Matraman", "drainageCondition": "Sedang"},
    {"name": "PASAR REBO", "label": "Pasar Rebo", "drainageCondition": "Baik"},
    {"name": "PULOGADUNG", "label": "Pulogadung", "drainageCondition": "Buruk"},
]


def load_notebook_text():
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    chunks = []

    for cell in notebook.get("cells", []):
        for output in cell.get("outputs", []):
            if "text" in output:
                chunks.append("".join(output["text"]))

    return "\n".join(chunks)


def extract_forecasts():
    text = load_notebook_text()
    forecasts = []

    for match in SIMULATION_PATTERN.finditer(text):
        day = int(match.group("day"))
        percent = float(match.group("percent"))
        probability = round(percent / 100, 4)
        level = int(match.group("level"))
        color = match.group("color").title()
        description = " ".join(match.group("description").split())
        actual = " ".join(match.group("actual").split())

        forecasts.append(
            {
                "dayIndex": day,
                "forecastLabel": f"Hari ke-{day}",
                "probabilityWaspada": probability,
                "probabilityWaspadaPercent": percent,
                "webgisLevel": level,
                "webgisColor": color,
                "webgisLevelLabel": f"Level {level}: {color}",
                "webgisDescription": description,
                "actualStatus": actual,
            }
        )

    if not forecasts:
        raise RuntimeError(
            "Output simulasi WebGIS tidak ditemukan di MODEL_BANJIR.ipynb. "
            "Jalankan cell 'SIMULASI OUTPUT UNTUK FRONTEND WEBGIS' dulu."
        )

    return sorted(forecasts, key=lambda item: item["dayIndex"])


def load_district_templates():
    if not OUTPUT_PATH.exists():
        return DEFAULT_DISTRICTS

    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    districts = payload.get("districts") or []

    if len(districts) < len(DEFAULT_DISTRICTS):
        return DEFAULT_DISTRICTS

    return [
        {
            "name": district.get("name", fallback["name"]),
            "label": district.get("label", fallback["label"]),
            "drainageCondition": district.get(
                "drainageCondition", fallback["drainageCondition"]
            ),
        }
        for district, fallback in zip(districts, DEFAULT_DISTRICTS)
    ]


def risk_category_from_level(level):
    if level >= 3:
        return "Tinggi"
    if level == 2:
        return "Sedang"
    return "Rendah"


def recommendation_from_level(level):
    if level >= 4:
        return "Aktifkan kesiapsiagaan tinggi dan pantau titik genangan prioritas."
    if level == 3:
        return "Siapkan pemantauan intensif pada saluran dan area rawan genangan."
    if level == 2:
        return "Lakukan monitoring berkala dan pembersihan saluran lokal."
    return "Pertahankan pemantauan rutin dan pemeliharaan preventif."


def estimate_rainfall_for_display(probability, level):
    # Notebook memberi probabilitas waspada, bukan prediksi mm langsung.
    # Nilai ini hanya konversi tampilan agar komponen WebGIS lama tetap terisi.
    base_mm_by_level = {
        1: 22,
        2: 72,
        3: 122,
        4: 178,
    }
    base = base_mm_by_level.get(level, 72)
    return int(round(base * (0.88 + probability * 0.24)))


def build_district_payload(template, forecast):
    probability = forecast["probabilityWaspada"]
    percent = forecast["probabilityWaspadaPercent"]
    level = forecast["webgisLevel"]
    level_label = forecast["webgisLevelLabel"]
    description = forecast["webgisDescription"]

    return {
        "name": template["name"],
        "label": template["label"],
        "predictedRainfallMm": estimate_rainfall_for_display(probability, level),
        "drainageCondition": template["drainageCondition"],
        "riskCategory": risk_category_from_level(level),
        "riskScore": probability,
        "probabilityWaspada": probability,
        "probabilityWaspadaPercent": percent,
        "webgisLevel": level,
        "webgisColor": forecast["webgisColor"],
        "webgisLevelLabel": level_label,
        "webgisDescription": description,
        "forecastLabel": forecast["forecastLabel"],
        "actualStatusFromNotebookTest": forecast["actualStatus"],
        "rainfallDisplayNote": (
            "Estimasi tampilan dari probabilitas model; notebook tidak "
            "mengeluarkan prediksi curah hujan dalam mm per kecamatan."
        ),
        "summary": (
            f"Output MODEL_BANJIR.ipynb untuk {forecast['forecastLabel']} memberi "
            f"probabilitas waspada {percent:.1f}% ({level_label}: {description}). "
            f"Nilai ini dipetakan ke {template['label']} sebagai skenario visual WebGIS."
        ),
        "recommendation": recommendation_from_level(level),
    }


def build_payload():
    forecasts = extract_forecasts()
    templates = load_district_templates()
    jakarta_tz = timezone(timedelta(hours=7))

    districts = [
        build_district_payload(template, forecast)
        for template, forecast in zip(templates, forecasts)
    ]

    return {
        "meta": {
            "datasetId": DATASET_ID,
            "model": "Hybrid Bi-LSTM + XGBoost dari MODEL_BANJIR.ipynb",
            "updatedAt": datetime.now(jakarta_tz).isoformat(timespec="seconds"),
            "refreshInterval": "Sesuai ekspor notebook",
            "rainfallSource": "MODEL_BANJIR.ipynb - simulasi 10 hari data test",
            "drainageSource": "Data kondisi drainase statis untuk display WebGIS",
            "forecastHorizonDays": len(forecasts),
            "modelAccuracyFromNotebook": 0.9038,
            "modelAccuracyNote": (
                "Akurasi biner dari notebook; recall kelas waspada masih rendah, "
                "jadi gunakan sebagai simulasi visual, bukan peringatan operasional."
            ),
            "conversionNote": (
                "Notebook menghasilkan prediksi berbasis hari, bukan per kecamatan. "
                "Untuk kebutuhan frontend statis, 10 output hari test dipetakan ke "
                "10 kecamatan Jakarta Timur."
            ),
        },
        "forecastDays": forecasts,
        "districts": districts,
    }


def main():
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Converted {len(payload['forecastDays'])} notebook forecasts")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
