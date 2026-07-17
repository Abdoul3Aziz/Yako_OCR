from __future__ import annotations

import re
import unicodedata
from typing import Literal


DocumentType = Literal["cni", "passeport"]


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.upper()


def detect_document_type(recto_text: str, verso_text: str) -> DocumentType:
    """Détecte le document grâce aux titres et aux préfixes MRZ."""
    text = _normalize(f"{recto_text}\n{verso_text}")
    scores = {"cni": 0, "passeport": 0}

    # Indices visuels explicites.
    if re.search(r"CARTE\s+NATIONALE\s+D[' ]?IDENTITE", text):
        scores["cni"] += 8
    if re.search(r"\bPASSEPORT\b|\bPASSPORT\b", text):
        scores["passeport"] += 8

    # MRZ ivoiriennes : TD1 pour la CNI, TD3 pour le passeport.
    if re.search(r"(?m)^\s*IDCIV", text):
        scores["cni"] += 7
    elif re.search(r"(?m)^\s*ID[A-Z<]{3}", text):
        scores["cni"] += 5

    if re.search(r"(?m)^\s*P<CIV", text):
        scores["passeport"] += 7
    elif re.search(r"(?m)^\s*P<[A-Z]{3}", text):
        scores["passeport"] += 5

    # Indices secondaires, insuffisants seuls pour décider.
    if re.search(r"\bNNI\b", text):
        scores["cni"] += 2
    if re.search(r"\bPASSEPORT\s*(?:N|NO|N°)", text):
        scores["passeport"] += 2

    best = max(scores, key=scores.get)
    other = "passeport" if best == "cni" else "cni"
    if scores[best] < 5 or scores[best] == scores[other]:
        raise ValueError(
            "Type de document non reconnu. Fournissez une CNI ou un passeport "
            "avec le titre ou la zone MRZ lisible."
        )
    return best  # type: ignore[return-value]
