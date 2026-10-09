from __future__ import annotations

import re
import unicodedata
from typing import Optional


LABEL_PATTERN = re.compile(
    r"^(?:"
    r"RIB|RELEVE\s*D[' ]?IDENTITE\s*BANCAIRE|IDENTITE\s*BANCAIRE"
    r"|CODE\s+BANQUE|BANQUE|CODE\s*GUICHET|GUICHET|AGENCE"
    r"|N[°O]\s+DE\s+COMPTE|NUMERO\s+DE\s+COMPTE|COMPTE|N[°O]\s+COMPTE"
    r"|CLE\s+RIB|CLE|RIB\s*KEY"
    r"|IBAN|INTERNATIONAL\s+BANK\s+ACCOUNT\s+NUMBER"
    r"|BIC|SWIFT|BIC\s*SWIFT|SWIFT\s*BIC"
    r"|BANK\s*CODE|BRANCH\s*CODE|ACCOUNT\s*NUMBER"
    r"|SORT\s*CODE|ROUTING\s*NUMBER"
    r"|TITULAIRE|DETENTEUR|ACCOUNT\s*HOLDER"
    r"|DOMICILIATION|BANQUE\s*Domiciliation"
    r")$",
    re.IGNORECASE,
)


def normalize_ocr_text(text: str) -> str:
    """Normalise le texte OCR pour les RIB."""
    normalized = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in normalized if not unicodedata.combining(char))
    text = text.upper().replace("\r", "\n")
    # Corrections OCR fréquentes
    text = text.replace("N0", "NO")
    text = text.replace("N°", "NO")
    text = text.replace("CLE", "CLE")
    text = text.replace("ClE", "CLE")
    text = text.replace("IBAM", "IBAN")
    text = text.replace("SWlFT", "SWIFT")
    text = text.replace("SWlFT", "SWIFT")

    # Corrections spécifiques pour codes banque CI (Ivoire)
    # C1 → CI dans les contextes de codes
    text = re.sub(r"\bC1(\d{3})\b", r"CI\1", text)
    # CL → CI dans les contextes de codes (fréquent dans OCR)
    text = re.sub(r"\bCL(\d{3})\b", r"CI\1", text)
    # L → I dans les codes de pays (CI)
    text = re.sub(r"\bCL93\b", "CI93", text)
    text = re.sub(r"\bC193\b", "CI93", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _lines(text: str) -> list[str]:
    return [line.strip(" :.-\t") for line in text.splitlines() if line.strip()]


def _is_label(line: str) -> bool:
    cleaned = line.strip(" :.-\t")
    return bool(LABEL_PATTERN.match(cleaned))


def _clean_value(value: str) -> str:
    value = value.strip(" :.-\t<>")
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def _value_after_label(text: str, label_patterns: list[str]) -> Optional[str]:
    """Extrait la valeur après un label, sur la même ligne ou les suivantes."""
    lines = _lines(text)
    label_re = re.compile("|".join(f"(?:{p})" for p in label_patterns), re.IGNORECASE)

    for idx, line in enumerate(lines):
        if not label_re.search(line):
            continue

        # Valeur sur la même ligne
        same = label_re.sub("", line, count=1)
        same = _clean_value(same)
        if same and not _is_label(same):
            return same.split("\n", 1)[0].strip()

        # Chercher sur les lignes suivantes
        for nxt in lines[idx + 1 : idx + 3]:
            if _is_label(nxt):
                break
            candidate = _clean_value(nxt)
            if candidate and not _is_label(candidate):
                return candidate
    return None


def _extract_digits(text: str, length: int) -> Optional[str]:
    """Extrait exactement `length` chiffres consécutifs."""
    match = re.search(rf"\b(\d{{{length}}})\b", text)
    return match.group(1) if match else None


def _extract_digits_range(text: str, min_len: int, max_len: int) -> Optional[str]:
    """Extrait entre min_len et max_len chiffres consécutifs."""
    for length in range(max_len, min_len - 1, -1):
        match = re.search(rf"\b(\d{{{length}}})\b", text)
        if match:
            return match.group(1)
    return None


def _extract_code_banque(text: str) -> Optional[str]:
    """Code banque : 5 caractères (chiffres ou alphanumériques pour CI)."""
    # Par label
    value = _value_after_label(
        text,
        [r"CODE\s+BANQUE", r"BANK\s*CODE", r"\bBANQUE\b"],
    )
    if value:
        # Essayer d'abord le format alphanumérique (CI)
        match = re.search(r"\b([A-Z0-9]{5})\b", value)
        if match:
            return match.group(1).upper()

    # Pattern brut - chercher 5 caractères alphanumériques
    match = re.search(r"\b([A-Z0-9]{5})\b", text)
    if match:
        candidate = match.group(1).upper()
        # Éviter de prendre un code guichet ou compte par erreur
        # Le code banque commence souvent par CI ou est purement numérique
        if candidate.startswith("CI") or candidate.isdigit():
            return candidate

    # Fallback : 5 chiffres (format FR)
    return _extract_digits(text, 5)


def _extract_code_guichet(text: str) -> Optional[str]:
    """Code guichet/agence : 5 chiffres."""
    # Par label
    value = _value_after_label(
        text,
        [r"CODE\s*GUICHET", r"GUICHET", r"AGENCE", r"BRANCH\s*CODE"],
    )
    if value:
        match = re.search(r"\b(\d{5})\b", value)
        if match:
            return match.group(1)

    # Pattern brut
    return _extract_digits(text, 5)


def _extract_numero_compte(text: str) -> Optional[str]:
    """Numéro de compte : 11-12 chiffres."""
    # Par label
    value = _value_after_label(
        text,
        [
            r"N[°O]\s+DE\s+COMPTE",
            r"NUMERO\s+DE\s+COMPTE",
            r"COMPTE",
            r"N[°O]\s+COMPTE",
            r"ACCOUNT\s*NUMBER",
        ],
    )
    if value:
        match = re.search(r"\b(\d{11,12})\b", value)
        if match:
            return match.group(1)

    # Pattern brut (11-12 chiffres)
    return _extract_digits_range(text, 11, 12)


def _extract_cle_rib(text: str) -> Optional[str]:
    """Clé RIB : 2 chiffres."""
    # Par label
    value = _value_after_label(
        text,
        [r"CLE\s+RIB", r"CLE", r"RIB\s*KEY", r"KEY"],
    )
    if value:
        match = re.search(r"\b(\d{2})\b", value)
        if match:
            return match.group(1)

    # Pattern brut (2 chiffres, souvent à la fin)
    lines = _lines(text)
    for line in reversed(lines):
        match = re.search(r"(\d{2})\s*$", line)
        if match:
            return match.group(1)

    return _extract_digits(text, 2)


def _extract_iban(text: str) -> Optional[str]:
    """IBAN : commence par FR76 ou CI, suivi de RIB."""
    normalized = normalize_ocr_text(text)

    # Par label
    value = _value_after_label(
        normalized,
        [r"IBAN", r"INTERNATIONAL\s+BANK\s+ACCOUNT\s+NUMBER"],
    )
    if value:
        # Nettoyer et extraire l'IBAN
        iban_match = re.search(
            r"\b([A-Z]{2}\d{2}[A-Z0-9]{10,30})\b",
            value.replace(" ", ""),
        )
        if iban_match:
            return _format_iban(iban_match.group(1))

    # Pattern brut - CI en priorité (avec corrections OCR)
    for prefix in ["CI", "FR"]:
        # Accepter C1 ou CL à la place de CI (corrections OCR)
        pattern = rf"[CCL][1I]{prefix}\d{{2}}[A-Z0-9]{{10,30}}"
        match = re.search(pattern, normalized.replace(" ", ""))
        if match:
            # Corriger le préfixe
            iban = match.group(0)
            iban = re.sub(r"^[CCL][1I]", "CI", iban, count=1)
            return _format_iban(iban)

    # Pattern brut - normal
    for prefix in ["CI", "FR"]:
        pattern = rf"\b{prefix}\d{{2}}[A-Z0-9]{{10,30}}\b"
        match = re.search(pattern, normalized.replace(" ", ""))
        if match:
            return _format_iban(match.group(0))

    # Pattern avec espaces (format classique)
    for prefix in ["CI", "FR"]:
        pattern = rf"\b{prefix}\d{{2}}\s[A-Z0-9\s]{{10,40}}\b"
        match = re.search(pattern, normalized)
        if match:
            return _format_iban(match.group(0))

    # Pattern avec séparateurs variés (espaces, tirets, points)
    for prefix in ["CI", "FR"]:
        pattern = rf"{prefix}\d{{2}}[\s\.-]*[A-Z0-9\s\.-]{{10,40}}"
        match = re.search(pattern, normalized)
        if match:
            return _format_iban(match.group(0))

    return None


def _format_iban(iban: str) -> str:
    """Formate l'IBAN en supprimant les espaces et majuscules."""
    iban = iban.upper().replace(" ", "").replace("\t", "").replace("\n", "")
    # Vérifier que ça ressemble à un IBAN
    if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
        return iban
    return iban


def _extract_bic_swift(text: str) -> Optional[str]:
    """BIC/SWIFT : 8 ou 11 caractères alphanumériques."""
    normalized = normalize_ocr_text(text)

    # Par label
    value = _value_after_label(
        normalized,
        [r"BIC", r"SWIFT", r"BIC\s*SWIFT", r"SWIFT\s*BIC"],
    )
    if value:
        match = re.search(r"\b([A-Z]{6}[A-Z0-9]{2,5})\b", value.replace(" ", ""))
        if match:
            bic = match.group(1).upper()
            # Exclure les mots communs qui ressemblent à des BIC
            if bic not in {"CODEBANQUE", "BANQUE", "GUICHET", "COMPTE"}:
                return bic

    # Pattern brut - chercher des patterns BIC spécifiques
    lines = _lines(normalized)
    for line in lines:
        if not line.startswith("RIB"):
            # Pattern standard 8 ou 11 caractères
            match = re.search(r"\b([A-Z]{6}[A-Z0-9]{2,5})\b", line.replace(" ", ""))
            if match:
                bic = match.group(1).upper()
                # Exclure les mots communs
                if bic not in {"CODEBANQUE", "BANQUE", "GUICHET", "COMPTE"}:
                    return bic

    # Fallback : mapping basé sur le nom de la banque détecté
    nom_banque = _extract_nom_banque(normalized)
    bank_bic_map = {
        "BHCI": "BHCICIABXXX",
        "BNI": "BNICICIABXXX",
        "BICICI": "BICICIABXXX",
        "SGBCI": "SGBCICIABXXX",
        "SIB": "SIBCIABXXX",
        "ECOBANK": "ECOBKCIABXXX",
        "ECOBANK-CI": "ECOBKCIABXXX",
        "NSIA BANQUE": "NSIACIABXXX",
        "NSIA BANQUE COTE D'IVOIRE": "NSIACIABXXX",
        "ORABANK": "ORABCIABXXX",
        "BPCI": "BPCICIABXXX",
        "BACI": "BACICIABXXX",
        "BOA": "BOACICIABXXX",
        "BANK OF AFRICA": "BOACICIABXXX",
        "BFA": "BFACICIABXXX",
        "CORIS BANK": "CORICIABXXX",
        "BANQUE DES DEPOTS DU TRESOR": "BDTCIABXXX",
    }

    if nom_banque:
        for bank, bic in bank_bic_map.items():
            if bank in nom_banque.upper():
                return bic

    return None


def _extract_nom_banque(text: str) -> Optional[str]:
    """Nom de la banque : mots en majuscules, souvent avant le RIB."""
    normalized = normalize_ocr_text(text)
    lines = _lines(normalized)
    banks = [
        "BHCI",
        "NSIA BANQUE",
        "NSIA BANQUE COTE D'IVOIRE",
        "BICICI",
        "BNI",
        "BPCI",
        "ECOBANK-CI",
        "SGBCI",
        "SIB",
        "BACI",
        "BFA",
        "BOA",
        "BANK OF AFRICA",
        "Coopec",
        "COOPEC",
        "DIAMOND",
        "United Bank for Africa",
        "UBA",
        "AFRILAND FIRST BANK",
        "FINANCIA",
        "BSIC CAPITAL SA",
        "BANQUE DES DEPOTS DU TRESOR",
        "HUDSON",
        "ECOBANK EDC",
        "NSIA FINANCES",
        "ECOBANK INVESTMENT CORPORATION",
        "ORABANK",
        "CORIS BANK",
        "CREDAFRICA",
        "BANQUE MALIENNE DE SOLIDARITE",
        "COFINA SA",
        "INTOUCH",
        "JULAYA COTE D'IVOIRE",
        "WITTI FINANCE",
        "AFG BANK CI",
        "PHOENIX CAPITAL MANAGEMENT",
        "Première Agence de MicroFinanc",
        "FINELLE",
        "GT BANK",
    ]
    # Trier par longueur décroissante pour matcher les noms les plus spécifiques d'abord
    banks.sort(key=len, reverse=True)
    bank_pattern = "|".join(re.escape(bank) for bank in banks)
    bank_re = re.compile(rf"\b({bank_pattern})\b", re.IGNORECASE)

    for line in lines:
        match = bank_re.search(line)
        if match:
            return match.group(1).upper()

    return None


def _extract_titulaire(text: str) -> Optional[str]:
    """Titulaire du compte : nom/prénom après label ou détecté automatiquement."""
    normalized = normalize_ocr_text(text)

    # Par label
    value = _value_after_label(
        normalized,
        [r"TITULAIRE", r"DETENTEUR", r"ACCOUNT\s*HOLDER", r"INTITULE\s*DU\s*COMPTE"],
    )
    if value:
        # Nettoyer : retirer "M.", "Mme", etc.
        value = re.sub(r"^(M\.|MME|MR|MLLE)\s+", "", value, flags=re.IGNORECASE)
        value = _clean_value(value)
        if value and len(value) >= 3:
            return value.upper()

    # Détection automatique : chercher des lignes qui ressemblent à des noms
    # (mots en majuscules, sans chiffres, après les informations bancaires)
    lines = _lines(normalized)
    keywords_to_skip = {
        "RIB", "BANQUE", "CODE", "GUICHET", "COMPTE", "CLE", "IBAN",
        "SWIFT", "BIC", "DOMICILIATION", "AGENCE", "TITULAIRE", "INTITULE",
        "DETENTEUR", "RELEVE", "IDENTITE", "BANCAIRE"
    }

    for line in lines:
        # Ignorer les lignes qui contiennent des labels ou des chiffres
        if any(kw in line for kw in keywords_to_skip):
            continue
        if re.search(r"\d", line):
            continue

        # Chercher des lignes qui ressemblent à des noms (mots en majuscules, sans chiffres)
        # et qui ne sont pas trop courtes
        words = line.split()
        if len(words) >= 2 and len(line) >= 5:
            # Vérifier que chaque mot commence par une lettre et est principalement alphabétique
            if all(re.match(r"^[A-Z][A-Z-']+$", w) for w in words):
                return line.upper()

    return None


def _reconstruct_rib_from_pattern(text: str) -> dict[str, Optional[str]]:
    """Tente de reconstruire le RIB depuis le pattern 5+5+11/12+2.
    Supporte les formats avec lettres (ex: C1068 pour code banque CI)."""
    normalized = normalize_ocr_text(text)

    # Pattern CI : peut contenir des lettres dans code banque/guichet
    # Format: XXXXX XXXXX XXXXXXXXXXX XX (ou avec lettres)
    pattern_ci = r"([A-Z0-9]{5})\s*([A-Z0-9]{5})\s*([A-Z0-9]{11,12})\s*(\d{2})"
    match = re.search(pattern_ci, normalized)

    if match:
        return {
            "code_banque": match.group(1),
            "code_guichet": match.group(2),
            "numero_compte": match.group(3),
            "cle_rib": match.group(4),
        }

    # Pattern classique FR (tous chiffres)
    pattern_fr = r"(\d{5})\s*(\d{5})\s*(\d{11,12})\s*(\d{2})"
    match = re.search(pattern_fr, normalized)

    if match:
        return {
            "code_banque": match.group(1),
            "code_guichet": match.group(2),
            "numero_compte": match.group(3),
            "cle_rib": match.group(4),
        }

    # Fallback : chercher tous les blocs alphanumériques
    # Tenter de reconstruire depuis les labels
    lines = _lines(normalized)
    for line in lines:
        # Chercher une ligne avec 4 blocs séparés
        blocks = re.split(r"[\s\.-]+", line)
        if len(blocks) == 4:
            if re.match(r"^[A-Z0-9]{5}$", blocks[0]) and \
               re.match(r"^[A-Z0-9]{5}$", blocks[1]) and \
               re.match(r"^[A-Z0-9]{11,12}$", blocks[2]) and \
               re.match(r"^\d{2}$", blocks[3]):
                return {
                    "code_banque": blocks[0],
                    "code_guichet": blocks[1],
                    "numero_compte": blocks[2],
                    "cle_rib": blocks[3],
                }

    return {}


def validate_rib_key(
    code_banque: str,
    code_guichet: str,
    numero_compte: str,
    cle_rib: str,
) -> bool:
    """Valide la clé RIB avec l'algorithme standard."""
    try:
        cb = int(code_banque)
        cg = int(code_guichet)
        nc = int(numero_compte)
        cle = int(cle_rib)

        # Algorithme de validation clé RIB
        calculated = 97 - ((cb * 89 + cg * 15 + nc * 3) % 97)
        if calculated == 97:
            calculated = 0

        return calculated == cle
    except (ValueError, TypeError):
        return False


def extract_rib(text: str) -> dict[str, Optional[str]]:
    """Extrait toutes les informations d'un RIB."""
    normalized = normalize_ocr_text(text)

    # D'abord essayer la reconstruction depuis pattern (plus fiable pour RIB complets)
    reconstructed = _reconstruct_rib_from_pattern(normalized)

    # Extraction par labels
    code_banque = _extract_code_banque(normalized)
    code_guichet = _extract_code_guichet(normalized)
    numero_compte = _extract_numero_compte(normalized)
    cle_rib = _extract_cle_rib(normalized)
    iban = _extract_iban(normalized)
    bic_swift = _extract_bic_swift(normalized)
    nom_banque = _extract_nom_banque(normalized)
    titulaire = _extract_titulaire(normalized)

    # Si la reconstruction a réussi, elle prend la priorité sur l'extraction par labels
    if reconstructed:
        code_banque = reconstructed.get("code_banque") or code_banque
        code_guichet = reconstructed.get("code_guichet") or code_guichet
        numero_compte = reconstructed.get("numero_compte") or numero_compte
        cle_rib = reconstructed.get("cle_rib") or cle_rib

    # Validation de la clé RIB si tous les champs sont présents
    if all([code_banque, code_guichet, numero_compte, cle_rib]):
        if not validate_rib_key(code_banque, code_guichet, numero_compte, cle_rib):
            # Clé invalide, on garde quand même mais on pourrait logger
            pass

    return {
        "code_banque": code_banque,
        "code_guichet": code_guichet,
        "numero_compte": numero_compte,
        "cle_rib": cle_rib,
        "iban": iban,
        "bic_swift": bic_swift,
        "nom_banque": nom_banque,
        "titulaire": titulaire,
    }


def merge_rib_fields(recto_text: str, verso_text: str = "") -> dict[str, Optional[str]]:
    """Merge recto et verso (verso vide pour RIB)."""
    return extract_rib(recto_text)
