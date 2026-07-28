from __future__ import annotations

import base64
from typing import Optional

import cv2
import numpy as np
from pydantic import BaseModel


class DocumentAsset(BaseModel):
    content_type: str = "image/jpeg"
    base64: str
    width: int
    height: int


def _guess_content_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def encode_upload_asset(
    image_bytes: bytes,
    content_type: Optional[str] = None,
) -> Optional[DocumentAsset]:
    """Encode l'image reçue (recto/verso) en DocumentAsset base64."""
    if not image_bytes:
        return None

    mime = (content_type or "").strip().lower()
    if not mime or mime == "application/octet-stream":
        mime = _guess_content_type(image_bytes)
    if mime == "image/jpg":
        mime = "image/jpeg"

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        # Image non décodable : on renvoie quand même le base64 sans dimensions fiables.
        return DocumentAsset(
            content_type=mime,
            base64=base64.b64encode(image_bytes).decode("ascii"),
            width=0,
            height=0,
        )

    height, width = image.shape[:2]
    return DocumentAsset(
        content_type=mime,
        base64=base64.b64encode(image_bytes).decode("ascii"),
        width=width,
        height=height,
    )
