import pytest

from ocr_pipeline.ingestion import Page, is_valid_bangla_text, split_pdf_pages


def test_page_dataclass_fields():
    page = Page(
        page_number=1,
        image_bytes=b"",
        native_text="some text",
        has_valid_text_layer=True,
    )
    assert page.page_number == 1
    assert page.image_bytes == b""
    assert page.native_text == "some text"
    assert page.has_valid_text_layer is True


def test_split_pdf_pages_not_implemented():
    with pytest.raises(NotImplementedError):
        split_pdf_pages("dummy.pdf")


def test_is_valid_bangla_text_not_implemented():
    with pytest.raises(NotImplementedError):
        is_valid_bangla_text("dummy text")
