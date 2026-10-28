"""Build examples/stat3120_applied_regression.pdf from the text sample (for the PDF upload demo)."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from termplan.pdfmini import make_pdf  # noqa: E402

src = ROOT / "examples" / "stat3120_applied_regression.txt"
dst = src.with_suffix(".pdf")
dst.write_bytes(make_pdf(src.read_text(encoding="utf-8")))
print(f"wrote {dst.relative_to(ROOT)} ({dst.stat().st_size} bytes)")
