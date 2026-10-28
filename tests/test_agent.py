from datetime import date

from conftest import TERM_END, TERM_START, client_for, sample, scripts_with
from termplan.agent import extract_course
from termplan.stub import create_stub_app

MODEL = "nvidia/Nemotron-3_5-Lightning"


def run(client, name, **kw):
    return extract_course(client, MODEL, sample(name), label=name, term_start=TERM_START,
                          term_end=TERM_END, **kw)


def test_clean_extraction_first_try(stub_client):
    res = run(stub_client, "stat3120")
    assert res.error is None
    assert res.course_code == "STAT 3120"
    assert len(res.attempts) == 1 and res.attempts[0].errors == []
    assert len(res.items) == 14
    assert all(i.verified for i in res.items)
    mid2 = next(i for i in res.items if i.title == "Midterm 2")
    assert mid2.due_date == date(2026, 11, 5) and mid2.due_time == "19:30" and mid2.kind == "exam"
    assert [i.due_date for i in res.items] == sorted(i.due_date for i in res.items)


def test_repair_loop_fixes_bad_json_then_bad_fields(stub_app):
    client = client_for(stub_app)
    res = run(client, "bio2450")
    assert [len(a.errors) > 0 for a in res.attempts] == [True, True, False]
    assert "not valid JSON" in res.attempts[0].errors[0]
    second = " ".join(res.attempts[1].errors)
    assert "due_time" in second and "not a verbatim excerpt" in second
    assert len(res.items) == 11 and all(i.verified for i in res.items)
    assert res.undated and "TBA" in res.undated[0].source_quote
    # The repair prompt sent back to the model carries the exact validation errors.
    last_req = stub_app.state.requests[-1]["messages"]
    assert last_req[-1]["role"] == "user" and "due_time must be 24-hour" in last_req[-1]["content"]
    assert sum(m["role"] == "assistant" for m in last_req) == 2


def test_reasoning_block_is_ignored(stub_client):
    res = run(stub_client, "hist2290")
    assert len(res.attempts) == 1 and len(res.items) == 11
    assert res.undated[0].title.startswith("Museum")


def test_gives_up_after_max_attempts_but_keeps_flagged_items():
    app = create_stub_app(scripts=scripts_with("BIO 2450", ["paraphrase_and_bad_time"]))
    res = run(client_for(app), "bio2450", max_attempts=2)
    assert len(res.attempts) == 2 and res.error is None
    lab3 = next(i for i in res.items if i.title.startswith("Lab 3"))
    assert not lab3.verified and "Quote not found" in lab3.warnings[0]
    assert not any(i.title == "Field study draft" for i in res.items)  # bad time -> dropped
    assert any("malformed" in w for w in res.warnings)
    assert sum(i.verified for i in res.items) == 9


def test_never_valid_json_reports_error():
    app = create_stub_app(scripts=scripts_with("STAT 3120", ["not_json"]))
    res = run(client_for(app), "stat3120")
    assert res.items == [] and "valid JSON" in res.error and len(res.attempts) == 3


def test_wrong_year_is_caught_by_calendar_check():
    app = create_stub_app(scripts=scripts_with("STAT 3120", ["wrong_year", "clean"]))
    res = run(client_for(app), "stat3120")
    assert "outside the term" in res.attempts[0].errors[0]
    assert len(res.attempts) == 2 and all(i.due_date.year == 2026 for i in res.items)


def test_truncated_reply_raises_token_budget():
    app = create_stub_app(scripts=scripts_with("STAT 3120", ["truncated", "clean"]))
    res = run(client_for(app), "stat3120")
    assert "token limit" in res.attempts[0].errors[0]
    assert app.state.requests[0]["max_tokens"] == 8192 and app.state.requests[1]["max_tokens"] == 16384
    assert len(res.items) == 14


def test_falls_back_to_json_object_when_schema_mode_rejected():
    app = create_stub_app(reject_json_schema=True)
    client = client_for(app)
    res = run(client, "stat3120")
    assert res.attempts[0].mode == "json_object" and len(res.items) == 14
    types = [r.get("response_format", {}).get("type") for r in app.state.requests]
    assert types[:2] == ["json_schema", "json_object"]
    run(client, "hist2290")  # the working mode is remembered per model
    assert app.state.requests[-1]["response_format"]["type"] == "json_object"


def test_prompt_carries_schema_and_term_dates(stub_app):
    run(client_for(stub_app), "stat3120")
    req = stub_app.state.requests[0]
    system = req["messages"][0]["content"]
    assert "2026-08-31" in system and "source_quote" in system and "VERBATIM" in system
    assert req["model"] == MODEL and req["response_format"]["type"] == "json_schema"


def test_unknown_syllabus_uses_stub_scanner(stub_client):
    text = "CHEM 1010 General Chemistry\nQuiz 1 -- Tuesday, September 15\nFinal exam December 15, 9 am\n"
    res = extract_course(stub_client, MODEL, text, label="chem.txt", term_start=TERM_START, term_end=TERM_END)
    assert res.course_code == "CHEM 1010"
    assert {i.kind for i in res.items} == {"quiz", "exam"} and all(i.verified for i in res.items)
