import cv2
import numpy as np

from ocr_pipeline.ingestion import Page


def _decode_grayscale(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    color = cv2.imdecode(array, cv2.IMREAD_COLOR)
    return cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)


def _canny_edges(gray: np.ndarray, low: int = 50, high: int = 150) -> np.ndarray:
    return cv2.Canny(gray, low, high)


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
    edges = _canny_edges(gray)
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


def _detect_skew_angle(gray: np.ndarray) -> float | None:
    edges = _canny_edges(gray)
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


def _enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.fastNlMeansDenoising(enhanced, h=10)


def preprocess_image(page: Page) -> bytes:
    gray = _decode_grayscale(page.image_bytes)
    denoised = cv2.medianBlur(gray, 3)
    corrected = _correct_perspective(denoised)
    deskewed = _deskew(corrected)
    enhanced = _enhance_contrast(deskewed)

    success, encoded = cv2.imencode(".png", enhanced)
    if not success:
        raise RuntimeError("Failed to encode preprocessed image as PNG")
    return encoded.tobytes()
