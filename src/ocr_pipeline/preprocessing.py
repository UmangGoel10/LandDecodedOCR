from ocr_pipeline.ingestion import Page


def preprocess_image(page: Page) -> bytes:
    """Deskew, correct perspective, and adjust contrast/denoise for a scanned page."""
    raise NotImplementedError
