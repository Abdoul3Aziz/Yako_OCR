from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


DATE_PATTERN = (
    r"(\d{1,2}[./\- ]\d{1,2}[./\- ]\d{2,4}|\d{4}-\d{2}-\d{2})"
)

# Labels stricts + variantes OCR bruitées
LABEL_LINE = re.compile(
    r"^(?:"
    r"REPUBLIQUE.*|PASSEPORT|PASSPORT|TYPE.*|TRIE.*"
    r"|CODE\s+DU\s+PAY.*|COUNTRY\s+CODE|CODE.*"
    r"|NOM|SURNAME|PRENOMS?|GIVEN\s+NAMES?"
    r"|NATIONALITE|NATIONALITY"
    r"|DATE\s+DE\s+NAISSANCE.*|DATE\s+OF\s+BIRTH.*|DACE\s+DE\s+NAL.*"
    r"|SEXE|SEX|LIEU\s+DE\s+NAISSANCE.*|PLACE\s+OF\s+BIRTH.*|BLOCE\s+OF.*"
    r"|DATE\s+DE\s+DELIVRANCE.*|DATE\s+OF\s+ISSUE.*|DASE\s+DE\s+DELL.*"
    r"|DATE\s+D[' ]?EXPIRATION.*|DATE\s+OF\s+EXPIRY.*|DATE\s+D[' ]?EXPIC.*"
    r"|AUTORITE|AUTHORITY|PASSEPORT\s*N|PASSPORT\s*NO"
    r"|PROFESSION|OCCUPATION|ADRESSE|ADDRESS|TAILLE.*|TALLLE.*|SIZE|HEIGHT|SIM"
    r"|SIGNES\s+PARTICULIERS.*|DISTINGUISHING.*"
    r"|SIGNATURE.*|SPECIMEN|CEDEAO.*|ECOWAS|CIV"
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
    # Corrections fréquentes OCR passeport CI
    replacements = {
        "DACE DE NALSANCE": "DATE DE NAISSANCE",
        "DATE D'EXPICATLON": "DATE D'EXPIRATION",
        "DATE D'EXPICATI0N": "DATE D'EXPIRATION",
        "DASE DE DELLURANCE": "DATE DE DELIVRANCE",
        "BLOCE OF BIRD": "PLACE OF BIRTH",
        "PLACE OF BIRD": "PLACE OF BIRTH",
        "TALLLE": "TAILLE",
        "ADRESSE/ADDRESS": "ADRESSE / ADDRESS",
        "TAILLE/SIM": "TAILLE / SIZE",
        "TALLLE/SIM": "TAILLE / SIZE",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _clean_value(value: str) -> str:
    value = value.strip(" :.-|\t<>")
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_label(line: str) -> bool:
    cleaned = _clean_value(line)
    if LABEL_LINE.match(cleaned):
        return True
    if re.match(
        r"^(NOM|PRENOMS?|NATIONALITE|SEXE|TAILLE|ADRESSE|PROFESSION|"
        r"LIEU\s+DE\s+NAISSANCE|DATE\s+DE\s+NAISSANCE|DATE\s+D[' ]?EXPIRATION|"
        r"DATE\s+DE\s+DELIVRANCE|PASSEPORT\s*N°?|PLACE\s+OF\s+BIRTH)"
        r"\s*/\s*[A-Z][A-Z\s/\-']+$",
        cleaned,
        re.IGNORECASE,
    ):
        return True
    # Lignes de bruit type "/BLOCE OF BIRD"
    if cleaned.startswith("/") and re.search(
        r"(BIRTH|BIRD|PLACE|SEX|SURNAME|NAME|ADDRESS|SIZE)",
        cleaned,
        re.I,
    ):
        return True
    return False


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    # "15 0913" -> "15 09 13"
    value = value.strip()
    glued = re.fullmatch(r"(\d{1,2})\s*(\d{2})(\d{2,4})", value)
    if glued and " " not in value.strip():
        value = f"{glued.group(1)} {glued.group(2)} {glued.group(3)}"
    value = re.sub(r"\s+", " ", value.strip())
    # "15 0913" with space only once
    m = re.fullmatch(r"(\d{1,2})\s+(\d{4})", value)
    if m:
        value = f"{m.group(1)} {m.group(2)[:2]} {m.group(2)[2:]}"
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d %m %Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %m %y",
    ):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _yymmdd_to_iso(yymmdd: str, *, expiry: bool = False) -> Optional[str]:
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    year = (2000 + yy) if expiry else ((1900 if yy >= 50 else 2000) + yy)
    try:
        return datetime(year, mm, dd).date().isoformat()
    except ValueError:
        return None


_ENGLISH_LABEL_NOISE = re.compile(
    r"^[/\\\-]\s*(?:"
    r"SURNAME|GIVEN\s+NAMES?|NATIONALITY|DATE\s+OF\s+BIRTH|SEX|"
    r"PLACE\s+OF\s+BIRTH|PLACE\s+OF\s+BIRD|BLOCE.*"
    r"|DATE\s+OF\s+EXPIRY|DATE\s+OF\s+ISSUE|"
    r"PASSPORT\s*NO\.?|OCCUPATION|ADDRESS|SIZE|HEIGHT|"
    r"DISTINGUISHING\s+MARKS|AUTHORITY"
    r").*$",
    re.IGNORECASE,
)


def _is_noise_value(value: str) -> bool:
    cleaned = _clean_value(value)
    if not cleaned or cleaned in {"NO", "N", "N°", "/", "-", "P", "CIV", "ECOWAS", "CEDEAO"}:
        return True
    if _is_label(cleaned):
        return True
    if _ENGLISH_LABEL_NOISE.match(cleaned):
        return True
    if cleaned.startswith("/") or cleaned.startswith("\\"):
        return True
    # Dates de délivrance collées type 160908
    if re.fullmatch(r"\d{6}", cleaned):
        return True
    return False


def _value_after_label(text: str, label_patterns: list[str]) -> Optional[str]:
    lines = _lines(text)
    label_re = re.compile("|".join(f"(?:{p})" for p in label_patterns), re.IGNORECASE)

    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue
        same = label_re.sub("", line, count=1)
        same = re.sub(
            r"^[/\\\-]\s*[A-Z][A-Z\s/\-']+$",
            "",
            _clean_value(same),
            flags=re.IGNORECASE,
        )
        same = _clean_value(same)
        if same and not _is_noise_value(same):
            return same.split("\n", 1)[0].strip()
        for nxt in lines[idx + 1 :]:
            if _is_label(nxt) or _ENGLISH_LABEL_NOISE.match(_clean_value(nxt)):
                break
            if _is_noise_value(nxt):
                continue
            candidate = _clean_value(nxt)
            if candidate and not _is_noise_value(candidate):
                return candidate
    return None


def _first_match(patterns: list[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            if match.lastindex:
                return _clean_value(match.group(match.lastindex))
            return _clean_value(match.group(0))
    return None


def _find_date_near_label(text: str, label_patterns: list[str]) -> Optional[str]:
    lines = _lines(text)
    label_re = re.compile("|".join(f"(?:{p})" for p in label_patterns), re.IGNORECASE)
    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue
        window = "\n".join(lines[idx : idx + 4])
        for raw in re.findall(DATE_PATTERN, window):
            normalized = _normalize_date(raw)
            if normalized:
                return normalized
        # Variante collée "15 0913"
        for raw in re.findall(r"\b(\d{1,2}\s+\d{4})\b", window):
            normalized = _normalize_date(raw)
            if normalized:
                return normalized
    return None


def _fix_ci_passport_number(numero: Optional[str]) -> Optional[str]:
    if not numero:
        return None
    numero = numero.upper().replace(" ", "").replace("<", "")
    # Écarter dates collées (160908) et mots sans chiffres (PASSEPORT)
    if re.fullmatch(r"\d{6}", numero) or not re.search(r"\d", numero):
        return None
    # OCR: I lu comme 1 -> 58C106019 -> 58CI06019
    m = re.fullmatch(r"(\d{2})C1(\d{5})", numero)
    if m:
        return f"{m.group(1)}CI{m.group(2)}"
    m = re.fullmatch(r"(\d{2})CI(\d{5})", numero)
    if m:
        return numero
    # Autres numéros passeport alphanumériques (au moins 2 lettres + chiffres)
    if re.fullmatch(r"(?=.*[A-Z])(?=.*\d)[A-Z0-9]{6,12}", numero):
        return numero
    return None


def parse_mrz_td3(text: str) -> dict[str, Optional[str]]:
    """MRZ passeport (2 lignes TD3)."""
    raw_lines = [re.sub(r"\s+", "", line.upper()) for line in text.splitlines() if line.strip()]

    line1 = next((line for line in raw_lines if re.match(r"^P<[A-Z]{3}", line)), None)
    line2 = next(
        (
            line
            for line in raw_lines
            # Accepte CIV ou variantes + numéro avec C1 au lieu de CI
            if re.match(r"^[A-Z0-9<]{8,9}\d?[A-Z]{3}\d{6}\d[MF<\d]\d{6}", line)
            or re.match(r"^[A-Z0-9]{9}\d[A-Z]{3}\d{6}\d[MF]\d{6}", line)
        ),
        None,
    )
    # Fallback plus souple: ligne contenant CIV + date + sexe
    if line2 is None:
        line2 = next(
            (
                line
                for line in raw_lines
                if "CIV" in line
                and re.search(r"\d{6}\d[MF]\d{6}", line)
                and not line.startswith("P<")
            ),
            None,
        )

    data: dict[str, Optional[str]] = {
        "numero": None,
        "nom": None,
        "prenoms": None,
        "nationalite": None,
        "date_naissance": None,
        "sexe": None,
        "date_expiration": None,
    }

    if line1:
        body = line1[5:] if line1.startswith("P<") else line1
        parts = body.split("<<", 1)
        if parts:
            data["nom"] = parts[0].replace("<", " ").strip() or None
        if len(parts) > 1:
            prenoms = parts[1].replace("<", " ").strip()
            prenoms = re.sub(r"\s+", " ", prenoms)
            data["prenoms"] = prenoms or None
        nat_code = line1[2:5]
        data["nationalite"] = "IVOIRIENNE" if nat_code == "CIV" else nat_code

    if line2:
        # 58CI060195CIV8201319F1309157... ou 58C1060195CIV...
        numero = _fix_ci_passport_number(line2[0:9].replace("<", ""))
        data["numero"] = numero
        civ_pos = line2.find("CIV")
        if civ_pos >= 0 and len(line2) >= civ_pos + 22:
            data["nationalite"] = "IVOIRIENNE"
            data["date_naissance"] = _yymmdd_to_iso(line2[civ_pos + 3 : civ_pos + 9])
            sex = line2[civ_pos + 10]
            data["sexe"] = sex if sex in {"M", "F"} else None
            data["date_expiration"] = _yymmdd_to_iso(
                line2[civ_pos + 11 : civ_pos + 17],
                expiry=True,
            )
        else:
            data["date_naissance"] = _yymmdd_to_iso(line2[13:19])
            data["sexe"] = line2[20] if len(line2) > 20 and line2[20] in {"M", "F"} else None
            data["date_expiration"] = _yymmdd_to_iso(line2[21:27], expiry=True)

    return data


def _extract_layout_recto(normalized: str) -> dict[str, Optional[str]]:
    """Heuristique quand les labels OCR sont trop dégradés."""
    lines = _lines(normalized)
    result: dict[str, Optional[str]] = {
        "numero": None,
        "nom": None,
        "prenoms": None,
        "nationalite": None,
        "lieu_naissance": None,
    }

    for idx, line in enumerate(lines):
        fixed = _fix_ci_passport_number(line)
        if fixed and idx + 2 < len(lines):
            result["numero"] = fixed
            cand_nom = _clean_value(lines[idx + 1])
            cand_prenoms = _clean_value(lines[idx + 2])
            if (
                cand_nom
                and not _is_noise_value(cand_nom)
                and not re.search(r"\d", cand_nom)
                and cand_nom == cand_nom.upper()
            ):
                result["nom"] = cand_nom
            if (
                cand_prenoms
                and not _is_noise_value(cand_prenoms)
                and not re.search(r"\d", cand_prenoms)
            ):
                result["prenoms"] = cand_prenoms
            # nationalité souvent 1-2 lignes après
            for nxt in lines[idx + 3 : idx + 6]:
                if "IVOIRIEN" in nxt:
                    result["nationalite"] = "IVOIRIENNE"
                    break
            break

    # Lieu de naissance: ligne après PLACE OF BIRTH (même bruité)
    for idx, line in enumerate(lines):
        if re.search(r"PLACE\s+OF\s+BIR|LIEU\s+DE\s+NAIS|BLOCE\s+OF", line, re.I):
            for nxt in lines[idx + 1 : idx + 3]:
                cand = _clean_value(nxt)
                if (
                    cand
                    and not _is_noise_value(cand)
                    and not re.search(r"\d", cand)
                    and len(cand) >= 3
                ):
                    result["lieu_naissance"] = cand
                    break
            break

    return result


def extract_recto(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    layout = _extract_layout_recto(normalized)

    numero = _fix_ci_passport_number(
        _first_match(
            [
                r"PASSEPORT\s*N\s*°?\s*[:\-]?\s*([A-Z0-9]{6,15})",
                r"PASSPORT\s*NO\.?\s*[:\-]?\s*([A-Z0-9]{6,15})",
                r"\b(\d{2}CI\d{5})\b",
                r"\b(\d{2}C1\d{5})\b",
            ],
            normalized,
        )
    ) or layout.get("numero")

    nom = _value_after_label(normalized, [r"\bNOM\b", r"\bSURNAME\b"])
    if nom and ("PRENOM" in nom or _is_label(nom) or _is_noise_value(nom)):
        nom = None
    nom = nom or layout.get("nom")

    prenoms = _value_after_label(
        normalized,
        [r"\bPRENOMS?\b", r"GIVEN\s+NAMES?"],
    ) or layout.get("prenoms")

    nationalite = _value_after_label(
        normalized,
        [r"\bNATIONALITE\b", r"\bNATIONALITY\b"],
    )
    if nationalite and re.search(r"\d", nationalite):
        nationalite = None
    if not nationalite and "IVOIRIEN" in normalized:
        nationalite = "IVOIRIENNE"
    nationalite = nationalite or layout.get("nationalite")

    date_naissance = _normalize_date(
        _first_match(
            [rf"(?:DATE\s+DE\s+NAISSANCE|DATE\s+OF\s+BIRTH)\s*[:\-]?\s*{DATE_PATTERN}"],
            normalized,
        )
    ) or _find_date_near_label(
        normalized,
        [r"DATE\s+DE\s+NAISSANCE", r"DATE\s+OF\s+BIRTH", r"DACE\s+DE\s+NAL"],
    )

    date_expiration = _normalize_date(
        _first_match(
            [
                rf"(?:DATE\s+D[' ]?EXPIRATION|DATE\s+OF\s+EXPIRY)\s*[:\-]?\s*{DATE_PATTERN}"
            ],
            normalized,
        )
    ) or _find_date_near_label(
        normalized,
        [r"DATE\s+D[' ]?EXPIRATION", r"DATE\s+OF\s+EXPIRY", r"DATE\s+D[' ]?EXPIC"],
    )

    sexe = _first_match(
        [
            r"\bSEXE\s*[/]?\s*SEX\s*[:\-]?\s*([MF])\b",
            r"\bSEXE\s*[:\-]?\s*([MF])\b",
            r"\bSEX\s*[:\-]?\s*([MF])\b",
            r"(?m)^\s*([MF])\s*$",
        ],
        normalized,
    )

    lieu_naissance = _value_after_label(
        normalized,
        [
            r"LIEU\s+DE\s+NAISSANCE",
            r"PLACE\s+OF\s+BIRTH",
            r"PLACE\s+OF\s+BIR",
            r"BLOCE\s+OF",
        ],
    ) or layout.get("lieu_naissance")

    return {
        "numero": numero,
        "nom": nom.upper() if nom else None,
        "prenoms": prenoms.title() if prenoms else None,
        "nationalite": nationalite.upper() if nationalite else None,
        "date_naissance": date_naissance,
        "date_expiration": date_expiration,
        "sexe": sexe.upper() if sexe else None,
        "lieu_naissance": lieu_naissance.upper() if lieu_naissance else None,
    }


def extract_verso(text: str) -> dict[str, Optional[str]]:
    normalized = normalize_ocr_text(text)
    lines = _lines(normalized)

    profession = _value_after_label(
        normalized,
        [r"\bPROFESSION\b", r"\bOCCUPATION\b"],
    )
    # Fallback: ligne avant ADRESSE (souvent sans label Profession lisible)
    if not profession:
        for idx, line in enumerate(lines):
            if re.search(r"\bADRESSE\b|\bADDRESS\b", line, re.I) and idx > 0:
                cand = _clean_value(lines[idx - 1])
                if (
                    cand
                    and not _is_noise_value(cand)
                    and not re.search(r"\d", cand)
                    and re.fullmatch(r"[A-Z\- ]{3,40}", cand)
                    and cand not in {"CEDEAO", "ECOWAS"}
                ):
                    profession = cand
                    break

    if profession:
        profession = profession.upper()

    adresse = _value_after_label(
        normalized,
        [r"\bADRESSE\b", r"\bADDRESS\b"],
    )
    if adresse:
        adresse = re.sub(r"\s+", "", adresse.upper())

    taille = _first_match(
        [
            r"\bTAILLE\s*(?:/\s*SIZE)?\s*[:\-]?\s*([0-9]{2,3})",
            r"\bSIZE\s*[:\-]?\s*([0-9]{2,3})",
            r"\bHEIGHT\s*[:\-]?\s*([0-9]{2,3})",
            r"(?m)^\s*([1-2][0-9]{2})\s*$",
        ],
        normalized,
    )
    if not taille:
        taille = _value_after_label(
            normalized,
            [r"\bTAILLE\b", r"\bTALLLE\b", r"\bSIZE\b", r"\bHEIGHT\b"],
        )

    return {
        "profession": profession,
        "adresse": adresse,
        "taille": taille,
    }


def _prefer(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None


def _prefer_prenoms(ocr_value: Optional[str], mrz_value: Optional[str]) -> Optional[str]:
    """Privilégie l'OCR s'il conserve l'apostrophe (N'GUESSAN)."""
    if ocr_value and ("'" in ocr_value or "’" in ocr_value):
        return ocr_value
    if ocr_value and mrz_value:
        # OCR plus long / plus riche
        if len(ocr_value.replace(" ", "")) >= len(mrz_value.replace(" ", "")):
            return ocr_value
    return _prefer(ocr_value, mrz_value)


def merge_passeport_fields(recto_text: str, verso_text: str) -> dict[str, Optional[str]]:
    recto = extract_recto(recto_text)
    verso = extract_verso(verso_text)
    mrz = parse_mrz_td3(recto_text)
    if not mrz.get("numero"):
        mrz = parse_mrz_td3(f"{recto_text}\n{verso_text}")

    # Numéro: MRZ prioritaire (évite 160908), puis OCR corrigé
    numero = _fix_ci_passport_number(mrz.get("numero")) or _fix_ci_passport_number(
        recto.get("numero")
    )

    merged = {
        "numero": numero,
        "nom": _prefer(recto.get("nom"), mrz.get("nom")),
        "prenoms": _prefer_prenoms(recto.get("prenoms"), mrz.get("prenoms")),
        "nationalite": _prefer(recto.get("nationalite"), mrz.get("nationalite")),
        "date_naissance": _prefer(mrz.get("date_naissance"), recto.get("date_naissance")),
        "date_expiration": _prefer(mrz.get("date_expiration"), recto.get("date_expiration")),
        "sexe": _prefer(mrz.get("sexe"), recto.get("sexe")),
        "lieu_naissance": recto.get("lieu_naissance"),
        "profession": verso.get("profession"),
        "adresse": verso.get("adresse"),
        "taille": verso.get("taille"),
    }

    if merged.get("prenoms"):
        # title() casse N'GUESSAN -> N'Guessan (OK). Préserve apostrophe.
        merged["prenoms"] = merged["prenoms"].replace("’", "'").title()
    if merged.get("nom"):
        merged["nom"] = merged["nom"].upper()
    if merged.get("nationalite"):
        merged["nationalite"] = merged["nationalite"].upper()
    if merged.get("lieu_naissance"):
        merged["lieu_naissance"] = merged["lieu_naissance"].upper()
    if merged.get("profession"):
        merged["profession"] = merged["profession"].upper()
    if merged.get("adresse"):
        merged["adresse"] = merged["adresse"].upper()
    if merged.get("sexe"):
        merged["sexe"] = merged["sexe"].upper()[:1]

    return merged
