from app.extractors.passeport import merge_passeport_fields, parse_mrz_td3
from app.schemas.passeport import PasseportRawText, PasseportResult


RECTO_SAMPLE = """
REPUBLIQUE DE COTE D'IVOIRE
PASSEPORT
Type P
Code du pays CIV
Passeport N° 58CI06019
Nom / Surname
KOFFI
Prénoms / Given names
N'GUESSAN NINA
Nationalité / Nationality
IVOIRIENNE
Date de naissance / Date of birth
31 01 82
Sexe / Sex
F
Lieu de naissance / Place of birth
DABOU
Date d'expiration / Date of expiry
15 09 13
P<CIVKOFFI<<NGUESSAN<NINA<<<<<<<<<<<<<<<<<<<
58CI060195CIV8201319F1309157<<<<<<<<<<<<<<<06
"""

VERSO_SAMPLE = """
Profession / Occupation
FONCTIONNAIRE
Adresse / Address
20BP121ABJ20
Taille / Size
166
Signes particuliers
NEANT
"""


def test_mrz_td3():
    mrz = parse_mrz_td3(RECTO_SAMPLE)
    assert mrz["nom"] == "KOFFI"
    assert mrz["prenoms"] == "NGUESSAN NINA"
    assert mrz["numero"] == "58CI06019"
    assert mrz["date_naissance"] == "1982-01-31"
    assert mrz["sexe"] == "F"
    assert mrz["date_expiration"] == "2013-09-15"


def test_merge_passeport():
    fields = merge_passeport_fields(RECTO_SAMPLE, VERSO_SAMPLE)
    assert fields["numero"] == "58CI06019"
    assert fields["nom"] == "KOFFI"
    assert fields["prenoms"] == "N'Guessan Nina"
    assert fields["nationalite"] == "IVOIRIENNE"
    assert fields["date_naissance"] == "1982-01-31"
    assert fields["date_expiration"] == "2013-09-15"
    assert fields["sexe"] == "F"
    assert fields["lieu_naissance"] == "DABOU"
    assert fields["profession"] == "FONCTIONNAIRE"
    assert fields["adresse"] == "20BP121ABJ20"
    assert fields["taille"] == "166"


def test_passeport_model():
    fields = merge_passeport_fields(RECTO_SAMPLE, VERSO_SAMPLE)
    result = PasseportResult(
        **fields,
        raw_text=PasseportRawText(recto=RECTO_SAMPLE, verso=VERSO_SAMPLE),
    )
    assert result.document_type == "passeport"
    assert result.champs_manquants == []


# OCR réel dégradé (labels bruités, C1 au lieu de CI, profession sans label)
RECTO_REAL = """
RÉPUBLIQUE DE COTE D'IVOIRE
Passeport
Trie/Th
Codé du pay
Passport
CIV
58C106019
KOFFI
N'GUESSAN NINA
IVOIRIENNE
Dace de nalsance/Dnref-bos
31 01 82
/Bloce of bird
DABOU
Dase de dellurance/Dets
160908
S/D PAF
Date d'expicatlon/Dem
15 0913
SPECIMEN
P<CIVKOFFI<<NGUESSAN<NINA<<<<<<<<<<<<<<<<<<<
58C1060195CIV8201319F1309157<<<<<<<<<<<<<<06
"""

VERSO_REAL = """
福
CEDEAO
ECOWAS
FONCTIONNAIRE
Adresse/Address
20BP121ABJ20
Tallle/Sim
166
Signes particullers/Digott m
NEANT
Signature de l'autorite/Author
"""


def test_real_ocr_passeport():
    fields = merge_passeport_fields(RECTO_REAL, VERSO_REAL)
    assert fields["numero"] == "58CI06019"
    assert fields["nom"] == "KOFFI"
    assert fields["prenoms"] == "N'Guessan Nina"
    assert fields["nationalite"] == "IVOIRIENNE"
    assert fields["date_naissance"] == "1982-01-31"
    assert fields["date_expiration"] == "2013-09-15"
    assert fields["sexe"] == "F"
    assert fields["lieu_naissance"] == "DABOU"
    assert fields["profession"] == "FONCTIONNAIRE"
    assert fields["adresse"] == "20BP121ABJ20"
    assert fields["taille"] == "166"


# OCR réel sans label "Prénoms" : la MRZ doit empêcher OUATTARA → prénoms.
RECTO_OUATTARA = """
RÉPUBLIQUE DE COTE D'IVOIRE
Passeport
P
CIV
21AF80987
Nom/Sard
OUATTARA
FOUSSENY
Nationalite/N
IVOIRIENNE
P<CIVOUATTARA<<FUSSENY<<<<<<<<<<<<<<<<
21AF809870CIV0109017M2704058<<<<<<<<<<<
"""


def test_passeport_mrz_prenoms_prioritaire_sur_nom():
    fields = merge_passeport_fields(RECTO_OUATTARA, "COMMERCIAL\n191")
    assert fields["numero"] == "21AF80987"
    assert fields["nom"] == "OUATTARA"
    assert fields["prenoms"] == "Fousseny"
    assert fields["date_naissance"] == "2001-09-01"
    assert fields["date_expiration"] == "2027-04-05"
    assert fields["sexe"] == "M"
