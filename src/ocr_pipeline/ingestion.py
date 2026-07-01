from dataclasses import dataclass


@dataclass
class Page:
    page_number: int
    image_bytes: bytes
    native_text: str | None
    has_valid_text_layer: bool


def split_pdf_pages(pdf_path: str) -> list[Page]:
    raise NotImplementedError


def is_valid_bangla_text(text: str) -> bool:
    raise NotImplementedError
