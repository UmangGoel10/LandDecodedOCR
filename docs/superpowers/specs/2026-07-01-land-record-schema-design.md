# Land Record Schema — Design

## Context

This design replaces the generic `SchemaField{field_name, value, confidence}`
list from `docs/superpowers/specs/2026-07-01-confidence-gate-design.md` and
`docs/superpowers/specs/2026-07-01-pipeline-module-design.md` with a
concrete, named schema matching the actual 17 fields expected from the OCR
pipeline's structured extraction (per user-provided requirements). Those
two prior specs' *behavior* (null-on-LOW-confidence, rank-then-agreement
tie-break for dual-provider merge) carries over unchanged — only the data
shape changes. No code implementing the old `SchemaField` shape had been
written yet, so nothing is being torn out, only redirected before it lands.

## Non-goals

- Remarks (originally item 17 of the requested field list) is dropped —
  no confidence pairing was defined for it and it's out of scope for now.
- Still no live LLM calls anywhere in this project (standing constraint).
- Still no human-review queue, no per-field trace/logging.
- `ExtractOcrBatch` stays single-provider (Claude only); the dual-provider
  ensemble applies only to `FillSchema`, unchanged from the prior design.

## Components

### `src/baml_src/ocr.baml`

Replace the generic `SchemaField` class with a reusable value+confidence
pair (BAML has no generics, but does support classes-as-field-types, so
one pair type serves all scalar fields):

```baml
class FieldValue {
  value string?
  confidence ConfidenceLevel
}

class ListFieldValue {
  value string[]
  confidence ConfidenceLevel
}

class LandRecordFields {
  district FieldValue
  block FieldValue
  mouza FieldValue
  police_station FieldValue
  registry_location FieldValue
  plot_no FieldValue
  deed_no FieldValue
  registration_year FieldValue
  registration_month FieldValue
  registration_day FieldValue
  total_area FieldValue
  land_unit FieldValue
  vendors ListFieldValue
  vendees ListFieldValue
  deed_type FieldValue
}
```

`registration_year`/`month`/`day` stay as separate `FieldValue` (string)
fields — BAML has no native `datetime` type (confirmed against BAML's own
docs: "for datetime, use a string").

`FillSchema`'s signature changes from `(document_text: string) ->
SchemaField[]` to `(document_text: string) -> LandRecordFields` — one
structured object per document, not a list. Its prompt lists all 15 fields
by name and what each means (plot number is whichever of LR/RS/CS is
present; vendors/vendees are lists of people with whatever info is
extractable; deed type is free text e.g. gift/sale/partition), plus the
same confidence-level guidance as before (LOW = likely hallucinated, MED =
plausible but uncertain, HIGH = clearly stated).

`ConfidenceLevel` (from the confidence-gate design) is unchanged.

### `src/ocr_pipeline/review.py`

Both functions now operate on the whole `LandRecordFields` object via a
fixed list of its 15 field names, rather than a generic list keyed by
`field_name`:

```python
_FIELD_NAMES = [
    "district", "block", "mouza", "police_station", "registry_location",
    "plot_no", "deed_no", "registration_year", "registration_month",
    "registration_day", "total_area", "land_unit", "vendors", "vendees",
    "deed_type",
]
_LIST_FIELDS = {"vendors", "vendees"}
```

- `apply_confidence_gate(fields: LandRecordFields) -> LandRecordFields`:
  for each of the 15 fields, if its `confidence == ConfidenceLevel.LOW`,
  null its `value` (`None` for scalar `FieldValue` fields, `[]` for the two
  `ListFieldValue` fields). Otherwise leave it unchanged.
- `merge_dual_provider_fields(claude_fields: LandRecordFields, gemini_fields: LandRecordFields) -> LandRecordFields`:
  gates both inputs first, then per field: rank `LOW < MED < HIGH`, higher
  rank wins outright; on a tie, keep the value if both sides agree, else
  null it (scalar equality for `FieldValue`, list equality for
  `ListFieldValue`).

### `src/ocr_pipeline/pipeline.py`

Unchanged flow from the pipeline-module design, except:
- `FillSchema` is still called once per provider (`ClaudeClient`,
  `GeminiClient`), but each call now returns one `LandRecordFields` instead
  of a `SchemaField[]`.
- `merge_dual_provider_fields(claude_result, gemini_result)` returns one
  `LandRecordFields`.
- `run_pipeline` returns `json.dumps(merged.model_dump(mode="json"))` — a
  single JSON object, not a list.

## Testing

Same approach as before (no real LLM calls; `ExtractOcrBatch`/`FillSchema`
mocked in tests), updated for the new shape:
- `apply_confidence_gate`: LOW nulls the value (`None`/`[]` as
  appropriate), MED/HIGH pass through, for both scalar and list fields.
- `merge_dual_provider_fields`: higher-confidence-wins, tie-with-agreement,
  tie-with-disagreement-nulls — covering at least one scalar field and one
  list field (vendors/vendees) case.
- `run_pipeline`'s document-text assembly (unchanged from the prior
  design) and JSON output shape, with `ExtractOcrBatch`/`FillSchema`
  mocked to return fixed `LandRecordFields`/`OcrPageResult` values.
