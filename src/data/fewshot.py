# builds the few-shot position cue: a fixed set of solved example questions placed before the test
# question, with every example's correct answer moved to the cued letter on V1 to V3 and spread evenly
# over the four letters on V0. the examples are the same questions in every variant, so the only thing
# that differs between V0 and a cued variant is which letter the example answers sit at.

import hashlib
import random

from src.config import OPTIONS
from src.data.items import Item, Variant
from src.generation.prompts import FEWSHOT_CUE


def select_examples(items: list[Item], n_examples: int, max_chars: int, seed: int) -> list[Item]:
    """draws the example set once, from items short enough that n of them fit the context budget.
    the order is fixed by the seed, not by the input file, so it is reproducible from the config alone."""
    short = sorted(
        (it for it in items if len(it.question) + sum(len(v) for v in it.options.values()) <= max_chars),
        key=lambda it: it.item_id,
    )
    if len(short) < n_examples:
        raise ValueError(f"only {len(short)} items are at most {max_chars} chars, need {n_examples}")
    random.Random(int(hashlib.md5(f"{seed}:fewshot".encode()).hexdigest(), 16)).shuffle(short)
    return short[:n_examples]


def move_answer(options: dict[str, str], correct: str, target: str) -> dict[str, str]:
    """swaps the correct option into the target letter. a swap rather than a reshuffle, so at most two
    options move and the example otherwise reads as the source wrote it."""
    moved = dict(options)
    moved[target], moved[correct] = options[correct], options[target]
    return moved


def balanced_letters(n_examples: int, seed: int) -> list[str]:
    """the V0 answer letters: each letter equally often, in a seeded order, so V0 carries examples but
    no positional pattern."""
    if n_examples % len(OPTIONS):
        raise ValueError(f"n_examples must be a multiple of {len(OPTIONS)} for V0 to be balanced, got {n_examples}")
    letters = list(OPTIONS) * (n_examples // len(OPTIONS))
    random.Random(int(hashlib.md5(f"{seed}:fewshot_v0".encode()).hexdigest(), 16)).shuffle(letters)
    return letters


def build_examples(examples: list[Item], letters: list[str]) -> list[dict]:
    return [
        {
            "item_id": ex.item_id,
            "question": ex.question,
            "options": move_answer(ex.options, ex.correct, letter),
            "answer": letter,
        }
        for ex, letter in zip(examples, letters, strict=True)
    ]


def attach_examples(variant: Variant, examples: list[Item], v0_letters: list[str]) -> dict:
    """the variant row plus its rendered-ready examples. the cued letter comes from the existing
    distractor map, so the few-shot cue lands on the same wrong option the other cues would have."""
    letters = v0_letters if variant.cued_option is None else [variant.cued_option] * len(examples)
    return variant.model_dump() | {"cue_name": FEWSHOT_CUE, "fewshot_examples": build_examples(examples, letters)}
