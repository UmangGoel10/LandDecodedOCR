import pytest

from baml_client.types import SchemaField
from ocr_pipeline.review import ReviewItem, enqueue_for_review, validate_field


def test_validate_field_not_implemented():
    field = SchemaField(field_name="area", value="12.5", confidence=0.4)
    with pytest.raises(NotImplementedError):
        validate_field(field)


def test_review_item_dataclass_fields():
    field = SchemaField(field_name="plot_no", value=None, confidence=0.2)
    item = ReviewItem(field=field, source_page=3, cropped_image_bytes=None)
    assert item.field is field
    assert item.source_page == 3
    assert item.cropped_image_bytes is None


def test_enqueue_for_review_not_implemented():
    field = SchemaField(field_name="plot_no", value=None, confidence=0.2)
    item = ReviewItem(field=field, source_page=3, cropped_image_bytes=None)
    with pytest.raises(NotImplementedError):
        enqueue_for_review(item)
