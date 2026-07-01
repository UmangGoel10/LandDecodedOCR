from baml_client.types import OcrPageResult, SchemaField


def test_ocr_page_result_fields():
    result = OcrPageResult(page_number=1, raw_text="text")
    assert result.page_number == 1
    assert result.raw_text == "text"


def test_schema_field_fields():
    field = SchemaField(field_name="owner_name", value="Rahim", confidence=0.9)
    assert field.field_name == "owner_name"
    assert field.value == "Rahim"
    assert field.confidence == 0.9
