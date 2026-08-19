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

---

## Cerebras gpt-oss-120b as reader + selector + solver (paid credits): abandoned

With \$5 of paid Cerebras credit the quota ceiling disappears — measured cost is
~\$0.001 per call, so a full 71-question reader run is **\$0.21** and \$5 buys ~23
of them. Cost was never the constraint. Time and rate limits were.

Final validation attempt, gpt-oss-120b carrying selection, reading and answer
synthesis with no Gemini in the path:

| component | gemini (v9 config) | cerebras | delta |
|---|---|---|---|
| paper F1 | 0.5837 | **0.6012** | +0.0175 |
| evidence F1 | 0.3197 | 0.1782 | −0.1415 |
| MC | 0.5854 | 0.4878 | −0.0976 |
| table row F1 | 0.5338 | 0.2792 | −0.2546 |
| table cell acc | 0.2611 | 0.0519 | −0.2092 |
| **overall** | **0.4545** | 0.3508 | **−0.1037** |

**This is not a clean capability measurement and should not be cited as one.** The
run logged **81 errors against 67 successful calls** and left 30 of 55 questions
with empty evidence. Paper F1 — the one stage that completed reliably — actually
*improved* (+0.0175), which is the shape you would expect if the reader was
failing rather than reading badly.

Three provider-specific faults had to be fixed to get even this far, each of
which produced a plausible-looking zero rather than an error:

1. `chat_template_kwargs` is a llama.cpp extension; Cerebras 400s on it. The
   first attempt returned evidence 0.0, table 0.0, 55/55 empty evidence.
2. `gpt-oss-120b` emits `reasoning_tokens` before the JSON body, so
   `max_tokens=512` truncated every answer into "no parseable JSON".
3. Gemini quota died mid-run and the selector silently fell back to the top
   candidate on 40 of 55 questions — paper F1 0.4982, exactly the fallback value.

The unresolved one is rate limiting. Cerebras caps requests per minute even on
paid credit, and the reader and the selector/solver hold **separate** limiters
against one shared quota, so their sum exceeds the cap. Dropping to 6 rpm each
still produced 81 errors and pushed the run to 26.5s/question. Fixing it properly
means a shared limiter across clients, which is a small change but not one worth
making with hours left on the clock.

**Abandoned rather than disproven.** A 120B model reading page text with an
enumerated locator list is a reasonable architecture and this says little about
it. What it does say: swapping the provider under three stages at once, on
deadline day, was the wrong-sized change to attempt.

---

## Retraction: the Cerebras selector is better, and the earlier table was measuring rate limits

The section above concluded that no free provider beats `gemini-flash-lite` at
selection. **That conclusion was an artefact and is withdrawn.** Re-measured as a
single-stage swap — Cerebras carrying selection only, Gemini left in place for
reading and synthesis, both arms run in the same session with identical flags:

| component | gemini selector | cerebras `gpt-oss-120b` | delta |
|---|---|---|---|
| paper F1 | 0.5984 | **0.6182** | +0.0198 |
| evidence F1 | 0.3240 | **0.3421** | +0.0181 |
| MC | 0.5854 | **0.6098** | +0.0244 |
| table row F1 | 0.5338 | **0.5797** | +0.0459 |
| table cell acc | 0.2838 | **0.3525** | +0.0687 |
| **overall** | **0.4634** | **0.4914** | **+0.0280** |

Both arms: 1 error, 0/55 empty evidence. Paper selection differs on 12 of 55
questions, and every downstream component moves in the same direction — the shape
you expect when selection improves, because selection multiplies into everything.

The earlier table scored this same model at 0.5538 against a 0.5837 baseline, a
**loss** of 0.0299. Two faults produced that inversion, and both were mine:

1. **58 errors on a 25 rpm cap.** Every failed selector call falls back to the
   top-ranked candidate, so the arm was part model and part BM25. The report said
   as much and still published the ordering as "probably real." It was not real;
   it was inverted. At 10 rpm the same model errors once.
2. **The baseline was quoted from an older report, not re-run.** The control
   re-measured in the same session scores **0.4634**, not the 0.4545 on file —
   0.0089 of apparent gain was drift between sessions. This repo has a written
   rule against exactly this (`README.md`, "both arms of an A/B must come from
   the same session"), added after the local-reader reversal, and I broke it
   again here.

**The honest caveat on the +0.0280.** Paired bootstrap over 55 questions, 4000
reps: **95% CI [−0.0121, +0.0806], P(delta > 0) = 0.886.** The interval spans
zero and is 3.3× the width of the effect. That is the same regime as the three
changes that were decided inside a wide CI and returned zero or worse on test.
So this is a *promising point estimate, not a demonstrated gain*, and it is
reported as one.

It is still worth submitting, for a reason independent of the statistics: the
leaderboard keeps the best score per team, so an additional entry has bounded
downside. v11 (0.5493) and v12 (0.5413) were both submitted after v9 and rank 7
at 0.5519 held.

### What the abandoned three-stage run actually showed

Read back with this result in hand, the earlier all-Cerebras attempt was not
evidence against the model at all. Paper F1 rose (+0.0175) while evidence and
table collapsed, and the run logged 81 errors — one stage was working and two
were starving on a shared rate limit. The correct inference was available at the
time: *split the swap and re-measure the stage that improved*. Instead the whole
architecture was abandoned on deadline day. The lesson is not about Cerebras. It
is that a multi-stage swap cannot be interpreted, so it should never be the first
experiment.

## Full-text indexing does not pay on the test regime

Candidate recall is capped at 71% by title+abstract reachability, and full text
lifts reachability to 89%. That 18-point gap was the largest unexploited lever on
file. It is **not worth building**, and the reason is a two-minute measurement
that should have been taken before the lever was ever written down as a
priority — where the question's mention of a gold paper actually lives, split by
task family:

| task family | n | in title/abstract | body only | nowhere |
|---|---|---|---|---|
| `hidden_source_single_paper` (test-like) | 24 | 23 (96%) | **1 (4%)** | 0 |
| `multi_paper` (cluster) | 100 | 65 (65%) | 21 (21%) | 14 (14%) |

The entire 18-point gap lives in `multi_paper`, which is 53% of validation and
**absent from the test split**. On the test-like family, title+abstract already
reaches 96% of gold papers and a full-text index would move at most one question
in twenty-four. The lever was real and pointed at the wrong split.

### CORRECTION: the "does not transfer" section below was computed with the wrong key

The section that followed here claimed the Cerebras selector chose identical
papers on **0 of 71** test questions, and concluded that the validation gain
transfers as exactly zero. **That was wrong.** The comparison read
`record["paper_ids"]`, a key these prediction files do not contain — the evaluator
reads papers from `gold_papers`. Both sides of the diff were therefore `None`, and
`None == None` produced a perfect-agreement result that was really a measurement of
nothing.

Corrected:

| comparison | papers differ | evidence differs |
|---|---|---|
| v9 (gemini selector) vs v13 (cerebras selector) | **26/71** | 29/71 |

Emitted set sizes also differ: v9 is `{1: 32, 2: 36, 3: 3}`, v13 is
`{1: 40, 2: 28, 3: 3}` — the Cerebras selector hedges less. So v13 is a real
change on the test split, not a re-draw of v9, and the selector-saturation story
built on the 0/71 figure is withdrawn along with it.

The claim survives only in weakened form: selector agreement does rise with how
identifiable the paper is (48% on validation cluster questions, 88% on
named-paper), but the test figure that made it look absolute was an artefact.

**Third instance of the same class of bug this session.** A silent wrong-key read,
like a silent rate-limit fallback, returns a plausible number rather than an
error. Both times the number was clean enough to publish and both times it was
measuring nothing. Any diff between two record sets must now assert that the key
it reads is present and non-empty on both sides.

## Where the remaining test headroom actually is

Retrieval is not the constraint on the test-like regime. Rank of the gold paper in
the candidate list, by family (`exp/21`, no API calls):

| family | R@1 | R@20 | R@200 | unreachable |
|---|---|---|---|---|
| `hidden_source_single_paper` (test-like) | 0.846 | **0.962** | 0.962 | 1/26 |
| `multi_paper` (cluster) | 0.100 | 0.533 | 0.658 | 41/120 |

On the test-like family recall is **flat from rank 20 to rank 200**: not one gold
paper sits in ranks 21-200. Widening `llm_shortlist` cannot help, which is
consistent with v11 (shortlist 30) scoring 0.5493 against v9's 0.5519. The
`multi_paper` curve is the one that keeps climbing, and that family is not in the
test set.

So the test constraint is **set size**, not retrieval and not selection. Two
independent bounds pin it down. Given v9's emitted size distribution
`{1: 32, 2: 36, 3: 3}`, the best achievable paper F1 if every test gold set had
size *g* is:

| g | ceiling | verdict against observed 0.7991 |
|---|---|---|
| 1 | 0.8099 | possible, implies 98.7% contains-gold |
| 2 | 0.8413 | possible, implies 95.0% of ceiling |
| 3 | 0.6732 | **impossible** |
| 4 | 0.5545 | **impossible** |

Test gold sets are size 1 or 2. That single fact was available from a scored
submission and an arithmetic identity, with no gold labels and no API calls, and
it was never computed until the last day.

The two surviving hypotheses recommend **opposite** actions, which is why this is
unresolved rather than fixed:

| if test gold size is | trim every set to its first paper | vs current 0.7991 |
|---|---|---|
| 1 | ~0.917 (first-is-gold runs 9/10 on validation) | **+0.118** |
| 2 | 0.6667 (hard ceiling) | **−0.169** |

The question-text cue that would discriminate them does not work: on validation,
"singular" questions average **2.68** gold papers and "plural" ones **3.50**, so
the wording carries no set-size signal. `predict_set_size` is guessing.


## H18 resolved: test gold sets are mostly size 2, and v9's set-size policy is already near-optimal

`test_v14` (v9 with every paper set trimmed to one, evidence and answers
byte-identical) was submitted. **It scored 0.5042 against v9's 0.5519, a loss of
0.0477.** The size-1 hypothesis is dead, and the prediction made before submitting
it — "a drop to ~0.50 means size 2" — was correct.

The bet lost but the measurement paid, because emitting exactly one paper turns the
precision/recall pair into a readout of the gold set sizes:

| v14 metric | value |
|---|---|
| paper precision | 0.84507 |
| paper recall | 0.566901 |
| paper F1 | 0.655869 |

With one paper emitted, precision *is* P(our top pick is gold) = 60 of 71 correct.
If every gold set had size 1, recall would **equal** precision. It is 0.567, so
`recall/precision = 0.671 = mean(1/|gold|)` over those 60. Solving
`n1 + n2/2 = 0.671 × 60` with `n1 + n2 = 60` gives **n1 = 20, n2 = 40**:

* at least **40 of 71 test gold sets (56%) contain two papers**
* our top-ranked pick is correct on **60 of 71** questions

Neither number needed a gold label. Both fall out of one scored submission and an
arithmetic identity, and the same trick would have worked on any run since v2.

### Why the obvious follow-up is wrong

If 56% of gold sets hold two papers and v9 emits two on only 39 of 71, padding the
32 singletons looks free. It is not. Fitting v9's measured 0.7991 under two
hypotheses about the selector's *size* judgement, with P(2nd pick is gold) as the
free parameter:

| hypothesis | fitted P(2nd gold) | reproduced F1 |
|---|---|---|
| selector knows which rows need two papers | 0.68 | 0.7997 ✓ |
| selector's size choice is independent of gold size | 1.00 (maximum) | 0.7805 ✗ |

The independent hypothesis **cannot reach the observed score even with a perfect
second pick.** Only a calibrated selector explains 0.7991. So the 32 singletons are
predominantly genuinely single-gold, and padding them would trade a 1.000 for a
0.667 on roughly 20 questions to chase 12. `preds/test_v15.jsonl` (every set forced
to exactly two) was built and validated, and is **deliberately not submitted** for
this reason.

The same argument predicts `test_v13` is *worse* than v9: its selector emits 40
singletons against v9's 32, moving away from a distribution that is already
calibrated. It is also left unsubmitted.

### Where this leaves the score

Set-size policy is closed — v9 is at or near its optimum. The residual is now
named exactly:

* **11 of 71 questions have a wrong top-ranked paper.** This is selection, and two
  independent models agree on most of it.
* **P(2nd pick is gold) = 0.68** on two-paper questions. The remaining 32% is the
  only mechanical headroom left in the paper stage, worth ~0.03 paper F1 if closed
  entirely, ~0.01 overall.

Both are small. The honest read is that the paper stage is within ~0.04 of what
this architecture supports, and the deficit against rank 1 (0.7837 vs 0.5519) is
not in paper selection at all — it is the table stage (row F1 0.274, cell accuracy
0.095), which is 1/3 of the answer score and where this project measured the least.

## Two more MC answers corrected (v37)

Ranking each paper's pages by how well they support the chosen option, then
reviewing where the page we cite lands, turned up two answers that were simply
wrong -- not mis-cited, wrong.

**`ltqa_d2b9a56db69fe43c`** -- "which two papers cite Dong-Hyun Lee's
pseudo-label work?" We answered "all three" and cited
`neurips2025_04917`, which is not one of the three papers the options name.
Fetched all three and read their bibliographies:

| paper | cites Lee |
|---|---|
| `iccv2025_02125` Semi-supervised Concept Bottleneck Models | yes, `[28]`, and p3 carries the question's own phrasing "reducing the entropy of unlabeled data [28]" |
| `iccv2025_02128` SemiVisBooster | yes, `[21]`, in text on p2 |
| `iccv2025_02075` SCAN | **no** |

So it is the two, option A. Answer, paper set and evidence all corrected.

**`ltqa_f0de7fb4352ad29c`** -- three counts, and we had two of them wrong:

| quantity | paper says | our option C | correct option D |
|---|---|---|---|
| KMI decision-module rules | "Based on two simple rules" (p5) | 2 | 2 |
| MASER initialization elements | "prompt GPT-4o to extract six initialization elements" (p3) | 7 | 6 |
| M2Lingual multi-turn Evol prompts | "taxonomy with 21 distinct dialogue variations" (p4) | 17 | 21 |

All three now cite the page that states the number.

Note what the page ranking is and is not good for. It cannot tell a right page
from a wrong one -- several pages I had already verified by hand rank third or
fourth, because a results table repeats the paper's vocabulary less than the
intro does. What it does reliably is find pages that support the answer with
*nothing*, and those are worth opening.
