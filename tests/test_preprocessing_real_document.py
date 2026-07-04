from pathlib import Path

import cv2
import numpy as np
import pytest

from ocr_pipeline.ingestion import split_pdf_pages
from ocr_pipeline.preprocessing import preprocess_image

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_land_record.pdf"


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(), reason="local-only sample PDF not present"
)
def test_preprocess_image_on_real_scanned_pages():
    pages = split_pdf_pages(str(FIXTURE_PATH))
    scanned_pages = [page for page in pages if not page.has_valid_text_layer]
    assert scanned_pages

    for page in scanned_pages:
        result = preprocess_image(page)

        assert isinstance(result, bytes)
        assert len(result) > 0
        decoded = cv2.imdecode(
            np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
        )
        assert decoded is not None
