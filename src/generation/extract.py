# llm answer extraction for free-form replies. prompts without an answer-format line read as more realistic, but the
# model then states its answer anywhere in prose, often first, which the tail-reading regex rules miss.

import re

EXTRACT_SYSTEM = """You read a reply to a four-option multiple choice question (options A, B, C, D) and report which
single option the reply finally chooses as its answer. If it chooses none, or more than one, report NONE.
Reply with exactly one token: A, B, C, D or NONE."""

EXTRACT_USER_TEMPLATE = """Question:
{question}

A) {option_a}
B) {option_b}
C) {option_c}
D) {option_d}

Reply:
<reply>
{reply}
</reply>"""

LETTER_RE = re.compile(r"^\W*([ABCD]|NONE)\W*$")


def build_extract_messages(question: str, options: dict[str, str], reply: str) -> list[dict]:
    user = EXTRACT_USER_TEMPLATE.format(
        question=question,
        option_a=options["A"],
        option_b=options["B"],
        option_c=options["C"],
        option_d=options["D"],
        reply=reply,
    )
    return [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}]


def parse_extracted(text: str | None) -> str | None:
    """a letter, or None for NONE or anything that is not exactly one token."""
    match = LETTER_RE.match((text or "").strip())
    return match.group(1) if match and match.group(1) != "NONE" else None
