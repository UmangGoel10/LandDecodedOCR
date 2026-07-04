# Ingestion Module: Real Implementation — Design

## Context

`src/ocr_pipeline/ingestion.py` currently has stub implementations of `Page`
(dataclass, already final), `split_pdf_pages`, and `is_valid_bangla_text`
(both raise `NotImplementedError`), scaffolded per
`docs/superpowers/plans/2026-07-01-ocr-pipeline-scaffolding.md`. This design
covers implementing the real logic for the two functions — the first
concrete stage of the OCR pipeline described in
`docs/superpowers/specs/2026-07-01-bangla-english-ocr-pipeline-design.md`.

## Non-goals

- Image preprocessing (`preprocessing.py`), BAML OCR/schema-fill calls,
  validation, and pipeline wiring (`pipeline.py`) remain stubbed —
  out of scope for this round.
- No new API/web layer. `split_pdf_pages` takes a local file path; a future
  endpoint accepting PDF uploads is out of scope here.
- No custom exception types — PyMuPDF's own errors (missing file, corrupt
  PDF) propagate uncaught.

## Flow

For each page in the PDF, decide whether it needs the (future) image-OCR
path or can be accepted as free native text:

```
page → has embedded image (PyMuPDF)?
          ├─ yes → has_valid_text_layer = False, always
          │        (scanned/photographed page — routed to image-OCR path
          │         by a later pipeline stage — regardless of what its text
          │         layer says; a page can carry a plausible-looking but
          │         meaningless overlay, e.g. "MASKED", over a real scan)
          └─ no  → extract native text (PyMuPDF) → is_valid_bangla_text(text)?
                                                       ├─ yes → has_valid_text_layer = True
                                                       │        (native text used as-is, no OCR)
                                                       └─ no  → has_valid_text_layer = False
                                                                (routed to image-OCR path)

Every page also gets a rendered PNG image (200 DPI), regardless of routing,
since Page.image_bytes is a required (non-Optional) field.
```

## Components

### `split_pdf_pages(pdf_path: str) -> list[Page]`

Uses PyMuPDF (`fitz`) — one library for both native text extraction and
page-to-image rendering, avoiding a second dependency (e.g. poppler-based
pdf2image) for the image path.

For each page (1-indexed `page_number`):
1. Extract text via `page.get_text()`.
2. Render the full page to PNG at 200 DPI via `page.get_pixmap(dpi=200)` for
   `image_bytes` — rendered for every page, not conditionally, since the
   field isn't optional.
3. Check for embedded images via `page.get_images()`.
4. `native_text`: the extracted text if non-empty, else `None`.
5. `has_valid_text_layer`: `False` if the page has any embedded image
   (`len(page.get_images()) > 0`) — a scanned/photographed page is always
   OCR'd, even if its text layer happens to look plausible (e.g. a
   "MASKED" overlay). Otherwise, `is_valid_bangla_text(native_text)` if
   text was extracted, else `False`.

Exceptions from PyMuPDF (file not found, corrupt/unopenable PDF) propagate
uncaught — no wrapping.

### `is_valid_bangla_text(text: str) -> bool`

Character-class ratio heuristic, chosen because legacy non-Unicode Bangla
fonts (SutonnyMJ/Bijoy) decode to symbol/Latin-range mojibake rather than
real Bangla Unicode or real English — the goal is catching *that* failure
mode, not enforcing a minimum amount of Bangla content (pages may be pure
English, pure Bangla, or mixed, and all should pass if genuinely typed).

- Classify each non-whitespace character as **allowed** (Bangla Unicode
  block U+0980–U+09FF, ASCII Latin letters `a-zA-Z`, digits `0-9`, and
  punctuation `.,;:!?'"-()/`) or **other**.
- Return `False` if the text is empty or whitespace-only.
- Return `False` if the ratio of "other" characters to total non-whitespace
  characters exceeds **5%**.
- Otherwise return `True`.

## Dependency

Add `pymupdf` via `uv add pymupdf` (the package name; imports as `fitz`).

## Testing

- **`is_valid_bangla_text`** — unit tests with synthetic strings: pure
  Bangla, pure English, mixed Bangla+English, gibberish exceeding the 5%
  threshold, and empty/whitespace-only text.
- **`split_pdf_pages`** — tests against a small PDF generated on the fly
  with PyMuPDF itself (e.g. `fitz.open()` + `insert_text`), so these run in
  CI/fresh clones with no external fixture. Assert page count, non-empty
  `image_bytes`, and correct `native_text`/`has_valid_text_layer` per page.
- **Real-document sanity check** — one additional test gated on a local
  sample PDF via `pytest.mark.skipif` (file not present → skip). The sample
  file (one real scanned land record, mostly image-based — just a sample
  for this test, not representative of any assumed page-count limit; the
  design spec's ~100-page target is unrelated) moves to
  `tests/fixtures/sample_land_record.pdf`; `tests/fixtures/` is added to
  `.gitignore` so it stays local-only and never enters git history, since
  its page images may still contain personal information even though its
  text layer shows "MASKED" overlays. This test is a manual sanity check,
  not part of the portable suite.
