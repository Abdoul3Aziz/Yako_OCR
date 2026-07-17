from app.extractors.permis import merge_permis_fields
from app.schemas.permis import PermisRawText, PermisResult


RECTO_PERMIS = """
RÉPUBLIQUE DE CÔTE D'IVOIRE
MINISTÈRE DES TRANSPORTS
PERMIS DE CONDUIRE
1. Nom
N'DA
2. Prénoms
KOUAME KONAN ALEXANDRE
3. Date el lieu de naissance
22-04-1998 KOUMASSI
4. Date et lieu de délivrance
26-08-2022 Abidjan
5. Numéro du permis de conduire
NDA01-22-00317474K
6. Restriction(s)
"""

VERSO_PERMIS = """
8. Date de validité
09-03-2000
9. Date d'expiration
Indéfinie
10. Document d'identité
CNI - NI - 01 - X
11. Groupe Sanguin
null
"""


def test_merge_permis_separe_dates_et_lieux():
    fields = merge_permis_fields(RECTO_PERMIS, VERSO_PERMIS)
    assert fields["nom"] == "N'DA"
    assert fields["prenoms"] == "Kouame Konan Alexandre"
    assert fields["date_naissance"] == "1998-04-22"
    assert fields["lieu_naissance"] == "KOUMASSI"
    assert fields["date_delivrance"] == "2022-08-26"
    assert fields["lieu_delivrance"] == "ABIDJAN"
    assert fields["numero_permis"] == "NDA01-22-00317474K"
    assert fields["groupe_sanguin"] is None


def test_permis_groupe_sanguin():
    fields = merge_permis_fields(RECTO_PERMIS, "11. Groupe Sanguin\nAB+")
    assert fields["groupe_sanguin"] == "AB+"
    result = PermisResult(
        **fields,
        raw_text=PermisRawText(recto=RECTO_PERMIS, verso="Groupe Sanguin\nAB+"),
    )
    assert result.document_type == "permis"
    assert result.champs_manquants == []
