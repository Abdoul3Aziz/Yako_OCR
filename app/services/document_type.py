from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast


DocumentType = Literal["cni", "passeport", "cmu", "permis"]


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.upper()


def detect_document_type(recto_text: str, verso_text: str) -> DocumentType:
    """Détecte le document grâce aux titres et aux préfixes MRZ."""
    text = _normalize(f"{recto_text}\n{verso_text}")
    scores = {"cni": 0, "passeport": 0, "cmu": 0, "permis": 0}

    # Indices visuels explicites.
    if re.search(r"CARTE\s+NATIONALE\s+D[' ]?IDENTITE", text):
        scores["cni"] += 8
    if re.search(r"\bPASSEPORT\b|\bPASSPORT\b", text):
        scores["passeport"] += 8
    if re.search(r"COUVERTURE\s+MALADIE\s+UNIVERSELLE", text):
        scores["cmu"] += 9
    if re.search(r"\bPERMIS\s+DE\s+CONDUIRE\b", text):
        scores["permis"] += 9

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
    if re.search(r"NUMERO\s+DE\s+SECURITE\s+SOCIALE", text):
        scores["cmu"] += 4
    if re.search(r"\bCNAM\b|CARTE\s+D[' ]?ASSURE", text):
        scores["cmu"] += 2
    if re.search(r"NUMERO\s+DU\s+PERMIS\s+DE\s+CONDUIRE", text):
        scores["permis"] += 4
    if re.search(r"MINISTERE\s+DES\s+TRANSPORTS", text):
        scores["permis"] += 2

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    if best_score < 5 or best_score == ranked[1][1]:
        raise ValueError(
            "Type de document non reconnu. Fournissez une CNI, un passeport, "
            "une carte CMU ou un permis de conduire "
            "avec le titre ou la zone MRZ lisible."
        )
    return cast(DocumentType, best)
