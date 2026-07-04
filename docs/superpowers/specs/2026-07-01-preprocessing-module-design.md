# Preprocessing Module: Real Implementation — Design

## Context

`src/ocr_pipeline/preprocessing.py` currently has a stub implementation of
`preprocess_image(page: Page) -> bytes` that raises `NotImplementedError`,
scaffolded per `docs/superpowers/plans/2026-07-01-ocr-pipeline-scaffolding.md`.
This design covers implementing the real logic — the second concrete stage
of the OCR pipeline, consuming `Page` objects produced by the now-implemented
`ingestion.py` (see
`docs/superpowers/specs/2026-07-01-ingestion-module-design.md`).

## Non-goals

- BAML OCR/schema-fill calls, validation, and pipeline wiring
  (`pipeline.py`) remain stubbed — out of scope for this round.
- No binarization. Output stays grayscale with enhanced contrast — the
  downstream consumer is a multimodal LLM (`ExtractOcrBatch`), not a
  traditional OCR engine, and hard black/white thresholding can destroy
  faint or low-contrast characters that a vision model could otherwise
  read.
- No custom exception types. Detection failures within a step (no
  quadrilateral found, no dominant skew angle) are not errors — they mean
  "nothing to correct for this page," and the pipeline continues with the
  image as-is at that step.

## Flow

`preprocess_image` takes a `Page` (already carrying rendered PNG bytes from
`ingestion.py`) and returns processed PNG bytes:

```
Page.image_bytes (PNG)
   → decode + grayscale
   → light denoise (stabilizes edge detection below)
   → perspective correction (only if a clear page quadrilateral is found)
   → deskew (always attempted — corrects residual rotation either way)
   → contrast enhancement (CLAHE) + final denoise
   → encode PNG
   → return bytes
```

## Components

### `preprocess_image(page: Page) -> bytes`

1. **Decode & grayscale** — `cv2.imdecode(np.frombuffer(page.image_bytes, ...), cv2.IMREAD_COLOR)`,
   then `cv2.cvtColor(..., cv2.COLOR_BGR2GRAY)`.
2. **Pre-denoise** — `cv2.medianBlur` with a small kernel, primarily to
   stabilize the edge detection in steps 3–4 (not the final quality pass).
3. **Perspective correction**:
   - `cv2.Canny` for edges, `cv2.findContours` for contours,
     `cv2.approxPolyDP` to reduce each to a polygon.
   - Pick the largest 4-vertex contour whose area exceeds ~20% of the
     frame area.
   - If found: order its 4 corners (top-left, top-right, bottom-right,
     bottom-left), compute the destination rectangle size from the corner
     distances, and warp via `cv2.getPerspectiveTransform` +
     `cv2.warpPerspective`.
   - If not found (common for embedded scan images that already fill the
     page, with no visible background/edge to detect): skip, keep the
     grayscale image as-is.
4. **Deskew**:
   - `cv2.Canny` + `cv2.HoughLinesP` (probabilistic Hough transform) over
     the image from step 3.
   - For each detected line segment `(x1, y1, x2, y2)`, compute its angle
     as `degrees(atan2(y2 - y1, x2 - x1))`, normalized into `(-90, 90]`.
   - Keep only segments whose angle falls within ±30° of horizontal (i.e.
     `abs(angle) <= 30`) — this is "near-horizontal" concretely: text
     baselines in a page with at most moderate rotation, excluding
     near-vertical edges (margins, embedded image borders) that would
     otherwise skew the result.
   - If at least one such segment exists, take the median of their angles
     and rotate via `cv2.getRotationMatrix2D` + `cv2.warpAffine` by
     `-median_angle` to correct it.
   - Always attempted, regardless of whether step 3 fired — a
     perspective-corrected page can still carry minor rotation, and a
     flat scan can be rotated with no perspective distortion at all.
   - If no near-horizontal segment is found: skip, no rotation applied.
5. **Contrast enhancement + final denoise** — CLAHE
   (`cv2.createCLAHE().apply(...)`) for uneven lighting, then a mild final
   denoise pass. No binarization.
6. **Encode** — `cv2.imencode(".png", ...)`, return the resulting bytes.

## Dependency

Add `opencv-python-headless` via `uv add opencv-python-headless` (headless
variant — no GUI/Qt dependencies needed in a backend pipeline). `numpy`
comes in transitively.

## Testing

- **Per-step behavior** — a synthetically rotated test image (grayscale
  image with text-like straight lines, rotated a known angle) should come
  back close to level after deskew.
- **End-to-end** — `preprocess_image` run against a `Page` built from a
  small synthetic image returns valid, non-empty, decodable PNG bytes.
- **Real-document sanity check** — same gitignored-fixture pattern as
  `ingestion.py`'s: run `preprocess_image` against pages from the local
  sample PDF (`tests/fixtures/sample_land_record.pdf`, `skipif` not
  present) and assert the output is valid, non-empty PNG bytes for each
  embedded-image page.
