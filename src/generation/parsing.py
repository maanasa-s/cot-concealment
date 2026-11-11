# splits a qwen3 generation into think and content blocks on the terminator token, and locates
# judge evidence spans inside the think text.

import difflib
import re

from src.config import THINK_END_TOKEN_ID

ANS = re.compile(r'"answer"\s*=?\s*:?\s*"?([ABCD])"?')

_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def strip_think_open(text: str) -> str:
    """qwen3 emits the opening <think> tag itself rather than the chat template injecting it, so it
    lands inside the decoded block. left in, it reaches the judge and doubles up in the prefill ablation."""
    text = text.strip()
    return text[len("<think>") :].strip() if text.startswith("<think>") else text


def split_trace(token_ids: list[int], tok, think_end: int = THINK_END_TOKEN_ID) -> tuple[str | None, str, bool]:
    """returns (think_text, content_text, truncated). splits on the first terminator so a trace that
    echoes the token inside its content block does not pull content into the think block."""
    if think_end not in token_ids:
        return None, strip_think_open(tok.decode(token_ids)), True
    idx = token_ids.index(think_end)
    return strip_think_open(tok.decode(token_ids[:idx])), tok.decode(token_ids[idx + 1 :]).strip(), False


def parse_answer(content: str) -> tuple[str | None, bool]:
    m = ANS.search(content)
    return (m.group(1), True) if m else (None, False)


# the model often ends in prose ("**Answer:** A", "The answer is A.") instead of the requested json
# field. those are real answers and dropping them biases the modal counts, so they are recovered from
# the tail only, where a final answer statement lives, and the method is recorded per generation.
# deliberately not re.I: the filler between "answer" and the letter may be any lowercase words, but the
# answer letter itself is always upper case, so [^A-D] stops the match running past a real candidate.
FINAL_ANS = re.compile(r"(?:[Aa]nswer|[Cc]hoice)\b[^A-D\n]{0,20}\(?([ABCD])\)?\b")


BARE_ANS = re.compile(r"""[\s"'`*()\[\]{}.:]*([ABCD])[\s"'`*()\[\]{}.:]*""")


# the first line must be nothing but an answer statement, so "the answer might be A but..." is not read.
LEAD_ANS = re.compile(r"""[*_#\s]*(?:[Ff]inal\s+)?[Aa]nswer[*_\s]*[:=\-]?[*_\s]*\(?([ABCD])\)?[*_.\s]*""")


def parse_answer_robust(content: str, tail_chars: int = 300) -> tuple[str | None, bool, str]:
    answer, ok = parse_answer(content)
    if ok:
        return answer, True, "json"
    hits = FINAL_ANS.findall(content[-tail_chars:])
    if hits:
        return hits[-1].upper(), True, "prose"
    # hosted models sometimes reply with the letter alone, or lead with "**Answer**: C" before a long explanation.
    bare = BARE_ANS.fullmatch(content.strip())
    if bare:
        return bare.group(1), True, "bare"
    lead = LEAD_ANS.fullmatch(content.strip().split("\n", 1)[0].strip())
    if lead:
        return lead.group(1), True, "lead"
    return None, False, "none"


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """lowercases, straightens punctuation and collapses whitespace, keeping a map back to original offsets."""
    chars: list[str] = []
    offsets: list[int] = []
    prev_space = False
    for i, ch in enumerate(text.translate(_PUNCT)):
        if ch.isspace():
            if prev_space or not chars:
                continue
            chars.append(" ")
            offsets.append(i)
            prev_space = True
        else:
            chars.append(ch.lower())
            offsets.append(i)
            prev_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return "".join(chars), offsets


def normalize_span(text: str) -> str:
    return _normalize_with_map(text)[0]


def find_span(think_text: str, span: str, min_ratio: float = 0.85) -> int | None:
    """character offset into think_text where span begins, or None if it cannot be located.
    judges return spans with renormalized whitespace and quotes, so byte equality is not enough."""
    if not span or not think_text:
        return None
    haystack, offsets = _normalize_with_map(think_text)
    needle, _ = _normalize_with_map(span)
    if not needle:
        return None
    pos = haystack.find(needle)
    if pos != -1:
        return offsets[pos]
    matcher = difflib.SequenceMatcher(None, haystack, needle, autojunk=False)
    block = matcher.find_longest_match(0, len(haystack), 0, len(needle))
    if block.size / len(needle) < min_ratio:
        return None
    return offsets[max(0, block.a - block.b)]
