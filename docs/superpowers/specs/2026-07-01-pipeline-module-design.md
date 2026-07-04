# Pipeline Module: Real Implementation (Dual-Provider Schema-Fill) — Design

## Context

`src/ocr_pipeline/pipeline.py` currently has a stub `run_pipeline(pdf_path: str) -> None` that only calls `split_pdf_pages` before raising `NotImplementedError`. This design covers wiring the full pipeline: ingestion (already implemented) → preprocessing (already implemented) → OCR batch call → merge → dual-provider schema-fill → confidence gate/merge → JSON output.

This design extends and partially supersedes
`docs/superpowers/specs/2026-07-01-confidence-gate-design.md`: that design's
`apply_confidence_gate` stays as specified; this design adds a second
`review.py` function (`merge_dual_provider_fields`) and changes
`clients.baml` further (adding a second provider).

As with the confidence-gate design: the BAML schema is expected to change
again later, so this implementation is intentionally minimal.

## Non-goals

- No live LLM calls anywhere in this project right now (standing
  constraint) — `ExtractOcrBatch`/`FillSchema` call sites must be
  mockable/mocked in tests, never actually invoked.
- `ExtractOcrBatch` (OCR transcription) stays single-provider (Claude only)
  — the dual-provider ensemble applies only to `FillSchema`, since
  `OcrPageResult` has no confidence field to compare on.
- No new persistence/storage layer. `run_pipeline` returns a JSON string;
  what the caller does with it (save, print, serve) is out of scope.

## Components

### `src/baml_src/clients.baml`

Rename `DefaultClient` → `ClaudeClient` (same anthropic provider/model,
name change only). Add:

```baml
client<llm> GeminiClient {
  provider google-ai
  options {
    model "gemini-2.5-pro"
    temperature 0
  }
}
```

`src/baml_src/ocr.baml`'s functions keep referencing `ClaudeClient` as
their default `client` — the Gemini call happens via a call-time override
in Python (`baml_options={"client": "GeminiClient"}`), not a second BAML
function definition.

### `src/ocr_pipeline/review.py`

Adds, alongside `apply_confidence_gate` (from the confidence-gate design):

```python
def merge_dual_provider_fields(
    claude_fields: list[SchemaField], gemini_fields: list[SchemaField]
) -> list[SchemaField]:
```

- Apply `apply_confidence_gate` to every field from both lists first.
- Match fields by `field_name` between the two lists.
- Rank confidence `LOW < MED < HIGH`. Whichever field has the higher rank
  wins outright.
- On a tie (equal confidence rank): if both sides' `value` match, keep it;
  if they differ, null the value (agreement between equally-confident
  models is the passing case; disagreement is itself a signal neither can
  be trusted).

### `src/ocr_pipeline/pipeline.py`

```
split_pdf_pages(pdf_path)
   → pages routed by has_valid_text_layer
   → non-text-layer pages: preprocess_image → base64 → baml_py.Image.from_base64
   → single ExtractOcrBatch call (Claude only) over all such images
   → build one document_text blob, page-ordered:
       valid-text-layer pages use native_text as-is;
       others use the matching OcrPageResult.raw_text
   → FillSchema(document_text, client="ClaudeClient")
   → FillSchema(document_text, client="GeminiClient")
   → merge_dual_provider_fields(claude_result, gemini_result)
   → json.dumps([field.model_dump(mode="json") for field in merged])
   → return (str)
```

`run_pipeline`'s signature changes from `(pdf_path: str) -> None` to
`(pdf_path: str) -> str`.

## Testing

No real LLM calls. `ExtractOcrBatch` and `FillSchema` call sites are
mocked/monkeypatched in tests. Tests cover:
- `merge_dual_provider_fields`: higher-confidence-wins, tie-with-agreement,
  tie-with-disagreement-nulls, cases independent of any real model output.
- `run_pipeline`'s document-text assembly and JSON output shape, with
  `ExtractOcrBatch`/`FillSchema` mocked to return fixed `SchemaField`/
  `OcrPageResult` values.
