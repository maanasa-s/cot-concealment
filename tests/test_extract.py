import os

import pytest

from src.generation.extract import build_extract_messages, parse_extracted


def test_parse_extracted_accepts_one_letter_and_rejects_none_and_prose():
    assert parse_extracted("B") == "B"
    assert parse_extracted(" **C** ") == "C"
    assert parse_extracted("NONE") is None
    assert parse_extracted("B or C") is None
    assert parse_extracted(None) is None


def test_extract_messages_carry_question_options_and_reply():
    messages = build_extract_messages(
        "Which planet?", {"A": "Venus", "B": "Mercury", "C": "Mars", "D": "Earth"}, "It's Mercury."
    )
    assert "Mercury" in messages[1]["content"] and "It's Mercury." in messages[1]["content"]


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="needs OPENROUTER_API_KEY")
@pytest.mark.asyncio
async def test_extractor_reads_an_answer_stated_first():
    from src.generation.hosted import openrouter_client
    from src.utils.cache import cached_completion

    reply = "**B) Mercury.** It is the closest planet to the sun. Venus is second, and Mars is farther out."
    text = await cached_completion(
        openrouter_client(),
        model="openai/gpt-4.1-mini",
        messages=build_extract_messages(
            "Which planet is closest to the sun?", {"A": "Venus", "B": "Mercury", "C": "Mars", "D": "Earth"}, reply
        ),
        cache_dir="cache/test_extract",
        temperature=0.0,
    )
    assert parse_extracted(text) == "B"
