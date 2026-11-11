import os

import pytest

from src.generation.hosted import (
    chat_messages,
    generate_hosted,
    openrouter_client,
    reasoning_missing_rate,
    reasoning_text,
    to_hosted_generation,
)
from src.generation.prompts import ARMS, build_user_message


def raw_response(content: str | None, reasoning: str | None = None, finish_reason: str = "stop", details=None) -> dict:
    """the shape openrouter returns through the openai sdk's model_dump, trimmed to the fields read."""
    message = {"role": "assistant", "content": content, "reasoning": reasoning}
    if details is not None:
        message["reasoning_details"] = details
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"completion_tokens": 120, "completion_tokens_details": {"reasoning_tokens": 100}},
    }


def test_hosted_generation_carries_reasoning_content_and_answer():
    g = to_hosted_generation(raw_response('"answer": "B"', "Mercury is closest."), sample_idx=3)
    assert g.sample_idx == 3
    assert g.think_text == "Mercury is closest."
    assert g.parsed_answer == "B" and g.parse_ok and g.parse_method == "json"
    assert g.truncated is False
    assert g.n_think_tokens == 100 and g.n_total_tokens == 120


def test_hosted_generation_flags_a_length_cut_as_truncated():
    assert to_hosted_generation(raw_response('"answer": "B"', "x", finish_reason="length"), 0).truncated is True


def test_hosted_generation_flags_empty_content_as_truncated():
    # the budget ran out inside the reasoning; there is no answer to count.
    g = to_hosted_generation(raw_response(None, "still thinking"), 0)
    assert g.truncated is True and g.parse_ok is False


def test_reasoning_falls_back_to_reasoning_details():
    message = {
        "reasoning": None,
        "reasoning_details": [{"type": "reasoning.text", "text": "step one. "}, {"text": "step two."}],
    }
    assert reasoning_text(message) == "step one. step two."


def test_missing_reasoning_is_none_and_counted():
    g = to_hosted_generation(raw_response('"answer": "A"'), 0)
    assert g.think_text is None
    assert reasoning_missing_rate([g, to_hosted_generation(raw_response('"answer": "A"', "r"), 1)]) == 0.5


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="needs OPENROUTER_API_KEY in .env")
@pytest.mark.asyncio
async def test_generate_hosted_returns_reasoning_and_a_parsed_answer():
    """a real call per the no-mocking rule: the cheapest model, one prompt, two samples. asserts the shape and
    that reasoning text comes back, which the whole study depends on."""
    question, options = "Which planet is closest to the sun?", {"A": "Venus", "B": "Mercury", "C": "Mars", "D": "Earth"}
    messages = chat_messages(ARMS["C3_neutral_private"], build_user_message(question, options, None))
    out = await generate_hosted(
        openrouter_client(),
        "openai/gpt-oss-120b",
        [messages],
        n_samples=2,
        cache_dir="cache/test_hosted",
        max_tokens=2048,
    )
    assert len(out) == 1 and len(out[0]) == 2
    for g in out[0]:
        assert g is not None
        assert g.think_text, "no reasoning text returned"
        assert g.parse_ok and g.parsed_answer in "ABCD"
