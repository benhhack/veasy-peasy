from veasy_peasy.classifier import classify


def test_passport():
    text = "PASSPORT United Kingdom P< GBR SMITH<<JOHN date of expiry"
    assert classify(text) == "passport"


def test_bank_statement():
    text = "Monthly Statement Account Number 12345678 Sort Code 00-11-22 transaction details"
    assert classify(text) == "bank_statement"


def test_proof_of_address():
    text = "Council Tax Bill 2024 billing address 123 Main Street electricity"
    assert classify(text) == "proof_of_address"


def test_employment_letter():
    text = "To Whom It May Concern We hereby confirm that John is employed as a position with annual salary"
    assert classify(text) == "employment_letter"


def test_unknown_empty():
    assert classify("") == "unknown"


def test_unknown_gibberish():
    assert classify("lorem ipsum dolor sit amet") == "unknown"


def test_tie_returns_unknown():
    # Text with equal hits for two categories
    text = "passport statement"
    assert classify(text) == "unknown"


def test_mrz_type_p_boosts_passport():
    # Ambiguous text, but MRZ type P should tip it to passport
    text = "some document with date of expiry"
    assert classify(text, has_mrz=True, mrz_type="P") == "passport"


def test_mrz_type_i_does_not_boost_passport():
    # MRZ type I (ID card / residence permit) should NOT boost passport
    text = "given names nationality place of birth"
    assert classify(text, has_mrz=True, mrz_type="I") == "unknown"
