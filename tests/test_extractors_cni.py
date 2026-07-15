from app.extractors.cni import extract_recto, extract_verso, merge_cni_fields, parse_mrz
from app.schemas.cni import CNIRawText, CNIResult


RECTO_SAMPLE = """
REPUBLIQUE DE COTE D'IVOIRE
CARTE NATIONALE D'IDENTITE
N°: C1234567890
NOM: KONE
PRENOMS: Moussa Jean
DATE DE NAISSANCE: 15/03/1998
SEXE: M
TAILLE: 1,75 m
NATIONALITE: IVOIRIENNE
LIEU DE NAISSANCE: ABIDJAN
DATE D'EXPIRATION: 20/01/2030
"""

VERSO_SAMPLE = """
NNI: 1234567890123
PROFESSION: ETUDIANT
DATE D'EMISSION: 20/01/2020 A ABIDJAN
"""

# Texte OCR réel (CNI Habib Wilfried AKOSSI)
RECTO_REAL = """
RÉPUBLIQUE DE CÔTE D'IVOIRE
CARTE NATIONALE D'IDENTITÉ
n° CI002745404
Prénom(s)
HABIB WILFRIED
Nom
AKOSSI
Date de Naissance
SexeTaille
Nationalité
7/09/1985 M1,86 IVOIRIENNE
Lieu de Naissance
ADJAME (CIV)
Signature du titula
Date d'expiration
527894
24/12/2031
"""

VERSO_REAL = """
RÉPUBLIQUE DE COTE DIVOIRE
UNION·-DIDCIPLIME·TRIVAS
11854850560
NNI:
11
Profession:SUPERSIVEUR
199226899
Dated'émission:
24/12/2021
à: ABIDJAN
Signature de l'Autorité
Le Directeur général de l'Office National
de l'État Civil et de l'ldentification
Gnénin Sitionni KAFANA
IDCIVCI0027454<040<<<<<<<<<<<<
8509174M3112249CIV118548505605
AKOSSI<<HABIB<WILFRIED<<<<<<<<
"""


def test_extract_recto_fields():
    data = extract_recto(RECTO_SAMPLE)
    assert data["numero"] == "C1234567890"
    assert data["nom"] == "KONE"
    assert data["prenoms"] == "Moussa Jean"
    assert data["date_naissance"] == "1998-03-15"
    assert data["sexe"] == "M"
    assert data["nationalite"] == "IVOIRIENNE"
    assert data["lieu_naissance"] == "ABIDJAN"
    assert data["date_expiration"] == "2030-01-20"


def test_extract_verso_fields():
    data = extract_verso(VERSO_SAMPLE)
    assert data["nni"] == "1234567890123"
    assert data["profession"] == "ETUDIANT"
    assert data["date_emission"] == "2020-01-20"
    assert data["lieu_emission"] == "ABIDJAN"


def test_real_cni_merge():
    fields = merge_cni_fields(RECTO_REAL, VERSO_REAL)
    assert fields["numero"] == "CI002745404"
    assert fields["prenoms"] == "Habib Wilfried"
    assert fields["nom"] == "AKOSSI"
    assert fields["date_naissance"] == "1985-09-17"
    assert fields["sexe"] == "M"
    assert fields["taille"] == "1,86"
    assert fields["nationalite"] == "IVOIRIENNE"
    assert fields["lieu_naissance"] == "ADJAME (CIV)"
    assert fields["date_expiration"] == "2031-12-24"
    assert fields["nni"] == "11854850560"
    assert fields["profession"] == "SUPERSIVEUR"
    assert fields["date_emission"] == "2021-12-24"
    assert fields["lieu_emission"] == "ABIDJAN"


def test_mrz_parse():
    mrz = parse_mrz(VERSO_REAL)
    assert mrz["nom"] == "AKOSSI"
    assert mrz["prenoms"] == "HABIB WILFRIED"
    assert mrz["date_naissance"] == "1985-09-17"
    assert mrz["sexe"] == "M"
    assert mrz["date_expiration"] == "2031-12-24"
    assert mrz["nni"] == "11854850560"


def test_cni_result_model():
    fields = merge_cni_fields(RECTO_SAMPLE, VERSO_SAMPLE)
    result = CNIResult(**fields, raw_text=CNIRawText(recto=RECTO_SAMPLE, verso=VERSO_SAMPLE))
    assert result.document_type == "cni"
    assert result.nom == "KONE"
    assert result.champs_manquants == []
