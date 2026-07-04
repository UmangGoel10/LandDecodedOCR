from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue
from ocr_pipeline.review import apply_confidence_gate, merge_dual_provider_fields


def _make_land_record(**overrides) -> LandRecordFields:
    defaults = {
        "district": FieldValue(value="Dhaka", confidence=ConfidenceLevel.HIGH),
        "block": FieldValue(value="Block A", confidence=ConfidenceLevel.HIGH),
        "mouza": FieldValue(value="Mouza X", confidence=ConfidenceLevel.HIGH),
        "police_station": FieldValue(value="PS 1", confidence=ConfidenceLevel.HIGH),
        "registry_location": FieldValue(value="Registry 1", confidence=ConfidenceLevel.HIGH),
        "plot_no": FieldValue(value="123", confidence=ConfidenceLevel.HIGH),
        "deed_no": FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH),
        "registration_year": FieldValue(value="2020", confidence=ConfidenceLevel.HIGH),
        "registration_month": FieldValue(value="5", confidence=ConfidenceLevel.HIGH),
        "registration_day": FieldValue(value="10", confidence=ConfidenceLevel.HIGH),
        "total_area": FieldValue(value="12.5", confidence=ConfidenceLevel.HIGH),
        "land_unit": FieldValue(value="decimal", confidence=ConfidenceLevel.HIGH),
        "vendors": ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.HIGH),
        "vendees": ListFieldValue(value=["Karim"], confidence=ConfidenceLevel.HIGH),
        "deed_type": FieldValue(value="sale", confidence=ConfidenceLevel.HIGH),
    }
    defaults.update(overrides)
    return LandRecordFields(**defaults)


def test_apply_confidence_gate_nulls_low_confidence_scalar_field():
    record = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.LOW)
    )

    result = apply_confidence_gate(record)

    assert result.total_area.value is None
    assert result.total_area.confidence == ConfidenceLevel.LOW
    # Unrelated fields are untouched.
    assert result.district.value == "Dhaka"


def test_apply_confidence_gate_empties_low_confidence_list_field():
    record = _make_land_record(
        vendors=ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.LOW)
    )

    result = apply_confidence_gate(record)

    assert result.vendors.value == []
    assert result.vendors.confidence == ConfidenceLevel.LOW


def test_apply_confidence_gate_keeps_medium_and_high_confidence_values():
    record = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.MED),
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH),
    )

    result = apply_confidence_gate(record)

    assert result.total_area.value == "12.5"
    assert result.deed_no.value == "D-1"


def test_merge_dual_provider_fields_prefers_higher_confidence():
    claude = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        total_area=FieldValue(value="15.0", confidence=ConfidenceLevel.MED)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.total_area.value == "12.5"
    assert merged.total_area.confidence == ConfidenceLevel.HIGH


def test_merge_dual_provider_fields_tie_with_agreement_keeps_value():
    claude = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.deed_no.value == "D-1"


def test_merge_dual_provider_fields_tie_with_disagreement_nulls_value():
    claude = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        deed_no=FieldValue(value="D-2", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.deed_no.value is None


def test_merge_dual_provider_fields_gates_low_confidence_before_comparing():
    claude = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.LOW)
    )
    gemini = _make_land_record(
        total_area=FieldValue(value="15.0", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.total_area.value == "15.0"
    assert merged.total_area.confidence == ConfidenceLevel.HIGH


def test_merge_dual_provider_fields_list_tie_no_overlap_returns_empty():
    claude = _make_land_record(
        vendors=ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        vendors=ListFieldValue(value=["Karim"], confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.vendors.value == []


def test_merge_dual_provider_fields_list_tie_partial_overlap_keeps_intersection():
    claude = _make_land_record(
        vendors=ListFieldValue(
            value=["Rahim", "Karim"], confidence=ConfidenceLevel.HIGH
        )
    )
    gemini = _make_land_record(
        vendors=ListFieldValue(
            value=["Rahim", "Karim", "Ali"], confidence=ConfidenceLevel.HIGH
        )
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.vendors.value == ["Rahim", "Karim"]


def test_merge_dual_provider_fields_list_tie_agrees_regardless_of_order():
    claude = _make_land_record(
        vendors=ListFieldValue(
            value=["Rahim", "Karim"], confidence=ConfidenceLevel.HIGH
        )
    )
    gemini = _make_land_record(
        vendors=ListFieldValue(
            value=["Karim", "Rahim"], confidence=ConfidenceLevel.HIGH
        )
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.vendors.value == ["Rahim", "Karim"]
