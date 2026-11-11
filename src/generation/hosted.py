# hosted generation through openrouter, for the behaviour-only models. writes the same Generation fields
# as the vllm path so the filter, cue test and judge read either without branching.

import asyncio
import logging
import os

from src.generation.engine import Generation
from src.generation.parsing import parse_answer_robust
from src.utils.cache import cached_chat_response

LOGGER = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def openrouter_client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
    )


def hosted_params(max_tokens: int, temperature: float | None = None) -> dict:
    """the provider's own sampling defaults unless a temperature is given; the qwen3 settings in RunConfig are
    that model's recommendations and do not transfer. reasoning is requested explicitly so traces come back."""
    params = {"max_tokens": max_tokens, "extra_body": {"reasoning": {"enabled": True}}}
    if temperature is not None:
        params["temperature"] = temperature
    return params


def chat_messages(system: str, user_message: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user_message}]


def reasoning_text(message: dict) -> str | None:
    """openrouter returns the reasoning as message.reasoning; some providers only fill reasoning_details."""
    if message.get("reasoning"):
        return message["reasoning"].strip()
    details = message.get("reasoning_details") or []
    text = "".join(d.get("text") or d.get("summary") or "" for d in details)
    return text.strip() or None


def to_hosted_generation(raw: dict, sample_idx: int) -> Generation:
    choice = raw["choices"][0]
    message = choice["message"]
    content = (message.get("content") or "").strip()
    think = reasoning_text(message)
    usage = raw.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    parsed_answer, parse_ok, parse_method = parse_answer_robust(content)
    return Generation(
        sample_idx=sample_idx,
        think_text=think,
        content_text=content,
        parsed_answer=parsed_answer,
        parse_ok=parse_ok,
        parse_method=parse_method,
        # an empty content block means the budget ran out inside the reasoning, the same case the vllm path
        # flags by a missing think terminator.
        truncated=choice.get("finish_reason") == "length" or not content,
        n_think_tokens=details.get("reasoning_tokens") or 0,
        n_total_tokens=usage.get("completion_tokens") or 0,
        finish_reason=choice.get("finish_reason"),
    )


async def generate_hosted(
    client,
    model: str,
    message_lists: list[list[dict]],
    n_samples: int,
    cache_dir: str,
    max_concurrent: int = 20,
    **params,
) -> list[list[Generation | None]]:
    """one call per sample, since openrouter does not honour n on every provider. a sample whose call still
    fails after retries comes back as None and is logged, so one bad request does not end a long run."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def one(messages: list[dict], sample_idx: int) -> Generation:
        async with semaphore:
            raw = await cached_chat_response(client, model, messages, cache_dir, sample_idx=sample_idx, **params)
        return to_hosted_generation(raw, sample_idx)

    calls = [one(m, s) for m in message_lists for s in range(n_samples)]
    results = await asyncio.gather(*calls, return_exceptions=True)
    failed = [r for r in results if isinstance(r, BaseException)]
    for r in failed:
        LOGGER.error(f"hosted generation failed after retries: {type(r).__name__}: {r}")
    # every call failing is a bug or a dead key, not a flaky network, so it crashes.
    if failed and len(failed) == len(results):
        raise failed[0]
    if failed:
        LOGGER.error(
            f"{len(failed)} of {len(results)} hosted samples failed; rerun the same command to fill them from cache"
        )
    flat = [None if isinstance(r, BaseException) else r for r in results]
    return [flat[i : i + n_samples] for i in range(0, len(flat), n_samples)]


def reasoning_missing_rate(generations: list[Generation]) -> float:
    return round(sum(g.think_text is None for g in generations) / len(generations), 4) if generations else 0.0
