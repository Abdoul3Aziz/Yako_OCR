import pytest

from app.services.document_type import detect_document_type


def test_detect_cni_from_title():
    assert (
        detect_document_type(
            "REPUBLIQUE DE COTE D'IVOIRE\nCARTE NATIONALE D'IDENTITE",
            "",
        )
        == "cni"
    )


def test_detect_cni_from_mrz():
    assert detect_document_type("", "IDCIVCI0027454<040<<<<<<<<<<<<") == "cni"


def test_detect_passport_from_title():
    assert detect_document_type("REPUBLIQUE DE COTE D'IVOIRE\nPASSEPORT", "") == "passeport"


def test_detect_passport_from_mrz():
    assert detect_document_type("", "P<CIVKOFFI<<NGUESSAN<NINA<<<<<<<<") == "passeport"


def test_reject_unknown_document():
    with pytest.raises(ValueError, match="Type de document non reconnu"):
        detect_document_type("PHOTO FLOUE", "TEXTE INCOMPLET")
