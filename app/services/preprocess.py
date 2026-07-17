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


def crop_document_if_possible(image: np.ndarray) -> np.ndarray:
    """Recadre le document si un grand contour net est détecté (photo téléphone)."""
    h, w = image.shape[:2]
    if min(h, w) < 200:
        return image

    scale = 600 / max(h, w)
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    cnt = max(contours, key=cv2.contourArea)
    area_ratio = cv2.contourArea(cnt) / float(small.shape[0] * small.shape[1])
    # Trop petit = élément interne (QR code, photo, puce), pas le document.
    if area_ratio < 0.30 or area_ratio > 0.95:
        return image

    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    if len(approx) != 4:
        x, y, bw, bh = cv2.boundingRect(cnt)
    else:
        x, y, bw, bh = cv2.boundingRect(approx)
    aspect = max(bw, bh) / max(1, min(bw, bh))
    if aspect < 1.20 or aspect > 2.40:
        return image

    # Marges légères
    pad = int(0.02 * max(small.shape[:2]))
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(small.shape[1], x + bw + pad)
    y1 = min(small.shape[0], y + bh + pad)

    # Remonter aux coordonnées image pleine
    inv = 1.0 / scale
    X0, Y0 = int(x0 * inv), int(y0 * inv)
    X1, Y1 = int(x1 * inv), int(y1 * inv)
    if X1 - X0 < 80 or Y1 - Y0 < 80:
        return image
    return image[Y0:Y1, X0:X1]


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    image = decode_image(image_bytes)
    # Ne PAS pivoter automatiquement les portraits téléphone :
    # ça tournait les CNI prises en portrait et cassait l'OCR / les champs.
    image = crop_document_if_possible(image)
    image = resize_max(image, MAX_SIDE)
    image = enhance_contrast_fast(image)
    return image
