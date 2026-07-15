from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.schemas.cni import CNIResult
from app.services.pipeline import process_cni, validate_upload

router = APIRouter(prefix="/ocr", tags=["CNI"])


@router.post(
    "/cni",
    response_model=CNIResult,
    summary="Extraire les informations d'une CNI (recto + verso)",
)
async def ocr_cni(
    recto: UploadFile = File(..., description="Image recto de la CNI"),
    verso: UploadFile = File(..., description="Image verso de la CNI"),
) -> CNIResult:
    try:
        validate_upload(recto.filename, recto.content_type)
        validate_upload(verso.filename, verso.content_type)

        recto_bytes = await recto.read()
        verso_bytes = await verso.read()
        if not recto_bytes or not verso_bytes:
            raise ValueError("Les fichiers recto et verso sont obligatoires.")

        return process_cni(recto_bytes, verso_bytes)
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
