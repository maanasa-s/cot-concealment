# cue_search_v1 notes

## Iteration 1 (261128): realism, and the template finding

- Tried: realism stage on authority / computed key (anchor) and on a bare no-hint prompt, json template.
- Happened: the anchor ranks as expected (computed key 1.0 < authority 1.7), but the **bare question scores 1.3**.
  Qwen3.8's reasons blame the json answer-format line ("typical of an AI evaluation prompt"). With that template no
  cue can pass realism > 5.
- Tried: two student-style templates. `casual` and `casual_after` (with an "Answer: X" line) reach 3.7; `casual_free`
  (no format line) reaches **8.5** on the bare question.
- Under `casual_free` all four textbook pairs pass realism (7.1 to 9.2); the computed key still fails (1.3).
- Next: screen the four textbook pairs; check that answers still parse without a format line.
