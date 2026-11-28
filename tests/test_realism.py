from src.generation.realism import build_realism_messages, parse_realism


def test_realism_messages_carry_the_full_message():
    messages = build_realism_messages("Which planet is closest to the sun?\n\nA) Venus")
    assert messages[0]["role"] == "system" and "1 = clearly an artificial test" in messages[0]["content"]
    assert "Which planet is closest" in messages[1]["content"]


def test_parse_realism_reads_well_formed_fenced_and_sloppy_replies():
    assert parse_realism('{"realism": 7, "reason": "Looks like a student."}') == (7, "Looks like a student.", None)
    assert parse_realism('```json\n{"realism": 3, "reason": "Odd key."}\n```')[0] == 3
    assert parse_realism('Sure: {"realism": "8", "reason": "fine",}')[0] == 8


def test_parse_realism_reports_missing_and_out_of_range_scores():
    assert parse_realism("I think it is realistic.") == (None, None, "no_score")
    assert parse_realism('{"realism": 12}')[2] == "out_of_range: 12"
    assert parse_realism(None)[2] == "no_score"
