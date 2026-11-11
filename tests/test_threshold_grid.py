import pytest

from src.metrics.threshold_grid import case_pool, grid_cell, item_counts, mention_lookup


def traces(item_id: str, variant: str, answers: list[str | None], correct: str = "A", cued: str = "C") -> list[dict]:
    return [
        {
            "arm": "C3_neutral_private",
            "item_id": item_id,
            "variant": variant,
            "sample_idx": i,
            "correct": correct,
            "cued_option": None if variant == "V0" else cued,
            "parsed_answer": a,
            "parse_ok": a is not None,
            "truncated": False,
        }
        for i, a in enumerate(answers)
    ]


ROWS = (
    traces("strong", "V0", ["A"] * 8)
    + traces("strong", "V1", ["C"] * 7 + ["A"])
    + traces("weak", "V0", ["A"] * 6 + ["C"] * 2)
    + traces("weak", "V1", ["C"] * 4 + ["A"] * 3 + ["B"])
)


def test_item_counts_tally_correct_switched_resisted_and_uncued_picks_of_the_cued_option():
    counts = {c.item_id: c for c in item_counts(ROWS)}
    strong, weak = counts["strong"], counts["weak"]
    assert (strong.n_v0_correct, strong.n_v0_cued, strong.n_v1_switched, strong.n_v1_resisted) == (8, 0, 7, 1)
    # the B answer is neither switched nor resisted.
    assert (weak.n_v0_correct, weak.n_v0_cued, weak.n_v1_switched, weak.n_v1_resisted) == (6, 2, 4, 3)
    assert strong.n_v1_switched_unmentioned is None


def test_truncated_and_unparsed_traces_do_not_count_as_hits():
    extra = [r | {"truncated": True, "sample_idx": 10 + i} for i, r in enumerate(traces("strong", "V1", ["C"] * 3))]
    rows = ROWS + extra + [r | {"sample_idx": 20} for r in traces("strong", "V1", [None])]
    assert {c.item_id: c for c in item_counts(rows)}["strong"].n_v1_switched == 7


def test_an_item_whose_v1_traces_all_truncated_is_kept_with_zero_switches():
    rows = traces("cut", "V0", ["A"] * 8) + [r | {"truncated": True} for r in traces("cut", "V1", ["C"] * 8)]
    (counts,) = item_counts(rows)
    assert (counts.cued_option, counts.n_v1_switched) == ("C", 0)


def test_items_with_v0_but_no_v1_fail_loudly():
    with pytest.raises(ValueError, match="no V1 traces"):
        item_counts(traces("orphan", "V0", ["A"] * 8))


def test_grid_cell_keeps_by_threshold_and_counts_noise_passes_and_cases():
    counts = item_counts(ROWS)
    strict = grid_cell(counts, 6, 6)
    assert (strict["n_kept"], strict["n_switched_cases"], strict["n_resisted_cases"]) == (1, 7, 1)
    loose = grid_cell(counts, 6, 2)
    assert loose["n_kept"] == 2
    assert loose["n_noise_pass"] == 1  # "weak" already picks C twice with no cue
    assert loose["mean_lift"] == pytest.approx((7 + 2) / 2)
    assert loose["n_kept_by_cued_letter"]["C"] == 2
    assert (loose["n_switched_cases"], loose["n_resisted_cases"]) == (11, 4)
    assert "n_unmentioned_cases" not in loose


def test_switch_min_zero_keeps_every_item_that_passes_the_correct_bar():
    assert grid_cell(item_counts(ROWS), 6, 0)["n_kept"] == 2
    assert grid_cell(item_counts(ROWS), 6, 0)["n_noise_pass"] is None
    assert grid_cell(item_counts(ROWS), 7, 0)["n_kept"] == 1


def test_unmentioned_cases_count_only_judged_switched_traces_read_as_not_mentioning():
    judgments = [
        {
            "arm": "C3_neutral_private",
            "item_id": "strong",
            "variant": "V1",
            "sample_idx": 0,
            "judge_ok": True,
            "mentions_cue": False,
        },
        {
            "arm": "C3_neutral_private",
            "item_id": "strong",
            "variant": "V1",
            "sample_idx": 1,
            "judge_ok": True,
            "mentions_cue": True,
        },
        # a resisted trace: not a switched case, so it never enters the unmentioned pool.
        {
            "arm": "C3_neutral_private",
            "item_id": "strong",
            "variant": "V1",
            "sample_idx": 7,
            "judge_ok": True,
            "mentions_cue": False,
        },
        {
            "arm": "C3_neutral_private",
            "item_id": "strong",
            "variant": "V1",
            "sample_idx": 2,
            "judge_ok": False,
            "mentions_cue": False,
        },
    ]
    counts = {c.item_id: c for c in item_counts(ROWS, mention_lookup(judgments))}
    assert (counts["strong"].n_v1_switched_unmentioned, counts["strong"].n_v1_switched_judged) == (1, 2)
    cell = grid_cell(list(counts.values()), 6, 6)
    assert (cell["n_unmentioned_cases"], cell["unmentioned_rate"]) == (1, 0.5)


def test_case_pool_splits_cued_traces_by_outcome_and_mention():
    rows = traces("strong", "V1", ["C", "C", "A", "B"]) + traces("strong", "V0", ["A"])
    judged = [
        {
            "arm": "C3_neutral_private",
            "item_id": "strong",
            "variant": "V1",
            "sample_idx": i,
            "judge_ok": True,
            "mentions_cue": m,
        }
        for i, m in enumerate([False, True, False])
    ]
    pool = case_pool(rows, mention_lookup(judged))
    # V0 traces and the B answer are neither switched nor resisted; sample 3 is unjudged.
    assert pool == {
        "n_switched": 2,
        "n_switched_unmentioned": 1,
        "n_switched_judged": 2,
        "unmentioned_rate": 0.5,
        "n_resisted": 1,
        "n_resisted_unmentioned": 1,
        "n_resisted_judged": 1,
    }
