# OCR Pipeline Repo Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the repo structure for the Bangla/English OCR pipeline described in `docs/superpowers/specs/2026-07-01-bangla-english-ocr-pipeline-design.md` — one focused module per pipeline stage, with typed data models and stub interfaces, but not implementing the actual OCR/LLM/image logic yet.

**Architecture:** A single flat package `ocr_pipeline/` at the repo root (sibling to `main.py`), with one module per pipeline stage from the design doc: ingestion, preprocessing, llm_calls, validation, review, and a top-level `pipeline.py` orchestrator. The two LLM calls (OCR batch, schema-fill) are defined as BAML functions in `baml_src/*.baml`; BAML's generated `baml_client` provides the typed output classes and schema-aligned parsing, so `ocr_pipeline` modules consume those generated types instead of hand-rolled dataclasses. Each stub function still raises `NotImplementedError`, locking in exact contracts for later work without adding files not yet needed.

**Tech Stack:** Python >=3.13, uv (dependency management), pytest (testing), BAML (`baml-py`) for LLM function definitions and schema-aligned output parsing.

## Global Constraints

- Python >=3.13 (from `pyproject.toml`).
- Use `uv` for all dependency management (`uv add`, `uv add --dev`) — do not hand-edit dependency lists.
- One fixed schema, single document type (per spec) — no per-doc-type abstraction.
- No escalation/re-query loop (per spec) — validation failures route straight to human review.
- Exactly two LLM call shapes in the design: a batched OCR call and a text-only schema-fill call, each implemented as one BAML function (`ExtractOcrBatch`, `FillSchema`) — do not add more.
- LLM output parsing/type-coercion is handled by BAML's schema-aligned parser (via the generated `baml_client` types) — do not hand-roll JSON parsing or type coercion for LLM outputs anywhere in `ocr_pipeline`.
- Keep `ocr_pipeline/` to 6 package files total — do not split further (e.g. no separate `models.py`; data models that aren't BAML-generated live in the module that produces them).

---

### Task 1: Project scaffolding & test tooling

**Files:**
- Create: `ocr_pipeline/__init__.py`
- Create: `tests/test_package.py`
- Modify: `pyproject.toml` (via `uv add --dev pytest`)

**Interfaces:**
- Produces: `ocr_pipeline` importable package, used by every later task and test file.

- [ ] **Step 1: Add pytest as a dev dependency**

Run: `uv add --dev pytest`
Expected: `pyproject.toml` gains a `[dependency-groups]` / `dev` entry for pytest, and `uv.lock` is created/updated.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_package.py
import ocr_pipeline


def test_package_importable():
    assert ocr_pipeline is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline'`

- [ ] **Step 4: Create the package**

```python
# ocr_pipeline/__init__.py
```

Empty file — just a package marker.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_package.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock ocr_pipeline/__init__.py tests/test_package.py
git commit -m "chore: scaffold ocr_pipeline package and pytest tooling"
```

---

### Task 2: BAML schema & client setup

**Files:**
- Create: `baml_src/generators.baml`
- Create: `baml_src/clients.baml`
- Create: `baml_src/ocr.baml`
- Generated: `baml_client/` (created by `baml-cli generate` — do not hand-write)
- Create: `tests/test_baml_schema.py`
- Modify: `pyproject.toml` (via `uv add baml-py`)

**Interfaces:**
- Produces:
  - `baml_client.types.OcrPageResult` (fields: `page_number: int`, `raw_text: str`, `bounding_boxes: list[BoundingBox]`) — consumed by Task 5.
  - `baml_client.types.BoundingBox` (fields: `x0: int`, `y0: int`, `x1: int`, `y1: int`) — consumed by Task 5.
  - `baml_client.types.SchemaField` (fields: `field_name: str`, `value: str | None`, `confidence: float`) — consumed by Tasks 5, 6, 7.
  - `baml_client.b.ExtractOcrBatch(page_images: list[Image]) -> list[OcrPageResult]` — consumed by Task 5.
  - `baml_client.b.FillSchema(document_text: str) -> list[SchemaField]` — consumed by Task 5.

- [ ] **Step 1: Add the BAML dependency**

Run: `uv add baml-py`
Expected: `pyproject.toml` gains `baml-py` under `dependencies`, `uv.lock` updated.

- [ ] **Step 2: Initialize the BAML project**

Run: `uv run baml-cli init`
Expected: creates a `baml_src/` directory with starter example `.baml` files (e.g. `baml_src/resume.baml`, `baml_src/clients.baml`, `baml_src/generators.baml`).

- [ ] **Step 3: Remove the starter example files, keep the generator config**

Run: `rm baml_src/resume.baml` (or whatever example file(s) `init` created besides `clients.baml`/`generators.baml`)
Expected: only `baml_src/clients.baml` and `baml_src/generators.baml` remain from the starter scaffold.

- [ ] **Step 4: Configure the generator for sync Python/Pydantic output**

```baml
// baml_src/generators.baml
generator target {
    output_type "python/pydantic"
    output_dir "../"
    default_client_mode "sync"
    version "0.203.1"
}
```

- [ ] **Step 5: Configure the LLM client**

```baml
// baml_src/clients.baml
client<llm> DefaultClient {
  provider anthropic
  options {
    model "claude-sonnet-4-20250514"
    temperature 0
  }
}
```

- [ ] **Step 6: Define the OCR batch and schema-fill BAML functions**

```baml
// baml_src/ocr.baml
class BoundingBox {
  x0 int
  y0 int
  x1 int
  y1 int
}

class OcrPageResult {
  page_number int
  raw_text string
  bounding_boxes BoundingBox[]
}

class SchemaField {
  field_name string
  value string?
  confidence float
}

function ExtractOcrBatch(page_images: image[]) -> OcrPageResult[] {
  client DefaultClient
  prompt #"
    Transcribe each of the following document page images exactly as
    written, preserving mixed Bangla and English text. For each page,
    return its raw text and bounding boxes for each text line/region.

    {{ ctx.output_format }}
  "#
}

function FillSchema(document_text: string) -> SchemaField[] {
  client DefaultClient
  prompt #"
    Extract the fixed set of schema fields from the following document
    text. For each field, return its value (or null if not found) and a
    confidence score between 0 and 1.

    Document text:
    ---
    {{ document_text }}
    ---

    {{ ctx.output_format }}
  "#
}
```

- [ ] **Step 7: Generate the typed Python client**

Run: `uv run baml-cli generate`
Expected: creates/updates `baml_client/` at the repo root, containing `types.py` (with `BoundingBox`, `OcrPageResult`, `SchemaField` Pydantic models) and the `b` client object.

- [ ] **Step 8: Write the failing tests**

```python
# tests/test_baml_schema.py
from baml_client.types import BoundingBox, OcrPageResult, SchemaField


def test_ocr_page_result_fields():
    box = BoundingBox(x0=0, y0=0, x1=10, y1=10)
    result = OcrPageResult(page_number=1, raw_text="text", bounding_boxes=[box])
    assert result.page_number == 1
    assert result.raw_text == "text"
    assert result.bounding_boxes == [box]


def test_schema_field_fields():
    field = SchemaField(field_name="owner_name", value="Rahim", confidence=0.9)
    assert field.field_name == "owner_name"
    assert field.value == "Rahim"
    assert field.confidence == 0.9
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_baml_schema.py -v`
Expected: PASS (2 passed) — constructing these generated Pydantic models doesn't call the LLM, so no API key is required yet.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock baml_src/ baml_client/ tests/test_baml_schema.py
git commit -m "feat: add BAML schema and generated client for OCR batch and schema-fill calls"
```

---

### Task 3: Ingestion module (page splitting + native text-layer detection)

**Files:**
- Create: `ocr_pipeline/ingestion.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: nothing (first stage of the pipeline).
- Produces:
  - `Page` dataclass with fields `page_number: int`, `image_bytes: bytes`, `native_text: str | None`, `has_valid_text_layer: bool` — consumed by Tasks 4, 5, 7.
  - `split_pdf_pages(pdf_path: str) -> list[Page]` — consumed by Task 8.
  - `is_valid_bangla_text(text: str) -> bool` — consumed by Task 8 (routing decision).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ingestion.py
import pytest

from ocr_pipeline.ingestion import Page, is_valid_bangla_text, split_pdf_pages


def test_page_dataclass_fields():
    page = Page(
        page_number=1,
        image_bytes=b"",
        native_text="some text",
        has_valid_text_layer=True,
    )
    assert page.page_number == 1
    assert page.image_bytes == b""
    assert page.native_text == "some text"
    assert page.has_valid_text_layer is True


def test_split_pdf_pages_not_implemented():
    with pytest.raises(NotImplementedError):
        split_pdf_pages("dummy.pdf")


def test_is_valid_bangla_text_not_implemented():
    with pytest.raises(NotImplementedError):
        is_valid_bangla_text("dummy text")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.ingestion'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/ingestion.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline/ingestion.py tests/test_ingestion.py
git commit -m "feat: add ingestion module with Page model and stub interfaces"
```

---

### Task 4: Preprocessing module (image cleanup)

**Files:**
- Create: `ocr_pipeline/preprocessing.py`
- Create: `tests/test_preprocessing.py`

**Interfaces:**
- Consumes: `Page` from `ocr_pipeline.ingestion`.
- Produces: `preprocess_image(page: Page) -> bytes` — consumed by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preprocessing.py
import pytest

from ocr_pipeline.ingestion import Page
from ocr_pipeline.preprocessing import preprocess_image


def test_preprocess_image_not_implemented():
    page = Page(
        page_number=1,
        image_bytes=b"",
        native_text=None,
        has_valid_text_layer=False,
    )
    with pytest.raises(NotImplementedError):
        preprocess_image(page)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.preprocessing'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/preprocessing.py
from ocr_pipeline.ingestion import Page


def preprocess_image(page: Page) -> bytes:
    """Deskew, correct perspective, and adjust contrast/denoise for a scanned page."""
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline/preprocessing.py tests/test_preprocessing.py
git commit -m "feat: add preprocessing module with stub interface"
```

---

### Task 5: LLM calls module (wraps BAML OCR batch + schema-fill)

**Files:**
- Create: `ocr_pipeline/llm_calls.py`
- Create: `tests/test_llm_calls.py`

**Interfaces:**
- Consumes:
  - `Page` from `ocr_pipeline.ingestion`.
  - `baml_client.types.OcrPageResult`, `baml_client.types.SchemaField` (generated in Task 2).
- Produces:
  - `call_ocr_batch(pages: list[Page]) -> list[OcrPageResult]` — consumed by Task 8.
  - `call_schema_fill(document_text: str) -> list[SchemaField]` — consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_calls.py
import pytest

from ocr_pipeline.ingestion import Page
from ocr_pipeline.llm_calls import call_ocr_batch, call_schema_fill


def test_call_ocr_batch_not_implemented():
    page = Page(page_number=1, image_bytes=b"", native_text=None, has_valid_text_layer=False)
    with pytest.raises(NotImplementedError):
        call_ocr_batch([page])


def test_call_schema_fill_not_implemented():
    with pytest.raises(NotImplementedError):
        call_schema_fill("merged document text")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm_calls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.llm_calls'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/llm_calls.py
from baml_client.types import OcrPageResult, SchemaField

from ocr_pipeline.ingestion import Page


def call_ocr_batch(pages: list[Page]) -> list[OcrPageResult]:
    """Wraps baml_client.b.ExtractOcrBatch; BAML handles the prompt and
    schema-aligned parsing of the response into OcrPageResult objects."""
    raise NotImplementedError


def call_schema_fill(document_text: str) -> list[SchemaField]:
    """Wraps baml_client.b.FillSchema; BAML handles the prompt and
    schema-aligned parsing of the response into SchemaField objects."""
    raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_calls.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline/llm_calls.py tests/test_llm_calls.py
git commit -m "feat: add llm_calls module wrapping BAML OCR batch and schema-fill functions"
```

---

### Task 6: Validation module

**Files:**
- Create: `ocr_pipeline/validation.py`
- Create: `tests/test_validation.py`

**Interfaces:**
- Consumes: `baml_client.types.SchemaField`.
- Produces: `validate_field(field: SchemaField) -> bool` — consumed by Task 8.

Note: BAML's schema-aligned parser already guarantees `SchemaField` instances are correctly typed/coerced (e.g. `confidence` is a real `float`). This module is only for business-rule sanity checks (e.g. confidence thresholds, per-field format rules) on top of that — not for re-parsing or re-coercing LLM output.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validation.py
import pytest

from baml_client.types import SchemaField
from ocr_pipeline.validation import validate_field


def test_validate_field_not_implemented():
    field = SchemaField(field_name="area", value="12.5", confidence=0.4)
    with pytest.raises(NotImplementedError):
        validate_field(field)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.validation'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/validation.py
from baml_client.types import SchemaField


def validate_field(field: SchemaField) -> bool:
    """Business-rule sanity checks (confidence threshold, per-field format
    rules) on top of BAML's schema-aligned parsing. Returns True if it passes."""
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_validation.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline/validation.py tests/test_validation.py
git commit -m "feat: add validation module with stub interface"
```

---

### Task 7: Review module (human-in-the-loop queue)

**Files:**
- Create: `ocr_pipeline/review.py`
- Create: `tests/test_review.py`

**Interfaces:**
- Consumes: `baml_client.types.SchemaField`.
- Produces:
  - `ReviewItem` dataclass with fields `field: SchemaField`, `source_page: int`, `cropped_image_bytes: bytes | None` — consumed by Task 8.
  - `enqueue_for_review(item: ReviewItem) -> None` — consumed by Task 8.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review.py
import pytest

from baml_client.types import SchemaField
from ocr_pipeline.review import ReviewItem, enqueue_for_review


def test_review_item_dataclass_fields():
    field = SchemaField(field_name="plot_no", value=None, confidence=0.2)
    item = ReviewItem(field=field, source_page=3, cropped_image_bytes=None)
    assert item.field is field
    assert item.source_page == 3
    assert item.cropped_image_bytes is None


def test_enqueue_for_review_not_implemented():
    field = SchemaField(field_name="plot_no", value=None, confidence=0.2)
    item = ReviewItem(field=field, source_page=3, cropped_image_bytes=None)
    with pytest.raises(NotImplementedError):
        enqueue_for_review(item)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.review'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/review.py
from dataclasses import dataclass

from baml_client.types import SchemaField


@dataclass
class ReviewItem:
    field: SchemaField
    source_page: int
    cropped_image_bytes: bytes | None


def enqueue_for_review(item: ReviewItem) -> None:
    """Send a failed-validation or low-confidence field to the human review queue."""
    raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ocr_pipeline/review.py tests/test_review.py
git commit -m "feat: add review module with stub interface"
```

---

### Task 8: Pipeline orchestrator

**Files:**
- Create: `ocr_pipeline/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `split_pdf_pages` from `ocr_pipeline.ingestion`.
- Produces: `run_pipeline(pdf_path: str) -> None` — the pipeline's public entry point, wiring stages in the order defined by the design doc (ingestion → preprocessing → BAML OCR batch call → merge → BAML schema-fill call → validation → review).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import pytest

from ocr_pipeline.pipeline import run_pipeline


def test_run_pipeline_not_implemented():
    with pytest.raises(NotImplementedError):
        run_pipeline("dummy.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_pipeline.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# ocr_pipeline/pipeline.py
from ocr_pipeline.ingestion import split_pdf_pages


def run_pipeline(pdf_path: str) -> None:
    """Entry point: split_pdf_pages -> preprocess -> BAML OCR batch call ->
    merge -> BAML schema-fill call -> validate -> route failures to review.
    Stages beyond page splitting are not implemented yet.
    """
    split_pdf_pages(pdf_path)
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS (13 passed) — all tests from Tasks 1-8 pass together.

- [ ] **Step 6: Commit**

```bash
git add ocr_pipeline/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrator wiring all stages"
```
