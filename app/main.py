from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_cni import router as cni_router
from app.api.routes_passeport import router as passeport_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="OCR Documents Ivoiriens",
    description="API OCR pour l'extraction structurée des documents d'identité.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cni_router)
app.include_router(passeport_router)

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
            "cni": "POST /ocr/cni (multipart: recto, verso)",
            "passeport": "POST /ocr/passeport (multipart: recto, verso)",
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
