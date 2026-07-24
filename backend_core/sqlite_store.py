from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SQLITE_DB_PATH = Path(os.getenv("FLOODGIS_DB_PATH", str(DATA_DIR / "floodgis.db")))


def get_sqlite_db_path() -> Path:
    return SQLITE_DB_PATH


def _connect() -> sqlite3.Connection:
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(SQLITE_DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_overrides (
                normalized_key TEXT PRIMARY KEY,
                district_name TEXT NOT NULL,
                drainage_condition TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                district_name TEXT
            );

            CREATE TABLE IF NOT EXISTS publication_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                published_at TEXT NOT NULL,
                payload_updated_at TEXT,
                published_district_count INTEGER NOT NULL DEFAULT 0,
                source_label TEXT,
                generated_from_live_at TEXT,
                published_by TEXT,
                override_reset_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS prediction_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_key TEXT NOT NULL UNIQUE,
                run_type TEXT NOT NULL,
                generated_at TEXT,
                observation_date TEXT,
                target_prediction_date TEXT,
                district_count INTEGER NOT NULL DEFAULT 0,
                source_label TEXT,
                model_name TEXT,
                published_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS district_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_run_id INTEGER NOT NULL,
                district_name TEXT NOT NULL,
                district_label TEXT,
                rain_class TEXT,
                rain_range_label TEXT,
                risk_level TEXT,
                risk_score REAL,
                dominant_confidence REAL,
                extreme_rain_probability REAL,
                latest_observed_rainfall REAL,
                avg_rainfall_3d REAL,
                latest_observed_temperature_c REAL,
                latest_observed_humidity_percent REAL,
                drainage_condition TEXT,
                drainage_score REAL,
                has_admin_override INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (prediction_run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
            );
            """
        )


def get_metadata(key: str) -> str | None:
    initialize_database()
    with _connect() as connection:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row["value"]) if row and row["value"] is not None else None


def set_metadata(key: str, value: str | None) -> None:
    initialize_database()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO app_metadata(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def load_admin_overrides_state() -> dict[str, Any]:
    initialize_database()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT normalized_key, district_name, drainage_condition, updated_at
            FROM admin_overrides
            ORDER BY district_name COLLATE NOCASE ASC
            """
        ).fetchall()

    districts: dict[str, dict[str, Any]] = {}
    for row in rows:
        districts[str(row["normalized_key"])] = {
            "districtName": row["district_name"],
            "drainageCondition": row["drainage_condition"],
            "updatedAt": row["updated_at"],
        }

    return {
        "updatedAt": get_metadata("admin_overrides_updated_at"),
        "districts": districts,
    }


def replace_admin_overrides_state(state: dict[str, Any]) -> None:
    initialize_database()
    districts = dict(state.get("districts", {}))

    with _connect() as connection:
        connection.execute("DELETE FROM admin_overrides")
        for normalized_key, entry in districts.items():
            connection.execute(
                """
                INSERT INTO admin_overrides(
                    normalized_key,
                    district_name,
                    drainage_condition,
                    updated_at
                )
                VALUES(?, ?, ?, ?)
                """,
                (
                    normalized_key,
                    entry.get("districtName"),
                    entry.get("drainageCondition"),
                    entry.get("updatedAt"),
                ),
            )

    set_metadata("admin_overrides_updated_at", state.get("updatedAt"))


def load_admin_history_state(limit: int) -> dict[str, Any]:
    initialize_database()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT timestamp, action_type, title, description, district_name
            FROM admin_activity_history
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    entries = [
        {
            "timestamp": row["timestamp"],
            "type": row["action_type"],
            "title": row["title"],
            "description": row["description"],
            "districtName": row["district_name"],
        }
        for row in rows
    ]

    return {
        "updatedAt": get_metadata("admin_history_updated_at"),
        "entries": entries,
    }


def replace_admin_history_state(state: dict[str, Any], limit: int) -> None:
    initialize_database()
    raw_entries = state.get("entries", [])
    entries = list(raw_entries if isinstance(raw_entries, list) else [])[:limit]

    with _connect() as connection:
        connection.execute("DELETE FROM admin_activity_history")
        for entry in entries:
            connection.execute(
                """
                INSERT INTO admin_activity_history(
                    timestamp,
                    action_type,
                    title,
                    description,
                    district_name
                )
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    entry.get("timestamp"),
                    entry.get("type"),
                    entry.get("title"),
                    entry.get("description"),
                    entry.get("districtName"),
                ),
            )

    set_metadata("admin_history_updated_at", state.get("updatedAt"))


def append_admin_history_entry(
    entry: dict[str, Any],
    limit: int,
    updated_at: str | None,
) -> None:
    initialize_database()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO admin_activity_history(
                timestamp,
                action_type,
                title,
                description,
                district_name
            )
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                entry.get("timestamp"),
                entry.get("type"),
                entry.get("title"),
                entry.get("description"),
                entry.get("districtName"),
            ),
        )
        connection.execute(
            """
            DELETE FROM admin_activity_history
            WHERE id NOT IN (
                SELECT id
                FROM admin_activity_history
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            )
            """,
            (limit,),
        )

    set_metadata("admin_history_updated_at", updated_at)


def get_latest_publication_snapshot() -> dict[str, Any] | None:
    initialize_database()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                published_at,
                payload_updated_at,
                published_district_count,
                source_label,
                generated_from_live_at,
                published_by,
                override_reset_count
            FROM publication_snapshots
            ORDER BY published_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    return {
        "publishedAt": row["published_at"],
        "payloadUpdatedAt": row["payload_updated_at"],
        "publishedDistrictCount": int(row["published_district_count"] or 0),
        "sourceLabel": row["source_label"],
        "generatedFromLiveAt": row["generated_from_live_at"],
        "publishedBy": row["published_by"],
        "overrideResetCount": int(row["override_reset_count"] or 0),
    }


def insert_publication_snapshot(snapshot: dict[str, Any]) -> None:
    initialize_database()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO publication_snapshots(
                published_at,
                payload_updated_at,
                published_district_count,
                source_label,
                generated_from_live_at,
                published_by,
                override_reset_count
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.get("publishedAt"),
                snapshot.get("payloadUpdatedAt"),
                int(snapshot.get("publishedDistrictCount") or 0),
                snapshot.get("sourceLabel"),
                snapshot.get("generatedFromLiveAt"),
                snapshot.get("publishedBy"),
                int(snapshot.get("overrideResetCount") or 0),
            ),
        )


def insert_prediction_run(payload: dict[str, Any], run_type: str) -> int | None:
    initialize_database()
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    districts = payload.get("districts", []) if isinstance(payload, dict) else []
    generated_at = meta.get("updatedAt")
    observation_date = meta.get("latestObservationDate")
    target_prediction_date = meta.get("forecastTargetDate")
    published_at = meta.get("publishedAt")
    source_label = meta.get("publicPayloadSourceLabel") or meta.get("publicPayloadSource")
    model_name = meta.get("model")
    run_key = "|".join(
        [
            str(run_type or "").strip(),
            str(generated_at or "").strip(),
            str(target_prediction_date or "").strip(),
            str(published_at or "").strip(),
        ]
    )

    if not generated_at and not target_prediction_date:
        return None

    with _connect() as connection:
        existing = connection.execute(
            "SELECT id FROM prediction_runs WHERE run_key = ?",
            (run_key,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])

        cursor = connection.execute(
            """
            INSERT INTO prediction_runs(
                run_key,
                run_type,
                generated_at,
                observation_date,
                target_prediction_date,
                district_count,
                source_label,
                model_name,
                published_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_key,
                run_type,
                generated_at,
                observation_date,
                target_prediction_date,
                len(districts) if isinstance(districts, list) else 0,
                source_label,
                model_name,
                published_at,
            ),
        )
        prediction_run_id = int(cursor.lastrowid)

        for district in districts if isinstance(districts, list) else []:
            connection.execute(
                """
                INSERT INTO district_predictions(
                    prediction_run_id,
                    district_name,
                    district_label,
                    rain_class,
                    rain_range_label,
                    risk_level,
                    risk_score,
                    dominant_confidence,
                    extreme_rain_probability,
                    latest_observed_rainfall,
                    avg_rainfall_3d,
                    latest_observed_temperature_c,
                    latest_observed_humidity_percent,
                    drainage_condition,
                    drainage_score,
                    has_admin_override
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_run_id,
                    district.get("name"),
                    district.get("label"),
                    district.get("predictedRainfallLabel"),
                    district.get("predictedRainfallRange"),
                    district.get("webgisLevelLabel"),
                    district.get("riskScore"),
                    district.get("predictedClassProbabilityPercent"),
                    district.get("probabilityWaspadaPercent"),
                    district.get("latestObservedRainfallMm"),
                    district.get("recentThreeDayAverageMm"),
                    district.get("latestObservedTemperatureC"),
                    district.get("latestObservedHumidityPercent"),
                    district.get("drainageCondition"),
                    district.get("drainageScore"),
                    1 if district.get("hasAdminOverride") else 0,
                ),
            )

    return prediction_run_id


def list_prediction_runs(limit: int = 20) -> list[dict[str, Any]]:
    initialize_database()
    safe_limit = max(1, min(int(limit), 100))

    with _connect() as connection:
        run_rows = connection.execute(
            """
            SELECT
                id,
                run_type,
                generated_at,
                observation_date,
                target_prediction_date,
                district_count,
                source_label,
                model_name,
                published_at
            FROM prediction_runs
            ORDER BY COALESCE(published_at, generated_at) DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

        runs: list[dict[str, Any]] = []
        for row in run_rows:
            top_rows = connection.execute(
                """
                SELECT
                    district_name,
                    district_label,
                    risk_level,
                    risk_score,
                    rain_class,
                    has_admin_override
                FROM district_predictions
                WHERE prediction_run_id = ?
                ORDER BY COALESCE(risk_score, 0) DESC, district_label ASC, district_name ASC
                LIMIT 3
                """,
                (int(row["id"]),),
            ).fetchall()

            runs.append(
                {
                    "id": int(row["id"]),
                    "runType": row["run_type"],
                    "generatedAt": row["generated_at"],
                    "observationDate": row["observation_date"],
                    "targetPredictionDate": row["target_prediction_date"],
                    "districtCount": int(row["district_count"] or 0),
                    "sourceLabel": row["source_label"],
                    "modelName": row["model_name"],
                    "publishedAt": row["published_at"],
                    "topDistricts": [
                        {
                            "districtName": top_row["district_name"],
                            "districtLabel": top_row["district_label"],
                            "riskLevel": top_row["risk_level"],
                            "riskScore": top_row["risk_score"],
                            "rainClass": top_row["rain_class"],
                            "hasAdminOverride": bool(top_row["has_admin_override"]),
                        }
                        for top_row in top_rows
                    ],
                }
            )

    return runs


def get_prediction_run_detail(run_id: int) -> dict[str, Any] | None:
    initialize_database()
    safe_run_id = int(run_id)

    with _connect() as connection:
        run_row = connection.execute(
            """
            SELECT
                id,
                run_type,
                generated_at,
                observation_date,
                target_prediction_date,
                district_count,
                source_label,
                model_name,
                published_at
            FROM prediction_runs
            WHERE id = ?
            """,
            (safe_run_id,),
        ).fetchone()

        if run_row is None:
            return None

        district_rows = connection.execute(
            """
            SELECT
                district_name,
                district_label,
                rain_class,
                rain_range_label,
                risk_level,
                risk_score,
                dominant_confidence,
                extreme_rain_probability,
                latest_observed_rainfall,
                avg_rainfall_3d,
                latest_observed_temperature_c,
                latest_observed_humidity_percent,
                drainage_condition,
                drainage_score,
                has_admin_override
            FROM district_predictions
            WHERE prediction_run_id = ?
            ORDER BY district_label ASC, district_name ASC
            """,
            (safe_run_id,),
        ).fetchall()

    return {
        "id": int(run_row["id"]),
        "runType": run_row["run_type"],
        "generatedAt": run_row["generated_at"],
        "observationDate": run_row["observation_date"],
        "targetPredictionDate": run_row["target_prediction_date"],
        "districtCount": int(run_row["district_count"] or 0),
        "sourceLabel": run_row["source_label"],
        "modelName": run_row["model_name"],
        "publishedAt": run_row["published_at"],
        "districts": [
            {
                "districtName": district_row["district_name"],
                "districtLabel": district_row["district_label"],
                "rainClass": district_row["rain_class"],
                "rainRangeLabel": district_row["rain_range_label"],
                "riskLevel": district_row["risk_level"],
                "riskScore": district_row["risk_score"],
                "dominantConfidence": district_row["dominant_confidence"],
                "extremeRainProbability": district_row["extreme_rain_probability"],
                "latestObservedRainfall": district_row["latest_observed_rainfall"],
                "avgRainfall3d": district_row["avg_rainfall_3d"],
                "latestObservedTemperatureC": district_row["latest_observed_temperature_c"],
                "latestObservedHumidityPercent": district_row["latest_observed_humidity_percent"],
                "drainageCondition": district_row["drainage_condition"],
                "drainageScore": district_row["drainage_score"],
                "hasAdminOverride": bool(district_row["has_admin_override"]),
            }
            for district_row in district_rows
        ],
    }
