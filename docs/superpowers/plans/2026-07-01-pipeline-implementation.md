# Pipeline Module Implementation Plan (Dual-Provider Schema-Fill, Land Record Schema)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `NotImplementedError` stub in `src/ocr_pipeline/pipeline.py` (`run_pipeline`) with a real implementation that wires ingestion, preprocessing, OCR, and a dual-provider (Claude + Gemini) schema-fill against a concrete `LandRecordFields` schema, with confidence-based merging, per `docs/superpowers/specs/2026-07-01-confidence-gate-design.md`, `docs/superpowers/specs/2026-07-01-pipeline-module-design.md`, and `docs/superpowers/specs/2026-07-01-land-record-schema-design.md` (the last of which supersedes the generic `SchemaField` shape used in the first two).

**Architecture:** BAML schema changes first (a `LandRecordFields` class built from reusable `FieldValue`/`ListFieldValue` pairs, a `ConfidenceLevel` enum, and a second provider client), then `review.py` gets two small pure functions (`apply_confidence_gate`, `merge_dual_provider_fields`) operating on whole `LandRecordFields` objects, then `pipeline.py` wires everything together and returns a JSON string.

**Tech Stack:** Python >=3.13, BAML (`baml-py`, already installed), `baml_py.Image` for multimodal input, pytest with `monkeypatch` for mocking LLM calls.

## Global Constraints

- **No live LLM calls, ever, in this project right now.** Every test that touches `ExtractOcrBatch` or `FillSchema` must mock/monkeypatch those call sites — never let a test actually invoke `baml_client.b.*`.
- `ExtractOcrBatch` stays single-provider (`ClaudeClient` only) — no dual-provider ensemble for OCR transcription, only for `FillSchema`.
- `FillSchema(document_text: string) -> LandRecordFields` — a single structured object per document, not a list. `LandRecordFields` has exactly these 15 fields, each `FieldValue` (scalar) or `ListFieldValue` (`vendors`, `vendees`): `district`, `block`, `mouza`, `police_station`, `registry_location`, `plot_no`, `deed_no`, `registration_year`, `registration_month`, `registration_day`, `total_area`, `land_unit`, `vendors`, `vendees`, `deed_type`. No `remarks` field (dropped).
- `FieldValue { value string?, confidence ConfidenceLevel }`; `ListFieldValue { value string[], confidence ConfidenceLevel }`. `ConfidenceLevel` is `LOW`/`MED`/`HIGH`; `LOW` means the LLM judges the value likely hallucinated.
- No human-review queue, no logging/trace of nulled fields — this was explicitly removed.
- Confidence-gate + merge tie-break rule (exact): rank `LOW < MED < HIGH`; higher rank wins; on a tie, keep the value if both sides agree, else null it (`None` for `FieldValue`, `[]` for `ListFieldValue`).
- `run_pipeline`'s signature changes from `(pdf_path: str) -> None` to `(pdf_path: str) -> str`, returning JSON (`json.dumps(merged.model_dump(mode="json"))`).
- Use `uv` for all dependency management — no new dependencies are needed in this plan (BAML/pydantic are already installed).

---

### Task 1: BAML schema — `LandRecordFields`, `ConfidenceLevel`, Gemini client

**Files:**
- Modify: `src/baml_src/clients.baml` (rename `DefaultClient` → `ClaudeClient`, add `GeminiClient`)
- Modify: `src/baml_src/ocr.baml` (add `ConfidenceLevel` enum, `FieldValue`/`ListFieldValue`/`LandRecordFields` classes, replace `SchemaField`, update both functions)
- Modify: `tests/test_baml_schema.py` (replace `SchemaField` tests with `LandRecordFields` tests)

**Interfaces:**
- Produces: `baml_client.types.ConfidenceLevel` (enum: `LOW`, `MED`, `HIGH`) — consumed by Task 2 (`review.py`).
- Produces: `baml_client.types.FieldValue { value: str | None, confidence: ConfidenceLevel }` — consumed by Task 2.
- Produces: `baml_client.types.ListFieldValue { value: list[str], confidence: ConfidenceLevel }` — consumed by Task 2.
- Produces: `baml_client.types.LandRecordFields` (15 named fields, listed in Global Constraints) — consumed by Task 2, Task 3.
- Produces: BAML clients named `"ClaudeClient"` and `"GeminiClient"` — consumed by Task 3 via `baml_options={"client": ...}`.

- [ ] **Step 1: Replace the test file**

Replace the entire contents of `tests/test_baml_schema.py` with:

```python
from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue, OcrPageResult


def test_ocr_page_result_fields():
    result = OcrPageResult(page_number=1, raw_text="text")
    assert result.page_number == 1
    assert result.raw_text == "text"


def test_field_value_fields():
    field = FieldValue(value="Rahim", confidence=ConfidenceLevel.HIGH)
    assert field.value == "Rahim"
    assert field.confidence == ConfidenceLevel.HIGH


def test_list_field_value_fields():
    field = ListFieldValue(value=["Rahim", "Karim"], confidence=ConfidenceLevel.MED)
    assert field.value == ["Rahim", "Karim"]
    assert field.confidence == ConfidenceLevel.MED


def test_land_record_fields_construction():
    empty = FieldValue(value=None, confidence=ConfidenceLevel.LOW)
    empty_list = ListFieldValue(value=[], confidence=ConfidenceLevel.LOW)
    record = LandRecordFields(
        district=empty,
        block=empty,
        mouza=empty,
        police_station=empty,
        registry_location=empty,
        plot_no=empty,
        deed_no=empty,
        registration_year=empty,
        registration_month=empty,
        registration_day=empty,
        total_area=empty,
        land_unit=empty,
        vendors=empty_list,
        vendees=empty_list,
        deed_type=empty,
    )
    assert record.district is empty
    assert record.vendors is empty_list
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_baml_schema.py -v`
Expected: FAIL — `ImportError` for `FieldValue`/`ListFieldValue`/`LandRecordFields` (don't exist in the generated client yet).

- [ ] **Step 3: Update the BAML client definitions**

Replace the entire contents of `src/baml_src/clients.baml` with:

```baml
client<llm> ClaudeClient {
  provider anthropic
  options {
    model "claude-sonnet-4-20250514"
    temperature 0
  }
}

client<llm> GeminiClient {
  provider google-ai
  options {
    model "gemini-2.5-pro"
    temperature 0
  }
}
```

- [ ] **Step 4: Update the BAML schema and functions**

Replace the entire contents of `src/baml_src/ocr.baml` with:

```baml
enum ConfidenceLevel {
  LOW
  MED
  HIGH
}

class OcrPageResult {
  page_number int
  raw_text string
}

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

function ExtractOcrBatch(page_images: image[]) -> OcrPageResult[] {
  client ClaudeClient
  prompt #"
    Transcribe each of the following document page images exactly as
    written, preserving mixed Bangla and English text. For each page,
    return its raw text.

    {{ ctx.output_format }}
  "#
}

function FillSchema(document_text: string) -> LandRecordFields {
  client ClaudeClient
  prompt #"
    Extract the following fixed set of fields from the land record
    document text below. For each field, return its value (or null/empty
    if not found) and a confidence level: LOW if the value is likely
    hallucinated or not actually present in the text, MED if plausible but
    uncertain, HIGH if clearly and directly stated.

    Fields to extract:
    - district, block, mouza, police_station, registry_location: location
      details of the land record.
    - plot_no: the plot number, whichever of LR/RS/CS plot number is
      present in the document.
    - deed_no: the deed number.
    - registration_year, registration_month, registration_day: the date
      the deed was registered, as separate values.
    - total_area: the total area of land transferred/given.
    - land_unit: the unit for total_area (e.g. decimal, acre, bigha, katha).
    - vendors: list of people transferring the land, with whatever info
      about each is extractable from the text.
    - vendees: list of people receiving the land, with whatever info about
      each is extractable from the text.
    - deed_type: the type of deed (e.g. gift, sale, partition).

    Document text:
    ---
    {{ document_text }}
    ---

    {{ ctx.output_format }}
  "#
}
```

- [ ] **Step 5: Regenerate the BAML client**

Run: `uv run baml-cli generate --from src/baml_src`
Expected: `src/baml_client/types.py` now defines `ConfidenceLevel`, `FieldValue`, `ListFieldValue`, and `LandRecordFields`; `SchemaField` no longer exists.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_baml_schema.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: `tests/test_review.py` and `tests/test_pipeline.py` will fail at this point (they still reference the old `SchemaField`/`validate_field`/stub shapes) — that's expected and fixed in Tasks 2-3. Confirm no *other* unrelated regressions (ingestion/preprocessing tests still pass).

```bash
git add src/baml_src/clients.baml src/baml_src/ocr.baml src/baml_client/ tests/test_baml_schema.py
git commit -m "feat: replace SchemaField with LandRecordFields schema, add GeminiClient"
```

---

### Task 2: `apply_confidence_gate`

**Files:**
- Modify: `src/ocr_pipeline/review.py` (remove `ReviewItem`/`enqueue_for_review`/`validate_field`, add `apply_confidence_gate`)
- Modify: `tests/test_review.py` (full rewrite)

**Interfaces:**
- Consumes: `baml_client.types.LandRecordFields`, `ConfidenceLevel`, `FieldValue`, `ListFieldValue` (Task 1).
- Produces: `apply_confidence_gate(fields: LandRecordFields) -> LandRecordFields` — consumed by Task 3 (`merge_dual_provider_fields`).
- Produces: `_FIELD_NAMES: list[str]` (module-level constant, the 15 field names) and `_LIST_FIELDS: set[str]` (`{"vendors", "vendees"}`) — consumed by Task 3.

- [ ] **Step 1: Replace the test file**

Replace the entire contents of `tests/test_review.py` with:

```python
from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue
from ocr_pipeline.review import apply_confidence_gate


def _make_land_record(**overrides) -> LandRecordFields:
    defaults = {
        "district": FieldValue(value="Dhaka", confidence=ConfidenceLevel.HIGH),
        "block": FieldValue(value="Block A", confidence=ConfidenceLevel.HIGH),
        "mouza": FieldValue(value="Mouza X", confidence=ConfidenceLevel.HIGH),
        "police_station": FieldValue(value="PS 1", confidence=ConfidenceLevel.HIGH),
        "registry_location": FieldValue(value="Registry 1", confidence=ConfidenceLevel.HIGH),
        "plot_no": FieldValue(value="123", confidence=ConfidenceLevel.HIGH),
        "deed_no": FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH),
        "registration_year": FieldValue(value="2020", confidence=ConfidenceLevel.HIGH),
        "registration_month": FieldValue(value="5", confidence=ConfidenceLevel.HIGH),
        "registration_day": FieldValue(value="10", confidence=ConfidenceLevel.HIGH),
        "total_area": FieldValue(value="12.5", confidence=ConfidenceLevel.HIGH),
        "land_unit": FieldValue(value="decimal", confidence=ConfidenceLevel.HIGH),
        "vendors": ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.HIGH),
        "vendees": ListFieldValue(value=["Karim"], confidence=ConfidenceLevel.HIGH),
        "deed_type": FieldValue(value="sale", confidence=ConfidenceLevel.HIGH),
    }
    defaults.update(overrides)
    return LandRecordFields(**defaults)


def test_apply_confidence_gate_nulls_low_confidence_scalar_field():
    record = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.LOW)
    )

    result = apply_confidence_gate(record)

    assert result.total_area.value is None
    assert result.total_area.confidence == ConfidenceLevel.LOW
    # Unrelated fields are untouched.
    assert result.district.value == "Dhaka"


def test_apply_confidence_gate_empties_low_confidence_list_field():
    record = _make_land_record(
        vendors=ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.LOW)
    )

    result = apply_confidence_gate(record)

    assert result.vendors.value == []
    assert result.vendors.confidence == ConfidenceLevel.LOW


def test_apply_confidence_gate_keeps_medium_and_high_confidence_values():
    record = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.MED),
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH),
    )

    result = apply_confidence_gate(record)

    assert result.total_area.value == "12.5"
    assert result.deed_no.value == "D-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review.py -v`
Expected: FAIL — `ImportError` for `apply_confidence_gate` (doesn't exist yet).

- [ ] **Step 3: Replace the implementation**

Replace the entire contents of `src/ocr_pipeline/review.py` with:

```python
from baml_client.types import ConfidenceLevel, LandRecordFields

_FIELD_NAMES = [
    "district",
    "block",
    "mouza",
    "police_station",
    "registry_location",
    "plot_no",
    "deed_no",
    "registration_year",
    "registration_month",
    "registration_day",
    "total_area",
    "land_unit",
    "vendors",
    "vendees",
    "deed_type",
]
_LIST_FIELDS = {"vendors", "vendees"}


def apply_confidence_gate(fields: LandRecordFields) -> LandRecordFields:
    updates = {}
    for name in _FIELD_NAMES:
        current = getattr(fields, name)
        if current.confidence == ConfidenceLevel.LOW:
            empty_value = [] if name in _LIST_FIELDS else None
            updates[name] = current.model_copy(update={"value": empty_value})
        else:
            updates[name] = current
    return fields.model_copy(update=updates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: `tests/test_pipeline.py` will still fail (addressed in Task 3). No other regressions.

```bash
git add src/ocr_pipeline/review.py tests/test_review.py
git commit -m "feat: replace review.py's human-review queue with a confidence gate for LandRecordFields"
```

---

### Task 3: `merge_dual_provider_fields`

**Files:**
- Modify: `src/ocr_pipeline/review.py` (add the function)
- Modify: `tests/test_review.py` (add tests)

**Interfaces:**
- Consumes: `apply_confidence_gate`, `_FIELD_NAMES`, `_LIST_FIELDS` (Task 2).
- Produces: `merge_dual_provider_fields(claude_fields: LandRecordFields, gemini_fields: LandRecordFields) -> LandRecordFields` — consumed by Task 4 (`pipeline.py`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_review.py`:

```python
from ocr_pipeline.review import merge_dual_provider_fields


def test_merge_dual_provider_fields_prefers_higher_confidence():
    claude = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        total_area=FieldValue(value="15.0", confidence=ConfidenceLevel.MED)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.total_area.value == "12.5"
    assert merged.total_area.confidence == ConfidenceLevel.HIGH


def test_merge_dual_provider_fields_tie_with_agreement_keeps_value():
    claude = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.deed_no.value == "D-1"


def test_merge_dual_provider_fields_tie_with_disagreement_nulls_value():
    claude = _make_land_record(
        deed_no=FieldValue(value="D-1", confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        deed_no=FieldValue(value="D-2", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.deed_no.value is None


def test_merge_dual_provider_fields_gates_low_confidence_before_comparing():
    claude = _make_land_record(
        total_area=FieldValue(value="12.5", confidence=ConfidenceLevel.LOW)
    )
    gemini = _make_land_record(
        total_area=FieldValue(value="15.0", confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.total_area.value == "15.0"
    assert merged.total_area.confidence == ConfidenceLevel.HIGH


def test_merge_dual_provider_fields_handles_list_field_tie_with_disagreement():
    claude = _make_land_record(
        vendors=ListFieldValue(value=["Rahim"], confidence=ConfidenceLevel.HIGH)
    )
    gemini = _make_land_record(
        vendors=ListFieldValue(value=["Karim"], confidence=ConfidenceLevel.HIGH)
    )

    merged = merge_dual_provider_fields(claude, gemini)

    assert merged.vendors.value == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review.py -v`
Expected: FAIL — `ImportError` for `merge_dual_provider_fields` (doesn't exist yet).

- [ ] **Step 3: Add the implementation**

In `src/ocr_pipeline/review.py`, add after `apply_confidence_gate`:

```python
_CONFIDENCE_RANK = {
    ConfidenceLevel.LOW: 0,
    ConfidenceLevel.MED: 1,
    ConfidenceLevel.HIGH: 2,
}


def merge_dual_provider_fields(
    claude_fields: LandRecordFields, gemini_fields: LandRecordFields
) -> LandRecordFields:
    gated_claude = apply_confidence_gate(claude_fields)
    gated_gemini = apply_confidence_gate(gemini_fields)

    updates = {}
    for name in _FIELD_NAMES:
        claude_field = getattr(gated_claude, name)
        gemini_field = getattr(gated_gemini, name)

        claude_rank = _CONFIDENCE_RANK[claude_field.confidence]
        gemini_rank = _CONFIDENCE_RANK[gemini_field.confidence]

        if claude_rank > gemini_rank:
            updates[name] = claude_field
        elif gemini_rank > claude_rank:
            updates[name] = gemini_field
        elif claude_field.value == gemini_field.value:
            updates[name] = claude_field
        else:
            empty_value = [] if name in _LIST_FIELDS else None
            updates[name] = claude_field.model_copy(update={"value": empty_value})

    return gated_claude.model_copy(update=updates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: `tests/test_pipeline.py` will still fail (addressed in Task 4). No other regressions.

```bash
git add src/ocr_pipeline/review.py tests/test_review.py
git commit -m "feat: add merge_dual_provider_fields for Claude/Gemini LandRecordFields reconciliation"
```

---

### Task 4: `pipeline.py` wiring

**Files:**
- Modify: `src/ocr_pipeline/pipeline.py` (replace the stub)
- Modify: `tests/test_pipeline.py` (replace the stub test — remove the real-fixture-PDF `skipif` test entirely; this task's tests mock all LLM calls, so no real PDF is needed)

**Interfaces:**
- Consumes: `split_pdf_pages`, `Page` from `ocr_pipeline.ingestion`; `preprocess_image` from `ocr_pipeline.preprocessing`; `merge_dual_provider_fields` from `ocr_pipeline.review` (Task 3); `baml_client.b.ExtractOcrBatch`/`FillSchema`, `baml_py.Image` (Task 1's clients/schema).
- Produces: `run_pipeline(pdf_path: str) -> str` — the pipeline's public entry point (final form for this plan).

- [ ] **Step 1: Replace the test file**

Replace the entire contents of `tests/test_pipeline.py` with:

```python
import json

from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue, OcrPageResult
from ocr_pipeline import pipeline
from ocr_pipeline.ingestion import Page


def _make_land_record(value: str, confidence: ConfidenceLevel) -> LandRecordFields:
    scalar = FieldValue(value=value, confidence=confidence)
    listed = ListFieldValue(value=[value], confidence=confidence)
    return LandRecordFields(
        district=scalar,
        block=scalar,
        mouza=scalar,
        police_station=scalar,
        registry_location=scalar,
        plot_no=scalar,
        deed_no=scalar,
        registration_year=scalar,
        registration_month=scalar,
        registration_day=scalar,
        total_area=scalar,
        land_unit=scalar,
        vendors=listed,
        vendees=listed,
        deed_type=scalar,
    )


def test_build_document_text_uses_native_text_for_valid_pages_and_ocr_for_others():
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Native text.",
            has_valid_text_layer=True,
        ),
        Page(
            page_number=2,
            image_bytes=b"",
            native_text=None,
            has_valid_text_layer=False,
        ),
    ]
    ocr_text_by_page = {2: "OCR text."}

    result = pipeline._build_document_text(pages, ocr_text_by_page)

    assert result == "Native text.\nOCR text."


def test_run_pipeline_batches_ocr_and_merges_document_text(monkeypatch):
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Clean typed text.",
            has_valid_text_layer=True,
        ),
        Page(
            page_number=2,
            image_bytes=b"scanned",
            native_text=None,
            has_valid_text_layer=False,
        ),
    ]
    monkeypatch.setattr(pipeline, "split_pdf_pages", lambda pdf_path: pages)
    monkeypatch.setattr(pipeline, "preprocess_image", lambda page: b"processed")

    def fake_extract_ocr_batch(page_images):
        assert len(page_images) == 1
        return [OcrPageResult(page_number=2, raw_text="OCR'd text.")]

    monkeypatch.setattr(pipeline.b, "ExtractOcrBatch", fake_extract_ocr_batch)

    def fake_fill_schema(document_text, baml_options):
        assert "Clean typed text." in document_text
        assert "OCR'd text." in document_text
        return _make_land_record("Rahim", ConfidenceLevel.HIGH)

    monkeypatch.setattr(pipeline.b, "FillSchema", fake_fill_schema)

    result = pipeline.run_pipeline("dummy.pdf")

    parsed = json.loads(result)
    assert parsed["district"] == {"value": "Rahim", "confidence": "HIGH"}
    assert parsed["vendors"] == {"value": ["Rahim"], "confidence": "HIGH"}


def test_run_pipeline_merges_results_from_both_providers(monkeypatch):
    pages = [
        Page(
            page_number=1,
            image_bytes=b"",
            native_text="Some text.",
            has_valid_text_layer=True,
        ),
    ]
    monkeypatch.setattr(pipeline, "split_pdf_pages", lambda pdf_path: pages)

    def fake_fill_schema(document_text, baml_options):
        if baml_options["client"] == "ClaudeClient":
            return _make_land_record("12.5", ConfidenceLevel.HIGH)
        return _make_land_record("15.0", ConfidenceLevel.MED)

    monkeypatch.setattr(pipeline.b, "FillSchema", fake_fill_schema)

    result = pipeline.run_pipeline("dummy.pdf")

    parsed = json.loads(result)
    assert parsed["total_area"] == {"value": "12.5", "confidence": "HIGH"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `AttributeError`/`ImportError` since `pipeline._build_document_text` doesn't exist and `run_pipeline` still raises `NotImplementedError`.

- [ ] **Step 3: Write the implementation**

Replace the entire contents of `src/ocr_pipeline/pipeline.py` with:

```python
import base64
import json

from baml_py import Image

from baml_client import b
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


def run_pipeline(pdf_path: str) -> str:
    pages = split_pdf_pages(pdf_path)

    ocr_pages = [page for page in pages if not page.has_valid_text_layer]
    ocr_text_by_page: dict[int, str] = {}
    if ocr_pages:
        images = []
        for page in ocr_pages:
            processed_bytes = preprocess_image(page)
            encoded = base64.b64encode(processed_bytes).decode("ascii")
            images.append(Image.from_base64("image/png", encoded))
        ocr_results = b.ExtractOcrBatch(page_images=images)
        for page, result in zip(ocr_pages, ocr_results):
            ocr_text_by_page[page.page_number] = result.raw_text

    document_text = _build_document_text(pages, ocr_text_by_page)

    claude_fields = b.FillSchema(document_text, baml_options={"client": "ClaudeClient"})
    gemini_fields = b.FillSchema(document_text, baml_options={"client": "GeminiClient"})

    merged_fields = merge_dual_provider_fields(claude_fields, gemini_fields)

    return json.dumps(merged_fields.model_dump(mode="json"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (3 passed). If the JSON assertions fail because `confidence` serializes differently than the plain enum-name string (e.g. as `"ConfidenceLevel.HIGH"` or different casing), adjust the test's expected literal to match the actual serialized form — don't change `run_pipeline`'s serialization approach.

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions across the whole suite.

```bash
git add src/ocr_pipeline/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire pipeline.py with dual-provider LandRecordFields schema-fill and confidence-based merge"
```
