from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


DATE_PATTERN = r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})"

LABEL_LINE = re.compile(
    r"^(?:"
    r"REPUBLIQUE.*|CARTE\s+NATIONALE.*"
    r"|PRENOM\(S\)|PRENOMS?|NOM(?:\s+DE\s+FAMILLE)?"
    r"|DATE\s+DE\s+NAISSANCE|SEXE|TAILLE|SEXETAILLE|NATIONALITE"
    r"|LIEU\s+DE\s+NAISSANCE|DATE\s+D[' ]?EXPIRATION|DATE\s+D[' ]?EMISSION"
    r"|NNI|PROFESSION|SIGNATURE.*|UNION.*"
    r"|LE\s+DIRECTEUR.*|DE\s+L[' ]?ETAT.*"
    r")$",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_ocr_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = _strip_accents(text)
    text = text.upper()
    text = text.replace("N0M", "NOM")
    text = re.sub(r"DATED[' ]?EMISSION", "DATE D'EMISSION", text)
    text = re.sub(r"DATED[' ]?EXPIRATION", "DATE D'EXPIRATION", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _clean_value(value: str) -> str:
    value = value.strip(" :.-|\t<>")
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
    if match:
        day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    return None


def _yymmdd_to_iso(yymmdd: str) -> Optional[str]:
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    century = 1900 if yy >= 50 else 2000
    try:
        return datetime(century + yy, mm, dd).date().isoformat()
    except ValueError:
        return None


def _expiry_yymmdd_to_iso(yymmdd: str) -> Optional[str]:
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    try:
        return datetime(2000 + yy, mm, dd).date().isoformat()
    except ValueError:
        return None


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_label(line: str) -> bool:
    cleaned = _clean_value(line)
    if LABEL_LINE.match(cleaned):
        return True
    if re.fullmatch(r"SEXE\s*TAILLE", cleaned, re.IGNORECASE):
        return True
    return False


def _value_after_label(text: str, label_patterns: list[str]) -> Optional[str]:
    """Valeur sur la même ligne après ':' ou sur les lignes suivantes non-labels."""
    lines = _lines(text)
    label_re = re.compile("|".join(f"(?:{p})" for p in label_patterns), re.IGNORECASE)

    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue

        same = label_re.sub("", line, count=1)
        same = _clean_value(same)
        same = re.sub(r"^\(+S?\)+\s*", "", same).strip()
        if same and not _is_label(same) and same not in {"(S)", "S)", "("}:
            # Une seule ligne / premier token utile
            return same.split("\n", 1)[0].strip()

        for nxt in lines[idx + 1 :]:
            if _is_label(nxt):
                break
            candidate = _clean_value(nxt)
            if candidate and candidate not in {"(S)", "S)"}:
                return candidate
    return None


def _parse_demographics_blob(text: str) -> dict[str, Optional[str]]:
    """Parse '17/09/1985 M1,86 IVOIRIENNE' (champs souvent collés par l'OCR)."""
    result: dict[str, Optional[str]] = {
        "date_naissance": None,
        "sexe": None,
        "taille": None,
        "nationalite": None,
    }
    match = re.search(
        rf"{DATE_PATTERN}\s*([MF])\s*([0-9]+[.,][0-9]{{1,2}})\s+([A-Z]+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf"{DATE_PATTERN}\s*([MF])\s*([0-9]+[.,][0-9]{{1,2}})\s*([A-Z]+)",
            text,
            re.IGNORECASE,
        )
    if match:
        result["date_naissance"] = _normalize_date(match.group(1))
        result["sexe"] = match.group(2).upper()
        result["taille"] = match.group(3).replace(".", ",")
        result["nationalite"] = match.group(4).upper()
    return result


def parse_mrz(text: str) -> dict[str, Optional[str]]:
    """Parse MRZ TD1 (3 lignes) du verso CNI."""
    raw_lines = [re.sub(r"\s+", "", line.upper()) for line in text.splitlines() if line.strip()]

    line1 = next((line for line in raw_lines if re.match(r"^ID[A-Z]{3}[A-Z0-9<]{9,}$", line)), None)
    line2 = next(
        (line for line in raw_lines if re.match(r"^\d{6}\d[MF]\d{6}\d[A-Z]{3}", line)),
        None,
    )
    # Nom<<Prenoms : exiger des lettres avant << (pas la ligne document ID...<<<)
    line3 = next((line for line in raw_lines if re.match(r"^[A-Z]+<<", line)), None)

    data: dict[str, Optional[str]] = {
        "numero": None,
        "nom": None,
        "prenoms": None,
        "date_naissance": None,
        "sexe": None,
        "date_expiration": None,
        "nni": None,
        "nationalite": None,
    }

    if line1 and len(line1) >= 15:
        # TD1: positions 6-14 = numéro (9), 15 = check, 16-30 = optional
        doc = line1[5:14].replace("<", "")
        optional_prefix = line1[15:17].replace("<", "")
        data["numero"] = f"{doc}{optional_prefix}" if doc else None

    if line2:
        m = re.match(r"^(\d{6})(\d)([MF])(\d{6})(\d)([A-Z]{3})([A-Z0-9<]+)$", line2)
        if m:
            data["date_naissance"] = _yymmdd_to_iso(m.group(1))
            data["sexe"] = m.group(3)
            data["date_expiration"] = _expiry_yymmdd_to_iso(m.group(4))
            nat = m.group(6)
            data["nationalite"] = "IVOIRIENNE" if nat == "CIV" else nat
            optional = m.group(7).replace("<", "")
            # NNI ivoirien = 11 chiffres (le 12e éventuel est une clé)
            nni_match = re.match(r"(\d{11})", optional)
            if nni_match:
                data["nni"] = nni_match.group(1)

    if line3:
        parts = line3.split("<<", 1)
        data["nom"] = parts[0].replace("<", " ").strip() or None
        if len(parts) > 1:
            prenoms = parts[1].split("<" * 2, 1)[0].replace("<", " ").strip()
            # Nettoyer fillers finaux
            prenoms = re.sub(r"\s+", " ", prenoms).strip()
            data["prenoms"] = prenoms or None

    return data


def _first_match_simple(patterns: list[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            if match.lastindex:
                return _clean_value(match.group(match.lastindex))
            return _clean_value(match.group(0))
    return None


def _first_match_numero(text: str) -> Optional[str]:
    return _first_match_simple(
        [
            r"\bN\s*°\s*[:\-]?\s*([A-Z]{0,3}\d{6,18})\b",
            r"(?m)^\s*N\s*°?\s*[:\-]?\s*([A-Z]{0,3}\d{6,18})\b",
            r"\b(CI\d{8,14})\b",
            r"\b(C\d{8,14})\b",
        ],
        text,
    )


def _find_date_near_label(text: str, label_patterns: list[str]) -> Optional[str]:
    lines = _lines(text)
    label_re = re.compile("|".join(f"(?:{p})" for p in label_patterns), re.IGNORECASE)
    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue
        window = "\n".join(lines[idx : idx + 5])
        for raw in re.findall(DATE_PATTERN, window):
            normalized = _normalize_date(raw)
            if normalized:
                return normalized
    return None


def extract_recto(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    demo = _parse_demographics_blob(normalized)

    numero = _first_match_numero(normalized)

    prenoms = _value_after_label(
        normalized,
        [r"PRENOM\(S\)", r"\bPRENOMS?\b"],
    )
    if prenoms and prenoms.upper() in {"(S)", "S)", "S", "PRE(S)"}:
        prenoms = None

    # \bNOM\b évite de matcher NOM dans PRENOM
    nom = _value_after_label(normalized, [r"\bNOM\b"])
    if nom and (_is_label(nom) or "PRE" in nom.upper()):
        nom = None

    date_naissance = demo["date_naissance"]
    sexe = demo["sexe"] or _first_match_simple(
        [r"\bSEXE\s*[:\-]?\s*([MF])\b", r"\bSEX\s*[:\-]?\s*([MF])\b"],
        normalized,
    )
    taille = demo["taille"] or _first_match_simple(
        [r"\bTAILLE\s*[:\-]?\s*([0-9]+[.,][0-9]{1,2})\b"],
        normalized,
    )

    nationalite = demo["nationalite"]
    if not nationalite:
        nationalite = _value_after_label(normalized, [r"\bNATIONALITE\b", r"\bNATIONALITY\b"])
        if nationalite and re.search(r"\d", nationalite):
            nationalite = None

    # Si les labels classiques ont une valeur dédiée (format "LABEL: valeur")
    classic_dob = _normalize_date(
        _first_match_simple(
            [rf"DATE\s+DE\s+NAISSANCE\s*[:\-]?\s*{DATE_PATTERN}"],
            normalized,
        )
    )
    if classic_dob:
        date_naissance = classic_dob

    classic_nat = _first_match_simple(
        [r"NATIONALITE\s*[:\-]?\s*([A-Z]{3,})"],
        normalized,
    )
    if classic_nat and not re.search(r"\d", classic_nat):
        nationalite = classic_nat

    lieu_naissance = _value_after_label(
        normalized,
        [r"LIEU\s+DE\s+NAISSANCE", r"PLACE\s+OF\s+BIRTH"],
    )

    date_expiration = _normalize_date(
        _first_match_simple(
            [rf"DATE\s+D[' ]?EXPIRATION\s*[:\-]?\s*{DATE_PATTERN}"],
            normalized,
        )
    )
    if date_expiration is None:
        date_expiration = _find_date_near_label(
            normalized,
            [r"DATE\s+D[' ]?EXPIRATION", r"EXPIRE\s+LE"],
        )

    return {
        "numero": numero,
        "prenoms": prenoms.title() if prenoms else None,
        "nom": nom.upper() if nom else None,
        "date_naissance": date_naissance,
        "sexe": sexe.upper() if sexe else None,
        "taille": taille,
        "nationalite": nationalite.upper() if nationalite else None,
        "lieu_naissance": lieu_naissance.upper() if lieu_naissance else None,
        "date_expiration": date_expiration,
    }


def extract_verso(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)

    nni = _first_match_simple(
        [
            r"\bNNI\s*[:\-]?\s*([0-9]{10,15})",
            r"(?m)^([0-9]{11})$",
            r"(?m)^([0-9]{10,13})$",
        ],
        normalized,
    )
    if nni and len(nni) < 10:
        nni = None

    profession = _value_after_label(
        normalized,
        [r"\bPROFESSION\b", r"\bOCCUPATION\b", r"\bMETIER\b"],
    )
    if profession:
        profession = re.sub(r"^PROFESSION\s*[:\-]?\s*", "", profession, flags=re.I)
        profession = profession.upper().strip()

    date_emission = _normalize_date(
        _first_match_simple(
            [rf"DATE\s+D[' ]?EMISSION\s*[:\-]?\s*{DATE_PATTERN}"],
            normalized,
        )
    )
    if date_emission is None:
        date_emission = _find_date_near_label(
            normalized,
            [r"DATE\s+D[' ]?EMISSION", r"DELIVRE\s+LE"],
        )

    lieu_emission = _first_match_simple(
        [
            r"(?m)^\s*A\s*[:\-]?\s*([A-Z][A-Z\-']{2,40})\s*$",
            r"\bA\s*[:\-]\s*([A-Z][A-Z\-']{2,40})\b",
            rf"{DATE_PATTERN}\s+A\s+([A-Z][A-Z\-']{{2,40}})\b",
        ],
        normalized,
    )
    if lieu_emission:
        lieu_emission = _clean_value(lieu_emission.split("\n", 1)[0]).upper()
        if (
            re.search(r"\d", lieu_emission)
            or "SIGNATURE" in lieu_emission
            or lieu_emission in {"A", "AU", "AUX"}
        ):
            lieu_emission = None

    return {
        "nni": nni,
        "profession": profession,
        "date_emission": date_emission,
        "lieu_emission": lieu_emission,
    }


def _prefer(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None


def merge_cni_fields(recto_text: str, verso_text: str) -> dict[str, Optional[str]]:
    recto = extract_recto(recto_text)
    verso = extract_verso(verso_text)
    mrz = parse_mrz(verso_text)

    merged = {
        "numero": _prefer(recto.get("numero"), mrz.get("numero")),
        "prenoms": _prefer(recto.get("prenoms"), mrz.get("prenoms")),
        "nom": _prefer(recto.get("nom"), mrz.get("nom")),
        # MRZ prioritaire pour la date de naissance (souvent tronquée en OCR: 7/09/1985)
        "date_naissance": _prefer(mrz.get("date_naissance"), recto.get("date_naissance")),
        "sexe": _prefer(recto.get("sexe"), mrz.get("sexe")),
        "taille": recto.get("taille"),
        "nationalite": _prefer(recto.get("nationalite"), mrz.get("nationalite")),
        "lieu_naissance": recto.get("lieu_naissance"),
        "date_expiration": _prefer(recto.get("date_expiration"), mrz.get("date_expiration")),
        "nni": _prefer(verso.get("nni"), mrz.get("nni")),
        "profession": verso.get("profession"),
        "date_emission": verso.get("date_emission"),
        "lieu_emission": verso.get("lieu_emission"),
    }

    if merged.get("prenoms"):
        merged["prenoms"] = merged["prenoms"].title()
    if merged.get("nom"):
        merged["nom"] = merged["nom"].upper()
    if merged.get("nationalite"):
        merged["nationalite"] = merged["nationalite"].upper()
    if merged.get("lieu_naissance"):
        merged["lieu_naissance"] = merged["lieu_naissance"].upper()
    if merged.get("lieu_emission"):
        merged["lieu_emission"] = merged["lieu_emission"].upper()
    if merged.get("profession"):
        merged["profession"] = merged["profession"].upper()
    if merged.get("sexe"):
        merged["sexe"] = merged["sexe"].upper()[:1]

    return merged
