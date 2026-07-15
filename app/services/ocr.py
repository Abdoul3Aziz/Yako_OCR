from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np

# Must be set BEFORE importing paddle / paddleocr (PaddlePaddle 3.3.x oneDNN/PIR bug)
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"


class OCRService:
    """Lazy singleton wrapper around PaddleOCR."""

    def __init__(self) -> None:
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                lang="fr",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,  # évite le crash oneDNN / PIR (Paddle 3.3.x)
            )
        return self._engine

    def extract_text(self, image: np.ndarray) -> str:
        engine = self._get_engine()
        results = engine.predict(image)
        return self._results_to_text(results)

    @staticmethod
    def _results_to_text(results: Any) -> str:
        if not results:
            return ""

        lines: list[str] = []
        for item in results:
            texts = OCRService._extract_texts_from_item(item)
            lines.extend(texts)
        return "\n".join(line.strip() for line in lines if line and line.strip())

    @staticmethod
    def _extract_texts_from_item(item: Any) -> list[str]:
        # PaddleOCR 3.x result objects expose .json / dict-like data with rec_texts
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
            # Nested structure sometimes uses "res"
            res = data.get("res")
            if isinstance(res, dict) and "rec_texts" in res:
                return [str(t) for t in res["rec_texts"]]

        # PaddleOCR 2.x style: [[[box], (text, score)], ...]
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
