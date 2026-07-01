from ocr_pipeline.ingestion import split_pdf_pages


def run_pipeline(pdf_path: str) -> None:
    """Entry point: split_pdf_pages -> preprocess -> baml_client.b.ExtractOcrBatch ->
    merge -> baml_client.b.FillSchema -> validate_field -> route failures to
    review.enqueue_for_review. Stages beyond page splitting are not implemented yet.
    """
    split_pdf_pages(pdf_path)
    raise NotImplementedError
