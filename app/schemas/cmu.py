from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assets import DocumentAsset


class CMURawText(BaseModel):
    recto: str = ""
    verso: str = ""


class CMUResult(BaseModel):
    document_type: Literal["cmu"] = "cmu"
    numero_securite_sociale: Optional[str] = None
    nom: Optional[str] = None
    prenoms: Optional[str] = None
    date_naissance: Optional[str] = None
    date_emission: Optional[str] = None
    photo: Optional[DocumentAsset] = None
    signature: Optional[DocumentAsset] = None
    champs_manquants: list[str] = Field(default_factory=list)
    raw_text: CMURawText = Field(default_factory=CMURawText)

    @field_validator("date_naissance", "date_emission", mode="before")
    @classmethod
    def normalize_date(cls, value: object) -> object:
        if value is None or value == "":
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @model_validator(mode="after")
    def compute_missing_and_critical(self) -> CMUResult:
        tracked = [
            "numero_securite_sociale",
            "nom",
            "prenoms",
            "date_naissance",
            "date_emission",
        ]
        self.champs_manquants = [name for name in tracked if not getattr(self, name)]
        if not self.nom or not self.numero_securite_sociale:
            raise ValueError(
                "Champs critiques absents: 'nom' et "
                "'numero_securite_sociale' sont requis."
            )
        return self
