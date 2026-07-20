from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.assets import DocumentAsset


class PermisRawText(BaseModel):
    recto: str = ""
    verso: str = ""


class PermisResult(BaseModel):
    document_type: Literal["permis"] = "permis"
    nom: Optional[str] = None
    prenoms: Optional[str] = None
    date_naissance: Optional[str] = None
    lieu_naissance: Optional[str] = None
    date_delivrance: Optional[str] = None
    lieu_delivrance: Optional[str] = None
    numero_permis: Optional[str] = None
    groupe_sanguin: Optional[str] = None
    photo: Optional[DocumentAsset] = None
    signature: Optional[DocumentAsset] = None
    champs_manquants: list[str] = Field(default_factory=list)
    raw_text: PermisRawText = Field(default_factory=PermisRawText)

    @field_validator("date_naissance", "date_delivrance", mode="before")
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

    @field_validator("groupe_sanguin", mode="before")
    @classmethod
    def normalize_blood_group(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip().upper().replace(" ", "")
        if text in {"", "NULL", "NUL", "NONE", "NEANT", "NÉANT", "-"}:
            return None
        return text

    @model_validator(mode="after")
    def compute_missing_and_critical(self) -> PermisResult:
        tracked = [
            "nom",
            "prenoms",
            "date_naissance",
            "lieu_naissance",
            "date_delivrance",
            "lieu_delivrance",
            "numero_permis",
            "groupe_sanguin",
        ]
        self.champs_manquants = [name for name in tracked if not getattr(self, name)]
        if not self.nom or not self.numero_permis:
            raise ValueError(
                "Champs critiques absents: 'nom' et 'numero_permis' sont requis."
            )
        return self
