# compares candidate simple hint cues on saved pilot data: switched and resisted cases per filter threshold from the
# filter traces, the unmentioned rate from the judged sweep traces, and the projected unmentioned pool. no gpu.
# uv run -m scripts.compare_hint_cues --cues grader_code,answer_key --filter_paths results/raw/filter_v1/generations.jsonl,results/raw/filter_answer_key/generations.jsonl --sweep_paths results/raw/sweep_v1/generations.jsonl+results/raw/sweep_v1_resume/generations.jsonl,results/raw/sweep_answer_key/generations.jsonl --judgments_paths results/raw/judge_v1/judgments.jsonl,results/raw/judge_answer_key/judgments.jsonl --output_dir results/analysis/hint_cue_comparison --model_id Qwen/Qwen3-8B --seed 42

import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import simple_parsing

from src.metrics.threshold_grid import case_pool, grid_cell, item_counts, mention_lookup
from src.utils.io import get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    cues: str = ""  # comma separated cue names, one per filter/sweep/judgments entry
    filter_paths: str = ""
    sweep_paths: str = ""  # comma separated per cue, "+" joins several files for one cue
    judgments_paths: str = ""
    output_dir: str = ""
    filter_arm: str = "C3_neutral_private"  # the arm the filter ran in, whose unmentioned rate is projected
    thresholds: str = "6/0,6/4,6/6"
    model_id: str = "Qwen/Qwen3-8B"
    seed: int = 42


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = simple_parsing.parse(Config)
    cues = config.cues.split(",")
    filter_paths, sweep_paths, judgments_paths = (
        p.split(",") for p in (config.filter_paths, config.sweep_paths, config.judgments_paths)
    )
    if not config.output_dir or not len(cues) == len(filter_paths) == len(sweep_paths) == len(judgments_paths):
        raise ValueError("--output_dir is required and every path list needs one entry per cue")
    thresholds = [tuple(int(x) for x in t.split("/")) for t in config.thresholds.split(",")]

    results = []
    for cue, filter_path, sweep_path, judgments_path in zip(cues, filter_paths, sweep_paths, judgments_paths):
        sweep = [r for p in sweep_path.split("+") for r in read_jsonl(p)]
        mentions = mention_lookup(read_jsonl(judgments_path))
        by_arm = {
            arm: case_pool([r for r in sweep if r["arm"] == arm], mentions) for arm in sorted({r["arm"] for r in sweep})
        }
        rate = by_arm[config.filter_arm]["unmentioned_rate"]
        counts = item_counts(read_jsonl(filter_path))
        cells = []
        for correct_min, switch_min in thresholds:
            cell = grid_cell(counts, correct_min, switch_min)
            cell["projected_unmentioned_cases"] = round(cell["n_switched_cases"] * rate, 1)
            cells.append(cell)
        LOGGER.info(f"{cue}: {len(counts)} filter items, {len(sweep)} sweep traces, unmentioned rate {rate}")
        results.append({"cue_name": cue, "sweep_case_pool_by_arm": by_arm, "filter_thresholds": cells})

    out = Path(config.output_dir)
    report_path = write_json(
        out / "hint_cue_comparison.json", {"git_hash": get_git_hash(), "config": vars(config), "cues": results}
    )

    fields = [
        ("n_switched_cases", "Switched"),
        ("n_resisted_cases", "Resisted"),
        ("projected_unmentioned_cases", "Unmentioned (projected)"),
    ]
    fig, axes = plt.subplots(1, len(thresholds), figsize=(5 * len(thresholds), 4.5), sharey=True)
    x = np.arange(len(fields))
    width = 0.8 / len(results)
    for ax, (i, (c, s)) in zip(np.atleast_1d(axes), enumerate(thresholds)):
        for k, res in enumerate(results):
            values = [res["filter_thresholds"][i][f] for f, _ in fields]
            bars = ax.bar(x + k * width, values, width, label=res["cue_name"])
            ax.bar_label(bars, fmt="%g", fontsize=8)
        ax.set_xticks(x + width * (len(results) - 1) / 2, [label for _, label in fields])
        ax.set_title(f"Filter {c}/{s} (correct / switched of 8)")
        ax.set_ylabel("Cases (single answers)")
    np.atleast_1d(axes)[0].legend()
    fig.suptitle(f"Simple hint candidates, {config.model_id}, {config.filter_arm} filter traces")
    fig.tight_layout()
    figure_path = out / "figures" / "hint_cue_comparison.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=150)

    print(f"Report: {report_path}")
    print(f"Figure: {figure_path}")
    for res in results:
        pool = res["sweep_case_pool_by_arm"][config.filter_arm]
        print(
            f"{res['cue_name']} sweep {config.filter_arm}: switched {pool['n_switched']}, "
            f"unmentioned {pool['n_switched_unmentioned']} of {pool['n_switched_judged']} judged "
            f"({pool['unmentioned_rate']}), resisted {pool['n_resisted']}"
        )
        for cell in res["filter_thresholds"]:
            print(
                f"{res['cue_name']} filter {cell['correct_min']}/{cell['switch_min']}: items {cell['n_kept']}, "
                f"switched {cell['n_switched_cases']}, resisted {cell['n_resisted_cases']}, "
                f"projected unmentioned {cell['projected_unmentioned_cases']}"
            )


main()
