from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


DATE_PATTERN = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
LABEL_PATTERN = re.compile(
    r"^(?:NUMERO\s+DE\s+SECURITE\s+SOCIALE|NOM|PRENOMS?|"
    r"DATE\s+DE\s+NAISSANCE|DATE\s+D[' ]?EMISSION|CNAM|"
    r"CARTE\s+D[' ]?ASSURE|COUVERTURE\s+MALADIE\s+UNIVERSELLE)$",
    re.IGNORECASE,
)


def normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in normalized if not unicodedata.combining(char))
    text = text.upper().replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _lines(text: str) -> list[str]:
    return [line.strip(" :.-\t") for line in text.splitlines() if line.strip()]


def _value_after_label(text: str, label: str) -> Optional[str]:
    lines = _lines(text)
    label_re = re.compile(label, re.IGNORECASE)
    for index, line in enumerate(lines):
        if not label_re.search(line):
            continue
        same_line = label_re.sub("", line, count=1).strip(" :.-")
        if same_line and not LABEL_PATTERN.fullmatch(same_line):
            return same_line
        for candidate in lines[index + 1 :]:
            if LABEL_PATTERN.fullmatch(candidate):
                break
            if candidate:
                return candidate
    return None


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(DATE_PATTERN, value)
    if not match:
        return None
    raw = match.group(0)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract_recto(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    numero = _value_after_label(
        normalized, r"NUMERO\s+DE\s+SECURITE\s+SOCIALE"
    )
    if numero:
        match = re.search(r"\b\d{10,16}\b", numero)
        numero = match.group(0) if match else None
    if not numero:
        match = re.search(r"(?m)^\s*(\d{10,16})\s*$", normalized)
        numero = match.group(1) if match else None

    nom = _value_after_label(normalized, r"(?<!PRE)\bNOM\b")
    prenoms = _value_after_label(normalized, r"\bPRENOMS?\b")
    date_naissance = _normalize_date(
        _value_after_label(normalized, r"DATE\s+DE\s+NAISSANCE")
    )

    return {
        "numero_securite_sociale": numero,
        "nom": nom.upper() if nom else None,
        "prenoms": prenoms.title() if prenoms else None,
        "date_naissance": date_naissance,
    }


def extract_verso(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    date_emission = _normalize_date(
        _value_after_label(normalized, r"DATE\s+D[' ]?EMISSION")
    )
    if not date_emission:
        date_emission = _normalize_date(normalized)
    return {"date_emission": date_emission}


def merge_cmu_fields(recto_text: str, verso_text: str) -> dict[str, Optional[str]]:
    return {**extract_recto(recto_text), **extract_verso(verso_text)}
