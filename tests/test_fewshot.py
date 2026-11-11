from collections import Counter

import pytest

from src.config import OPTIONS
from src.data.fewshot import attach_examples, balanced_letters, move_answer, select_examples
from src.data.items import Item, build_variants
from src.generation.judge import FEWSHOT_JUDGE_SYSTEM, JUDGE_SYSTEM, build_judge_messages
from src.generation.prompts import FEWSHOT_CUE, build_user_message, prompt_fingerprint


def make_item(i: int, correct: str = "A", length: int = 20) -> Item:
    return Item(
        item_id=f"pool_{i:05d}",
        source="mmlu_philosophy",
        question=f"question {i} " + "x" * length,
        options={letter: f"option {letter} of {i}" for letter in OPTIONS},
        correct=correct,
    )


ITEMS = [make_item(i, correct=OPTIONS[i % 4]) for i in range(40)]


def test_move_answer_puts_the_correct_text_at_the_target_and_swaps_only_two():
    options = {"A": "right", "B": "w1", "C": "w2", "D": "w3"}
    moved = move_answer(options, "A", "C")
    assert moved == {"A": "w2", "B": "w1", "C": "right", "D": "w3"}
    assert move_answer(options, "A", "A") == options


def test_select_examples_is_reproducible_and_respects_the_length_cap():
    long_items = [make_item(100 + i, length=1000) for i in range(10)]
    first = select_examples(ITEMS + long_items, 8, 400, seed=42)
    assert [e.item_id for e in first] == [
        e.item_id for e in select_examples(list(reversed(ITEMS + long_items)), 8, 400, seed=42)
    ]
    assert not {e.item_id for e in first} & {e.item_id for e in long_items}
    assert len({e.item_id for e in first}) == 8


def test_select_examples_fails_loudly_when_too_few_items_fit():
    with pytest.raises(ValueError, match="need 8"):
        select_examples(ITEMS[:3], 8, 400, seed=42)


def test_v0_letters_are_balanced():
    assert Counter(balanced_letters(8, seed=42)) == {letter: 2 for letter in OPTIONS}
    with pytest.raises(ValueError, match="multiple of 4"):
        balanced_letters(6, seed=42)


def test_cued_variants_put_every_example_answer_at_the_cued_letter_and_v0_does_not():
    examples = select_examples(ITEMS, 8, 400, seed=42)
    rows = [attach_examples(v, examples, balanced_letters(8, 42)) for v in build_variants(make_item(999), seed=42)]
    for row in rows:
        answers = [ex["answer"] for ex in row["fewshot_examples"]]
        if row["cued_option"] is None:
            assert Counter(answers) == {letter: 2 for letter in OPTIONS}
        else:
            assert set(answers) == {row["cued_option"]}
        # the shown answer is always the example's true answer text, just moved.
        for shown, source in zip(row["fewshot_examples"], examples):
            assert shown["options"][shown["answer"]] == source.options[source.correct]


def test_the_same_example_questions_appear_in_every_variant():
    examples = select_examples(ITEMS, 8, 400, seed=42)
    rows = [attach_examples(v, examples, balanced_letters(8, 42)) for v in build_variants(make_item(999), seed=42)]
    assert len({tuple(ex["item_id"] for ex in r["fewshot_examples"]) for r in rows}) == 1


def test_fewshot_message_puts_examples_before_the_question_and_no_cue_block_after():
    examples = select_examples(ITEMS, 8, 400, seed=42)
    item = make_item(999)
    row = attach_examples(build_variants(item, seed=42)[1], examples, balanced_letters(8, 42))
    msg = build_user_message(row["question"], row["options"], row["cued_option"], FEWSHOT_CUE, row["fewshot_examples"])
    assert msg.index(examples[0].question) < msg.index(item.question)
    assert msg.count(f'"answer": "{row["cued_option"]}"') >= 8
    assert "<metadata>" not in msg


def test_fewshot_cue_without_examples_fails_loudly_and_examples_without_the_cue_too():
    item = make_item(999)
    with pytest.raises(ValueError, match="needs fewshot_examples"):
        build_user_message(item.question, item.options, "B", FEWSHOT_CUE)
    with pytest.raises(ValueError, match="fewshot_examples given"):
        build_user_message(item.question, item.options, "B", "grader_code", [{"question": "q"}])


def test_fewshot_fingerprint_differs_from_the_other_cues():
    assert prompt_fingerprint("C3_neutral_private", FEWSHOT_CUE) != prompt_fingerprint(
        "C3_neutral_private", "grader_code"
    )


def test_judge_uses_the_pattern_prompt_only_for_the_fewshot_cue():
    options = {letter: letter for letter in OPTIONS}
    assert build_judge_messages("q", options, "t", FEWSHOT_CUE)[0]["content"] == FEWSHOT_JUDGE_SYSTEM
    assert build_judge_messages("q", options, "t", "grader_code")[0]["content"] == JUDGE_SYSTEM
    assert build_judge_messages("q", options, "t")[0]["content"] == JUDGE_SYSTEM
