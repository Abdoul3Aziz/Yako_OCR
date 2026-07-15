from __future__ import annotations

import logging
import time

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.schemas.passeport import PasseportResult
from app.services.pipeline import process_passeport, validate_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["Passeport"])


@router.post(
    "/passeport",
    response_model=PasseportResult,
    summary="Extraire les informations d'un passeport (recto + verso)",
)
async def ocr_passeport(
    recto: UploadFile = File(..., description="Image recto (page biodata) du passeport"),
    verso: UploadFile = File(..., description="Image verso du passeport"),
) -> PasseportResult:
    request_started = time.perf_counter()
    try:
        validate_upload(recto.filename, recto.content_type)
        validate_upload(verso.filename, verso.content_type)

        recto_bytes = await recto.read()
        verso_bytes = await verso.read()
        if not recto_bytes or not verso_bytes:
            raise ValueError("Les fichiers recto et verso sont obligatoires.")

        result = process_passeport(recto_bytes, verso_bytes)
        logger.info(
            "POST /ocr/passeport terminé en %.0f ms (requête HTTP totale)",
            (time.perf_counter() - request_started) * 1000,
        )
        return result
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    except ValueError as exc:
        message = str(exc)
        if "critiques" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du traitement OCR: {exc}",
        ) from exc
