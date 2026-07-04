# Preprocessing Module Real Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `NotImplementedError` stub in `src/ocr_pipeline/preprocessing.py` (`preprocess_image`) with a real image-cleanup pipeline, per `docs/superpowers/specs/2026-07-01-preprocessing-module-design.md`.

**Architecture:** `preprocess_image` is built from small, independently-testable private helper functions — decode/grayscale, perspective correction, deskew, contrast enhancement — composed together and wired in incrementally, one stage per task. Each stage degrades gracefully (returns the image unchanged) when its detection step finds nothing to correct.

**Tech Stack:** Python >=3.13, OpenCV (`opencv-python-headless` package, imports as `cv2`), numpy (transitive dependency of opencv), pytest.

## Global Constraints

- Use `uv` for all dependency management (`uv add`) — do not hand-edit dependency lists.
- No binarization anywhere in the pipeline — output stays grayscale with enhanced contrast (the consumer is a multimodal LLM, not a traditional OCR engine).
- No custom exception types. A detection step finding nothing (no quadrilateral, no dominant skew angle) is not an error — return the image unchanged at that step and continue.
- Deskew "near-horizontal" line segments are defined as angle magnitude `<= 30` degrees, where angle is `degrees(atan2(y2 - y1, x2 - x1))` normalized into `(-90, 90]`.
- Perspective correction only fires for a 4-vertex contour whose area exceeds 20% of the frame area; otherwise skip.
- The real sample PDF fixture (`tests/fixtures/sample_land_record.pdf`, already gitignored per the ingestion module work) is reused for the real-document sanity test in this plan — do not create a second copy.
- Do not modify `Page` or anything in `ingestion.py` — this plan only touches `preprocessing.py` and its tests.
- `preprocess_image`'s pipeline order (fixed across all tasks): decode/grayscale → light denoise → perspective correction → deskew → contrast enhancement → encode. Each task adds exactly one stage between the previous stage's output and the encode step.

---

### Task 1: Decode/grayscale plumbing + basic end-to-end pipeline

**Files:**
- Modify: `pyproject.toml` (via `uv add opencv-python-headless`)
- Modify: `src/ocr_pipeline/preprocessing.py` (replace the stub body)
- Modify: `tests/test_preprocessing.py` (remove the stub test, add real tests)

**Interfaces:**
- Consumes: `Page` from `ocr_pipeline.ingestion` (unchanged).
- Produces:
  - `_decode_grayscale(image_bytes: bytes) -> np.ndarray` — internal helper, consumed by `preprocess_image` and later tasks' tests.
  - `preprocess_image(page: Page) -> bytes` — real implementation (this task: decode + grayscale + light denoise + encode only; perspective/deskew/contrast land in later tasks, each adding one line to this function's body).

- [ ] **Step 1: Add the OpenCV dependency**

Run: `uv add opencv-python-headless`
Expected: `pyproject.toml` gains `opencv-python-headless` under `dependencies`, `uv.lock` updated.

- [ ] **Step 2: Replace the stub test with real tests**

Replace the entire contents of `tests/test_preprocessing.py` with:

```python
import cv2
import numpy as np

from ocr_pipeline.ingestion import Page
from ocr_pipeline.preprocessing import _decode_grayscale, preprocess_image


def _make_page(image_bgr: np.ndarray) -> Page:
    success, encoded = cv2.imencode(".png", image_bgr)
    assert success
    return Page(
        page_number=1,
        image_bytes=encoded.tobytes(),
        native_text=None,
        has_valid_text_layer=False,
    )


def test_decode_grayscale_returns_2d_array():
    color = np.full((20, 30, 3), 128, dtype=np.uint8)
    success, encoded = cv2.imencode(".png", color)
    assert success

    gray = _decode_grayscale(encoded.tobytes())

    assert gray.shape == (20, 30)
    assert gray.dtype == np.uint8


def test_preprocess_image_returns_valid_png():
    color = np.full((40, 60, 3), 200, dtype=np.uint8)
    page = _make_page(color)

    result = preprocess_image(page)

    assert isinstance(result, bytes)
    assert len(result) > 0
    decoded = cv2.imdecode(np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: FAIL — `ImportError`/`AttributeError` for `_decode_grayscale` (doesn't exist yet), and `preprocess_image` still raises `NotImplementedError`.

- [ ] **Step 4: Write the implementation**

Replace the entire contents of `src/ocr_pipeline/preprocessing.py` with:

```python
import cv2
import numpy as np

from ocr_pipeline.ingestion import Page


def _decode_grayscale(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    color = cv2.imdecode(array, cv2.IMREAD_COLOR)
    return cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)


def preprocess_image(page: Page) -> bytes:
    gray = _decode_grayscale(page.image_bytes)
    denoised = cv2.medianBlur(gray, 3)

    success, encoded = cv2.imencode(".png", denoised)
    if not success:
        raise RuntimeError("Failed to encode preprocessed image as PNG")
    return encoded.tobytes()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add pyproject.toml uv.lock src/ocr_pipeline/preprocessing.py tests/test_preprocessing.py
git commit -m "feat: implement preprocess_image decode/grayscale/denoise pipeline"
```

---

### Task 2: Perspective correction

**Files:**
- Modify: `src/ocr_pipeline/preprocessing.py` (add perspective helpers; wire in with a 1-line change)
- Modify: `tests/test_preprocessing.py` (add tests)

**Interfaces:**
- Consumes: `_decode_grayscale`, the `denoised` variable in `preprocess_image` (Task 1).
- Produces:
  - `_order_corners(pts: np.ndarray) -> np.ndarray` — internal helper.
  - `_find_page_quadrilateral(gray: np.ndarray) -> np.ndarray | None` — internal helper, consumed by `_correct_perspective` and this task's tests.
  - `_correct_perspective(gray: np.ndarray) -> np.ndarray` — internal helper, consumed by `preprocess_image`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preprocessing.py`:

```python
from ocr_pipeline.preprocessing import _correct_perspective, _find_page_quadrilateral


def _make_bordered_quad_image() -> np.ndarray:
    # A 200x200 black frame with a white 100x100 square (the "page") in the
    # middle — a clear, high-contrast quadrilateral for edge detection.
    frame = np.zeros((200, 200), dtype=np.uint8)
    frame[50:150, 50:150] = 255
    return frame


def test_find_page_quadrilateral_detects_bordered_page():
    frame = _make_bordered_quad_image()

    quad = _find_page_quadrilateral(frame)

    assert quad is not None
    assert quad.shape == (4, 2)


def test_find_page_quadrilateral_returns_none_for_full_bleed_image():
    # A uniform image with no border/edge contrast has no quadrilateral to find.
    full_bleed = np.full((100, 100), 200, dtype=np.uint8)

    quad = _find_page_quadrilateral(full_bleed)

    assert quad is None


def test_correct_perspective_crops_to_detected_quad():
    frame = _make_bordered_quad_image()

    result = _correct_perspective(frame)

    # The detected square is ~100x100; allow generous tolerance since exact
    # contour/warp pixel counts vary slightly.
    assert 80 <= result.shape[0] <= 120
    assert 80 <= result.shape[1] <= 120


def test_correct_perspective_returns_unchanged_when_no_quad_found():
    full_bleed = np.full((100, 100), 200, dtype=np.uint8)

    result = _correct_perspective(full_bleed)

    assert result.shape == full_bleed.shape
    assert np.array_equal(result, full_bleed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: FAIL — `ImportError` for `_correct_perspective`/`_find_page_quadrilateral` (don't exist yet).

- [ ] **Step 3: Add the perspective-correction functions**

In `src/ocr_pipeline/preprocessing.py`, insert these functions between `_decode_grayscale` and `preprocess_image`:

```python
def _order_corners(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    total = pts.sum(axis=1)
    rect[0] = pts[np.argmin(total)]
    rect[2] = pts[np.argmax(total)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _find_page_quadrilateral(gray: np.ndarray) -> np.ndarray | None:
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = gray.shape[0] * gray.shape[1]
    best_candidate = None
    best_area = 0.0

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4:
            continue
        area = cv2.contourArea(approx)
        if area < 0.2 * image_area:
            continue
        if area > best_area:
            best_area = area
            best_candidate = approx.reshape(4, 2)

    return best_candidate


def _correct_perspective(gray: np.ndarray) -> np.ndarray:
    quad = _find_page_quadrilateral(gray)
    if quad is None:
        return gray

    rect = _order_corners(quad.astype("float32"))
    top_left, top_right, bottom_right, bottom_left = rect

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    max_width = int(max(width_top, width_bottom))

    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)
    max_height = int(max(height_left, height_right))

    if max_width <= 0 or max_height <= 0:
        return gray

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(gray, matrix, (max_width, max_height))
```

- [ ] **Step 4: Wire it into `preprocess_image`**

In `preprocess_image`, change:
```python
    denoised = cv2.medianBlur(gray, 3)

    success, encoded = cv2.imencode(".png", denoised)
```
to:
```python
    denoised = cv2.medianBlur(gray, 3)
    corrected = _correct_perspective(denoised)

    success, encoded = cv2.imencode(".png", corrected)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add src/ocr_pipeline/preprocessing.py tests/test_preprocessing.py
git commit -m "feat: add perspective correction to preprocess_image"
```

---

### Task 3: Deskew

**Files:**
- Modify: `src/ocr_pipeline/preprocessing.py` (add deskew helpers; wire in with a 1-line change)
- Modify: `tests/test_preprocessing.py` (add tests)

**Interfaces:**
- Consumes: `_correct_perspective`, the `corrected` variable in `preprocess_image` (Task 2).
- Produces:
  - `_detect_skew_angle(gray: np.ndarray) -> float | None` — internal helper, consumed by `_deskew` and this task's tests.
  - `_deskew(gray: np.ndarray) -> np.ndarray` — internal helper, consumed by `preprocess_image`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preprocessing.py`:

```python
from ocr_pipeline.preprocessing import _deskew, _detect_skew_angle


def _make_line_image_at_angle(angle_degrees: float) -> np.ndarray:
    frame = np.zeros((200, 200), dtype=np.uint8)
    center = (100, 100)
    length = 80
    radians = np.radians(angle_degrees)
    dx = int(length * np.cos(radians))
    dy = int(length * np.sin(radians))
    for offset in range(-1, 2):
        cv2.line(
            frame,
            (center[0] - dx, center[1] - dy + offset),
            (center[0] + dx, center[1] + dy + offset),
            255,
            thickness=2,
        )
    return frame


def test_detect_skew_angle_finds_known_angle():
    frame = _make_line_image_at_angle(10.0)

    angle = _detect_skew_angle(frame)

    assert angle is not None
    assert abs(angle - 10.0) <= 3.0


def test_detect_skew_angle_returns_none_for_blank_image():
    blank = np.zeros((100, 100), dtype=np.uint8)

    angle = _detect_skew_angle(blank)

    assert angle is None


def test_deskew_returns_unchanged_when_no_angle_found():
    blank = np.zeros((100, 100), dtype=np.uint8)

    result = _deskew(blank)

    assert result.shape == blank.shape
    assert np.array_equal(result, blank)


def test_deskew_preserves_shape_when_angle_found():
    frame = _make_line_image_at_angle(10.0)

    result = _deskew(frame)

    assert result.shape == frame.shape
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: FAIL — `ImportError` for `_deskew`/`_detect_skew_angle` (don't exist yet).

- [ ] **Step 3: Add the deskew functions**

In `src/ocr_pipeline/preprocessing.py`, insert these functions between `_correct_perspective` and `preprocess_image`:

```python
def _detect_skew_angle(gray: np.ndarray) -> float | None:
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=50, minLineLength=40, maxLineGap=10
    )
    if lines is None:
        return None

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if angle > 90:
            angle -= 180
        elif angle <= -90:
            angle += 180
        if abs(angle) <= 30:
            angles.append(angle)

    if not angles:
        return None
    return float(np.median(angles))


def _deskew(gray: np.ndarray) -> np.ndarray:
    angle = _detect_skew_angle(gray)
    if angle is None or angle == 0:
        return gray

    height, width = gray.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
```

- [ ] **Step 4: Wire it into `preprocess_image`**

In `preprocess_image`, change:
```python
    corrected = _correct_perspective(denoised)

    success, encoded = cv2.imencode(".png", corrected)
```
to:
```python
    corrected = _correct_perspective(denoised)
    deskewed = _deskew(corrected)

    success, encoded = cv2.imencode(".png", deskewed)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add src/ocr_pipeline/preprocessing.py tests/test_preprocessing.py
git commit -m "feat: add deskew to preprocess_image"
```

---

### Task 4: Contrast enhancement (final pipeline wiring)

**Files:**
- Modify: `src/ocr_pipeline/preprocessing.py` (add contrast helper; wire in with a 1-line change)
- Modify: `tests/test_preprocessing.py` (add test)

**Interfaces:**
- Consumes: `_deskew`, the `deskewed` variable in `preprocess_image` (Task 3).
- Produces:
  - `_enhance_contrast(gray: np.ndarray) -> np.ndarray` — internal helper, consumed by `preprocess_image`.
  - `preprocess_image(page: Page) -> bytes` — now the complete pipeline (final form for this plan).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_preprocessing.py`:

```python
from ocr_pipeline.preprocessing import _enhance_contrast


def test_enhance_contrast_increases_standard_deviation():
    # A low-contrast image: values clustered tightly around 128.
    rng = np.random.default_rng(seed=0)
    low_contrast = np.full((100, 100), 128, dtype=np.uint8)
    noise = rng.integers(-5, 6, size=(100, 100)).astype(np.int16)
    low_contrast = np.clip(low_contrast.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    enhanced = _enhance_contrast(low_contrast)

    assert enhanced.shape == low_contrast.shape
    assert enhanced.dtype == np.uint8
    assert float(np.std(enhanced)) > float(np.std(low_contrast))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: FAIL — `ImportError` for `_enhance_contrast` (doesn't exist yet).

- [ ] **Step 3: Add the contrast-enhancement function**

In `src/ocr_pipeline/preprocessing.py`, insert this function between `_deskew` and `preprocess_image`:

```python
def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.fastNlMeansDenoising(enhanced, h=10)
```

- [ ] **Step 4: Wire it into `preprocess_image`**

In `preprocess_image`, change:
```python
    deskewed = _deskew(corrected)

    success, encoded = cv2.imencode(".png", deskewed)
```
to:
```python
    deskewed = _deskew(corrected)
    enhanced = _enhance_contrast(deskewed)

    success, encoded = cv2.imencode(".png", enhanced)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_preprocessing.py -v`
Expected: PASS (11 passed)

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS, no regressions.

```bash
git add src/ocr_pipeline/preprocessing.py tests/test_preprocessing.py
git commit -m "feat: add contrast enhancement, completing preprocess_image pipeline"
```

---

### Task 5: Real-document sanity test

**Files:**
- Create: `tests/test_preprocessing_real_document.py`

**Interfaces:**
- Consumes: `preprocess_image` (Task 4), `split_pdf_pages` from `ocr_pipeline.ingestion` (already implemented).

- [ ] **Step 1: Write the sanity-check test**

```python
# tests/test_preprocessing_real_document.py
from pathlib import Path

import cv2
import numpy as np
import pytest

from ocr_pipeline.ingestion import split_pdf_pages
from ocr_pipeline.preprocessing import preprocess_image

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_land_record.pdf"


@pytest.mark.skipif(
    not FIXTURE_PATH.exists(), reason="local-only sample PDF not present"
)
def test_preprocess_image_on_real_scanned_pages():
    pages = split_pdf_pages(str(FIXTURE_PATH))
    scanned_pages = [page for page in pages if not page.has_valid_text_layer]
    assert scanned_pages

    for page in scanned_pages:
        result = preprocess_image(page)

        assert isinstance(result, bytes)
        assert len(result) > 0
        decoded = cv2.imdecode(
            np.frombuffer(result, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
        )
        assert decoded is not None
```

- [ ] **Step 2: Run the test to verify it passes (or skips cleanly on a fresh clone)**

Run: `uv run pytest tests/test_preprocessing_real_document.py -v`
Expected: PASS if `tests/fixtures/sample_land_record.pdf` is present locally; SKIPPED if not.

- [ ] **Step 3: Run the full suite and commit**

Run: `uv run pytest -v`
Expected: PASS (plus 1 skipped or passed for this test), no regressions.

```bash
git add tests/test_preprocessing_real_document.py
git commit -m "test: add real-document sanity check for preprocess_image"
```
