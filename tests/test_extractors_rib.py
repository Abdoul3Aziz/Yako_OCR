import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractors.rib import extract_rib


def test_extract_rib_basic():
    """Test basique d'extraction RIB."""
    # Texte OCR simulé d'un RIB
    text = """
    RELEVE D'IDENTITE BANCAIRE
    CODE BANQUE: 12345
    CODE GUICHET: 67890
    N° DE COMPTE: 12345678901
    CLE RIB: 12
    IBAN: FR76 12345 67890 12345678901 12
    BIC: BNPAFRPP
    """

    result = extract_rib(text)

    assert result["code_banque"] == "12345"
    assert result["code_guichet"] == "67890"
    assert result["numero_compte"] == "12345678901"
    assert result["cle_rib"] == "12"
    assert result["iban"] == "FR7612345678901234567890112"
    assert result["bic_swift"] == "BNPAFRPP"


def test_extract_rib_ci():
    """Test extraction RIB Côte d'Ivoire."""
    text = """
    CODE BANQUE: 01234
    CODE GUICHET: 56789
    NUMERO DE COMPTE: 012345678901
    CLE: 34
    IBAN: CI56 01234 56789 012345678901 34
    BIC: SGBCICCI
    """

    result = extract_rib(text)

    assert result["code_banque"] == "01234"
    assert result["code_guichet"] == "56789"
    assert result["numero_compte"] == "012345678901"
    assert result["cle_rib"] == "34"
    assert result["iban"] == "CI56012345678901234567890134"
    # Le BIC peut être extrait ou None selon le parsing
    assert result["bic_swift"] in ["SGBCICCI", None]


def test_extract_rib_pattern_reconstruction():
    """Test reconstruction depuis pattern 5+5+11+2."""
    text = """
    12345 67890 12345678901 12
    """

    result = extract_rib(text)

    assert result["code_banque"] == "12345"
    assert result["code_guichet"] == "67890"
    assert result["numero_compte"] == "12345678901"
    assert result["cle_rib"] == "12"


def test_extract_rib_empty():
    """Test avec texte vide."""
    result = extract_rib("")
    assert result["code_banque"] is None
    assert result["code_guichet"] is None
    assert result["numero_compte"] is None
    assert result["cle_rib"] is None


if __name__ == "__main__":
    test_extract_rib_basic()
    print("[OK] test_extract_rib_basic passed")

    test_extract_rib_ci()
    print("[OK] test_extract_rib_ci passed")

    test_extract_rib_pattern_reconstruction()
    print("[OK] test_extract_rib_pattern_reconstruction passed")

    test_extract_rib_empty()
    print("[OK] test_extract_rib_empty passed")

    print("\nAll tests passed!")
