from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

# Bon compromis mesuré (~10s OCR sur CNI légères)
MAX_SIDE = 1280


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Décode l'image; pour JPEG volumineux, réduit tôt via Pillow."""
    # Chemin rapide Pillow (downsample JPEG)
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
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    return cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)


def correct_orientation(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    if h > w * 1.2:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    image = decode_image(image_bytes)
    image = resize_max(image, MAX_SIDE)
    image = correct_orientation(image)
    image = enhance_contrast_fast(image)
    return image
