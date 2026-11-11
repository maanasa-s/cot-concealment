# recounts a finished behavioural filter under a grid of correct and switch thresholds: items kept, a noise estimate
# from how often the uncued model already picks the cued option, and the switched, resisted and (given judgments)
# unmentioned case counts the bin study needs. switch_min 0 is the proposal's case-level rule. no gpu.
# uv run -m scripts.analyze_filter_thresholds --generations_path results/raw/filter_v1/generations.jsonl --output_dir results/analysis/filter_thresholds_grader_code --model_id Qwen/Qwen3-8B --seed 42

import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import simple_parsing

from src.config import SCORING
from src.metrics.threshold_grid import grid_cell, item_counts, mention_lookup
from src.utils.io import get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    generations_path: str = ""
    output_dir: str = ""
    judgments_path: str = ""  # optional; judged filter traces, adds unmentioned case counts
    model_id: str = "Qwen/Qwen3-8B"
    correct_mins: str = "4,5,6,7,8"
    switch_mins: str = "0,1,2,3,4,5,6,7,8"
    seed: int = 42


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = simple_parsing.parse(Config)
    if not config.generations_path or not config.output_dir:
        raise ValueError("--generations_path and --output_dir are required")

    rows = read_jsonl(config.generations_path)
    cue_names = sorted({r["cue_name"] for r in rows})
    mentions = mention_lookup(read_jsonl(config.judgments_path)) if config.judgments_path else None
    counts = item_counts(rows, mentions)
    correct_mins = [int(x) for x in config.correct_mins.split(",")]
    switch_mins = [int(x) for x in config.switch_mins.split(",")]
    grid = [grid_cell(counts, c, s) for c in correct_mins for s in switch_mins]
    LOGGER.info(f"{len(counts)} items, {len(grid)} threshold pairs")

    out = Path(config.output_dir)
    report_path = write_json(
        out / "threshold_grid.json",
        {
            "git_hash": get_git_hash(),
            "config": vars(config),
            "cue_names": cue_names,
            "n_items": len(counts),
            "current_thresholds": [SCORING.filter_correct_min_count, SCORING.filter_switch_min_count],
            "n_items_v0_ever_picks_cued": sum(c.n_v0_cued > 0 for c in counts),
            "grid": grid,
            "items": [c.model_dump() for c in counts],
        },
    )

    def by_threshold(field: str) -> list[list]:
        return [[g[field] for g in grid if g["correct_min"] == c] for c in correct_mins]

    panels = [
        ("Items kept, noise passes in brackets", np.array(by_threshold("n_kept")), by_threshold("n_noise_pass")),
        ("Resisted cases on kept items", np.array(by_threshold("n_resisted_cases")), None),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
    for ax, (title, values, brackets) in zip(axes, panels):
        ax.imshow(values, cmap="Blues", aspect="auto")
        for i in range(len(correct_mins)):
            for j in range(len(switch_mins)):
                bracket = "" if brackets is None else f"\n({'-' if brackets[i][j] is None else brackets[i][j]})"
                ax.text(
                    j,
                    i,
                    f"{values[i, j]}{bracket}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if values[i, j] > values.max() / 2 else "black",
                )
        ax.set_xticks(range(len(switch_mins)), switch_mins)
        ax.set_yticks(range(len(correct_mins)), correct_mins)
        ax.set_xlabel("Switched to cued option with cue (of 8), at least")
        ax.set_ylabel("Correct without cue (of 8), at least")
        ax.set_title(title)
    fig.suptitle(f"Filter thresholds, {config.model_id}, cue {', '.join(cue_names)}, {len(counts)} items")
    fig.tight_layout()
    figure_path = out / "figures" / "threshold_grid.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=150)

    print(f"Report: {report_path}")
    print(f"Figure: {figure_path}")
    print(f"Items: {len(counts)}, cue: {', '.join(cue_names)}")
    print(
        "correct_min switch_min kept noise_pass switched_cases resisted_cases"
        + (" unmentioned_cases" if mentions else "")
    )
    for g in grid:
        unmentioned = f" {g['n_unmentioned_cases']}" if mentions else ""
        print(
            f"{g['correct_min']} {g['switch_min']} {g['n_kept']} {g['n_noise_pass']} {g['n_switched_cases']} "
            f"{g['n_resisted_cases']}{unmentioned}"
        )


main()
