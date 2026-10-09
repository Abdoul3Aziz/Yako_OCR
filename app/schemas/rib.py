from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assets import DocumentAsset


CRITICAL_FIELDS = ("iban",)
IDENTITY_FIELDS = ("code_banque", "code_guichet", "numero_compte", "cle_rib")


class RIBRawText(BaseModel):
    recto: str = ""
    verso: str = ""


class RIBResult(BaseModel):
    document_type: Literal["rib"] = "rib"
    code_banque: Optional[str] = None
    code_guichet: Optional[str] = None
    numero_compte: Optional[str] = None
    cle_rib: Optional[str] = None
    iban: Optional[str] = None
    bic_swift: Optional[str] = None
    nom_banque: Optional[str] = None
    titulaire: Optional[str] = None
    photo: Optional[DocumentAsset] = None
    signature: Optional[DocumentAsset] = None
    recto: Optional[DocumentAsset] = None
    verso: Optional[DocumentAsset] = None
    champs_manquants: list[str] = Field(default_factory=list)
    raw_text: RIBRawText = Field(default_factory=RIBRawText)

    @field_validator("code_banque", mode="before")
    @classmethod
    def validate_code_banque(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper()
        # Accepte 5 chiffres (FR) ou 5 caractères alphanumériques (CI)
        if re.match(r"^[A-Z0-9]{5}$", text):
            return text
        return None

    @field_validator("code_guichet", mode="before")
    @classmethod
    def validate_code_guichet(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper()
        # Accepte 5 chiffres (FR) ou 5 caractères alphanumériques (CI)
        if re.match(r"^[A-Z0-9]{5}$", text):
            return text
        return None

    @field_validator("numero_compte", mode="before")
    @classmethod
    def validate_numero_compte(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper()
        # Accepte 11-12 chiffres (FR) ou alphanumériques (CI)
        if re.match(r"^[A-Z0-9]{11,12}$", text):
            return text
        return None

    @field_validator("cle_rib", mode="before")
    @classmethod
    def validate_cle_rib(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip()
        if re.match(r"^\d{2}$", text):
            return text
        return None

    @field_validator("iban", mode="before")
    @classmethod
    def validate_iban(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper().replace(" ", "")
        # IBAN : 2 lettres + 2 chiffres + 10-30 caractères alphanumériques
        if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", text):
            return text
        return None

    @field_validator("bic_swift", mode="before")
    @classmethod
    def validate_bic_swift(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper().replace(" ", "")
        # BIC/SWIFT : 6 lettres + 2-5 caractères alphanumériques
        if re.match(r"^[A-Z]{6}[A-Z0-9]{2,5}$", text):
            return text
        return None

    @field_validator("nom_banque", mode="before")
    @classmethod
    def normalize_nom_banque(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return str(value).strip().upper()

    @field_validator("titulaire", mode="before")
    @classmethod
    def normalize_titulaire(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return str(value).strip().upper()

    @model_validator(mode="after")
    def compute_missing_and_critical(self) -> RIBResult:
        tracked = [
            "code_banque",
            "code_guichet",
            "numero_compte",
            "cle_rib",
            "iban",
            "bic_swift",
            "nom_banque",
            "titulaire",
        ]
        missing = [name for name in tracked if not getattr(self, name)]
        self.champs_manquants = missing

        # Validation : soit IBAN, soit le RIB complet
        has_iban = bool(self.iban)
        has_rib = all(
            getattr(self, name)
            for name in IDENTITY_FIELDS
        )

        if not has_iban and not has_rib:
            raise ValueError(
                "Champs critiques absents: au minimum 'iban' ou "
                "('code_banque' + 'code_guichet' + 'numero_compte' + 'cle_rib') sont requis."
            )

        return self
