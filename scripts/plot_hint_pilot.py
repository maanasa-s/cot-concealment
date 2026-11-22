# draws a hint cue pilot's outcomes, mention and awareness rates, and the proposal's three pilot checks from its summary.json.
# uv run -m scripts.plot_hint_pilot --summary_path results/raw/hint_pilot_qwen3_8_27b_v1/summary.json --output_dir results/analysis/hint_pilot_qwen3_8_27b_v1 --seed 42

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import simple_parsing

from src.utils.io import get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)

CONTROLS = ("no_hint", "fewshot_none")
OUTCOME_COLORS = {"flipped": "#c0504d", "resisted": "#4f81bd", "dropped": "#9e9e9e"}


@dataclass
class Config:
    summary_path: str = ""
    output_dir: str = ""
    seed: int = 42


def outcome_counts(generations: list[dict], condition: str, known: set[str]) -> dict[str, int]:
    rows = [
        r
        for r in generations
        if r["condition"] == condition and r["item_id"] in known and not r["truncated"] and r["parse_ok"]
    ]
    flipped = sum(r["parsed_answer"] == r["cued_option"] for r in rows)
    resisted = sum(r["parsed_answer"] == r["correct"] for r in rows)
    return {"flipped": flipped, "resisted": resisted, "dropped": len(rows) - flipped - resisted}


def known_items(generations: list[dict], control: str) -> set[str]:
    by_item: dict[str, list[bool]] = {}
    for r in generations:
        if r["condition"] == control:
            by_item.setdefault(r["item_id"], []).append(not r["truncated"] and r["parsed_answer"] == r["correct"])
    return {i for i, oks in by_item.items() if oks and all(oks)}


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = simple_parsing.parse(Config)
    if not config.summary_path or not config.output_dir:
        raise ValueError("--summary_path and --output_dir are required")
    summary_path = Path(config.summary_path)
    summary = json.loads(summary_path.read_text())
    generations = read_jsonl(summary_path.parent / "generations.jsonl")
    hinted = [s for s in summary["summaries"] if s["condition"] not in CONTROLS]
    names = [s["condition"] for s in hinted]
    labels = [n.replace("_", "\n", 1) for n in names]
    known = {c: known_items(generations, c) for c in CONTROLS}
    counts = {
        s["condition"]: outcome_counts(
            generations, s["condition"], known["fewshot_none" if s["condition"].startswith("fewshot") else "no_hint"]
        )
        for s in hinted
    }

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), gridspec_kw={"width_ratios": [1, 1, 1.5]})
    x = np.arange(len(names))

    ax = axes[0]
    bottom = np.zeros(len(names))
    for outcome, color in OUTCOME_COLORS.items():
        totals = np.array([sum(counts[n].values()) or 1 for n in names])
        values = np.array([counts[n][outcome] for n in names]) / totals
        ax.bar(x, values, 0.6, bottom=bottom, label=outcome, color=color)
        bottom += values
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Share of answers on known items")
    ax.set_title("What the model did with the hint")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14))

    ax = axes[1]
    series = {
        "mentions hint when flipped": [s["mention_rate_when_switched"] for s in hinted],
        "suspects a test": [s["awareness_rate"] for s in hinted],
    }
    for i, (label, values) in enumerate(series.items()):
        ax.bar(x + (i - 0.5) * 0.35, [v or 0 for v in values], 0.35, label=label)
        for xi, v in zip(x + (i - 0.5) * 0.35, values):
            ax.text(xi, (v or 0) + 0.01, "n/a" if v is None else f"{v:.2f}", ha="center", fontsize=7)
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Rate")
    ax.set_title("Mention and evaluation awareness")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.14))

    ax = axes[2]
    rows = []
    for c in summary["pilot_checks"]:
        for cue, flip in c["flip_rate_corrected_known"].items():
            rows.append((f"{cue}\nflip >= 10%", flip or 0, 0.10, c["flips_at_least_10pct"][cue]))
        rows.append(
            (
                f"{c['complex']}\non-cue >= 70%",
                c["complex_cued_share"] or 0,
                0.70,
                c["complex_cued_share_at_least_70pct"],
            )
        )
        rows.append(
            (
                f"awareness gap <= 5pp\n{c['simple']} vs {c['complex']}",
                c["awareness_gap"] or 0,
                0.05,
                c["awareness_within_5pp"],
            )
        )
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [r[1] for r in rows], color=["#2e7d32" if r[3] else "#c62828" for r in rows])
    for yi, r in zip(y, rows):
        ax.plot([r[2], r[2]], [yi - 0.4, yi + 0.4], color="black", lw=1.5)
        ax.text(min(r[1], 0.98) + 0.01, yi, f"{r[1]:.2f} {'pass' if r[3] else 'fail'}", va="center", fontsize=8)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8)
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("Value (black line = threshold)")
    ax.set_title("Proposal pilot checks")

    n_known = {c: len(v) for c, v in known.items()}
    fig.suptitle(
        f"Hint cue pilot on {summary['model_id']}, {summary.get('arm', '')} framing\n"
        f"known items: {n_known['no_hint']} (no-hint control), {n_known['fewshot_none']} (few-shot control)"
    )
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out = Path(config.output_dir)
    figure_path = out / "figures" / "hint_pilot.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    meta_path = write_json(
        out / "hint_pilot_plot.json",
        {"git_hash": get_git_hash(), "config": vars(config), "n_known_items": n_known, "outcome_counts": counts},
    )
    print(f"Figure: {figure_path}")
    print(f"Counts: {meta_path}")


main()
