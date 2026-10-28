import pytest

from termplan.textutil import PayloadError, normalize, parse_json_payload, quote_in_source, strip_reasoning

SOURCE = """Problem Set 1 (simple regression) -- due Friday, September 11
The full essay is due
Thursday, November 5 at 5:00 pm. Late essays lose a third of a letter grade."""


def test_quote_matches_across_line_breaks_and_dashes():
    assert quote_in_source("The full essay is due Thursday, November 5 at 5:00 pm.", SOURCE)
    assert quote_in_source("Problem Set 1 (simple regression) — due Friday, September 11", SOURCE)
    assert quote_in_source("problem set 1 (simple regression) - due friday, september 11", SOURCE)


def test_quote_handles_curly_quotes_nbsp_and_soft_hyphens():
    src = 'Read the "Notes" chapter on lever­age before class.'
    assert quote_in_source("Read the “Notes” chapter on leverage before class.", src)


def test_quote_handles_pdf_hyphenation():
    src = "The midterm is on Wednes-\nday, November 4."
    assert quote_in_source("The midterm is on Wednesday, November 4.", src)


def test_ellipsis_fragments_must_all_be_present():
    assert quote_in_source("The full essay is due ... November 5 at 5:00 pm", SOURCE)
    assert not quote_in_source("The full essay is due ... November 6 at 5:00 pm", SOURCE)


def test_paraphrase_and_tiny_quotes_rejected():
    assert not quote_in_source("Essay two due the first Thursday of November", SOURCE)
    assert not quote_in_source("due", SOURCE)
    assert not quote_in_source("...", SOURCE)


def test_normalize_collapses_whitespace_and_case():
    assert normalize("  A–B \n\n C  ") == "a-b c"


def test_parse_plain_fenced_and_prose():
    assert parse_json_payload('{"a": 1}') == {"a": 1}
    assert parse_json_payload('Sure!\n```json\n{"a": 2}\n```\nDone.') == {"a": 2}
    assert parse_json_payload('Here you go: {"a": {"b": 3}} hope it helps') == {"a": {"b": 3}}


def test_parse_strips_reasoning():
    assert parse_json_payload('<think>dates... {"x": 0}</think>\n{"a": 1}') == {"a": 1}
    assert strip_reasoning("<think>unterminated") == ""


@pytest.mark.parametrize("raw,needle", [
    ("", "empty"),
    ("no json here", "No JSON object"),
    ('{"a": 1,}', "not valid JSON"),
    ("[1, 2]", "No JSON object"),
])
def test_parse_errors_are_actionable(raw, needle):
    with pytest.raises(PayloadError, match=needle):
        parse_json_payload(raw)
