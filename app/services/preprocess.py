from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode uploaded bytes into a BGR OpenCV image."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is not None:
        return image

    try:
        pil_image = Image.open(BytesIO(image_bytes))
        pil_image = ImageOps.exif_transpose(pil_image)
        rgb = np.array(pil_image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Image illisible ou format non supporté.") from exc


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))
    if max_width < 50 or max_height < 50:
        return image

    dst = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def crop_document(image: np.ndarray) -> np.ndarray:
    """Crop the largest document-like contour when possible."""
    ratio = 500.0 / max(image.shape[0], 1)
    resized = cv2.resize(image, None, fx=ratio, fy=ratio) if ratio < 1 else image.copy()
    scale = image.shape[0] / resized.shape[0]

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)
    edged = cv2.dilate(edged, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    image_area = resized.shape[0] * resized.shape[1]

    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and area > 0.2 * image_area:
            pts = (approx.reshape(4, 2) * scale).astype("float32")
            return _four_point_transform(image, pts)
    return image


def deskew(image: np.ndarray) -> np.ndarray:
    """Estimate and correct small skew angles."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5 or abs(angle) > 15:
        return image

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(
        image,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def correct_orientation(image: np.ndarray) -> np.ndarray:
    """Rotate 90° steps if the card looks clearly portrait instead of landscape."""
    h, w = image.shape[:2]
    # CNI is landscape; rotate if strongly portrait
    if h > w * 1.2:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Full preprocessing pipeline for a CNI face image."""
    image = decode_image(image_bytes)
    image = correct_orientation(image)
    image = crop_document(image)
    image = deskew(image)
    image = enhance_contrast(image)

    # Limit max side for OCR speed without destroying readability
    max_side = 1600
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / longest
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image
