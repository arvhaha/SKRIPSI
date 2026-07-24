from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from backend_core.legacy_core import (
    ADMIN_OVERRIDE_CONFIDENCE_LABEL,
    ADMIN_OVERRIDE_CONFIDENCE_SCORE,
    ADMIN_OVERRIDE_SOURCE_NAME,
    DRAINAGE_PATH,
    DrainageProfile,
    append_admin_history_entry,
    apply_drainage_adjustment,
    condition_to_default_score,
    current_jakarta_timestamp,
    get_template_district_label_map,
    get_template_district_name_map,
    is_blank_value,
    load_admin_history_state,
    load_admin_overrides_state,
    normalize_name,
    normalize_optional_text,
    probability_to_level,
    recommendation_for_level,
    sanitize_override_condition,
    save_admin_overrides_state,
    score_to_condition,
)


@lru_cache(maxsize=1)
def load_drainage_profiles() -> dict[str, DrainageProfile]:
    if not DRAINAGE_PATH.exists():
        return {}

    df = pd.read_csv(DRAINAGE_PATH, sep=";")
    profiles: dict[str, DrainageProfile] = {}

    for _, row in df.iterrows():
        district_name = str(row.get("Kecamatan", "")).strip()
        if not district_name:
            continue

        manual_condition = None if is_blank_value(row.get("Kondisi_Drainase_Manual")) else str(
            row.get("Kondisi_Drainase_Manual")
        ).strip()
        manual_score = None if is_blank_value(row.get("Skor_Drainase_Manual")) else float(
            row.get("Skor_Drainase_Manual")
        )
        suggested_condition = (
            None
            if is_blank_value(row.get("Kondisi_Drainase_Saran"))
            else str(row.get("Kondisi_Drainase_Saran")).strip()
        )
        suggested_score = (
            None
            if is_blank_value(row.get("Skor_Drainase_Saran"))
            else float(row.get("Skor_Drainase_Saran"))
        )

        if manual_score is None and manual_condition:
            manual_score = condition_to_default_score(manual_condition)
        if manual_condition is None and manual_score is not None:
            manual_condition = score_to_condition(manual_score)

        uses_manual = manual_condition is not None or manual_score is not None

        if uses_manual:
            final_condition = manual_condition or suggested_condition or "Tidak diketahui"
            final_score = manual_score if manual_score is not None else suggested_score
            source_type = "manual"
        else:
            final_condition = suggested_condition or "Tidak diketahui"
            final_score = suggested_score
            source_type = "derived"

        if final_score is None:
            final_score = condition_to_default_score(final_condition)

        confidence_label_value = (
            "Tidak tersedia"
            if is_blank_value(row.get("Confidence_Drainase"))
            else str(row.get("Confidence_Drainase")).strip()
        )
        confidence_score_value = (
            0.0
            if is_blank_value(row.get("Skor_Confidence_Drainase"))
            else float(row.get("Skor_Confidence_Drainase"))
        )

        if uses_manual and confidence_score_value == 0.0:
            confidence_label_value = "Manual estimasi"
            confidence_score_value = 45.0

        note_parts = []
        if not is_blank_value(row.get("Catatan_Manual")):
            note_parts.append(str(row.get("Catatan_Manual")).strip())
        if not is_blank_value(row.get("Catatan")):
            note_parts.append(str(row.get("Catatan")).strip())

        profiles[normalize_name(district_name)] = DrainageProfile(
            condition=final_condition,
            score=final_score,
            confidence_label=confidence_label_value,
            confidence_score=confidence_score_value,
            source_type=source_type,
            source_name=str(row.get("Sumber_Data", DRAINAGE_PATH.name)).strip() or DRAINAGE_PATH.name,
            note=" ".join(note_parts).strip(),
            manual_condition=manual_condition,
            manual_score=manual_score,
            suggested_condition=suggested_condition,
            suggested_score=suggested_score,
        )

    return profiles


def save_admin_override(district_name: str, drainage_condition_value: Any) -> dict[str, Any]:
    normalized_district_name = normalize_optional_text(district_name)
    if not normalized_district_name:
        raise ValueError("districtName wajib diisi.")

    drainage_condition = sanitize_override_condition(drainage_condition_value)
    template_name_map = get_template_district_name_map()
    template_label_map = get_template_district_label_map()
    district_key = normalize_name(normalized_district_name)
    canonical_district_name = template_name_map.get(district_key)
    if canonical_district_name is None:
        raise ValueError("Kecamatan tidak dikenali oleh template WebGIS.")

    canonical_district_label = (
        template_label_map.get(district_key)
        or normalize_optional_text(canonical_district_name).title()
        or canonical_district_name
    )

    overrides_state = load_admin_overrides_state()
    district_entry = {
        "districtName": canonical_district_name,
        "drainageCondition": drainage_condition,
        "updatedAt": current_jakarta_timestamp().isoformat(),
    }

    if drainage_condition:
        overrides_state.setdefault("districts", {})[district_key] = district_entry
    else:
        overrides_state.setdefault("districts", {}).pop(district_key, None)

    overrides_state["updatedAt"] = current_jakarta_timestamp().isoformat()
    save_admin_overrides_state(overrides_state)
    append_admin_history_entry(
        action_type="override_saved" if drainage_condition else "override_reset",
        title=(
            "Override drainase disimpan"
            if drainage_condition
            else "Override drainase direset"
        ),
        description=(
            f"{canonical_district_label}: drainase publik diubah menjadi {drainage_condition.lower()}."
            if drainage_condition
            else f"{canonical_district_label}: draft override dikembalikan ke hasil backend."
        ),
        district_name=canonical_district_label,
    )

    has_override = bool(drainage_condition)
    return {
        "status": "ok",
        "districtName": canonical_district_name,
        "districtLabel": canonical_district_label,
        "drainageCondition": drainage_condition,
        "hasOverride": has_override,
        "message": (
            f"Draft admin untuk {canonical_district_name} berhasil disimpan."
            if has_override
            else f"Draft admin untuk {canonical_district_name} berhasil direset."
        ),
    }


def build_override_drainage_profile(
    base_profile: DrainageProfile | None,
    override_entry: dict[str, Any],
) -> DrainageProfile | None:
    override_condition = sanitize_override_condition(override_entry.get("drainageCondition"))

    if override_condition:
        override_score = condition_to_default_score(override_condition)
        return DrainageProfile(
            condition=override_condition,
            score=override_score,
            confidence_label=ADMIN_OVERRIDE_CONFIDENCE_LABEL,
            confidence_score=ADMIN_OVERRIDE_CONFIDENCE_SCORE,
            source_type="admin_override",
            source_name=ADMIN_OVERRIDE_SOURCE_NAME,
            note="Override drainase admin aktif. Nilai publik mengikuti pilihan admin terbaru.",
            manual_condition=override_condition,
            manual_score=override_score,
            suggested_condition=base_profile.suggested_condition if base_profile is not None else None,
            suggested_score=base_profile.suggested_score if base_profile is not None else None,
        )

    return base_profile


def apply_drainage_profile_to_district_payload(
    district_payload: dict[str, Any],
    drainage_profile: DrainageProfile | None,
    override_entry: dict[str, Any] | None = None,
) -> None:
    prediction_unavailable = (
        district_payload.get("decisionSource") == "missing_source_data"
        or int(district_payload.get("webgisLevel") or 0) == 0
    )
    base_score_value = district_payload.get("baseModelRiskScore", district_payload.get("riskScore", 0.0))
    try:
        base_score = float(base_score_value)
    except (TypeError, ValueError):
        base_score = 0.0

    if prediction_unavailable:
        adjusted_risk_score = base_score if base_score > 0 else 0.0
        drainage_adjustment = 0.0
        adjusted_risk_score_percent = None
    else:
        adjusted_risk_score, drainage_adjustment = apply_drainage_adjustment(base_score, drainage_profile)
        level_info = probability_to_level(adjusted_risk_score)
        district_payload.update(level_info)
        adjusted_risk_score_percent = round(adjusted_risk_score * 100, 1)
        district_payload["riskScore"] = round(adjusted_risk_score, 4)
        district_payload["riskScorePercent"] = adjusted_risk_score_percent

    district_payload["drainageCondition"] = (
        drainage_profile.condition if drainage_profile is not None else "Tidak tersedia"
    )
    district_payload["drainageScore"] = (
        round(float(drainage_profile.score), 1)
        if drainage_profile is not None and drainage_profile.score is not None
        else None
    )
    district_payload["drainageConfidence"] = (
        drainage_profile.confidence_label if drainage_profile is not None else "Tidak tersedia"
    )
    district_payload["drainageConfidenceScore"] = (
        round(float(drainage_profile.confidence_score), 1) if drainage_profile is not None else 0.0
    )
    district_payload["drainageAdjustmentApplied"] = round(drainage_adjustment, 4)
    district_payload["drainageAdjustmentPercent"] = round(drainage_adjustment * 100, 1)
    district_payload["drainageDataSourceType"] = (
        drainage_profile.source_type if drainage_profile is not None else "template"
    )
    district_payload["drainageDataSourceName"] = (
        drainage_profile.source_name if drainage_profile is not None else "Template WebGIS"
    )
    district_payload["drainageSuggestedCondition"] = (
        drainage_profile.suggested_condition if drainage_profile is not None else None
    )
    district_payload["drainageSuggestedScore"] = (
        round(float(drainage_profile.suggested_score), 1)
        if drainage_profile is not None and drainage_profile.suggested_score is not None
        else None
    )
    district_payload["drainageManualCondition"] = (
        drainage_profile.manual_condition if drainage_profile is not None else None
    )
    district_payload["drainageManualScore"] = (
        round(float(drainage_profile.manual_score), 1)
        if drainage_profile is not None and drainage_profile.manual_score is not None
        else None
    )

    override_condition = None
    override_updated_at = ""
    if override_entry:
        override_condition = sanitize_override_condition(override_entry.get("drainageCondition"))
        override_updated_at = normalize_optional_text(override_entry.get("updatedAt"))

    if override_condition:
        district_payload["drainageNote"] = (
            "Override drainase admin aktif. Nilai publik mengikuti pilihan admin terbaru."
        )
    else:
        district_payload["drainageNote"] = drainage_profile.note if drainage_profile is not None else ""

    district_payload["hasAdminOverride"] = bool(override_condition)
    district_payload["hasAdminDrainageOverride"] = bool(override_condition)
    district_payload["adminOverrideUpdatedAt"] = override_updated_at or None

    if prediction_unavailable:
        district_payload["recommendation"] = (
            "Data historis kecamatan belum cukup untuk membentuk prediksi baru. "
            "Lengkapi data sumber terlebih dahulu sebelum dipublikasikan."
        )
        base_summary = normalize_optional_text(district_payload.get("summary"))
        if base_summary:
            district_payload["summary"] = base_summary
        return

    district_payload["recommendation"] = recommendation_for_level(int(district_payload["webgisLevel"]))

    district_label = district_payload.get("label") or district_payload.get("name") or "kecamatan ini"
    forecast_label = normalize_optional_text(district_payload.get("forecastLabel")) or "Prediksi aktif"
    rainfall_label = (
        normalize_optional_text(district_payload.get("predictedRainfallLabel"))
        or normalize_optional_text(district_payload.get("predictedRainfallRange"))
        or "kelas hujan tidak tersedia"
    )
    predicted_class_probability = float(district_payload.get("predictedClassProbabilityPercent", 0.0) or 0.0)
    extreme_probability = float(district_payload.get("probabilityWaspadaPercent", 0.0) or 0.0)

    if drainage_profile is None or abs(drainage_adjustment) < 0.0001:
        drainage_summary = "tanpa penyesuaian tambahan dari layer drainase"
    else:
        adjustment_sign = "+" if drainage_adjustment > 0 else ""
        drainage_summary = (
            f"dengan penyesuaian drainase {adjustment_sign}{drainage_adjustment * 100:.1f} poin "
            f"(kondisi {district_payload['drainageCondition']}, confidence {district_payload['drainageConfidence']})"
        )

    summary = (
        f"{forecast_label} untuk {district_label} berada pada kelas {rainfall_label} "
        f"dengan confidence {predicted_class_probability:.1f}% dan probabilitas kelas lebat/ekstrem "
        f"{extreme_probability:.1f}% {drainage_summary}, sehingga skor risiko akhir menjadi "
        f"{adjusted_risk_score_percent:.1f}% ({district_payload['webgisLevelLabel']}: "
        f"{district_payload['webgisDescription']})."
    )
    district_payload["summary"] = summary


def apply_admin_overrides_to_payload(
    payload: dict[str, Any],
    overrides_state: dict[str, Any],
    drainage_profiles: dict[str, DrainageProfile] | None = None,
) -> dict[str, Any]:
    resolved_profiles = drainage_profiles or load_drainage_profiles()
    overrides_by_district = dict(overrides_state.get("districts", {}))
    applied_count = 0

    for district_payload in payload.get("districts", []):
        district_name = normalize_optional_text(district_payload.get("name"))
        district_key = normalize_name(district_name)
        override_entry = overrides_by_district.get(district_key)

        if not override_entry:
            district_payload["hasAdminOverride"] = False
            district_payload["hasAdminDrainageOverride"] = False
            district_payload["adminOverrideUpdatedAt"] = None
            continue

        override_profile = build_override_drainage_profile(
            resolved_profiles.get(district_key),
            override_entry,
        )
        apply_drainage_profile_to_district_payload(
            district_payload,
            override_profile,
            override_entry=override_entry,
        )
        applied_count += 1

    payload.setdefault("meta", {})
    payload["meta"]["adminOverrideCount"] = applied_count
    return payload


__all__ = [
    "apply_admin_overrides_to_payload",
    "apply_drainage_adjustment",
    "apply_drainage_profile_to_district_payload",
    "build_override_drainage_profile",
    "load_admin_history_state",
    "load_admin_overrides_state",
    "load_drainage_profiles",
    "save_admin_override",
    "save_admin_overrides_state",
]
