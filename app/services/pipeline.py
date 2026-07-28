from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pydantic import ValidationError

from app.extractors.cmu import merge_cmu_fields
from app.extractors.cni import merge_cni_fields
from app.extractors.passeport import merge_passeport_fields
from app.extractors.permis import merge_permis_fields
from app.schemas.assets import encode_upload_asset
from app.schemas.cmu import CMURawText, CMUResult
from app.schemas.cni import CNIRawText, CNIResult
from app.schemas.passeport import PasseportRawText, PasseportResult
from app.schemas.permis import PermisRawText, PermisResult
from app.services.document_assets import extract_document_assets
from app.services.document_type import DocumentType, detect_document_type
from app.services.ocr import OCR_BACKEND, ocr_service
from app.services.preprocess import (
    prepare_cni_demographics_roi,
    preprocess_image,
    preprocess_image_with_source,
)

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
CNI_PRIORITY = ("nom", "prenoms", "numero", "nni", "date_naissance", "sexe", "taille")
# Zone recto fond vert: taille / date / sexe souvent perdus → ROI dédié
CNI_DEMOGRAPHICS_FIELDS = (
    "taille",
    "date_naissance",
    "sexe",
    "nationalite",
    "lieu_naissance",
)
PASSEPORT_PRIORITY = ("nom", "prenoms", "numero", "date_naissance", "sexe", "nationalite")
CMU_PRIORITY = (
    "nom",
    "prenoms",
    "numero_securite_sociale",
    "date_naissance",
    "date_emission",
)
PERMIS_PRIORITY = (
    "nom",
    "prenoms",
    "numero_permis",
    "date_naissance",
    "lieu_naissance",
    "date_delivrance",
    "lieu_delivrance",
)
FALLBACK_MIN_MISSING = max(1, int(os.getenv("OCR_FALLBACK_MIN_MISSING", "2")))


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
    # Paddle reste obligatoire si le résultat ne pourrait pas être validé.
    if not fields.get("nom"):
        return True
    identity = (
        fields.get("numero")
        or fields.get("nni")
        or fields.get("numero_securite_sociale")
        or fields.get("numero_permis")
    )
    if not identity:
        return True

    # Sur passeport, date de naissance / sexe absents → souvent MRZ mal lue : Paddle aide.
    if "date_naissance" in priority and not fields.get("date_naissance"):
        return True
    if "sexe" in priority and not fields.get("sexe"):
        return True
    # CNI: taille souvent absente après enhance → on tente aussi Paddle.
    if "taille" in priority and not fields.get("taille"):
        return True

    return len(missing) >= FALLBACK_MIN_MISSING


def _needs_cni_demographics_roi(fields: dict[str, Optional[str]]) -> bool:
    return any(not fields.get(name) for name in CNI_DEMOGRAPHICS_FIELDS)


def _enrich_cni_demographics_roi(
    recto_source,
    recto_text: str,
    verso_text: str,
    fields: dict[str, Optional[str]],
    *,
    backend: str,
) -> tuple[str, dict[str, Optional[str]]]:
    """Re-OCR la zone date/sexe/taille quand le contraste global a perdu ces champs."""
    if not _needs_cni_demographics_roi(fields):
        return recto_text, fields
    try:
        from app.extractors.cni import extract_recto

        roi = prepare_cni_demographics_roi(recto_source)
        roi_text = ocr_service.extract_texts([roi], backend=backend)[0]
        if not roi_text.strip():
            return recto_text, fields
        # Extraire seulement le ROI (pas concaténer avant) pour ne pas
        # figer un prénom tronqué type « NDR » avant « MAHI LANDRY ».
        roi_fields = extract_recto(roi_text)
        enriched = dict(fields)
        for key, value in roi_fields.items():
            if not value:
                continue
            current = enriched.get(key)
            if not current:
                enriched[key] = value
            elif key in {"prenoms", "lieu_naissance"} and len(str(value)) > len(str(current)):
                enriched[key] = value
        combined = f"{recto_text}\n{roi_text}".strip()
        logger.info(
            "ROI démographique CNI appliqué (manquants avant: %s)",
            ", ".join(n for n in CNI_DEMOGRAPHICS_FIELDS if not fields.get(n))
            or "aucun",
        )
        return combined, enriched
    except Exception as exc:  # noqa: BLE001
        logger.warning("ROI démographique CNI impossible: %s", exc)
        return recto_text, fields


def _preprocess_pair(recto_bytes: bytes, verso_bytes: bytes):
    fut_recto = _preprocess_pool.submit(preprocess_image, recto_bytes)
    fut_verso = _preprocess_pool.submit(preprocess_image, verso_bytes)
    return fut_recto.result(), fut_verso.result()


def _preprocess_pair_with_sources(recto_bytes: bytes, verso_bytes: bytes):
    fut_recto = _preprocess_pool.submit(preprocess_image_with_source, recto_bytes)
    fut_verso = _preprocess_pool.submit(preprocess_image_with_source, verso_bytes)
    (recto_ocr, recto_source) = fut_recto.result()
    (verso_ocr, verso_source) = fut_verso.result()
    return recto_ocr, verso_ocr, recto_source, verso_source


def _ocr_both_faces(
    recto_bytes: bytes,
    verso_bytes: bytes,
    *,
    merge_fn,
    priority_fields: tuple[str, ...],
) -> tuple[str, str, dict[str, Optional[str]], dict[str, float], str]:
    t0 = time.perf_counter()
    (
        recto_image,
        verso_image,
        recto_source,
        _verso_source,
    ) = _preprocess_pair_with_sources(recto_bytes, verso_bytes)
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

    if merge_fn is merge_cni_fields:
        had_taille = bool(fields.get("taille"))
        roi_backend = "paddle" if mode in {"paddle", "hybrid"} else "rapid"
        recto_text, fields = _enrich_cni_demographics_roi(
            recto_source,
            recto_text,
            verso_text,
            fields,
            backend=roi_backend,
        )
        if not had_taille and fields.get("taille"):
            used = f"{used}+roi"

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


def process_document(
    recto_bytes: bytes,
    verso_bytes: bytes,
    *,
    recto_content_type: str | None = None,
    verso_content_type: str | None = None,
) -> CNIResult | PasseportResult | CMUResult | PermisResult:
    """Détecte le document puis applique l'extracteur correspondant, sans refaire l'OCR."""
    started = time.perf_counter()
    t0 = time.perf_counter()
    (
        recto_image,
        verso_image,
        recto_source,
        verso_source,
    ) = _preprocess_pair_with_sources(recto_bytes, verso_bytes)
    preprocess_ms = (time.perf_counter() - t0) * 1000

    mode = OCR_BACKEND if OCR_BACKEND in {"rapid", "paddle", "hybrid"} else "hybrid"
    first_backend = "paddle" if mode == "paddle" else "rapid"
    t_ocr = time.perf_counter()
    recto_text, verso_text = ocr_service.extract_texts(
        [recto_image, verso_image], backend=first_backend
    )
    used = first_backend
    paddle_texts: tuple[str, str] | None = None

    try:
        document_type = detect_document_type(recto_text, verso_text)
    except ValueError:
        if mode != "hybrid":
            raise
        logger.info("Type non reconnu par RapidOCR, nouvelle détection avec PaddleOCR")
        p_recto, p_verso = ocr_service.extract_texts(
            [recto_image, verso_image], backend="paddle"
        )
        paddle_texts = (p_recto, p_verso)
        document_type = detect_document_type(
            f"{recto_text}\n{p_recto}",
            f"{verso_text}\n{p_verso}",
        )
        recto_text = _prefer_text(recto_text, p_recto)
        verso_text = _prefer_text(verso_text, p_verso)
        used = "hybrid+paddle-detection"

    merge_fn, priority_fields = _document_pipeline(document_type)
    fields = merge_fn(recto_text, verso_text)

    if mode == "hybrid" and _should_fallback(fields, priority_fields):
        missing = _missing_priority(fields, priority_fields)
        logger.info(
            "Hybrid fallback Paddle (type=%s, champs prioritaires manquants: %s)",
            document_type,
            ", ".join(missing) or "plusieurs vides",
        )
        try:
            t_fb = time.perf_counter()
            if paddle_texts is None:
                paddle_results = ocr_service.extract_texts(
                    [recto_image, verso_image], backend="paddle"
                )
                paddle_texts = (paddle_results[0], paddle_results[1])
            p_recto, p_verso = paddle_texts
            paddle_fields = merge_fn(p_recto, p_verso)
            fields = _merge_fields(fields, paddle_fields)
            recto_text = _prefer_text(recto_text, p_recto)
            verso_text = _prefer_text(verso_text, p_verso)
            used = f"hybrid+paddle({(time.perf_counter() - t_fb) * 1000:.0f}ms)"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallback Paddle impossible: %s", exc)

    if document_type == "cni":
        had_taille = bool(fields.get("taille"))
        roi_backend = "paddle" if mode in {"paddle", "hybrid"} else first_backend
        recto_text, fields = _enrich_cni_demographics_roi(
            recto_source,
            recto_text,
            verso_text,
            fields,
            backend=roi_backend,
        )
        if not had_taille and fields.get("taille"):
            used = f"{used}+roi"

    assets = extract_document_assets(document_type, recto_source, verso_source)
    upload_assets = {
        "recto": encode_upload_asset(recto_bytes, recto_content_type),
        "verso": encode_upload_asset(verso_bytes, verso_content_type),
    }
    if document_type == "cni":
        result: CNIResult | PasseportResult | CMUResult | PermisResult = CNIResult(
            **fields,
            **assets,
            **upload_assets,
            raw_text=CNIRawText(recto=recto_text, verso=verso_text),
        )
    elif document_type == "passeport":
        result = PasseportResult(
            **fields,
            **assets,
            **upload_assets,
            raw_text=PasseportRawText(recto=recto_text, verso=verso_text),
        )
    elif document_type == "cmu":
        result = CMUResult(
            **fields,
            **assets,
            **upload_assets,
            raw_text=CMURawText(recto=recto_text, verso=verso_text),
        )
    else:
        result = PermisResult(
            **fields,
            **assets,
            **upload_assets,
            raw_text=PermisRawText(recto=recto_text, verso=verso_text),
        )

    logger.info(
        "Document détecté=%s traité en %.0f ms "
        "(preprocess=%.0f ms, ocr+extract=%.0f ms, backend=%s)",
        document_type,
        (time.perf_counter() - started) * 1000,
        preprocess_ms,
        (time.perf_counter() - t_ocr) * 1000,
        used,
    )
    return result


def _document_pipeline(document_type: DocumentType):
    if document_type == "cni":
        return merge_cni_fields, CNI_PRIORITY
    if document_type == "passeport":
        return merge_passeport_fields, PASSEPORT_PRIORITY
    if document_type == "cmu":
        return merge_cmu_fields, CMU_PRIORITY
    return merge_permis_fields, PERMIS_PRIORITY
