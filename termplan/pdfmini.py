"""Write a plain text-only PDF (Helvetica, letter size). Used to build the sample PDF syllabus
and PDF test fixtures without extra dependencies."""

from __future__ import annotations

import textwrap


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text: str, *, lines_per_page: int = 54, width: int = 95) -> bytes:
    lines: list[str] = []
    for raw in text.splitlines():
        wrapped = textwrap.wrap(raw, width=width) or [""]
        lines.extend(wrapped)
    pages = [lines[i : i + lines_per_page] for i in range(0, max(len(lines), 1), lines_per_page)]

    objects: list[bytes] = []
    n_pages = len(pages)
    # 1 catalog, 2 pages, 3 font, then (page, content) pairs
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, page in enumerate(pages):
        content_id = 5 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        body = ["BT", "/F1 10 Tf", "13 TL", "54 740 Td"]
        for ln in page:
            body.append(f"({_pdf_escape(ln)}) Tj T*")
        body.append("ET")
        stream = "\n".join(body).encode("cp1252", errors="replace")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
