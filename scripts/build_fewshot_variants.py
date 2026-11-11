# builds the few-shot position cue variants: a fixed set of solved examples drawn from the pool, prepended to every
# remaining item with their answers balanced on V0 and all at the cued letter on V1 to V3. also writes a preview of
# rendered prompts for checking the cue by hand in a chat interface before any generation.
# uv run -m scripts.build_fewshot_variants --pool_path data/processed/pool_seed42.jsonl --output_dir data/processed/fewshot_v1 --n_examples 8 --max_example_chars 400 --seed 42

import logging
from dataclasses import dataclass
from pathlib import Path

import simple_parsing

from src.data.fewshot import attach_examples, balanced_letters, select_examples
from src.data.items import Item, build_variants
from src.generation.prompts import ARMS, FEWSHOT_CUE, build_user_message
from src.utils.io import append_jsonl, get_git_hash, read_jsonl, write_json

LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    pool_path: str = ""
    output_dir: str = ""
    n_examples: int = 8
    # 400 chars keeps 8 examples near 700 tokens, so the longest test question plus a 6144 token trace
    # still fits max_model_len 8192.
    max_example_chars: int = 400
    n_preview: int = 10
    preview_arm: str = "C3_neutral_private"
    seed: int = 42


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = simple_parsing.parse(Config)
    if not config.pool_path or not config.output_dir:
        raise ValueError("--pool_path and --output_dir are required")

    out = Path(config.output_dir)
    variants_path = out / f"variants_fewshot_seed{config.seed}.jsonl"
    if variants_path.exists():
        raise FileExistsError(f"{variants_path} exists; the write appends, so use a new output_dir")

    items = [Item(**r) for r in read_jsonl(config.pool_path)]
    examples = select_examples(items, config.n_examples, config.max_example_chars, config.seed)
    example_ids = {ex.item_id for ex in examples}
    v0_letters = balanced_letters(config.n_examples, config.seed)

    # an example item is never also a test item, or the model would see its answer key in the prompt.
    test_items = [it for it in items if it.item_id not in example_ids]
    rows = [attach_examples(v, examples, v0_letters) for it in test_items for v in build_variants(it, config.seed)]
    append_jsonl(variants_path, rows)
    LOGGER.info(f"{len(rows)} variant rows over {len(test_items)} items, {len(examples)} examples held out")

    preview_rows = [r for r in rows if r["variant"] in ("V0", "V1")][: 2 * config.n_preview]
    preview = "".join(
        f"## {r['item_id']} {r['variant']}  correct={r['correct']} cued={r['cued_option']}\n\n"
        f"System:\n\n```\n{ARMS[config.preview_arm]}\n```\n\nUser:\n\n```\n"
        f"{build_user_message(r['question'], r['options'], r['cued_option'], FEWSHOT_CUE, r['fewshot_examples'])}\n```\n\n"
        for r in preview_rows
    )
    preview_path = out / "fewshot_chat_preview.md"
    preview_path.write_text(f"# Few-shot position cue: prompts for a manual chat check\n\n{preview}")

    meta_path = write_json(
        out / f"variants_fewshot_seed{config.seed}_meta.json",
        {
            "git_hash": get_git_hash(),
            "config": vars(config),
            "cue_name": FEWSHOT_CUE,
            "example_item_ids": [ex.item_id for ex in examples],
            "example_sources": [ex.source for ex in examples],
            "example_original_correct": [ex.correct for ex in examples],
            "v0_letters": v0_letters,
            "n_test_items": len(test_items),
            "n_variant_rows": len(rows),
        },
    )

    print(f"Variants: {variants_path} ({len(rows)} rows, {len(test_items)} items)")
    print(f"Metadata: {meta_path}")
    print(f"Chat preview: {preview_path}")
    print(
        f"Next: uv run -m scripts.run_filter --variants_path {variants_path} --output_dir results/raw/filter_fewshot_probe "
        f"--model_id Qwen/Qwen3-8B --cue_name {FEWSHOT_CUE} --num_tasks 30 --seed {config.seed}"
    )


main()
