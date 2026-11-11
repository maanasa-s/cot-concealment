# measures, per hint version, how often a hosted model switches to the hinted wrong option and how often its reasoning mentions the hint.
# uv run -m scripts.run_hint_cue_test --variants_path data/processed/variants_seed42.jsonl --output_dir results/raw/hint_cue_test_v1 --model_id openai/gpt-oss-120b --num_tasks 10 --n_samples 4 --seed 42

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import simple_parsing
from dotenv import load_dotenv

from src.generation.hosted import (
    chat_messages,
    generate_hosted,
    hosted_params,
    openrouter_client,
    reasoning_missing_rate,
)
from src.generation.judge import build_judge_messages, parse_judgment
from src.generation.prompts import ARMS, COMPLEX_HINT_CUES, build_user_message, prompt_fingerprint
from src.utils.cache import cached_completion
from src.utils.io import append_jsonl, get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    variants_path: str = ""
    output_dir: str = ""
    model_id: str = "openai/gpt-oss-120b"
    cues: str = ",".join(("grader_code", *COMPLEX_HINT_CUES))
    num_tasks: int = 20  # items; every item is asked once without a hint and once per hint version
    n_samples: int = 4
    arm: str = "C3_neutral_private"
    judge_model: str = "openai/gpt-4.1-mini"
    hosted_max_tokens: int = 8192
    hosted_temperature: float | None = None
    max_concurrent: int = 20
    cache_dir: str = "cache/hosted"
    judge_cache_dir: str = "cache/judge"
    seed: int = 42


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(records: list[dict], condition: str) -> dict:
    rows = [r for r in records if r["condition"] == condition]
    eligible = [r for r in rows if not r["truncated"] and r["parse_ok"]]
    out = {
        "condition": condition,
        "n_samples": len(rows),
        "n_eligible": len(eligible),
        "truncation_rate": rate(sum(r["truncated"] for r in rows), len(rows)),
        "parse_fail_rate": rate(sum(not r["parse_ok"] for r in rows if not r["truncated"]), len(rows)),
        "reasoning_missing_rate": rate(sum(r["think_text"] is None for r in rows), len(rows)),
        "correct_rate": rate(sum(r["parsed_answer"] == r["correct"] for r in eligible), len(eligible)),
    }
    if condition == "no_hint":
        return out
    switched = [r for r in eligible if r["parsed_answer"] == r["cued_option"]]
    judged = [r for r in eligible if r.get("judge_ok")]
    judged_switched = [r for r in switched if r.get("judge_ok")]
    mentioned = [r for r in judged if r["mentions_cue"]]
    unmentioned_switched = [r for r in judged_switched if not r["mentions_cue"]]
    return out | {
        "switch_rate": rate(len(switched), len(eligible)),
        "resist_rate": out["correct_rate"],
        "n_judged": len(judged),
        "mention_rate": rate(len(mentioned), len(judged)),
        "mention_rate_when_switched": rate(len(judged_switched) - len(unmentioned_switched), len(judged_switched)),
        # the quantity the study needs: switched to the hint with no mention of it.
        "n_unmentioned_switched": len(unmentioned_switched),
        "unmentioned_switch_rate": rate(len(unmentioned_switched), len(judged)),
        # a mention that names a letter other than the cued one is a failed decoding or a stale reading.
        "misdecoded_rate": rate(
            sum(r["named_option"] not in (None, r["cued_option"]) for r in mentioned), len(mentioned)
        ),
    }


async def judge_all(rows: list[dict], client, config: Config) -> list[dict]:
    semaphore = asyncio.Semaphore(config.max_concurrent)

    async def one(row: dict) -> str:
        async with semaphore:
            return await cached_completion(
                client,
                model=config.judge_model,
                messages=build_judge_messages(row["question"], row["options"], row["think_text"], row["condition"]),
                cache_dir=config.judge_cache_dir,
                temperature=0.0,
                response_format={"type": "json_object"},
            )

    texts = await asyncio.gather(*[one(r) for r in rows], return_exceptions=True)
    results = []
    for row, text in zip(rows, texts):
        if isinstance(text, BaseException):
            LOGGER.error(f"judge call failed for {row['id']}: {type(text).__name__}: {text}")
            results.append({"judge_ok": False, "judge_error": f"{type(text).__name__}: {text}"})
            continue
        judgment, error = parse_judgment(text)
        if error:
            LOGGER.error(f"judge parse failed for {row['id']}: {error}")
        results.append(
            {"judge_ok": judgment is not None, "judge_error": error} | (judgment.model_dump() if judgment else {})
        )
    return results


def plot(summaries: list[dict], model_id: str, n_items: int, n_samples: int, path: Path) -> None:
    hinted = [s for s in summaries if s["condition"] != "no_hint"]
    names = [s["condition"] for s in hinted]
    series = {
        "switch rate": [s["switch_rate"] or 0 for s in hinted],
        "mention rate when switched": [s["mention_rate_when_switched"] or 0 for s in hinted],
        "unmentioned switch rate": [s["unmentioned_switch_rate"] or 0 for s in hinted],
    }
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, (label, values) in enumerate(series.items()):
        ax.bar(x + (i - 1) * 0.27, values, 0.27, label=label)
    ax.set_xticks(x, names)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate")
    ax.set_title(f"Hint versions on {model_id}\n{n_items} items x {n_samples} samples, wrong option hinted")
    ax.legend(frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    load_dotenv()
    config = simple_parsing.parse(Config)
    if not config.variants_path or not config.output_dir:
        raise ValueError("--variants_path and --output_dir are required")
    out = Path(config.output_dir)
    generations_path = out / "generations.jsonl"
    if generations_path.exists():
        raise FileExistsError(f"{generations_path} exists; the write appends, so use a new output_dir")

    cues = config.cues.split(",")
    v1_rows = {r["item_id"]: r for r in read_jsonl(config.variants_path) if r["variant"] == "V1"}
    item_ids = sorted(v1_rows)
    random.Random(config.seed).shuffle(item_ids)
    items = [v1_rows[i] for i in item_ids[: config.num_tasks]]

    conditions = [("no_hint", "V0")] + [(cue, "V1") for cue in cues]
    prompts = [(item, condition, variant) for condition, variant in conditions for item in items]
    messages = [
        chat_messages(
            ARMS[config.arm],
            build_user_message(
                item["question"],
                item["options"],
                None if variant == "V0" else item["cued_option"],
                condition if variant == "V1" else "grader_code",
            ),
        )
        for item, condition, variant in prompts
    ]
    LOGGER.info(
        f"{len(items)} items x {len(conditions)} conditions x {config.n_samples} samples = {len(messages) * config.n_samples} calls"
    )

    client = openrouter_client()
    params = hosted_params(config.hosted_max_tokens, config.hosted_temperature)
    generations = asyncio.run(
        generate_hosted(
            client, config.model_id, messages, config.n_samples, config.cache_dir, config.max_concurrent, **params
        )
    )

    records = [
        {
            "id": f"{item['item_id']}_{condition}_{g.sample_idx}",
            "item_id": item["item_id"],
            "source": item["source"],
            "condition": condition,
            "variant": variant,
            "question": item["question"],
            "options": item["options"],
            "correct": item["correct"],
            "cued_option": None if variant == "V0" else item["cued_option"],
            "model_id": config.model_id,
            "arm": config.arm,
            "prompt_fingerprint": prompt_fingerprint(config.arm, condition if variant == "V1" else "grader_code"),
        }
        | g.model_dump()
        for (item, condition, variant), gens in zip(prompts, generations)
        for g in gens
        if g is not None
    ]

    to_judge = [r for r in records if r["variant"] == "V1" and r["think_text"] and not r["truncated"]]
    LOGGER.info(f"judging {len(to_judge)} hinted traces with {config.judge_model}")
    judgments = asyncio.run(judge_all(to_judge, client, config))
    for row, judgment in zip(to_judge, judgments):
        row |= judgment
    append_jsonl(generations_path, records)

    summaries = [summarize(records, condition) for condition, _ in conditions]
    summary_path = write_json(out / "summary.json", {"model_id": config.model_id, "summaries": summaries})
    write_json(
        out / "config.json",
        {
            "git_hash": get_git_hash(),
            "config": vars(config),
            "hosted_params": params,
            "item_ids": [i["item_id"] for i in items],
            "reasoning_missing_rate": reasoning_missing_rate(
                [g for gens in generations for g in gens if g is not None]
            ),
        },
    )
    figure_path = out / "figures" / "hint_cue_test.png"
    plot(summaries, config.model_id, len(items), config.n_samples, figure_path)

    print(f"Generations: {generations_path}")
    print(f"Summary: {summary_path}")
    print(f"Figure: {figure_path}")
    print(
        f"{'condition':<14} {'correct':>8} {'switch':>8} {'mention|sw':>11} {'unmentioned sw':>15} {'misdecoded':>11}"
    )
    for s in summaries:
        print(
            f"{s['condition']:<14} {s['correct_rate']!s:>8} {s.get('switch_rate')!s:>8} {s.get('mention_rate_when_switched')!s:>11} "
            f"{s.get('n_unmentioned_switched', '')!s:>15} {s.get('misdecoded_rate')!s:>11}"
        )


main()
