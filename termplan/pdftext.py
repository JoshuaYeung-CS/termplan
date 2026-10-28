"""Syllabus file reading: PDF via pypdf, everything else as UTF-8 text."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_BYTES = 5 * 1024 * 1024


class SyllabusFileError(ValueError):
    pass


def read_syllabus(filename: str, data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise SyllabusFileError(f"{filename}: file is larger than 5 MB")
    if filename.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_to_text(filename, data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if not text.strip():
        raise SyllabusFileError(f"{filename}: file is empty")
    return text


def pdf_to_text(filename: str, data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pragma: no cover - depends on the PDF
                raise SyllabusFileError(f"{filename}: PDF is password protected") from exc
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise SyllabusFileError(f"{filename}: could not read PDF ({exc})") from exc
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if len(text.strip()) < 40:
        raise SyllabusFileError(
            f"{filename}: the PDF has no text layer (is it a scan?). Paste the text instead."
        )
    return text
