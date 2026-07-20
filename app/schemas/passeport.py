from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assets import DocumentAsset


CRITICAL_FIELDS = ("nom", "numero")


class PasseportRawText(BaseModel):
    recto: str = ""
    verso: str = ""


class PasseportResult(BaseModel):
    document_type: Literal["passeport"] = "passeport"
    numero: Optional[str] = None
    prenoms: Optional[str] = None
    nom: Optional[str] = None
    nationalite: Optional[str] = None
    date_naissance: Optional[str] = None
    date_expiration: Optional[str] = None
    sexe: Optional[Literal["M", "F"]] = None
    lieu_naissance: Optional[str] = None
    profession: Optional[str] = None
    adresse: Optional[str] = None
    taille: Optional[str] = None
    photo: Optional[DocumentAsset] = None
    signature: Optional[DocumentAsset] = None
    champs_manquants: list[str] = Field(default_factory=list)
    raw_text: PasseportRawText = Field(default_factory=PasseportRawText)

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

    @field_validator("date_naissance", "date_expiration", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
            "%d %m %Y",
            "%d/%m/%y",
            "%d %m %y",
            "%d-%m-%y",
        ):
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
        text = text.replace("cm", "").replace("CM", "").replace("m", "").replace("M", "")
        text = text.replace(",", ".")
        try:
            height = float(text)
            # Passeport: souvent en cm (ex: 166)
            if height > 3:
                return str(int(height)) if height == int(height) else f"{height:.0f}"
            return f"{height:.2f}".replace(".", ",")
        except ValueError:
            return str(value).strip()

    @model_validator(mode="after")
    def compute_missing_and_critical(self) -> PasseportResult:
        tracked = [
            "numero",
            "prenoms",
            "nom",
            "nationalite",
            "date_naissance",
            "date_expiration",
            "sexe",
            "lieu_naissance",
            "profession",
            "adresse",
            "taille",
        ]
        self.champs_manquants = [name for name in tracked if not getattr(self, name)]

        if not all(getattr(self, name) for name in CRITICAL_FIELDS):
            raise ValueError(
                "Champs critiques absents: 'nom' et 'numero' (Passeport N°) sont requis."
            )
        return self
