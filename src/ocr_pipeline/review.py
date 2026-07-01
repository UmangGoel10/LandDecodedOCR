from dataclasses import dataclass

from baml_client.types import SchemaField


def validate_field(field: SchemaField) -> bool:
    """Business-rule sanity checks (confidence threshold, per-field format
    rules) on top of BAML's schema-aligned parsing. Returns True if it passes."""
    raise NotImplementedError


@dataclass
class ReviewItem:
    field: SchemaField
    source_page: int
    cropped_image_bytes: bytes | None


def enqueue_for_review(item: ReviewItem) -> None:
    """Send a failed-validation or low-confidence field to the human review queue."""
    raise NotImplementedError
