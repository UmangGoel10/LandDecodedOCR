from dataclasses import dataclass

import fitz


@dataclass
class Page:
    page_number: int
    image_bytes: bytes
    native_text: str | None
    has_valid_text_layer: bool


def split_pdf_pages(pdf_path: str) -> list[Page]:
    pages = []
    with fitz.open(pdf_path) as doc:
        for index, pdf_page in enumerate(doc):
            text = pdf_page.get_text()
            image_bytes = pdf_page.get_pixmap(dpi=200).tobytes("png")
            has_embedded_image = len(pdf_page.get_images()) > 0
            native_text = text if text else None
            has_valid_text_layer = (
                not has_embedded_image and bool(text) and is_valid_bangla_text(text)
            )
            pages.append(
                Page(
                    page_number=index + 1,
                    image_bytes=image_bytes,
                    native_text=native_text,
                    has_valid_text_layer=has_valid_text_layer,
                )
            )
    return pages


_ALLOWED_PUNCTUATION = set(".,;:!?'\"-()/")
_BANGLA_BLOCK_START = chr(0x0980)
_BANGLA_BLOCK_END = chr(0x09FF)


def _is_allowed_char(char: str) -> bool:
    if _BANGLA_BLOCK_START <= char <= _BANGLA_BLOCK_END:
        return True
    if char.isascii() and char.isalnum():
        return True
    return char in _ALLOWED_PUNCTUATION


def is_valid_bangla_text(text: str) -> bool:
    non_whitespace = [char for char in text if not char.isspace()]
    if not non_whitespace:
        return False

    other_count = sum(1 for char in non_whitespace if not _is_allowed_char(char))
    other_ratio = other_count / len(non_whitespace)
    return other_ratio <= 0.05
