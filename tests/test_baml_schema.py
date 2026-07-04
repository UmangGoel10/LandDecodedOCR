from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue, OcrPageResult


def test_ocr_page_result_fields():
    result = OcrPageResult(page_number=1, raw_text="text")
    assert result.page_number == 1
    assert result.raw_text == "text"


def test_field_value_fields():
    field = FieldValue(value="Rahim", confidence=ConfidenceLevel.HIGH)
    assert field.value == "Rahim"
    assert field.confidence == ConfidenceLevel.HIGH


def test_list_field_value_fields():
    field = ListFieldValue(value=["Rahim", "Karim"], confidence=ConfidenceLevel.MED)
    assert field.value == ["Rahim", "Karim"]
    assert field.confidence == ConfidenceLevel.MED


def test_land_record_fields_construction():
    empty = FieldValue(value=None, confidence=ConfidenceLevel.LOW)
    empty_list = ListFieldValue(value=[], confidence=ConfidenceLevel.LOW)
    record = LandRecordFields(
        district=empty,
        block=empty,
        mouza=empty,
        police_station=empty,
        registry_location=empty,
        plot_no=empty,
        deed_no=empty,
        registration_year=empty,
        registration_month=empty,
        registration_day=empty,
        total_area=empty,
        land_unit=empty,
        vendors=empty_list,
        vendees=empty_list,
        deed_type=empty,
    )
    assert record.district is empty
    assert record.vendors is empty_list
