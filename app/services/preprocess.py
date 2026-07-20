from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

# Bon compromis mesuré (~10s OCR sur CNI légères)
MAX_SIDE = 1600


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Décode l'image; respecte l'orientation EXIF (crucial photos téléphone)."""
    try:
        pil_image = Image.open(BytesIO(image_bytes))
        pil_image = ImageOps.exif_transpose(pil_image)
        if getattr(pil_image, "format", None) == "JPEG":
            try:
                pil_image.draft("RGB", (MAX_SIDE, MAX_SIDE))
            except Exception:  # noqa: BLE001
                pass
        # Si déjà plus petit que MAX, thumbnail ne grossit pas
        pil_image.thumbnail((MAX_SIDE * 2, MAX_SIDE * 2), Image.Resampling.BILINEAR)
        rgb = np.array(pil_image.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        pass

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image illisible ou format non supporté.")
    return image


def resize_max(image: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def enhance_contrast_fast(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    enhanced = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)
    # Léger sharpen — utile pour photos caméra floues / JPEG compressés
    blur = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    return cv2.addWeighted(enhanced, 1.35, blur, -0.35, 0)


def _order_document_corners(points: np.ndarray) -> np.ndarray:
    """Ordonne les coins: haut-gauche, haut-droit, bas-droit, bas-gauche."""
    points = points.astype(np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype=np.float32,
    )


def _warp_document(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = _order_document_corners(
        corners
    )
    width = round(
        max(
            np.linalg.norm(top_right - top_left),
            np.linalg.norm(bottom_right - bottom_left),
        )
    )
    height = round(
        max(
            np.linalg.norm(bottom_left - top_left),
            np.linalg.norm(bottom_right - top_right),
        )
    )
    if width < 80 or height < 80:
        return image

    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(
        np.array([top_left, top_right, bottom_right, bottom_left]),
        destination,
    )
    warped = cv2.warpPerspective(
        image,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if warped.shape[0] > warped.shape[1]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped


def crop_document_if_possible(image: np.ndarray) -> np.ndarray:
    """Détecte, recadre et redresse le document photographié."""
    h, w = image.shape[:2]
    if min(h, w) < 200:
        return image

    scale = min(1.0, 700 / max(h, w))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        np.ones((9, 9), np.uint8),
        iterations=2,
    )

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    image_area = float(small.shape[0] * small.shape[1])
    selected = None
    fallback = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:15]:
        area_ratio = cv2.contourArea(contour) / image_area
        if area_ratio < 0.18 or area_ratio > 0.95:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4:
            approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
        x, y, bw, bh = cv2.boundingRect(approx if len(approx) == 4 else contour)
        aspect = max(bw, bh) / max(1, min(bw, bh))
        if aspect < 1.20 or aspect > 2.40:
            continue
        candidate = (contour, approx, x, y, bw, bh)
        if fallback is None:
            fallback = candidate
        if len(approx) == 4:
            selected = candidate
            break

    if selected is None:
        selected = fallback
    if selected is None:
        return image

    _, approx, x, y, bw, bh = selected
    coverage_width = bw / small.shape[1]
    coverage_height = bh / small.shape[0]
    # Un fichier déjà cadré ne doit pas être recadré sur un contour interne :
    # cela supprimait notamment la signature située en bas des CNI.
    if coverage_width > 0.88 and coverage_height > 0.70:
        return image

    inv = 1.0 / scale
    if len(approx) == 4:
        corners = approx.reshape(4, 2).astype(np.float32) * inv
        return _warp_document(image, corners)

    # Marges légères
    pad = int(0.02 * max(small.shape[:2]))
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(small.shape[1], x + bw + pad)
    y1 = min(small.shape[0], y + bh + pad)

    # Remonter aux coordonnées image pleine
    X0, Y0 = int(x0 * inv), int(y0 * inv)
    X1, Y1 = int(x1 * inv), int(y1 * inv)
    if X1 - X0 < 80 or Y1 - Y0 < 80:
        return image
    return image[Y0:Y1, X0:X1]


def prepare_image(image_bytes: bytes) -> np.ndarray:
    image = decode_image(image_bytes)
    # Ne PAS pivoter automatiquement les portraits téléphone :
    # ça tournait les CNI prises en portrait et cassait l'OCR / les champs.
    image = crop_document_if_possible(image)
    image = resize_max(image, MAX_SIDE)
    return image


def preprocess_image_with_source(
    image_bytes: bytes,
) -> tuple[np.ndarray, np.ndarray]:
    """Retourne l'image OCR améliorée et une source couleur plus nette pour les assets."""
    image = decode_image(image_bytes)
    image = crop_document_if_possible(image)
    # Source assets un peu plus grande pour photo/signature moins floues.
    source = resize_max(image, max(MAX_SIDE, 2200))
    ocr_base = resize_max(source, MAX_SIDE) if max(source.shape[:2]) > MAX_SIDE else source
    return enhance_contrast_fast(ocr_base), source


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    image, _ = preprocess_image_with_source(image_bytes)
    return image
