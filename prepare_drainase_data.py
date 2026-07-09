from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pandas as pd


ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "DATA DRAINASE JAKTIM.xlsx"
DATA_DIR = ROOT / "data"

RAW_OUTPUT_PATH = DATA_DIR / "drainase_jaktim_bersih.csv"
SUMMARY_OUTPUT_PATH = DATA_DIR / "drainase_jaktim_ringkasan_kecamatan.csv"
BACKEND_TEMPLATE_OUTPUT_PATH = DATA_DIR / "drainase_jaktim_template_backend.csv"

EXPECTED_DISTRICTS = [
    "Cakung",
    "Cipayung",
    "Ciracas",
    "Duren Sawit",
    "Jatinegara",
    "Kramat Jati",
    "Makasar",
    "Matraman",
    "Pasar Rebo",
    "Pulo Gadung",
]

DISTRICT_RENAMES = {
    "Pulogadung": "Pulo Gadung",
    "Kramatjati": "Kramat Jati",
}

MANUAL_FALLBACKS = {
    "Cakung": {
        "Kondisi_Drainase_Manual": "Buruk",
        "Skor_Drainase_Manual": 70,
        "Catatan_Manual": "Estimasi manual sementara karena data drainase kecamatan belum tersedia di file sumber.",
    }
}

SELECTED_COLUMNS = {
    0: "ID_Saluran",
    1: "Kode_Saluran",
    2: "Nama_Saluran",
    5: "Kota_Administrasi",
    6: "Kecamatan",
    8: "Panjang_m",
    9: "Lebar_m",
    10: "Tinggi_m",
    18: "Status_Pencatatan",
    20: "Jenis_Konstruksi",
}

XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def excel_column_to_index(cell_reference: str) -> int:
    letters = "".join(ch for ch in cell_reference if ch.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def read_shared_strings(zip_file: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []

    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    shared_strings: list[str] = []
    for string_item in root.findall("main:si", XML_NS):
        text_parts = [node.text or "" for node in string_item.iterfind(".//main:t", XML_NS)]
        shared_strings.append("".join(text_parts))
    return shared_strings


def read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", XML_NS)

    if value_node is None:
        inline_node = cell.find("main:is", XML_NS)
        if inline_node is None:
            return None
        text_parts = [node.text or "" for node in inline_node.iterfind(".//main:t", XML_NS)]
        return "".join(text_parts) or None

    raw_value = value_node.text
    if raw_value is None:
        return None

    if cell_type == "s":
        return shared_strings[int(raw_value)]

    return raw_value


def read_first_sheet_rows(path: Path) -> list[dict[str, object]]:
    with ZipFile(path) as zip_file:
        shared_strings = read_shared_strings(zip_file)

        workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
        workbook_rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in workbook_rels_root.findall("pkgrel:Relationship", XML_NS)
        }

        first_sheet = workbook_root.find("main:sheets", XML_NS)[0]
        relationship_id = first_sheet.attrib[
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        ]
        target = rel_map[relationship_id]
        if not target.startswith("xl/"):
            target = f"xl/{target}"

        worksheet_root = ET.fromstring(zip_file.read(target))

        rows: list[dict[str, object]] = []
        for row_node in worksheet_root.findall(".//main:sheetData/main:row", XML_NS):
            row_number = int(row_node.attrib.get("r", "0"))
            row_values: dict[int, str | None] = {}

            for cell_node in row_node.findall("main:c", XML_NS):
                cell_reference = cell_node.attrib.get("r", "")
                column_index = excel_column_to_index(cell_reference)
                row_values[column_index] = read_cell_value(cell_node, shared_strings)

            if not row_values:
                continue

            rows.append({"Baris_Excel": row_number, "cells": row_values})

    return rows


def build_raw_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    cleaned_rows: list[dict[str, object]] = []

    for row in rows:
        row_cells = row["cells"]
        extracted = {"Baris_Excel": row["Baris_Excel"]}
        for column_index, column_name in SELECTED_COLUMNS.items():
            extracted[column_name] = row_cells.get(column_index)
        cleaned_rows.append(extracted)

    df = pd.DataFrame(cleaned_rows)
    df = df.dropna(how="all", subset=[name for name in df.columns if name != "Baris_Excel"])

    for column in [
        "ID_Saluran",
        "Kode_Saluran",
        "Nama_Saluran",
        "Kota_Administrasi",
        "Kecamatan",
        "Status_Pencatatan",
        "Jenis_Konstruksi",
    ]:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
        )

    df = df[df["Kota_Administrasi"] == "Kota Adm. Jakarta Timur"].copy()
    df["Kecamatan"] = df["Kecamatan"].replace(DISTRICT_RENAMES)

    for column in ["Panjang_m", "Lebar_m", "Tinggi_m"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df.loc[df[column] <= 0, column] = pd.NA

    same_height_length_mask = (
        df["Panjang_m"].notna()
        & df["Tinggi_m"].notna()
        & (df["Panjang_m"] == df["Tinggi_m"])
        & (df["Panjang_m"] > 10)
    )
    df.loc[same_height_length_mask, "Tinggi_m"] = pd.NA

    df["Status_Pencatatan"] = df["Status_Pencatatan"].fillna("Tidak diketahui")
    df["Jenis_Konstruksi"] = df["Jenis_Konstruksi"].fillna("Tidak diketahui")

    df["Status_Tercatat"] = df["Status_Pencatatan"].eq("Tercatat")
    df["Dimensi_Lengkap"] = df[["Panjang_m", "Lebar_m", "Tinggi_m"]].notna().all(axis=1)
    df["Luas_Penampang_Proxy_m2"] = (df["Lebar_m"] * df["Tinggi_m"]).round(3)

    data_notes: list[str] = []
    for _, row in df.iterrows():
        flags: list[str] = []

        if pd.isna(row["Panjang_m"]) or pd.isna(row["Lebar_m"]) or pd.isna(row["Tinggi_m"]):
            flags.append("dimensi_tidak_lengkap")
        if row["Status_Pencatatan"] != "Tercatat":
            flags.append("status_belum_tercatat")
        if same_height_length_mask.loc[row.name]:
            flags.append("tinggi_sama_dengan_panjang_dikosongkan")

        data_notes.append(", ".join(flags))

    df["Catatan_Data"] = pd.Series(data_notes, index=df.index, dtype="string")
    df = df.sort_values(["Kecamatan", "Kode_Saluran", "Nama_Saluran", "Baris_Excel"]).reset_index(
        drop=True
    )
    return df


def dominant_construction_type(frame: pd.DataFrame) -> str:
    valid_types = frame["Jenis_Konstruksi"].dropna()
    valid_types = valid_types[valid_types != "Tidak diketahui"]
    if valid_types.empty:
        return "Tidak diketahui"
    return str(valid_types.mode().iloc[0])


def build_summary_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    def condition_from_score(score_value: float | None) -> str:
        if score_value is None or pd.isna(score_value):
            return "Tidak diketahui"
        if score_value >= 67:
            return "Buruk"
        if score_value >= 34:
            return "Sedang"
        return "Baik"

    def confidence_score_from_quality(
        percent_complete: float | None,
        percent_recorded: float | None,
    ) -> float:
        if percent_complete is None or pd.isna(percent_complete):
            return 0.0
        if percent_recorded is None or pd.isna(percent_recorded):
            return float(percent_complete)
        return round((0.7 * float(percent_complete)) + (0.3 * float(percent_recorded)), 2)

    def confidence_label(score_value: float) -> str:
        if score_value >= 85:
            return "Tinggi"
        if score_value >= 65:
            return "Sedang"
        if score_value > 0:
            return "Rendah"
        return "Tidak tersedia"

    summary_rows: list[dict[str, object]] = []

    for district in EXPECTED_DISTRICTS:
        frame = raw_df[raw_df["Kecamatan"] == district].copy()

        if frame.empty:
            summary_rows.append(
                {
                    "Kecamatan": district,
                    "Jumlah_Ruas": 0,
                    "Jumlah_Ruas_Tercatat": 0,
                    "Jumlah_Ruas_Dimensi_Lengkap": 0,
                    "Jumlah_Ruas_Dimensi_Tidak_Lengkap": 0,
                    "Total_Panjang_Valid_m": 0.0,
                    "Rata_Rata_Lebar_m": pd.NA,
                    "Rata_Rata_Tinggi_m": pd.NA,
                    "Rata_Rata_Luas_Penampang_Proxy_m2": pd.NA,
                    "Persen_Status_Tercatat": pd.NA,
                    "Persen_Dimensi_Lengkap": pd.NA,
                    "Jumlah_Baris_Anomali": 0,
                    "Jenis_Konstruksi_Dominan": "Data tidak tersedia",
                    "Catatan": "Data kecamatan tidak ditemukan pada file sumber.",
                }
            )
            continue

        total_rows = len(frame)
        tercatat_rows = int(frame["Status_Tercatat"].sum())
        complete_rows = int(frame["Dimensi_Lengkap"].sum())
        incomplete_rows = total_rows - complete_rows
        anomaly_rows = int(frame["Catatan_Data"].fillna("").ne("").sum())
        mean_width = round(float(frame["Lebar_m"].mean(skipna=True)), 3)
        mean_height = round(float(frame["Tinggi_m"].mean(skipna=True)), 3)
        mean_area = round(float(frame["Luas_Penampang_Proxy_m2"].mean(skipna=True)), 3)
        percent_recorded = round((tercatat_rows / total_rows) * 100, 2)
        percent_complete = round((complete_rows / total_rows) * 100, 2)

        summary_rows.append(
            {
                "Kecamatan": district,
                "Jumlah_Ruas": total_rows,
                "Jumlah_Ruas_Tercatat": tercatat_rows,
                "Jumlah_Ruas_Dimensi_Lengkap": complete_rows,
                "Jumlah_Ruas_Dimensi_Tidak_Lengkap": incomplete_rows,
                "Total_Panjang_Valid_m": round(float(frame["Panjang_m"].sum(skipna=True)), 2),
                "Rata_Rata_Lebar_m": mean_width,
                "Rata_Rata_Tinggi_m": mean_height,
                "Rata_Rata_Luas_Penampang_Proxy_m2": mean_area,
                "Persen_Status_Tercatat": percent_recorded,
                "Persen_Dimensi_Lengkap": percent_complete,
                "Jumlah_Baris_Anomali": anomaly_rows,
                "Jenis_Konstruksi_Dominan": dominant_construction_type(frame),
                "Catatan": (
                    f"{anomaly_rows} baris perlu perhatian; "
                    f"{incomplete_rows} ruas masih punya dimensi belum lengkap."
                ),
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    valid_area_series = summary_df["Rata_Rata_Luas_Penampang_Proxy_m2"].dropna()
    min_area = float(valid_area_series.min()) if not valid_area_series.empty else 0.0
    max_area = float(valid_area_series.max()) if not valid_area_series.empty else 1.0

    def score_from_area(area_value: float | None) -> float | None:
        if area_value is None or pd.isna(area_value):
            return None
        if max_area == min_area:
            return 50.0

        normalized_capacity = (float(area_value) - min_area) / (max_area - min_area)
        normalized_capacity = max(0.0, min(1.0, normalized_capacity))
        return round(20 + (1 - normalized_capacity) * 60, 2)

    summary_df["Skor_Drainase_Saran"] = summary_df["Rata_Rata_Luas_Penampang_Proxy_m2"].apply(
        score_from_area
    )
    summary_df["Kondisi_Drainase_Saran"] = summary_df["Skor_Drainase_Saran"].apply(
        condition_from_score
    )
    summary_df["Skor_Confidence_Drainase"] = summary_df.apply(
        lambda row: confidence_score_from_quality(
            row["Persen_Dimensi_Lengkap"],
            row["Persen_Status_Tercatat"],
        ),
        axis=1,
    )
    summary_df["Confidence_Drainase"] = summary_df["Skor_Confidence_Drainase"].apply(
        confidence_label
    )

    return summary_df


def build_backend_template_dataframe(summary_df: pd.DataFrame) -> pd.DataFrame:
    backend_df = summary_df.copy()
    backend_df.insert(1, "Kondisi_Drainase_Manual", "")
    backend_df.insert(2, "Skor_Drainase_Manual", "")
    backend_df.insert(3, "Catatan_Manual", "")
    backend_df.insert(4, "Sumber_Data", INPUT_PATH.name)

    for district, fallback in MANUAL_FALLBACKS.items():
        mask = backend_df["Kecamatan"] == district
        for column_name, column_value in fallback.items():
            backend_df.loc[mask, column_name] = column_value

    backend_df["Catatan"] = backend_df["Catatan"].astype("string")
    return backend_df


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    rows = read_first_sheet_rows(INPUT_PATH)
    raw_df = build_raw_dataframe(rows)
    summary_df = build_summary_dataframe(raw_df)
    backend_template_df = build_backend_template_dataframe(summary_df)

    raw_df.to_csv(RAW_OUTPUT_PATH, sep=";", index=False, encoding="utf-8")
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, sep=";", index=False, encoding="utf-8")
    backend_template_df.to_csv(
        BACKEND_TEMPLATE_OUTPUT_PATH,
        sep=";",
        index=False,
        encoding="utf-8",
    )

    print(f"File sumber              : {INPUT_PATH.name}")
    print(f"Total ruas Jaktim        : {len(raw_df)}")
    print(f"Jumlah kecamatan terisi  : {raw_df['Kecamatan'].nunique()}")
    print(f"Output baris per saluran : {RAW_OUTPUT_PATH}")
    print(f"Output ringkasan         : {SUMMARY_OUTPUT_PATH}")
    print(f"Output template backend  : {BACKEND_TEMPLATE_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
