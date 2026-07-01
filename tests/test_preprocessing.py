import pytest

from ocr_pipeline.ingestion import Page
from ocr_pipeline.preprocessing import preprocess_image


def test_preprocess_image_not_implemented():
    page = Page(
        page_number=1,
        image_bytes=b"",
        native_text=None,
        has_valid_text_layer=False,
    )
    with pytest.raises(NotImplementedError):
        preprocess_image(page)
