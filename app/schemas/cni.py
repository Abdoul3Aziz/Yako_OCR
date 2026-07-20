from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assets import DocumentAsset


CRITICAL_FIELDS = ("nom",)
IDENTITY_FIELDS = ("numero", "nni")


class CNIRawText(BaseModel):
    recto: str = ""
    verso: str = ""


class CNIResult(BaseModel):
    document_type: Literal["cni"] = "cni"
    numero: Optional[str] = None
    prenoms: Optional[str] = None
    nom: Optional[str] = None
    date_naissance: Optional[str] = None
    sexe: Optional[Literal["M", "F"]] = None
    taille: Optional[str] = None
    nationalite: Optional[str] = None
    lieu_naissance: Optional[str] = None
    date_expiration: Optional[str] = None
    nni: Optional[str] = None
    profession: Optional[str] = None
    date_emission: Optional[str] = None
    lieu_emission: Optional[str] = None
    photo: Optional[DocumentAsset] = None
    signature: Optional[DocumentAsset] = None
    champs_manquants: list[str] = Field(default_factory=list)
    raw_text: CNIRawText = Field(default_factory=CNIRawText)

    @field_validator("sexe", mode="before")
    @classmethod
    def normalize_sexe(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().upper()
        if text in {"M", "MASCULIN", "HOMME", "MALE"}:
            return "M"
        if text in {"F", "FEMININ", "FÉMININ", "FEMME", "FEMALE"}:
            return "F"
        return text

    @field_validator(
        "date_naissance",
        "date_expiration",
        "date_emission",
        mode="before",
    )
    @classmethod
    def normalize_date(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @field_validator("taille", mode="before")
    @classmethod
    def normalize_taille(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip().replace(" ", "")
        text = text.replace("m", "").replace("M", "")
        text = text.replace(",", ".")
        try:
            height = float(text)
            if height > 3:
                height = height / 100
            return f"{height:.2f}".replace(".", ",")
        except ValueError:
            return str(value).strip()

    @model_validator(mode="after")
    def compute_missing_and_critical(self) -> CNIResult:
        tracked = [
            "numero",
            "prenoms",
            "nom",
            "date_naissance",
            "sexe",
            "taille",
            "nationalite",
            "lieu_naissance",
            "date_expiration",
            "nni",
            "profession",
            "date_emission",
            "lieu_emission",
        ]
        missing = [name for name in tracked if not getattr(self, name)]
        self.champs_manquants = missing

        has_identity = any(getattr(self, name) for name in IDENTITY_FIELDS)
        has_critical = all(getattr(self, name) for name in CRITICAL_FIELDS)
        if not has_identity or not has_critical:
            raise ValueError(
                "Champs critiques absents: au minimum 'nom' et "
                "('numero' ou 'nni') sont requis."
            )
        return self
