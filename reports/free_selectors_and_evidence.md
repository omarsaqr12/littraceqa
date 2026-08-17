# Free selector alternatives, and where evidence actually loses

## No free provider beats `gemini-flash-lite` at selection

Paper selection is the binding constraint on the score, and the hosted path
cannot support experimenting on it — `gemini-3.7-flash` exhausts its free daily
quota in roughly fifteen calls. So the selector was pointed at every free model
reachable, with all arms reusing the **same** candidate lists so only the model
varies.

| selector | paper F1 | delta | 95% CI | s/q | errors |
|---|---|---|---|---|---|
| `gemini-flash-lite` | **0.5837** | — | — | — | — |
| cerebras `gpt-oss-120b` | 0.5538 | −0.0299 | [−0.097, +0.042] | 2.8 | 58 |
| groq `openai/gpt-oss-120b` | 0.5415 | −0.0422 | [−0.114, +0.030] | 3.2 | 71 |
| groq `qwen/qwen3.6-27b` | 0.5127 | −0.0710 | [−0.145, +0.010] | 7.0 | 135 |
| cerebras `zai-glm-4.7` | 0.4800 | −0.1037 | [−0.191, −0.015] | 7.6 | 162 |

All four are below the baseline, and a 120B model does not beat a small hosted
one here. **Caveat that limits how far this should be trusted:** the error counts
are high even at a 25 rpm client-side cap, and a failed call falls back to the
top-ranked candidate, so each arm is part model and part fallback. The ordering
is probably real; the magnitudes are not reliable.

An earlier version of this table reported cerebras at 0.5358 with **109** errors,
before rate limiting was added. That number was a rate-limit artefact presented
as a capability result — the same request succeeds on its own. Errors in the
usage counter are now checked before any score is read off a run.

### `gemini-3.7-flash` remains untested, not disproven

The one measurement that exists (paper F1 0.4982, returning exactly one paper on
all 55 questions) was taken with thinking disabled by this client's global
setting. The retest is blocked: 3.7-flash allowed **one** call before returning a
per-day 429. That call agreed with flash-lite, which is not evidence of anything.

A separate bug had to be fixed first: `thinking_budget` was missing from the LLM
cache key, so a thinking-on run replayed thinking-off responses and reported a
score identical to six decimals. That reads as "the variable had no effect" when
the truth is "the variable was never tested."

## Where evidence loses, decomposed

Validation, v9 config. Gold has 130 evidence items; we emit 69.

| outcome | count |
|---|---|
| gold item we emitted nothing for | **105** |
| exact match | 25 |
| wrong paper | 19 |
| right paper + type, **wrong page** | 18 |
| right paper, wrong `source_type` | 6 |
| right paper + type + page, wrong object id | 1 |

Only 36% of what we emit is exact. Of the 44 wrong items, 19 (43%) are on a paper
that is not gold — unfixable except by paper selection. The other **25 have the
right paper and a wrong locator**, and those are the reader's to win.

Two things follow:

* **Recall dominates.** 105 unmatched gold items against 69 emitted. Most of that
  is papers we never selected, which is the same paper-selection constraint
  again — evidence recall is bounded by `paper_recall × locator_accuracy`.
* **Page is the failure mode, not object id.** 18 of the 25 addressable errors are
  right-paper-right-type-wrong-page, against 1 wrong object id. E4 attributes
  ~27% of page disagreement to edition differences we cannot fix, so some of
  these 18 are ours and some are not; the split is not separable with the data
  available.

This is why padding evidence did not pay (E5: recall +0.032, precision −0.028).
The second locator the reader offers is drawn from the same distribution as the
first, and the first is right half the time on a correctly-selected paper.
