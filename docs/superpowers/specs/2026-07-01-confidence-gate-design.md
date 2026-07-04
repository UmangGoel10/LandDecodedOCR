# Confidence Gate: Replacing the Human-Review Queue — Design

## Context

The scaffolding plan originally gave `review.py` two stub responsibilities:
`validate_field` (business-rule checks) and a human-review queue
(`ReviewItem`/`enqueue_for_review`). This design removes the human-review
queue entirely and replaces field-level validation with a simpler
confidence gate. Note: the BAML schema touched here is expected to change
again soon — this implementation is intentionally minimal, not a final
design.

## Change of approach

- No human-review queue. A low-confidence field is not queued for a human
  to look at — it's nulled and the pipeline moves on. There is no log,
  count, or trace of what was nulled (an explicit choice, not an oversight).
- Confidence becomes a three-value enum (`LOW`, `MED`, `HIGH`) returned
  directly by the LLM in the `FillSchema` call, replacing the existing
  `confidence: float`. `LOW` means the LLM itself judges the value likely
  hallucinated/unreliable.

## Components

### `src/baml_src/ocr.baml`

Add:
```baml
enum ConfidenceLevel {
  LOW
  MED
  HIGH
}
```

Change `SchemaField.confidence` from `float` to `ConfidenceLevel`.

Update `FillSchema`'s prompt with one line instructing the LLM on what each
level means, e.g.: "confidence should be LOW if the value is likely
hallucinated or not actually present in the text, MED if plausible but
uncertain, HIGH if clearly and directly stated."

Regenerate the client: `uv run baml-cli generate --from src/baml_src`.

### `src/ocr_pipeline/review.py`

Remove `validate_field`, `ReviewItem`, `enqueue_for_review` entirely.
Replace with:

```python
def apply_confidence_gate(field: SchemaField) -> SchemaField:
    if field.confidence == ConfidenceLevel.LOW:
        return field.model_copy(update={"value": None})
    return field
```

Returns a new `SchemaField` with `value=None` if confidence is `LOW`;
otherwise returns the field unchanged (`MED`/`HIGH` pass through as-is).

## Non-goals

- No logging/auditing of nulled fields.
- No change to `pipeline.py` wiring in this round (it's still a stub that
  only calls `split_pdf_pages` — this design just prepares `review.py` and
  the BAML schema for when pipeline wiring happens).

## Testing

- `tests/test_baml_schema.py`: update `SchemaField` construction to use
  `ConfidenceLevel.HIGH` (or `MED`/`LOW`) instead of a float.
- `tests/test_review.py`: full rewrite — test `apply_confidence_gate` nulls
  `value` for `LOW`, and passes `MED`/`HIGH` fields through unchanged.
