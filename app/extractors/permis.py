from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


DATE_PATTERN = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
LABEL_PATTERN = re.compile(
    r"^(?:\d{1,2}[.)]?\s*)?(?:NOM|PRENOMS?|DATE\s+(?:ET|EL)\s+LIEU\s+DE\s+"
    r"(?:NAISSANCE|DELIVRANCE)|NUMERO\s+DU\s+PERMIS\s+DE\s+CONDUIRE|"
    r"GROUPE\s+SANGUIN|RESTRICTIONS?|DATE\s+DE\s+VALIDITE|"
    r"DATE\s+D[' ]?EXPIRATION|DOCUMENT\s+D[' ]?IDENTITE).*$",
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
    return [line.strip(" :.\t") for line in text.splitlines() if line.strip()]


def _value_after_label(text: str, label: str) -> Optional[str]:
    lines = _lines(text)
    label_re = re.compile(label, re.IGNORECASE)
    for index, line in enumerate(lines):
        label_line = re.sub(r"^\d{1,2}[.)]?\s*", "", line)
        if not label_re.search(label_line):
            continue
        same_line = label_re.sub("", label_line, count=1).strip(" :.-")
        if same_line and not LABEL_PATTERN.fullmatch(same_line):
            return same_line
        for candidate in lines[index + 1 :]:
            if LABEL_PATTERN.fullmatch(candidate):
                break
            if candidate:
                return candidate
    return None


def _normalize_date(raw: str) -> Optional[str]:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _date_and_place(text: str, label: str) -> tuple[Optional[str], Optional[str]]:
    value = _value_after_label(text, label)
    if not value:
        return None, None
    match = re.search(rf"({DATE_PATTERN})\s*(.*)", value)
    if not match:
        return None, None
    date_value = _normalize_date(match.group(1))
    place = match.group(2).strip(" :-")
    place = place if place and not re.search(r"\d", place) else None
    return date_value, place.upper() if place else None


def extract_recto(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    nom = _value_after_label(normalized, r"(?:^|\s)NOM(?:\s*/\s*SURNAME)?")
    prenoms = _value_after_label(
        normalized, r"(?:^|\s)PRENOMS?(?:\s*/\s*GIVEN\s+NAMES?)?"
    )
    date_naissance, lieu_naissance = _date_and_place(
        normalized,
        r"DATE\s+(?:ET|EL)\s+LIEU\s+DE\s+NAISSANCE",
    )
    date_delivrance, lieu_delivrance = _date_and_place(
        normalized,
        r"DATE\s+(?:ET|EL)\s+LIEU\s+DE\s+DELIVRANCE",
    )

    numero = _value_after_label(
        normalized, r"NUMERO\s+DU\s+PERMIS\s+DE\s+CONDUIRE"
    )
    if numero:
        numero_match = re.search(r"\b(?=[A-Z0-9-]*\d)[A-Z0-9-]{8,25}\b", numero)
        numero = numero_match.group(0) if numero_match else None
    if not numero:
        match = re.search(
            r"(?m)^\s*((?=[A-Z0-9-]*\d)[A-Z]{2,5}[A-Z0-9-]{7,24})\s*$",
            normalized,
        )
        numero = match.group(1) if match else None

    return {
        "nom": nom.upper() if nom else None,
        "prenoms": prenoms.title() if prenoms else None,
        "date_naissance": date_naissance,
        "lieu_naissance": lieu_naissance,
        "date_delivrance": date_delivrance,
        "lieu_delivrance": lieu_delivrance,
        "numero_permis": numero.upper() if numero else None,
    }


def extract_verso(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    groupe = _value_after_label(normalized, r"GROUPE\s+SANGUIN")
    if groupe:
        group_match = re.search(
            r"(?<![A-Z])(?:AB|A|B|O)[+-](?![A-Z0-9])",
            groupe.replace(" ", ""),
        )
        if group_match:
            groupe = group_match.group(0)
        elif groupe.strip().upper() in {"NULL", "NUL", "NONE", "NEANT", "-"}:
            groupe = None
        else:
            groupe = groupe.strip().upper()
    return {"groupe_sanguin": groupe}


def merge_permis_fields(recto_text: str, verso_text: str) -> dict[str, Optional[str]]:
    return {**extract_recto(recto_text), **extract_verso(verso_text)}
