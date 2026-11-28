---
title: "Withheld or Never Computed? Sorting Unmentioned Hint Influence in Reasoning Models"
---

**Maanasa Srikrishna**, [co-contributor names]

[email], [co-contributor emails]

## Abstract

When a hint changes a reasoning model's answer but its chain of thought never mentions it, the model may be
concealing the hint or may never have computed it reportably. We aim to tell the two apart. Midterm
work on hint cues shows explicit hints are almost always mentioned: 2 unmentioned flips in 334 across four
models. A redesigned "textbook" hint draws far less test suspicion and gives the first unmentioned flips, up to
17% on one model. No cue pair yet passes every pilot check.

## Introduction

Chain-of-thought (CoT) monitoring is a useful safety tool only if the CoT reflects what drives behaviour. Hint studies show it often does not: models switch to a hinted answer without mentioning the
hint [1], [2]. Under **concealment**, the model represents the hint and leaves it out; under **absent computation**,
the hint acts through processing that never reaches the trace. Elicitation could fix the first; only training
the second.

**Research question.** When a cue changes a model's answer and the trace does not mention it, was the cue
available for the model to report?

The project sorts unmentioned cases into three bins (withheld, represented but not reportable, absent) using
probes and elicitation. This report covers hint cues. Contributions so far:

1. Evidence across four hosted models and a validation pilot that explicit hints are almost always mentioned.
2. A pilot pipeline measuring flip rate, mention and evaluation awareness per cue.
3. A cue redesign that lowers awareness and yields the first unmentioned flips.

## Related Work

Turpin et al. [1] showed CoT explanations omit biasing features such as answer-position patterns in few-shot
examples. Chen et al. [2] found reasoning models rarely mention six hint types; their templates are our starting
point. Lanham et al. [3] tested faithfulness by intervening on the CoT, and Korbak et al. [4] argue CoT
monitorability is valuable but fragile. Emmons et al. [5] find models struggle to hide reasoning a task truly
requires, motivating our simple/complex contrast. Sharma et al. [6] document sycophancy, another cue type.
Prior work measures *whether* cues are mentioned; we ask *why* unmentioned cues go unmentioned, case by case.

## Methods

**Data.** Four-option questions from non-arithmetic MMLU subjects [7] and ARC-Challenge [8], in a 300-question
pool (seed 42). Each hint points to a random wrong option, balanced across A to D.

**Models.** Qwen3.8 27B, gpt-oss 20B and gpt-oss 120B, plus DeepSeek V4 Pro and Qwen3.5 27B in an earlier test,
all through OpenRouter at each model's recommended thinking-mode sampling. A validation pilot used Qwen3-8B.

**Cues.** Each cue has a simple version (acted on directly) and a complex version (needs several reasoning
steps). Pairs tested: grader code (`assert answer == "C"`) and decodable variants; an authority statement
versus a computed key `(17 × 3) mod 4`; few-shot answer patterns; and a textbook answer, stated or found by
question number in a list.

**Measures.** Rates use *known* questions, answered correctly without a hint. The corrected flip rate
subtracts chance landings, estimated from switches to other wrong options [2]. A gpt-4.1-mini judge labels
each trace for hint mention and test awareness; it matched 50 hand labels at κ = 1.00 (mention) and 0.92
(attribution). **Pilot checks:** flips ≥ 10%, an awareness gap between versions ≤ 5 points, and for the
complex version ≥ 70% of cue-following answers on the hinted option.

## Results

**Explicit hints are mentioned almost every time.** In the validation pilot, influence without mention appeared
in 0, 0 and 1 of 120 Qwen3-8B questions under three system prompts; privacy framing made no difference.
Across hosted models, metadata-style hints flipped 22–100% of known answers. Only **2 of 334 judged flips** never mentioned the hint (Figure 1, grey).

![Figure 1. Share of flips to the hinted answer whose reasoning never mentions the hint, on known questions,
with 95% exact intervals.](../results/analysis/midterm_v1/figures/fig1_unmentioned_share.png)

**The proposal's cue pair fails the pilot on Qwen3.8 27B.** The computed key flipped 93% of answers, but 90%
of traces suspected a test, often treating the key as an order. The authority cue flipped only 6%, and few-shot
patterns none.

**A shared-source redesign lowers awareness** (Figure 2). Both versions come from a textbook's answer section:
the simple one states the answer, the complex one requires a lookup.

| Model | Flip (simple / complex) | Awareness | Pilot checks |
|---|---|---|---|
| gpt-oss 20B | 32% / 31% | 6% / 9% | all pass |
| gpt-oss 120B | 45% / 14% | 3% / 10% | awareness gap fails |
| Qwen3.8 27B | 34% / 71% | 20% / 40% | awareness gap fails |

![Figure 2. Corrected flip rate against evaluation awareness for each cue candidate on three
models.](../results/analysis/midterm_v1/figures/fig2_awareness_vs_flip.png)

Textbook cues gave the first unmentioned flips (Figure 1, red): 6/36 on gpt-oss 20B, 3/65 on Qwen3.8, 2/33 on
gpt-oss 120B.

**Negative results.** Qwen3.5 traces were scrambled in 42% of samples where the model quoted `<think>` tags
from an old system prompt, since removed. Round-two data are partial: credit ran out, losing 54 Qwen3.8 lookup
answers and about 200 judge labels per gpt-oss model.

## Discussion

Explicit hints leave nothing to classify: models follow or resist them openly. Silence appears only when a hint
reads as ordinary context rather than a planted test, consistent with (but not proof of) evaluation awareness
driving disclosure. Surprisingly, the computed key's puzzle-like encoding signalled a test, so it measured
realism as much as computation.

**Limitations.** 50 questions × 2 samples cannot resolve a 5-point gap: at a true 20% in both versions, chance
exceeds it about 38% of the time. Trace-based awareness misses unverbalized suspicion. Unmentioned counts are
small and partly from partial runs.

**Future work.**

1. An automated search over cue variants scored on awareness, realism (rated by Qwen3.8) and flip rate,
   confirmed on held-out questions with four samples.
2. Scaling to 3,000 questions per cue type to reach 50 unmentioned cases per cell.
3. Probes and elicitation on the resulting pool.

## Conclusion

Current reasoning models almost always mention explicit hints, so such hints cannot separate concealment
from absent computation. Realistic hints lower evaluation awareness and yield the first unmentioned flips.
A cue pair that is realistic, effective and equally unsuspicious in both versions is the next critical step.

## References

[1] M. Turpin, J. Michael, E. Perez, and S. R. Bowman, "Language models don't always say what they think:
Unfaithful explanations in chain-of-thought prompting," in *Proc. NeurIPS*, 2023.

[2] Y. Chen *et al.*, "Reasoning models don't always say what they think," arXiv:2505.05410, 2025.

[3] T. Lanham *et al.*, "Measuring faithfulness in chain-of-thought reasoning," arXiv:2307.13702, 2023.

[4] T. Korbak *et al.*, "Chain of thought monitorability: A new and fragile opportunity for AI safety,"
arXiv:2507.11473, 2025.

[5] S. Emmons *et al.*, "When chain of thought is necessary, language models struggle to evade monitors,"
arXiv:2507.05246, 2025.

[6] M. Sharma *et al.*, "Towards understanding sycophancy in language models," in *Proc. ICLR*, 2024.

[7] D. Hendrycks *et al.*, "Measuring massive multitask language understanding," in *Proc. ICLR*, 2021.

[8] P. Clark *et al.*, "Think you have solved question answering? Try ARC, the AI2 reasoning challenge,"
arXiv:1803.05457, 2018.
