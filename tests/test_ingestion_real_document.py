from pathlib import Path

import pytest

from ocr_pipeline.ingestion import split_pdf_pages

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_land_record.pdf"


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(), reason="local-only sample PDF not present"
)
def test_split_pdf_pages_on_real_scanned_document():
    pages = split_pdf_pages(str(FIXTURE_PATH))

    assert len(pages) > 0
    for page in pages:
        assert page.image_bytes

    # Every page in this sample except the last one carries an embedded
    # scanned image — those must always be routed to the image-OCR path,
    # even though their text layer carries a "MASKED" overlay that could
    # otherwise look like plausible (if terse) valid text.
    scanned_pages = pages[:-1]
    assert scanned_pages
    assert all(not page.has_valid_text_layer for page in scanned_pages)
