from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from app.extractors.cni import merge_cni_fields
from app.extractors.passeport import merge_passeport_fields
from app.schemas.cni import CNIRawText, CNIResult
from app.schemas.passeport import PasseportRawText, PasseportResult
from app.services.ocr import ocr_service
from app.services.preprocess import preprocess_image


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/octet-stream",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_upload(filename: Optional[str], content_type: Optional[str]) -> None:
    extension = ""
    if filename and "." in filename:
        extension = "." + filename.rsplit(".", 1)[-1].lower()

    content_ok = (content_type or "").lower() in ALLOWED_CONTENT_TYPES
    extension_ok = extension in ALLOWED_EXTENSIONS
    if not content_ok and not extension_ok:
        raise ValueError(
            "Type de fichier non supporté. Formats acceptés: jpg, jpeg, png, webp."
        )


def _ocr_both_faces(recto_bytes: bytes, verso_bytes: bytes) -> tuple[str, str]:
    recto_image = preprocess_image(recto_bytes)
    verso_image = preprocess_image(verso_bytes)
    recto_text = ocr_service.extract_text(recto_image)
    verso_text = ocr_service.extract_text(verso_image)
    return recto_text, verso_text


def process_cni(recto_bytes: bytes, verso_bytes: bytes) -> CNIResult:
    recto_text, verso_text = _ocr_both_faces(recto_bytes, verso_bytes)
    fields = merge_cni_fields(recto_text, verso_text)
    try:
        return CNIResult(
            **fields,
            raw_text=CNIRawText(recto=recto_text, verso=verso_text),
        )
    except ValidationError:
        raise
    except ValueError:
        raise


def process_passeport(recto_bytes: bytes, verso_bytes: bytes) -> PasseportResult:
    recto_text, verso_text = _ocr_both_faces(recto_bytes, verso_bytes)
    fields = merge_passeport_fields(recto_text, verso_text)
    try:
        return PasseportResult(
            **fields,
            raw_text=PasseportRawText(recto=recto_text, verso=verso_text),
        )
    except ValidationError:
        raise
    except ValueError:
        raise
