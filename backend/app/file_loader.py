from pathlib import Path
from tempfile import NamedTemporaryFile

from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv"}


async def extract_text(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type. Upload one of: {supported}")

    raw = await upload.read()
    if suffix in {".txt", ".md", ".csv"}:
        return raw.decode("utf-8", errors="ignore")

    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(raw)
        temp_path = Path(temp_file.name)

    try:
        if suffix == ".pdf":
            reader = PdfReader(str(temp_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

        document = Document(str(temp_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    finally:
        temp_path.unlink(missing_ok=True)

