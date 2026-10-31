from app.services.document_service import validate_file


def test_valid_pdf_passes():
    assert validate_file("a.pdf", 1000) is None


def test_wrong_extension_rejected():
    assert validate_file("a.exe", 1000) is not None


def test_too_big_rejected():
    assert validate_file("a.pdf", 21 * 1024 * 1024) is not None


def test_missing_name_rejected():
    assert validate_file(None, 1000) is not None