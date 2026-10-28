import pytest

from conftest import sample
from termplan.pdfmini import make_pdf
from termplan.pdftext import SyllabusFileError, read_syllabus
from termplan.textutil import quote_in_source


def test_pdf_round_trip_keeps_quotes_verifiable():
    text = sample("stat3120")
    extracted = read_syllabus("stat.pdf", make_pdf(text))
    assert "Midterm 2 is an evening exam" in extracted
    assert quote_in_source("Midterm 2 is an evening exam on Thursday, November 5, 7:30-9:00 pm", extracted)
    assert quote_in_source(
        "Project proposal (one page: question, data source, planned model) due Monday, November 2 at 11:59 pm.",
        extracted)


def test_pdf_detected_by_magic_bytes():
    assert "Hello syllabus" in read_syllabus("noext", make_pdf("Hello syllabus with enough words in it to count."))


def test_pdf_without_text_layer_is_rejected():
    with pytest.raises(SyllabusFileError, match="no text layer"):
        read_syllabus("scan.pdf", make_pdf(""))


def test_corrupt_pdf_is_rejected():
    with pytest.raises(SyllabusFileError):
        read_syllabus("bad.pdf", b"%PDF-1.4\nnot really a pdf")


def test_text_files_and_empty_files():
    assert read_syllabus("a.txt", "Café syllabus".encode()) == "Café syllabus"
    assert read_syllabus("b.txt", b"\xe9t\xe9 latin-1") == "été latin-1"
    with pytest.raises(SyllabusFileError, match="empty"):
        read_syllabus("c.txt", b"   ")
