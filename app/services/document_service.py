import hashlib
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

def validate_file(
        file_name: str | None, file_size: int | None, max_size_mb: int = 20
) -> str | None:
    """Повертає текст помилки українською або None, якщо файл ок. """
    if not file_name or Path(file_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return "Я читаю файли лише PDF, DOCX і TXT. Надішли один з цих форматів."
    if file_size is not None and file_size > max_size_mb * 1024 * 1024:
        return f"Файл завеликий. Максмилальний розмір - {max_size_mb} МБ."
    return None

def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def save_file(data: bytes, sha256: str, file_name: str, data_dir:str) -> str:
    uploads = Path(data_dir) / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads / f"{sha256}{Path(file_name).suffix.lower()}"
    path.write_bytes(data)
    return str(path)
