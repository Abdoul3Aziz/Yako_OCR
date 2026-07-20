from __future__ import annotations

from pydantic import BaseModel


class DocumentAsset(BaseModel):
    content_type: str = "image/jpeg"
    base64: str
    width: int
    height: int
