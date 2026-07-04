import cv2
import numpy as np

from ocr_pipeline.ingestion import Page
from ocr_pipeline.preprocessing import (
    _correct_perspective,
    _decode_grayscale,
    _deskew,
    _detect_skew_angle,
    _enhance_contrast,
    _find_page_quadrilateral,
    preprocess_image,
)


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


def test_enhance_contrast_increases_standard_deviation():
    # A low-contrast image with real spatial structure (a checkerboard)
    # compressed into a narrow gray range. Pure random noise isn't a good
    # stand-in for low contrast here since the denoise step would smooth
    # it away rather than the CLAHE step amplifying real signal.
    y, x = np.ogrid[:100, :100]
    checkerboard = ((x // 10 + y // 10) % 2).astype(np.uint8)
    low_contrast = 120 + checkerboard * 20  # values are either 120 or 140

    enhanced = _enhance_contrast(low_contrast)

    assert enhanced.shape == low_contrast.shape
    assert enhanced.dtype == np.uint8
    assert float(np.std(enhanced)) > float(np.std(low_contrast))
