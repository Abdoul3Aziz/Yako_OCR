from __future__ import annotations

import logging
import time
from typing import Annotated, Union

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import Field, ValidationError

from app.schemas.cmu import CMUResult
from app.schemas.cni import CNIResult
from app.schemas.passeport import PasseportResult
from app.schemas.permis import PermisResult
from app.services.pipeline import process_document, validate_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["Document"])

DocumentResult = Annotated[
    Union[CNIResult, PasseportResult, CMUResult, PermisResult],
    Field(discriminator="document_type"),
]


@router.post(
    "/document",
    response_model=DocumentResult,
    summary="Détecter puis extraire une CNI ou un passeport",
)
async def ocr_document(
    recto: UploadFile = File(..., description="Image recto du document"),
    verso: UploadFile = File(..., description="Image verso du document"),
) -> DocumentResult:
    request_started = time.perf_counter()
    try:
        validate_upload(recto.filename, recto.content_type)
        validate_upload(verso.filename, verso.content_type)

        recto_bytes = await recto.read()
        verso_bytes = await verso.read()
        if not recto_bytes or not verso_bytes:
            raise ValueError("Les fichiers recto et verso sont obligatoires.")

        result = process_document(
            recto_bytes,
            verso_bytes,
            recto_content_type=recto.content_type,
            verso_content_type=verso.content_type,
        )
        logger.info(
            "POST /ocr/document terminé en %.0f ms (type=%s)",
            (time.perf_counter() - request_started) * 1000,
            result.document_type,
        )
        return result
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            ),
        ) from exc
    except ValueError as exc:
        message = str(exc)
        code = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if "critiques" in message.lower() or "type de document" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=message) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du traitement OCR: {exc}",
        ) from exc
