# OCR Pipeline for Typed Bangla/English Mixed Documents — Design

## Context

LandDecoded needs to digitize typed documents (land records) that mix Bangla and
English text. Input is PDFs up to ~100 pages each. Some PDFs already carry a
real, extractable text layer; others are scanned or photographed pages with
uneven lighting and perspective distortion. Each document follows one fixed,
known schema of structured fields (e.g. owner name, plot number, area, dates).

Goal: maximize extraction accuracy while minimizing paid LLM API calls
(Gemini/Claude), with a human-in-the-loop safety net for anything the
pipeline isn't confident about.

## Non-goals

- Handwritten document support (documents are typed).
- Multiple document types/schemas (only one fixed schema for now).
- Automatic correction/escalation loops — low-confidence output goes straight
  to human review instead (see "Escalation" below).

## Pipeline overview

```
PDF → split pages → [text-layer check]
                        ├─ good text layer → raw text (free, no LLM call)
                        └─ no/bad text layer → preprocess (deskew/perspective/contrast)
                                              → batch → LLM Call #1 (OCR only)
                                              → raw text + line/word bounding boxes
                     ↓
        merge all pages' raw text → full document text
                     ↓
        LLM Call #2 (schema fill, text-only) → structured fields + per-field confidence
                     ↓
        validation (type/regex/cross-field sanity checks)
                     ↓
        field fails validation or low confidence?
           ├─ yes → human review queue (value, confidence, source page,
           │         cropped source region shown side-by-side)
           └─ no  → accept as-is
```

## Components

### 1. Page splitting

Split the incoming PDF into individual pages up front so each page can be
routed independently (native-text vs. image-OCR path).

### 2. Native text-layer detection

For each page, attempt native text extraction (e.g. PyMuPDF). A text layer
being *present* is not sufficient — Bangladeshi PDFs frequently use legacy
non-Unicode Bangla fonts (e.g. SutonnyMJ/Bijoy) whose extracted bytes look
like a text layer but decode to gibberish when read as Unicode.

Validate extracted text against a Bangla-Unicode-block / character-frequency
heuristic. Pages that pass are accepted as-is, at zero LLM cost. Pages that
fail (no text layer, or text layer that fails validation) are routed to the
image-OCR path.

This step is the primary cost-saving lever: any document with a real
Unicode text layer skips the OCR call entirely.

### 3. Image preprocessing

For pages routed to the image-OCR path, apply local (non-LLM) preprocessing:
deskew, perspective correction, contrast/denoise. This is free and improves
OCR accuracy on the subsequent LLM call, reducing the odds of a page needing
human review later.

### 4. LLM Call #1 — OCR phase

Batches all image-OCR-path pages from a document into as few multimodal calls
as page/token limits allow (target: 1 call per document; split into more
only if a document's page count or image size requires it — ≤100 pages per
document keeps this to a small, bounded number of calls).

Prompt scope: pure transcription. For each page, return:
- raw transcribed text
- bounding boxes for text lines/regions

The bounding boxes are captured now (not schema-derived later) because the
human review UI needs to show a reviewer the cropped source region next to
a flagged field, without a second vision call.

This call has no knowledge of the downstream schema — keeps the OCR prompt
stable even if the schema changes later.

### 5. Merge

Concatenate the free native-text pages and the Call #1 OCR output, in page
order, into one full-document text blob (with enough page/position metadata
retained to map a schema field's value back to a source page + bounding box
for the review UI).

### 6. LLM Call #2 — schema-fill phase

Text-only call (no image tokens) over the merged document text. Uses the
one fixed, known schema. Structured/JSON-constrained output. Each field is
returned with a confidence value.

Decoupling this from OCR means the schema/prompt can be iterated on
independently of the vision pipeline.

### 7. Validation

Per-field sanity checks: type/format checks (e.g. area must be numeric),
required-field presence, cross-field consistency where applicable. This is
local logic, not an LLM call.

### 8. Escalation — none (explicitly removed)

A field failing validation, or returned with low confidence, is **not**
re-queried against the LLM. It goes directly to human review. This keeps the
pipeline to exactly two LLM call types per document (OCR batch + schema
fill), with no conditional extra calls.

### 9. Human-in-the-loop review

Any field that fails validation or carries low confidence is queued for
manual review, showing: the extracted value, its confidence, the source
page, and the cropped source region (from the Call #1 bounding box) so a
human can verify or correct it quickly without hunting through the full
page.

## LLM call budget per document

- 0 calls for pages with a valid native Unicode text layer.
- 1 batched call (rarely more, only if page/size limits force a split) for
  OCR on the remaining image pages.
- 1 call for schema-fill over the full merged text.

Total: typically **2 LLM calls per document**, regardless of page count
(up to the ~100-page target), independent of how many fields end up flagged
for human review.

## Testing/validation approach

Not yet defined — to be addressed when moving to implementation planning
(need representative sample PDFs covering: valid Unicode text layer, legacy
non-Unicode Bangla font text layer, clean scans, and photographed/distorted
pages).
