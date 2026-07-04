import asyncio
import json

from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue, OcrPageResult
from ocr_pipeline import pipeline
from ocr_pipeline.ingestion import Page


def _make_land_record(value: str, confidence: ConfidenceLevel) -> LandRecordFields:
    scalar = FieldValue(value=value, confidence=confidence)
    listed = ListFieldValue(value=[value], confidence=confidence)
    return LandRecordFields(
        district=scalar,
        block=scalar,
        mouza=scalar,
        police_station=scalar,
        registry_location=scalar,
        plot_no=scalar,
        deed_no=scalar,
        registration_year=scalar,
        registration_month=scalar,
        registration_day=scalar,
        total_area=scalar,
        land_unit=scalar,
        vendors=listed,
        vendees=listed,
        deed_type=scalar,
    )


def test_build_document_text_uses_native_text_for_valid_pages_and_ocr_for_others():
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Native text.",
            has_valid_text_layer=True,
        ),
        Page(
            page_number=2,
            image_bytes=b"",
            native_text=None,
            has_valid_text_layer=False,
        ),
    ]
    ocr_text_by_page = {2: "OCR text."}

    result = pipeline._build_document_text(pages, ocr_text_by_page)

    assert result == "Native text.\nOCR text."


def test_run_pipeline_batches_ocr_and_merges_document_text(monkeypatch):
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Clean typed text.",
            has_valid_text_layer=True,
        ),
        Page(
            page_number=2,
            image_bytes=b"scanned",
            native_text=None,
            has_valid_text_layer=False,
        ),
    ]
    monkeypatch.setattr(pipeline, "split_pdf_pages", lambda pdf_path: pages)
    monkeypatch.setattr(pipeline, "preprocess_image", lambda page: b"processed")

    def fake_extract_ocr_batch(page_images):
        assert len(page_images) == 1
        return [OcrPageResult(page_number=2, raw_text="OCR'd text.")]

    monkeypatch.setattr(pipeline.sync_b, "ExtractOcrBatch", fake_extract_ocr_batch)

    async def fake_fill_schema(document_text, baml_options):
        assert "Clean typed text." in document_text
        assert "OCR'd text." in document_text
        return _make_land_record("Rahim", ConfidenceLevel.HIGH)

    monkeypatch.setattr(pipeline.async_b, "FillSchema", fake_fill_schema)

    result = asyncio.run(pipeline.run_pipeline("dummy.pdf"))

    parsed = json.loads(result)
    assert parsed["district"] == {"value": "Rahim", "confidence": "HIGH"}
    assert parsed["vendors"] == {"value": ["Rahim"], "confidence": "HIGH"}


def test_run_pipeline_merges_results_from_both_providers(monkeypatch):
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Some text.",
            has_valid_text_layer=True,
        ),
    ]
    monkeypatch.setattr(pipeline, "split_pdf_pages", lambda pdf_path: pages)

    async def fake_fill_schema(document_text, baml_options):
        if baml_options["client"] == "ClaudeClient":
            return _make_land_record("12.5", ConfidenceLevel.HIGH)
        return _make_land_record("15.0", ConfidenceLevel.MED)

    monkeypatch.setattr(pipeline.async_b, "FillSchema", fake_fill_schema)

    result = asyncio.run(pipeline.run_pipeline("dummy.pdf"))

    parsed = json.loads(result)
    assert parsed["total_area"] == {"value": "12.5", "confidence": "HIGH"}
