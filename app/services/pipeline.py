from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pydantic import ValidationError

from app.extractors.cni import merge_cni_fields
from app.extractors.passeport import merge_passeport_fields
from app.schemas.cni import CNIRawText, CNIResult
from app.schemas.passeport import PasseportRawText, PasseportResult
from app.services.ocr import OCR_BACKEND, ocr_service
from app.services.preprocess import preprocess_image

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/octet-stream",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_preprocess_pool = ThreadPoolExecutor(max_workers=2)

# Champs prioritaires: si absents après Rapid → fallback Paddle
CNI_PRIORITY = ("nom", "prenoms", "numero", "nni", "date_naissance", "sexe")
PASSEPORT_PRIORITY = ("nom", "prenoms", "numero", "date_naissance", "sexe", "nationalite")
FALLBACK_MIN_MISSING = int(os.getenv("OCR_FALLBACK_MIN_MISSING", "3"))


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


def _prefer_text(a: str, b: str) -> str:
    """Garde le texte le plus informatif."""
    if not a:
        return b or ""
    if not b:
        return a
    return a if len(a) >= len(b) else b


def _merge_fields(
    primary: dict[str, Optional[str]],
    secondary: dict[str, Optional[str]],
) -> dict[str, Optional[str]]:
    keys = set(primary) | set(secondary)
    merged: dict[str, Optional[str]] = {}
    for key in keys:
        merged[key] = primary.get(key) or secondary.get(key)
    return merged


def _missing_priority(fields: dict[str, Optional[str]], priority: tuple[str, ...]) -> list[str]:
    return [key for key in priority if not fields.get(key)]


def _should_fallback(fields: dict[str, Optional[str]], priority: tuple[str, ...]) -> bool:
    missing = _missing_priority(fields, priority)
    if missing:
        return True
    # Aussi si beaucoup de champs globaux vides
    empty = sum(1 for value in fields.values() if not value)
    return empty >= FALLBACK_MIN_MISSING


def _preprocess_pair(recto_bytes: bytes, verso_bytes: bytes):
    fut_recto = _preprocess_pool.submit(preprocess_image, recto_bytes)
    fut_verso = _preprocess_pool.submit(preprocess_image, verso_bytes)
    return fut_recto.result(), fut_verso.result()


def _ocr_both_faces(
    recto_bytes: bytes,
    verso_bytes: bytes,
    *,
    merge_fn,
    priority_fields: tuple[str, ...],
) -> tuple[str, str, dict[str, Optional[str]], dict[str, float], str]:
    t0 = time.perf_counter()
    recto_image, verso_image = _preprocess_pair(recto_bytes, verso_bytes)
    preprocess_ms = (time.perf_counter() - t0) * 1000

    mode = OCR_BACKEND if OCR_BACKEND in {"rapid", "paddle", "hybrid"} else "hybrid"
    used = mode

    t1 = time.perf_counter()
    if mode == "paddle":
        recto_text, verso_text = ocr_service.extract_texts(
            [recto_image, verso_image], backend="paddle"
        )
        fields = merge_fn(recto_text, verso_text)
    else:
        # rapid (seul ou première passe hybrid)
        recto_text, verso_text = ocr_service.extract_texts(
            [recto_image, verso_image], backend="rapid"
        )
        fields = merge_fn(recto_text, verso_text)

        if mode == "hybrid" and _should_fallback(fields, priority_fields):
            missing = _missing_priority(fields, priority_fields)
            logger.info(
                "Hybrid fallback Paddle (champs prioritaires manquants: %s)",
                ", ".join(missing) or "plusieurs vides",
            )
            try:
                t_fb = time.perf_counter()
                p_recto, p_verso = ocr_service.extract_texts(
                    [recto_image, verso_image], backend="paddle"
                )
                paddle_fields = merge_fn(p_recto, p_verso)
                fields = _merge_fields(fields, paddle_fields)
                recto_text = _prefer_text(recto_text, p_recto)
                verso_text = _prefer_text(verso_text, p_verso)
                used = f"hybrid+paddle({(time.perf_counter() - t_fb) * 1000:.0f}ms)"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallback Paddle impossible: %s", exc)
                used = "rapid"

    ocr_ms = (time.perf_counter() - t1) * 1000
    timings = {"preprocess_ms": preprocess_ms, "ocr_ms": ocr_ms}
    return recto_text, verso_text, fields, timings, used


def process_cni(recto_bytes: bytes, verso_bytes: bytes) -> CNIResult:
    started = time.perf_counter()
    recto_text, verso_text, fields, timings, backend = _ocr_both_faces(
        recto_bytes,
        verso_bytes,
        merge_fn=merge_cni_fields,
        priority_fields=CNI_PRIORITY,
    )

    t_extract = time.perf_counter()
    extract_ms = (time.perf_counter() - t_extract) * 1000

    try:
        result = CNIResult(
            **fields,
            raw_text=CNIRawText(recto=recto_text, verso=verso_text),
        )
    except ValidationError:
        raise
    except ValueError:
        raise
    finally:
        total_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "CNI traité en %.0f ms (preprocess=%.0f ms, ocr=%.0f ms, extract=%.0f ms, backend=%s) "
            "recto=%d B verso=%d B",
            total_ms,
            timings["preprocess_ms"],
            timings["ocr_ms"],
            extract_ms,
            backend,
            len(recto_bytes),
            len(verso_bytes),
        )

    return result


def process_passeport(recto_bytes: bytes, verso_bytes: bytes) -> PasseportResult:
    started = time.perf_counter()
    recto_text, verso_text, fields, timings, backend = _ocr_both_faces(
        recto_bytes,
        verso_bytes,
        merge_fn=merge_passeport_fields,
        priority_fields=PASSEPORT_PRIORITY,
    )

    t_extract = time.perf_counter()
    extract_ms = (time.perf_counter() - t_extract) * 1000

    try:
        result = PasseportResult(
            **fields,
            raw_text=PasseportRawText(recto=recto_text, verso=verso_text),
        )
    except ValidationError:
        raise
    except ValueError:
        raise
    finally:
        total_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Passeport traité en %.0f ms (preprocess=%.0f ms, ocr=%.0f ms, extract=%.0f ms, backend=%s) "
            "recto=%d B verso=%d B",
            total_ms,
            timings["preprocess_ms"],
            timings["ocr_ms"],
            extract_ms,
            backend,
            len(recto_bytes),
            len(verso_bytes),
        )

    return result
