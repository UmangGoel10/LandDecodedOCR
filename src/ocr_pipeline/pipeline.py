import asyncio
import base64

from baml_py import Image

from baml_client import b as sync_b
from baml_client.async_client import b as async_b
from ocr_pipeline.ingestion import Page, split_pdf_pages
from ocr_pipeline.preprocessing import preprocess_image
from ocr_pipeline.review import merge_dual_provider_fields


def _build_document_text(pages: list[Page], ocr_text_by_page: dict[int, str]) -> str:
    parts = []
    for page in pages:
        if page.has_valid_text_layer:
            parts.append(page.native_text or "")
        else:
            parts.append(ocr_text_by_page.get(page.page_number, ""))
    return "\n".join(parts)


async def run_pipeline(pdf_path: str) -> str:
    pages = split_pdf_pages(pdf_path)

    ocr_pages = [page for page in pages if not page.has_valid_text_layer]
    ocr_text_by_page: dict[int, str] = {}
    if ocr_pages:
        images = []
        for page in ocr_pages:
            processed_bytes = preprocess_image(page)
            encoded = base64.b64encode(processed_bytes).decode("ascii")
            images.append(Image.from_base64("image/png", encoded))
        ocr_results = sync_b.ExtractOcrBatch(page_images=images)
        for result in ocr_results:
            ocr_text_by_page[result.page_number] = result.raw_text

    document_text = _build_document_text(pages, ocr_text_by_page)

    # Claude and Gemini are independent calls with no data dependency between
    # them; run them concurrently instead of paying their latency twice.
    claude_fields, gemini_fields = await asyncio.gather(
        async_b.FillSchema(document_text, baml_options={"client": "ClaudeClient"}),
        async_b.FillSchema(document_text, baml_options={"client": "GeminiClient"}),
    )

    merged_fields = merge_dual_provider_fields(claude_fields, gemini_fields)

    return merged_fields.model_dump_json()
