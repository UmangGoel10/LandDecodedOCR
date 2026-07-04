# Ingestion Module Real Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `NotImplementedError` stubs in `src/ocr_pipeline/ingestion.py` (`is_valid_bangla_text`, `split_pdf_pages`) with real logic, per `docs/superpowers/specs/2026-07-01-ingestion-module-design.md`.

**Architecture:** `is_valid_bangla_text` is a pure string-classification heuristic with no dependencies. `split_pdf_pages` uses PyMuPDF (`fitz`) to extract native text and render each page to a PNG image, then calls `is_valid_bangla_text` to decide per-page routing. A real (gitignored, local-only) sample PDF backs one additional sanity-check test that's skipped when the file isn't present.

**Tech Stack:** Python >=3.13, PyMuPDF (`pymupdf` package, imports as `fitz`), pytest (existing `tmp_path` fixture for synthetic PDFs).

## Global Constraints

- Use `uv` for all dependency management (`uv add`) — do not hand-edit dependency lists.
- `is_valid_bangla_text`: allowed characters are Bangla Unicode block U+0980–U+09FF, ASCII Latin letters `a-zA-Z`, digits `0-9`, and punctuation `` .,;:!?'"-()/ ``. Return `False` if text is empty/whitespace-only, or if the ratio of "other" (non-allowed, non-whitespace) characters to total non-whitespace characters exceeds 5%. Otherwise `True`.
- `split_pdf_pages`: render every page's image at 200 DPI PNG regardless of text-layer validity (`Page.image_bytes` is non-optional). No custom exception wrapping — let PyMuPDF's own errors propagate.
- The real sample PDF (currently `download (1) (15).pdf` at repo root) must never be committed to git — move it under `tests/fixtures/`, and add `tests/fixtures/` to `.gitignore` before it's referenced by any test.
- Do not modify the `Page` dataclass — its shape is already final from prior scaffolding work.

---

### Task 1: `is_valid_bangla_text` implementation

**Files:**
- Modify: `src/ocr_pipeline/ingestion.py` (replace the stub body)
- Modify: `tests/test_ingestion.py` (add new tests; keep the existing 3 scaffolding tests intact — `is_valid_bangla_text` currently has a `pytest.raises(NotImplementedError)` test that must be replaced, not left alongside real tests)

**Interfaces:**
- Produces: `is_valid_bangla_text(text: str) -> bool` — real implementation, consumed by Task 2's `split_pdf_pages`.

- [ ] **Step 1: Replace the stub `NotImplementedError` test with real behavior tests**

In `tests/test_ingestion.py`, remove this existing test (it tested the stub, which no longer applies):

```python
def test_is_valid_bangla_text_not_implemented():
    with pytest.raises(NotImplementedError):
        is_valid_bangla_text("dummy text")
```

Replace it with:

```python
def test_is_valid_bangla_text_pure_english():
    assert is_valid_bangla_text("Hello, this is a valid English sentence.") is True


def test_is_valid_bangla_text_pure_bangla():
    assert is_valid_bangla_text("এটি একটি বৈধ বাংলা বাক্য।") is True


def test_is_valid_bangla_text_mixed():
    assert is_valid_bangla_text("Owner: রহিম, Plot No: 123") is True


def test_is_valid_bangla_text_gibberish():
    assert is_valid_bangla_text("¤§¶†‡•‰∑∆π√∫≈≠±÷×¥£€¢©®™¤§¶†‡•‰∑∆") is False


def test_is_valid_bangla_text_empty():
    assert is_valid_bangla_text("") is False


def test_is_valid_bangla_text_whitespace_only():
    assert is_valid_bangla_text("   \n\t  ") is False


def test_is_valid_bangla_text_tolerates_small_noise():
    assert is_valid_bangla_text("A mostly clean English sentence with one stray symbol: ¤") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: FAIL — the new tests fail with `NotImplementedError` (from the current stub body), and the old removed test is gone (no collection error).

- [ ] **Step 3: Write the real implementation**

In `src/ocr_pipeline/ingestion.py`, replace:

```python
def is_valid_bangla_text(text: str) -> bool:
    raise NotImplementedError
```

with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: PASS (all `is_valid_bangla_text` tests plus the untouched `Page`/`split_pdf_pages` stub tests — `split_pdf_pages` is still a stub until Task 2)

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add src/ocr_pipeline/ingestion.py tests/test_ingestion.py
git commit -m "feat: implement is_valid_bangla_text with character-class ratio heuristic"
```

---

### Task 2: `split_pdf_pages` implementation

**Files:**
- Modify: `pyproject.toml` (via `uv add pymupdf`)
- Modify: `src/ocr_pipeline/ingestion.py` (replace the stub body, add `import fitz`)
- Modify: `tests/test_ingestion.py` (replace the stub test, add real tests using synthetically generated PDFs)

**Interfaces:**
- Consumes: `is_valid_bangla_text` (Task 1).
- Produces: `split_pdf_pages(pdf_path: str) -> list[Page]` — real implementation, consumed by a future pipeline-wiring task (not in this plan).

- [ ] **Step 1: Add the PyMuPDF dependency**

Run: `uv add pymupdf`
Expected: `pyproject.toml` gains `pymupdf` under `dependencies`, `uv.lock` updated.

- [ ] **Step 2: Replace the stub `NotImplementedError` test with real behavior tests**

In `tests/test_ingestion.py`, remove this existing test:

```python
def test_split_pdf_pages_not_implemented():
    with pytest.raises(NotImplementedError):
        split_pdf_pages("dummy.pdf")
```

Replace it with (uses pytest's built-in `tmp_path` fixture — no new test dependency):

```python
import fitz


def test_split_pdf_pages_returns_one_page_per_pdf_page(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Hello, this is a valid English sentence.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Another valid page of text.")
    doc.save(str(pdf_path))
    doc.close()

    pages = split_pdf_pages(str(pdf_path))

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
    for page in pages:
        assert page.image_bytes
        assert page.native_text is not None
        assert page.has_valid_text_layer is True


def test_split_pdf_pages_blank_page_has_no_valid_text_layer(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    pages = split_pdf_pages(str(pdf_path))

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].native_text is None
    assert pages[0].has_valid_text_layer is False
    assert pages[0].image_bytes
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: FAIL — the new tests fail with `NotImplementedError` from the current stub body.

- [ ] **Step 4: Write the real implementation**

In `src/ocr_pipeline/ingestion.py`, add the import at the top of the file (alongside the existing `from dataclasses import dataclass`):

```python
import fitz
```

Then replace:

```python
def split_pdf_pages(pdf_path: str) -> list[Page]:
    raise NotImplementedError
```

with:

```python
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
```

Note (post-implementation revision): a page carrying any embedded image is
always routed to the OCR path (`has_valid_text_layer = False`), even if its
text layer happens to extract as plausible-looking text — a scanned page
can carry a meaningless overlay (e.g. "MASKED") that would otherwise pass
`is_valid_bangla_text`. This was added after the plan was first written; see
`docs/superpowers/specs/2026-07-01-ingestion-module-design.md` for the
updated flow diagram. No synthetic-image unit test was added for this — the
real sample PDF (Task 3) covers it, since it consists almost entirely of
image-bearing pages.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: PASS (all ingestion tests, including Task 1's).

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add pyproject.toml uv.lock src/ocr_pipeline/ingestion.py tests/test_ingestion.py
git commit -m "feat: implement split_pdf_pages using PyMuPDF"
```

---

### Task 3: Real-document sanity test

**Files:**
- Create: `tests/fixtures/sample_land_record.pdf` (moved from repo root — see Step 1; not committed, see Step 2)
- Modify: `.gitignore` (add `tests/fixtures/`)
- Create: `tests/test_ingestion_real_document.py`

**Interfaces:**
- Consumes: `split_pdf_pages` (Task 2).
- Produces: nothing consumed elsewhere — this is a standalone manual sanity check.

- [ ] **Step 1: Move the sample PDF into the fixtures directory**

Run:
```bash
mkdir -p tests/fixtures
mv "download (1) (15).pdf" tests/fixtures/sample_land_record.pdf
```
Expected: file now at `tests/fixtures/sample_land_record.pdf`; nothing left at the repo root.

- [ ] **Step 2: Gitignore the fixtures directory**

Add this line to `.gitignore`:

```
tests/fixtures/
```

This must happen before the file is ever staged — the sample PDF contains scanned personal-record images and must never enter git history.

- [ ] **Step 3: Write the sanity-check test**

```python
# tests/test_ingestion_real_document.py
from pathlib import Path

import pytest

from ocr_pipeline.ingestion import split_pdf_pages

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_land_record.pdf"


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(), reason="local-only sample PDF not present"
)
def test_split_pdf_pages_on_real_scanned_document():
    pages = split_pdf_pages(str(FIXTURE_PATH))

    assert len(pages) > 0
    for page in pages:
        assert page.image_bytes

    # This sample is a mostly-scanned document — at least one page should
    # be routed to the image-OCR path (no valid native text layer).
    assert any(not page.has_valid_text_layer for page in pages)
```

- [ ] **Step 4: Run the test to verify it passes (or skips cleanly on a fresh clone)**

Run: `uv run pytest tests/test_ingestion_real_document.py -v`
Expected: PASS if `tests/fixtures/sample_land_record.pdf` is present locally (1 passed); SKIPPED if not (e.g. a fresh clone without the local-only fixture).

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS (plus 1 skipped or passed for the real-document test), no regressions.

```bash
git add .gitignore tests/test_ingestion_real_document.py
git commit -m "test: add gitignored real-document sanity check for split_pdf_pages"
```

Note: do NOT `git add` the PDF itself — it's gitignored by design (Step 2).
