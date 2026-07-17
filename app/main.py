import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_document import router as document_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("yako_ocr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Précharge PaddleOCR au démarrage pour éviter le 1er appel très lent
    from app.services.ocr import ocr_service

    try:
        import time

        logger.info("Warmup OCR en cours...")
        t0 = time.perf_counter()
        ocr_service.warmup()
        logger.info("Warmup OCR terminé en %.0f ms", (time.perf_counter() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Warmup OCR ignoré: %s", exc)
    yield


app = FastAPI(
    title="OCR Documents Ivoiriens",
    description="API OCR pour l'extraction structurée des documents d'identité.",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api")
def api_info():
    return {
        "message": "OCR API fonctionne",
        "endpoints": {
            "document": "POST /ocr/document (détection automatique, multipart: recto, verso)",
            "docs": "/docs",
            "ui": "/",
            "health": "/health",
        },
    }


@app.get("/")
def ui():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return api_info()
    return FileResponse(index)
