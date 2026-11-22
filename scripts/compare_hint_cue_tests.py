# puts finished hint cue test runs from several models side by side, as one table and one figure per rate.
# uv run -m scripts.compare_hint_cue_tests --summary_paths results/raw/hint_cue_test_gptoss_v2/summary.json,results/raw/hint_cue_test_deepseek_v4_pro_v1/summary.json,results/raw/hint_cue_test_qwen3_5_27b_v1/summary.json --output_dir results/analysis/hint_cue_test_models_v1 --seed 42

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import simple_parsing

from src.utils.io import get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)

RATES = ("switch_rate", "resist_rate", "mention_rate_when_switched", "unmentioned_switch_rate")


@dataclass
class Config:
    summary_paths: str = ""  # comma separated summary.json files from scripts.run_hint_cue_test
    output_dir: str = ""
    seed: int = 42


def resisted_unmentioned(generations_path: Path) -> dict[str, dict[str, int]]:
    """the resisted set split by mention, per hint. a resisted trace that never mentions the hint may not
    have registered it, which matters for using the resisted set as the probes' control."""
    rows = [
        r for r in read_jsonl(generations_path) if r["variant"] == "V1" and r.get("judge_ok") and not r["truncated"]
    ]
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["parsed_answer"] != r["correct"]:
            continue
        counts = out.setdefault(r["condition"], {"n_resisted": 0, "n_resisted_unmentioned": 0})
        counts["n_resisted"] += 1
        counts["n_resisted_unmentioned"] += not r["mentions_cue"]
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = simple_parsing.parse(Config)
    if not config.summary_paths or not config.output_dir:
        raise ValueError("--summary_paths and --output_dir are required")

    models = []
    for path in map(Path, config.summary_paths.split(",")):
        summary = json.loads(path.read_text())
        resisted = resisted_unmentioned(path.parent / "generations.jsonl")
        hinted = [
            s | resisted.get(s["condition"], {"n_resisted": 0, "n_resisted_unmentioned": 0})
            for s in summary["summaries"]
            if s["condition"] != "no_hint"
        ]
        no_hint = next(s for s in summary["summaries"] if s["condition"] == "no_hint")
        models.append(
            {
                "model_id": summary["model_id"],
                "summary_path": str(path),
                "no_hint_correct_rate": no_hint["correct_rate"],
                "hints": hinted,
            }
        )

    out = Path(config.output_dir)
    result_path = write_json(
        out / "hint_cue_test_models.json", {"git_hash": get_git_hash(), "config": vars(config), "models": models}
    )

    cues = [h["condition"] for h in models[0]["hints"]]
    fig, axes = plt.subplots(1, len(RATES), figsize=(4 * len(RATES), 4), sharey=True)
    width = 0.8 / len(models)
    x = np.arange(len(cues))
    for ax, rate in zip(axes, RATES):
        for i, m in enumerate(models):
            values = [next(h for h in m["hints"] if h["condition"] == c).get(rate) or 0 for c in cues]
            ax.bar(x + (i - (len(models) - 1) / 2) * width, values, width, label=m["model_id"])
        ax.set_xticks(x, [c.removeprefix("grader_") for c in cues])
        ax.set_title(rate.replace("_", " ").capitalize())
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("Rate")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Hint cue test across models, wrong option hinted (grader framing)")
    fig.tight_layout()
    figure_path = out / "figures" / "hint_cue_test_models.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)

    print(f"Results: {result_path}")
    print(f"Figure: {figure_path}")
    print(
        f"{'model':<26} {'hint':<8} {'switch':>7} {'resist':>7} {'mention|sw':>11} {'unment sw':>10} {'resisted':>9} {'resist unment':>14}"
    )
    for m in models:
        for h in m["hints"]:
            print(
                f"{m['model_id']:<26} {h['condition'].removeprefix('grader_'):<8} {h['switch_rate']!s:>7} {h['resist_rate']!s:>7} "
                f"{h['mention_rate_when_switched']!s:>11} {h['n_unmentioned_switched']!s:>10} {h['n_resisted']!s:>9} {h['n_resisted_unmentioned']!s:>14}"
            )


main()
