from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import numpy as np

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")

logger = logging.getLogger(__name__)

# rapid | paddle | hybrid (rapid puis paddle si champs manquants)
OCR_BACKEND = os.getenv("OCR_BACKEND", "hybrid").strip().lower()


class OCRService:
    """
    - rapid: RapidOCR LATIN (rapide)
    - paddle: PaddleOCR mobile
    - hybrid: rapid d'abord, paddle en complément si besoin
    """

    def __init__(self) -> None:
        self._backend_name: Optional[str] = None
        self._rapid: Any = None
        self._paddle_engines: list[Any] = []
        self._lock = threading.Lock()
        self._worker_pool = ThreadPoolExecutor(max_workers=2)
        self._rapid_legacy = False
        self._paddle_ready = False

    @property
    def active_backend(self) -> str:
        return self._backend_name or OCR_BACKEND

    def warmup(self) -> None:
        # Image avec du texte (évite warning "detection result is empty")
        dummy = np.full((120, 320, 3), 255, dtype=np.uint8)
        try:
            import cv2

            cv2.putText(
                dummy,
                "CNI TEST 123",
                (15, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )
        except Exception:  # noqa: BLE001
            pass

        mode = OCR_BACKEND if OCR_BACKEND in {"rapid", "paddle", "hybrid"} else "hybrid"

        if mode in {"rapid", "hybrid"}:
            self._ensure_rapid()
            self._extract_rapid_parallel([dummy, dummy.copy()])

        if mode in {"paddle", "hybrid"}:
            try:
                self._ensure_paddle()
                self._extract_paddle_parallel([dummy, dummy.copy()])
            except Exception as exc:  # noqa: BLE001
                if mode == "paddle":
                    raise
                logger.warning("Warmup Paddle ignoré (fallback offline): %s", exc)

        self._backend_name = mode
        logger.info("Backend OCR actif: %s", self._backend_name)

    def extract_text(self, image: np.ndarray) -> str:
        return self.extract_texts([image])[0]

    def extract_texts(self, images: list[np.ndarray], *, backend: Optional[str] = None) -> list[str]:
        if not images:
            return []
        mode = (backend or OCR_BACKEND).strip().lower()
        if mode == "paddle":
            self._ensure_paddle()
            return self._extract_paddle_parallel(images)
        # rapid par défaut
        self._ensure_rapid()
        return self._extract_rapid_parallel(images)

    def _ensure_rapid(self) -> None:
        if self._rapid is not None:
            return
        with self._lock:
            if self._rapid is not None:
                return
            if not self._init_rapid():
                raise RuntimeError(
                    "RapidOCR indisponible. Installez: pip install rapidocr onnxruntime"
                )

    def _ensure_paddle(self) -> None:
        if self._paddle_ready:
            return
        with self._lock:
            if self._paddle_ready:
                return
            if not self._init_paddle():
                raise RuntimeError(
                    "PaddleOCR indisponible. Installez: pip install paddleocr paddlepaddle"
                )

    def _init_rapid(self) -> bool:
        """
        LATIN PP-OCRv5 exige model_type=mobile (pas small).
        Voir: https://rapidai.github.io/RapidOCRDocs/main/model_list/
        """
        configs = []
        try:
            from rapidocr import (
                EngineType,
                LangDet,
                LangRec,
                ModelType,
                OCRVersion,
                RapidOCR,
            )

            # 1) LATIN PP-OCRv5 (det=ch mobile + rec=latin mobile)
            configs.append(
                (
                    "LATIN / PP-OCRv5 / mobile",
                    {
                        "Det.engine_type": EngineType.ONNXRUNTIME,
                        "Det.lang_type": LangDet.CH,
                        "Det.model_type": ModelType.MOBILE,
                        "Det.ocr_version": OCRVersion.PPOCRV5,
                        "Rec.engine_type": EngineType.ONNXRUNTIME,
                        "Rec.lang_type": LangRec.LATIN,
                        "Rec.model_type": ModelType.MOBILE,
                        "Rec.ocr_version": OCRVersion.PPOCRV5,
                    },
                )
            )
            # 2) PP-OCRv6 small (même modèle multilingual, FR inclus)
            configs.append(
                (
                    "PP-OCRv6 small (fr inclus)",
                    {
                        "Det.engine_type": EngineType.ONNXRUNTIME,
                        "Det.lang_type": LangDet.CH,
                        "Det.model_type": ModelType.SMALL,
                        "Det.ocr_version": OCRVersion.PPOCRV6,
                        "Rec.engine_type": EngineType.ONNXRUNTIME,
                        "Rec.lang_type": LangRec.CH,
                        "Rec.model_type": ModelType.SMALL,
                        "Rec.ocr_version": OCRVersion.PPOCRV6,
                    },
                )
            )
            # 3) LATIN / PP-OCRv4 / mobile (stable)
            configs.append(
                (
                    "LATIN / PP-OCRv4 / mobile",
                    {
                        "Det.engine_type": EngineType.ONNXRUNTIME,
                        "Det.lang_type": LangDet.EN,
                        "Det.model_type": ModelType.MOBILE,
                        "Det.ocr_version": OCRVersion.PPOCRV4,
                        "Rec.engine_type": EngineType.ONNXRUNTIME,
                        "Rec.lang_type": LangRec.LATIN,
                        "Rec.model_type": ModelType.MOBILE,
                        "Rec.ocr_version": OCRVersion.PPOCRV4,
                    },
                )
            )

            for label, params in configs:
                try:
                    self._rapid = RapidOCR(params=params)
                    self._rapid_legacy = False
                    logger.info("RapidOCR initialisé (%s)", label)
                    return True
                except Exception as exc_cfg:  # noqa: BLE001
                    logger.info("Config RapidOCR %s indisponible: %s", label, exc_cfg)

            # Dernier recours: défaut package
            self._rapid = RapidOCR()
            self._rapid_legacy = False
            logger.warning(
                "RapidOCR initialisé (défaut chinois) — qualité FR potentiellement réduite"
            )
            return True
        except Exception as exc_modern:  # noqa: BLE001
            logger.info("rapidocr indisponible (%s), essai legacy...", exc_modern)

        try:
            from rapidocr_onnxruntime import RapidOCR

            self._rapid = RapidOCR()
            self._rapid_legacy = True
            logger.info("RapidOCR initialisé (legacy onnxruntime)")
            return True
        except Exception as exc_legacy:  # noqa: BLE001
            logger.warning("Init RapidOCR échouée: %s", exc_legacy)
            return False

    def _init_paddle(self) -> bool:
        try:
            from paddleocr import PaddleOCR

            common = dict(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
            self._paddle_engines = []
            for _ in range(2):
                try:
                    engine = PaddleOCR(
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name="PP-OCRv5_mobile_rec",
                        **common,
                    )
                except Exception:  # noqa: BLE001
                    engine = PaddleOCR(lang="fr", **common)
                self._paddle_engines.append(engine)

            self._paddle_ready = True
            logger.info(
                "PaddleOCR initialisé (%d engines parallèles)",
                len(self._paddle_engines),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Init PaddleOCR échouée: %s", exc)
            return False

    def _extract_rapid_parallel(self, images: list[np.ndarray]) -> list[str]:
        if len(images) == 1:
            return [self._rapid_one(images[0])]
        futs = [self._worker_pool.submit(self._rapid_one, img) for img in images]
        return [fut.result() for fut in futs]

    def _rapid_one(self, image: np.ndarray) -> str:
        output = self._rapid(image)

        if self._rapid_legacy and isinstance(output, tuple):
            result = output[0] if output else None
            if not result:
                return ""
            lines = []
            for item in result:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text = str(item[1]).strip()
                    if text:
                        lines.append(text)
            return "\n".join(lines)

        txts = getattr(output, "txts", None)
        if txts:
            return "\n".join(str(t).strip() for t in txts if t and str(t).strip())

        if isinstance(output, list):
            lines = []
            for item in output:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text = str(item[1]).strip()
                    if text:
                        lines.append(text)
            return "\n".join(lines)

        return ""

    def _extract_paddle_parallel(self, images: list[np.ndarray]) -> list[str]:
        if not self._paddle_engines:
            return [""] * len(images)
        if len(images) == 1:
            return [self._paddle_one(self._paddle_engines[0], images[0])]

        futs = []
        for idx, image in enumerate(images):
            engine = self._paddle_engines[idx % len(self._paddle_engines)]
            futs.append(self._worker_pool.submit(self._paddle_one, engine, image))
        return [fut.result() for fut in futs]

    def _paddle_one(self, engine: Any, image: np.ndarray) -> str:
        results = engine.predict(image)
        if not results:
            return ""
        lines: list[str] = []
        for item in results:
            lines.extend(self._extract_texts_from_item(item))
        return "\n".join(line.strip() for line in lines if line and str(line).strip())

    @staticmethod
    def _extract_texts_from_item(item: Any) -> list[str]:
        data: Optional[dict[str, Any]] = None
        if hasattr(item, "json") and isinstance(item.json, dict):
            data = item.json
        elif isinstance(item, dict):
            data = item
        elif hasattr(item, "keys"):
            try:
                data = dict(item)
            except Exception:  # noqa: BLE001
                data = None

        if data is not None:
            if "rec_texts" in data and isinstance(data["rec_texts"], (list, tuple)):
                return [str(t) for t in data["rec_texts"]]
            res = data.get("res")
            if isinstance(res, dict) and "rec_texts" in res:
                return [str(t) for t in res["rec_texts"]]

        if isinstance(item, list):
            collected: list[str] = []
            for line in item:
                if (
                    isinstance(line, (list, tuple))
                    and len(line) >= 2
                    and isinstance(line[1], (list, tuple))
                    and line[1]
                ):
                    collected.append(str(line[1][0]))
                elif isinstance(line, str):
                    collected.append(line)
            return collected
        return []


ocr_service = OCRService()
