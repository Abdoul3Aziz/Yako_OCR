from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.schemas.assets import DocumentAsset
from app.services.document_type import DocumentType


@dataclass(frozen=True)
class AssetRegion:
    side: str
    x1: float
    y1: float
    x2: float
    y2: float
    max_width: int


# Coordonnées relatives après recadrage du document.
# Elles restent indépendantes de la résolution de l'image.
ASSET_REGIONS: dict[DocumentType, dict[str, AssetRegion]] = {
    "cni": {
        # Portrait principal (gauche) — s'arrête avant « Signature du titulaire ».
        "photo": AssetRegion("recto", 0.04, 0.22, 0.34, 0.72, 360),
        # Sous le portrait, bande gauche jusqu'au bas (signature manuscrite).
        "signature": AssetRegion("recto", 0.00, 0.72, 0.36, 0.98, 560),
    },
    "passeport": {
        "photo": AssetRegion("recto", 0.03, 0.22, 0.29, 0.71, 420),
        "signature": AssetRegion("recto", 0.55, 0.60, 0.90, 0.76, 520),
    },
    "cmu": {
        "photo": AssetRegion("recto", 0.03, 0.34, 0.31, 0.96, 360),
    },
    "permis": {
        "photo": AssetRegion("recto", 0.02, 0.33, 0.32, 0.96, 400),
    },
}

_FACE_DETECTOR: Optional[cv2.CascadeClassifier] = None


def _face_detector() -> cv2.CascadeClassifier:
    global _FACE_DETECTOR
    if _FACE_DETECTOR is None:
        _FACE_DETECTOR = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _FACE_DETECTOR


def _detect_faces_in(
    image: np.ndarray,
    *,
    min_side: int,
) -> list[tuple[int, int, int, int]]:
    if image.size == 0:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _face_detector().detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=5,
        minSize=(min_side, min_side),
    )
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]


def _detect_face(
    image: np.ndarray,
    *,
    document_type: Optional[DocumentType] = None,
) -> Optional[tuple[int, int, int, int]]:
    """Détecte le portrait principal. Sur CNI, ignore l'hologramme bas-droite."""
    height, width = image.shape[:2]

    if document_type == "cni":
        # Zone du vrai portrait (gauche). L'hologramme est à droite, plus petit.
        x0 = 0
        y0 = round(height * 0.18)
        x1 = round(width * 0.42)
        y1 = round(height * 0.82)
        roi = image[y0:y1, x0:x1]
        # Le portrait CNI occupe ~15–25 % de la hauteur ; l'hologramme est bien plus petit.
        min_side = max(36, round(height * 0.12))
        faces = _detect_faces_in(roi, min_side=min_side)
        if not faces:
            # Second passage un peu plus permissif, toujours limité à gauche.
            faces = _detect_faces_in(roi, min_side=max(28, round(height * 0.09)))
        if not faces:
            return None
        x, y, w, h = max(faces, key=lambda face: face[2] * face[3])
        return x + x0, y + y0, w, h

    min_side = max(24, round(min(height, width) * 0.07))
    faces = _detect_faces_in(image, min_side=min_side)
    if not faces:
        return None

    # Préférer le plus grand visage dans la moitié gauche (photo d'identité).
    scored = []
    for x, y, w, h in faces:
        area = w * h
        center_x = x + w / 2
        left_bonus = 1.35 if center_x < width * 0.45 else 0.65
        scored.append((area * left_bonus, (x, y, w, h)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _crop_pixels(
    image: np.ndarray,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> Optional[np.ndarray]:
    height, width = image.shape[:2]
    left = max(0, min(width - 1, round(x1)))
    top = max(0, min(height - 1, round(y1)))
    right = max(left + 1, min(width, round(x2)))
    bottom = max(top + 1, min(height, round(y2)))
    crop = image[top:bottom, left:right]
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
        return None
    return crop


def _portrait_from_face(
    image: np.ndarray,
    face: tuple[int, int, int, int],
    *,
    document_type: Optional[DocumentType] = None,
) -> Optional[np.ndarray]:
    x, y, width, height = face
    center_x = x + width / 2
    img_h = image.shape[0]
    if document_type == "cni":
        # S'arrêter avant le bandeau « Signature du titulaire ».
        portrait_width = width * 1.70
        top = y - height * 0.50
        bottom = min(y + height * 1.28, img_h * 0.72)
    else:
        portrait_width = width * 1.75
        top = y - height * 0.55
        bottom = y + height * 1.65
    return _crop_pixels(
        image,
        center_x - portrait_width / 2,
        top,
        center_x + portrait_width / 2,
        bottom,
    )


def _finalize_cni_signature(crop: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Retire le libellé, recentre, agrandit puis blanchit (trait plus net)."""
    if crop is None:
        return None
    cut = round(crop.shape[0] * 0.55)
    trimmed = crop[cut:, :]
    if trimmed.shape[0] < 18:
        trimmed = crop[round(crop.shape[0] * 0.40) :, :]
    if trimmed.shape[0] < 18:
        trimmed = crop

    centered = _center_on_ink(trimmed, generous=True)
    if centered is None:
        centered = trimmed

    # Agrandir AVANT le blanchiment pour garder les niveaux de gris du trait
    # (blanchir puis agrandir accentue le crénelage).
    centered = _resize_max_side(centered, target=300, max_scale=2.8)
    cleaned = _whiten_signature_background(centered)
    cleaned = _pad_signature_centered(cleaned)
    cleaned = _sharpen_light(cleaned)
    return cleaned


def _resize_max_side(
    image: np.ndarray,
    *,
    target: int,
    max_scale: float,
) -> np.ndarray:
    longest = max(image.shape[0], image.shape[1])
    if longest <= 0 or longest >= target:
        return image
    scale = min(max_scale, target / longest)
    if scale <= 1.05:
        return image
    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_LANCZOS4,
    )


def _whiten_signature_background(image: np.ndarray) -> np.ndarray:
    """Fond blanc net après agrandissement (seuillage sur image déjà upscalée)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    out = np.full_like(image, 255)
    # Après Lanczos, le seuil donne un trait net sans gros crénelage.
    ink = gray < 148
    out[ink] = image[ink]
    return out


def _pad_signature_centered(image: np.ndarray) -> np.ndarray:
    """Recadre sur l'encre puis ajoute une marge égale (signature bien centrée)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = (gray < 160).astype(np.uint8) * 255
    points = cv2.findNonZero(ink)
    if points is None:
        return image
    x, y, w, h = cv2.boundingRect(points)
    tight = image[y : y + h, x : x + w]
    pad_x = max(16, round(w * 0.55))
    pad_y = max(14, round(h * 0.70))
    canvas = np.full(
        (h + pad_y * 2, w + pad_x * 2, 3),
        255,
        dtype=np.uint8,
    )
    canvas[pad_y : pad_y + h, pad_x : pad_x + w] = tight
    return canvas


def _sharpen_light(image: np.ndarray) -> np.ndarray:
    """Léger unsharp — redonne du piqué sans transformer le trait en tache."""
    blur = cv2.GaussianBlur(image, (0, 0), 0.8)
    sharp = cv2.addWeighted(image, 1.35, blur, -0.35, 0)
    return np.clip(sharp, 0, 255).astype(np.uint8)


def _ink_mask(image: np.ndarray) -> np.ndarray:
    """Masque de l'encre manuscrite sombre (ignore fond clair / motifs verts)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark = cv2.inRange(gray, 0, 130)
    mask = cv2.bitwise_and(otsu, dark)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    not_security = np.where(
        (hsv[:, :, 1] < 100) | (hsv[:, :, 2] < 90),
        255,
        0,
    ).astype(np.uint8)
    mask = cv2.bitwise_and(mask, not_security)

    hw = max(18, round(mask.shape[1] * 0.75))
    lines = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (hw, 1)),
    )
    return cv2.bitwise_and(mask, cv2.bitwise_not(lines))


def _main_ink_component(mask: np.ndarray) -> Optional[np.ndarray]:
    """Conserve le composant principal (signature), ignore le bruit."""
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return None

    img_h, img_w = mask.shape[:2]
    min_area = max(6, mask.size // 3500)
    best_label = None
    best_score = -1.0

    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        if w > img_w * 0.65 and h < max(4, img_h * 0.18):
            continue
        cy = float(centroids[label][1])
        vertical_bonus = 1.0 + (cy / max(1, img_h))
        compactness = area / max(1.0, float(w * h))
        score = area * vertical_bonus * (0.5 + compactness)
        if score > best_score:
            best_score = score
            best_label = label

    if best_label is None:
        return None

    cleaned = np.zeros_like(mask)
    bx = int(stats[best_label, cv2.CC_STAT_LEFT])
    by = int(stats[best_label, cv2.CC_STAT_TOP])
    bw = int(stats[best_label, cv2.CC_STAT_WIDTH])
    bh = int(stats[best_label, cv2.CC_STAT_HEIGHT])
    pad = max(8, round(max(bw, bh) * 0.6))
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area and label != best_label:
            continue
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        if w > img_w * 0.65 and h < max(4, img_h * 0.18):
            continue
        if label != best_label and (
            x + w < bx - pad
            or x > bx + bw + pad
            or y + h < by - pad
            or y > by + bh + pad
        ):
            continue
        cleaned[labels == label] = 255

    return cleaned if cv2.countNonZero(cleaned) > 0 else None


def _center_on_ink(
    image: np.ndarray,
    *,
    generous: bool = False,
) -> Optional[np.ndarray]:
    """Recadre autour de la signature pour la centrer."""
    cleaned = _main_ink_component(_ink_mask(image))
    if cleaned is None:
        return None
    points = cv2.findNonZero(cleaned)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    if h < 3 and w > image.shape[1] * 0.45:
        return None
    if generous:
        margin_x = max(18, round(w * 0.85))
        margin_y = max(14, round(h * 0.90))
    else:
        margin_x = max(12, round(w * 0.45))
        margin_y = max(10, round(h * 0.55))
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(image.shape[1], x + w + margin_x)
    y2 = min(image.shape[0], y + h + margin_y)
    return image[y1:y2, x1:x2]


def _signature_from_face(
    document_type: DocumentType,
    image: np.ndarray,
    face: tuple[int, int, int, int],
) -> Optional[np.ndarray]:
    x, y, width, height = face
    img_h, img_w = image.shape[:2]
    if document_type == "cni":
        crop = _crop_pixels(
            image,
            0,
            y + height * 1.15,
            img_w * 0.36,
            img_h * 0.98,
        )
        return _finalize_cni_signature(crop)
    if document_type == "passeport":
        return _crop_pixels(
            image,
            x + width * 3.00,
            y + height * 1.18,
            x + width * 4.60,
            y + height * 1.90,
        )
    return None


def _crop_region(
    recto: np.ndarray,
    verso: np.ndarray,
    region: AssetRegion,
) -> Optional[np.ndarray]:
    image = recto if region.side == "recto" else verso
    if image is None or image.size == 0:
        return None

    height, width = image.shape[:2]
    x1 = max(0, min(width - 1, round(region.x1 * width)))
    y1 = max(0, min(height - 1, round(region.y1 * height)))
    x2 = max(x1 + 1, min(width, round(region.x2 * width)))
    y2 = max(y1 + 1, min(height, round(region.y2 * height)))
    crop = image[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
        return None

    if crop.shape[1] > region.max_width:
        scale = region.max_width / crop.shape[1]
        crop = cv2.resize(
            crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    return crop


def _remove_signature_background(
    image: np.ndarray,
    *,
    remove_horizontal_lines: bool,
) -> Optional[np.ndarray]:
    """Isole l'encre et retourne une image BGRA centrée, fond transparent."""
    focused = _center_on_ink(image)
    if focused is not None:
        image = focused

    cleaned = _main_ink_component(_ink_mask(image))
    if cleaned is None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, cleaned = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        if remove_horizontal_lines:
            hw = max(18, round(cleaned.shape[1] * 0.80))
            lines = cv2.morphologyEx(
                cleaned,
                cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (hw, 1)),
            )
            cleaned = cv2.bitwise_and(cleaned, cv2.bitwise_not(lines))

    points = cv2.findNonZero(cleaned)
    if points is None:
        return None

    x, y, width, height = cv2.boundingRect(points)
    if height < 3 and width > image.shape[1] * 0.5:
        return None

    margin = max(10, round(min(width, height) * 0.35 + 6))
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(image.shape[1], x + width + margin)
    y2 = min(image.shape[0], y + height + margin)

    alpha = cleaned[y1:y2, x1:x2]
    alpha = cv2.dilate(
        alpha,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)),
        iterations=1,
    )
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)

    transparent = np.zeros((y2 - y1, x2 - x1, 4), dtype=np.uint8)
    transparent[:, :, 0] = 36
    transparent[:, :, 1] = 48
    transparent[:, :, 2] = 42
    transparent[:, :, 3] = alpha

    pad = max(8, round(min(transparent.shape[:2]) * 0.22))
    canvas = np.zeros(
        (transparent.shape[0] + pad * 2, transparent.shape[1] + pad * 2, 4),
        dtype=np.uint8,
    )
    canvas[pad : pad + transparent.shape[0], pad : pad + transparent.shape[1]] = (
        transparent
    )
    transparent = canvas

    # Agrandir pour remplir correctement la carte UI (évite un point minuscule).
    target = 280
    longest = max(transparent.shape[0], transparent.shape[1])
    if longest < target:
        scale = target / max(1, longest)
        transparent = cv2.resize(
            transparent,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    return transparent


def _encode_asset(
    image: Optional[np.ndarray],
    *,
    transparent: bool = False,
    remove_horizontal_lines: bool = False,
) -> Optional[DocumentAsset]:
    if image is None:
        return None
    if transparent:
        processed = _remove_signature_background(
            image,
            remove_horizontal_lines=remove_horizontal_lines,
        )
        # Si l'isolation échoue, renvoyer le crop JPEG plutôt qu'un filet vide.
        if processed is None:
            transparent = False
        else:
            image = processed
            extension = ".png"
            content_type = "image/png"
            options = [cv2.IMWRITE_PNG_COMPRESSION, 6]

    if not transparent:
        extension = ".jpg"
        content_type = "image/jpeg"
        options = [cv2.IMWRITE_JPEG_QUALITY, 95]

    success, encoded = cv2.imencode(extension, image, options)
    if not success:
        return None
    height, width = image.shape[:2]
    return DocumentAsset(
        content_type=content_type,
        base64=base64.b64encode(encoded.tobytes()).decode("ascii"),
        width=width,
        height=height,
    )


def extract_document_assets(
    document_type: DocumentType,
    recto: np.ndarray,
    verso: np.ndarray,
) -> dict[str, Optional[DocumentAsset]]:
    regions = ASSET_REGIONS.get(document_type, {})
    face = _detect_face(recto, document_type=document_type)

    photo_crop = (
        _portrait_from_face(recto, face, document_type=document_type)
        if face
        else None
    )
    if photo_crop is None and "photo" in regions:
        photo_crop = _crop_region(recto, verso, regions["photo"])

    signature_crop = None
    if face:
        signature_crop = _signature_from_face(document_type, recto, face)
    if signature_crop is None and "signature" in regions:
        signature_crop = _crop_region(recto, verso, regions["signature"])
        if document_type == "cni":
            signature_crop = _finalize_cni_signature(signature_crop)

    return {
        "photo": _encode_asset(photo_crop),
        # CNI : JPEG recentré + fond blanchi (la transparence rendait le trait invisible).
        "signature": _encode_asset(
            signature_crop,
            transparent=document_type != "cni",
            remove_horizontal_lines=document_type != "cni",
        )
        if signature_crop is not None
        else None,
    }
