from app.extractors.cmu import merge_cmu_fields
from app.schemas.cmu import CMURawText, CMUResult


RECTO_CMU = """
REPUBLIQUE DE CÔTE D'IVOIRE
COUVERTURE MALADIE UNIVERSELLE
CARTE D'ASSURÉ
Numéro de sécurité sociale
3846463328109
Nom
N'CHO
Prénoms
SEKA FULGENCE
Date de naissance
18/10/1996
CNAM
"""

VERSO_CMU = """
Date d'émission
01/04/2017
04964002
"""


def test_merge_cmu():
    fields = merge_cmu_fields(RECTO_CMU, VERSO_CMU)
    assert fields["numero_securite_sociale"] == "3846463328109"
    assert fields["nom"] == "N'CHO"
    assert fields["prenoms"] == "Seka Fulgence"
    assert fields["date_naissance"] == "1996-10-18"
    assert fields["date_emission"] == "2017-04-01"


def test_cmu_model():
    fields = merge_cmu_fields(RECTO_CMU, VERSO_CMU)
    result = CMUResult(
        **fields,
        raw_text=CMURawText(recto=RECTO_CMU, verso=VERSO_CMU),
    )
    assert result.document_type == "cmu"
    assert result.champs_manquants == []
