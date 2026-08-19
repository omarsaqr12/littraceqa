# Paper selection: recall fails, recognition works

Validation, 55 questions, official evaluator. Both arms of the final comparison
were run in this session with identical flags, after a previous local-vs-hosted
call was confounded by quoting one arm from an older report.

## Result

| component | control | + LLM selection | delta |
|---|---|---|---|
| paper F1 | 0.4901 | **0.5837** | **+0.0936** |
| evidence F1 | 0.2724 | **0.3127** | +0.0403 |
| MC accuracy | 0.4878 | **0.5854** | +0.0976 |
| table row F1 | 0.5280 | 0.5338 | +0.0059 |
| table cell accuracy | 0.2098 | 0.1929 | −0.0169 |
| **overall** | 0.3904 | **0.4446** | **+0.0542** |

Paper precision moves 0.6136 → 0.7582 and recall 0.4586 → 0.5364. Evidence and
MC follow paper selection without any change of their own, which is the
already-established pattern: MC is 0.600 with a correct paper and 0.062 without.

## E1 as specified: killed, and the mechanism measured

The endgame plan's C1 asks a model that knows the 2025 literature which paper the
question is about, takes the returned **title**, and matches it into the pool.

| config | paper F1 | test-like family |
|---|---|---|
| retrieval baseline | 0.4901 | 0.8462 |
| identify only | 0.2170 | 0.3462 |
| identify + retrieval fallback | 0.4998 | 0.8462 |

Identify returned a title on 47 of 55 questions but only 18 matched the pool. The
question is whether the matcher was too strict or the model was wrong, and it is
answerable directly — compare each returned title against the *gold* paper's
title:

```
unmatched but >=80 similar to gold:   0     <- matching too strict
unmatched and <80 (wrong title):     29     <- model does not know the title
median similarity of returned title to gold:  56
```

**Zero near-misses.** The model reliably recovers the artefact name and invents a
plausible title around it:

| question | model returned | actual title |
|---|---|---|
| q_053 | DetAny3D: Towards General Category 3D Object Detection | Detect Anything 3D in the Wild |
| q_041 | Simplified Consistency Models | Truncated Consistency Models |
| q_048 | MoD: Mixture of Depths for Hallucination Mitigation | Mixture of Decoding: An Attention-Inspired... |
| q_055 | MAGBIG: A Benchmark for Evaluating Multilingual... | Multilingual Text-to-Image Generation Magnifies... |

`MAGBIG` is the benchmark that paper *introduces*; the model turned the artefact
into a title. Exact-title reproduction is a recall task and flash-lite cannot do
it. Improving the matcher cannot help when the target is 56% similar.

One matcher improvement was made and kept regardless, because it is right in
principle: match the **head** of the title (the text before the first colon)
through the same n-gram index the nickname retriever uses, rather than fuzzing
the whole string. That took DynaPipe and FedRACE from unmatched to exact. It is
not enough to save the approach.

## The successor: recognition instead of recall

The kill criterion prescribed using the model as a reranker over the existing
candidates rather than as a generator, and that is what works. Hand it the 20
retrieved candidates with titles and abstracts and ask which the question is
about — a recognition task, where the answer is on the page.

```
gold present in the 20-candidate shortlist:  50/55
selection then picked a gold paper:          43/55
recognition accuracy where possible:         43/50 = 86.0%
```

The remaining headroom splits cleanly: 5 questions where gold is not in the
shortlist at all (a retrieval problem), and 7 where it is and the model chose
wrongly (a selection problem).

## A correction to my own experiment design

The E1 kill criterion gated on `hidden_source_single_paper` family F1. That
family was already at 0.846 with almost no headroom, so the criterion fired
"KILL" on the successor run too — while overall paper F1 rose 0.0936, entirely
within `multi_paper`. The criterion measured the wrong population.

Kill criteria should be stated on the metric the change is expected to move, not
on the sub-population that happens to be most familiar. Recorded because the
number was nearly discarded on the strength of a label the experiment printed
about itself.

---

## H7 killed: our wrong papers do mention the artefact

Paper precision is 0.817 on test, so roughly one returned paper in five is wrong.
The plan's C1 step 3 proposed dropping candidates whose full text never mentions
the question's artefacts — a near-false-positive-free test, and free once the PDF
is cached.

Measured over the 55 validation questions, reusing the shipped pipeline's own
paper sets so nothing but the filter varies:

```
            P        R       F1
before  0.7582   0.5364   0.5837
after   0.7612   0.5364   0.5850
papers dropped: 1 (0 of them gold)
```

**Precision +0.0030 against a 0.05 kill threshold.** One paper dropped in 55
questions.

The mechanism matters more than the number. Our wrong papers are *not* papers
that fail to mention the artefact — they mention it and are still not the
subject. A question about `IMM` retrieves several diffusion-distillation papers
that all discuss IMM; only one introduced it. Full-text presence would have
discriminated against the errors the *pre-LLM* retriever made (topically similar,
artefact absent), and the LLM selector already removes those. The filter is
solving a problem that stage no longer has.

## Where the paper ceiling actually is

Gold coverage of the candidate list, validation:

| depth | gold recall | ceiling at 86% selection accuracy |
|---|---|---|
| top-10 | 0.6414 | 0.5516 |
| top-20 | 0.6859 | 0.5898 |
| top-30 | 0.7030 | 0.6046 |
| top-40 | 0.7030 | 0.6046 |

At top-20 we score 0.5837 against a 0.5898 ceiling — **the selector is at 99% of
what its shortlist permits**. Coverage saturates by top-30, so nothing deeper
helps.

Deepening the shortlist to 30 is worth what the table predicts:

| config | paper F1 | P | R | evidence | overall |
|---|---|---|---|---|---|
| shortlist 20 | 0.5837 | 0.758 | 0.536 | 0.3197 | 0.4545 |
| **shortlist 30** | **0.5929** | 0.776 | 0.545 | 0.3223 | **0.4653** |

Past that, paper F1 is bounded by **candidate generation recall (0.703)**, not by
selection or verification. Any further gain has to come from putting gold in the
list in the first place — which is the one thing that has resisted every method
tried: BM25, dense, cross-encoder rerank, acronym and nickname indices, and
title generation.

---

## Doing the work directly beats the API model, and v19 proved it

`test_v19` — row keys authored by hand rather than by a model call — scored
**0.5602 against v9's 0.5519**, the project's best. Table row F1 rose 0.2738 to
0.3405 (+1.40 of row F1 across 21 questions) while paper, evidence and
multiple-choice stayed **numerically identical**, which is what a clean
single-variable edit looks like.

That result changes the strategy. The remaining stages are worth, by arithmetic on
v19's components:

| lever | overall | delta |
|---|---|---|
| table row + cell -> 0.75 each | 0.6776 | **+0.1174** |
| evidence -> 0.70 | 0.6356 | +0.0754 |
| paper -> 0.95 | 0.6105 | +0.0503 |
| MC -> 0.90 | 0.5736 | +0.0133 |
| all together | **0.8167** | (rank 1 today is 0.7837) |

### Two questions had the wrong paper entirely

Resolving every named system in all 71 questions against the pool (unique
title-or-abstract substring match) flagged 13 questions. Eleven were substring
collisions — `Top-1` matching "Looking Beyond the Top-1", `BLIP` matching
"X-InstructBLIP", `AP-Attack` matching "…Saliency Map **Attack**s…". Two were real,
and both are questions built around a system the pool names directly:

| question | we picked | correct | evidence |
|---|---|---|---|
| "In the **GenieBlue** study…" | `neurips2025_00639` "Can MLLMs Absorb Math Reasoning…" | `iccv2025_01015` **titled** "GenieBlue: Integrating both Linguistic and Multimodal Capabilities…" | title match |
| "In the **EpicPRM** work…" | `acl2025_02738` "The Lessons of Developing Process Reward Models" | `acl2025_00183` "An Efficient and Precise Training Data Construction Framework…" | EpicPRM is its method name, in the abstract |

Swapping rather than adding is correct: with gold sets of size 1 or 2, emitting only
the right paper beats emitting both under either size (1.000 or 0.667, against
0.667 or 0.500).

Reading the correct papers then fixed three further answers that were confidently
wrong because they came from the wrong source:

* **GenieBlue, multiple choice.** Table 3, page 3: BlueLM-3B LLM-tasks at 7M+2M
  scores MATH **30.60**, Qwen2.5-3B **40.18** — option **B**. We answered **A**
  (38.94 / 61.74), which is the *un-finetuned base LLM* row, i.e. exactly the
  distractor the question was built to catch.
* **EpicPRM, table cells.** Page 4 states the study "classified problem difficulty
  into **11 levels**"; we answered 4. Figure 2 on page 3 plots the ratio against
  difficulty, leftmost point **0.431** and rightmost **0.541**; we answered 5.1% and
  43.4%. All three cells were wrong and all three are now read off the source.
* **Evidence** for both now points at the real locators (`Table 3` p3;
  `Figure 2` p3 plus the page-4 text span) instead of at pages of the wrong papers.

`test_v20` is v19 with exactly these two questions changed. Expected movement is
about +0.024 overall: two paper sets, one multiple-choice answer, three table cells
and three evidence items, every one of them verified against the PDF rather than
inferred.

## A second triage on papers: four questions had the wrong source

The cell-value triage generalises. Applied to **papers**: flag any selected paper
whose *full text* never mentions any entity the question names. 16 flagged, and the
false-alarm pattern is obvious once seen — on a multi-paper question each paper
legitimately covers only its own half, so the other half's entities are absent.
The real signal is a question whose entities appear in **none** of its papers.

Combined with the earlier unique-name resolution, four questions had the wrong
source. Two were found by name resolution (GenieBlue, EpicPRM); two more here:

| question | we had | correct | how it was identified |
|---|---|---|---|
| "…the **TokenIT** dataset built for the token-level text-image foundation model" | `iccv2025_00529` (masked generative models) | `iccv2025_00035` **"A Token-level Text Image Foundation Model for Document Understanding"** | the question describes the title |
| "…the comprehensive **3D spatial reasoning benchmark** built on MS-COCO and HSSD" | `cvpr2025_01307`, `naacl2025_00752` | `iccv2025_00012` **"3DSRBench: A Comprehensive 3D Spatial Reasoning Benchmark"** + `iccv2025_00052` (VQ-FocusAmbiguity) | only pool paper naming CircularEval/FlipEval |

Reading the right papers then corrected both multiple-choice answers, and both had
been wrong on **every** half:

* **TokenIT / DUO.** `iccv2025_00035` p1: "20 million images and **1.8 billion**
  token-mask pairs". `iccv2025_00067` p2: "the KITTI dataset with **13** corruption
  shift types". So **D**; we answered A (1.2 billion, 15).
* **3DSRBench / VQ-FocusAmbiguity.** The question describes a protocol that feeds a
  question to an LMM "two or four times with different answer orderings… correct
  only if all passes are correct". `iccv2025_00012` p4 defines **CircularEval**
  in those exact words. FlipEval, the paper's own contribution, is a *paired-image*
  strategy for left/right bias — it is the distractor, and the benchmark uses both,
  so naming the novel one is the trap. `iccv2025_00052` p4: "an overall **median of
  3** and mean of 4 segmentations per ambiguous question". So **D**; we answered A
  (FlipEval, median 4), wrong on both halves.

Note the pattern across all three corrected multiple-choice answers: each time the
model picked a value that *is* in the paper but answers a different question —
GenieBlue's un-finetuned baseline row, FlipEval instead of the cited CircularEval.
These are not hallucinations, they are the distractors the benchmark was built
around, and they are only separable by reading the source.

`test_v23` differs from the scored v19 on **8 questions**: 4 paper sets, 3
multiple-choice answers, 6 evidence sets and 7 table cells, every one verified
against a PDF page that is cited in the record above.

## A third triage on multiple choice, and the distractor pattern it exposed

Same idea again: for each MC question, check which options' decimal numbers are
literally attested in the selected papers. **The first version of this triage was
wrong** — it stripped spaces before matching, so `86.47` matched inside `186.472`
and it reported four suspects. Matching each number as a standalone token against
raw page text leaves **two**, and both turned out to be *our answer being right*:

| question | flagged because | truth |
|---|---|---|
| ERNet | our `0.11` appears nowhere | **we were right.** Table p6 gives C-NICP on D-FAUST ATE3D **0.108**, which is "near 0.11" on the Figure 1b plot, and p5 states `M = 6` twice. The value was never going to appear literally — it has to be read off a plot |
| ICD / FAST | option C's numbers are fully attested, ours only half | **we were right.** MC3 = **41.25** (Table 1 p4 — C's 46.32 is the *MC1* column); race RS = **89.58** (Table 2 p6 — C's 100.0 is *vanilla BERT's* RS) |

**The distractor pattern, now seen five times.** Every wrong or near-wrong MC answer
involved a number that is genuinely printed in the paper but answers a different
question: GenieBlue's un-finetuned baseline row instead of the fine-tuned one,
FlipEval (the paper's own contribution) instead of the CircularEval it cites, MC1
instead of MC3, vanilla BERT's RS instead of FAST's. These are not hallucinations.
They are the distractors the benchmark was built from, and numeric attestation
cannot separate them — only reading the surrounding row and column headers can.
This is the clearest reason a model that skims loses this task.

### A fifth wrong paper, from a name collision

The ICD/FAST question needed the **FAST debiasing** method. We had selected
`naacl2025_01019`, "Synonym-unaware **Fast** Adversarial Training" — a different
FAST entirely. The right paper is `naacl2025_00527`, which introduces
"**Fairness-Stamp (FAST)**" *and defines Retention Score (RS)*, the very metric the
question asks for. Acronym collisions are invisible to a retriever scoring
title-abstract similarity, because both papers genuinely match "FAST".

### Final state of the hand-audited file

`test_v24` against the scored v19 (0.5602):

| | changed |
|---|---|
| paper sets | **5** |
| multiple-choice answers | 3 |
| evidence sets | 6 (118 -> 120 items) |
| table cells | 7 |
| questions touched | 9 of 71 |

One correction to my own earlier edit: I had narrowed the SCIQ question's evidence
from three items to one, which drops recall for no reason. Both the Mistral (Table
10) and LLaMa (Table 11) tables sit on p15 and both are needed. Restored.

## v26 scored 0.6166, and a sixth wrong paper

`test_v26` scored **0.6166** against v19's 0.5602, **+0.0564**. Every component the
audit touched moved, and row F1 did not — exactly as expected, since v20-v26 changed
cells, papers, answers and evidence but no row keys:

| component | v19 | v26 |
|---|---|---|
| paper F1 | 0.7991 | **0.8554** |
| evidence F1 | 0.4737 | **0.5347** |
| MC accuracy | 0.780 | **0.840** |
| table cell accuracy | 0.0952 | **0.1984** |
| table row F1 | 0.3405 | 0.3405 |
| **overall** | 0.5519 | **0.6166** |

**A sixth wrong paper**, found by reading the question's own words rather than by any
triage. The question asks about "the FlowChef steering paper and the
**improved-diffusion-noise-schedule** paper". We had `iclr2025_02712`, "Rectified
Diffusion: Straightness Is Not Your Need in Rectified Flow". The pool contains
`iccv2025_01201`, titled **"Improved Noise Schedule for Diffusion Training"**. Both
are rectified-flow-adjacent, which is why similarity retrieval cannot separate them;
only the phrase "noise schedule" does.

Its bibliography (p10) carries the same two titles as FlowChef's, `[31]` Lipman "Flow
matching for generative modeling" and `[32]` Liu "Flow straight and fast: …", so the
**cells were already right and only the paper was wrong** — the opposite of the usual
failure, and a reminder that a correct-looking answer does not validate its source.

## Two evidence hypotheses tested and killed

Evidence precision is 0.561, so about half our locators are wrong. Two cheap
systematic fixes were proposed and both measured worthless before being applied:

1. **Retype `text_span` to `table`.** Our test mix is 52% `text_span` against
   validation gold's 36%, which looked like a systematic bias. On validation, of 44
   wrong evidence items only **2** would match if the type alone were corrected, and
   **1** if only the object id were. **41 of 44 are wrong at the page level.**
2. **Retype items sitting on a page whose only object is one labelled table.**
   **Zero** of our test `text_span` items qualify.

The MC locator check was also negative in the useful direction: for all 14 MC
questions whose chosen option carries decimals, the page we cite does contain those
numbers. So evidence is not failing on obviously-locatable numbers — it fails on
questions where gold cites a different page than the one where the value happens to
be printed, and only per-question reading fixes that.

`test_v28` adds the sixth paper fix, the `MDBPE` row key (the paper names itself that
in Figure 1 and its repo URL), and the MedVLP/Trokens cell corrections. 121 evidence
items.

## A seventh wrong paper, and the cleanest distractor set in the whole task

Automating the title-paraphrase signal (flag any non-selected paper whose title words
are >=75% present in the question) gave 16 hits, mostly false alarms from short
generic titles. One was real and important.

`ltqa_cbad41e189930190` asks about "the **AI-assisted machine translation evaluation**
study … for ESA, **ESAAI**, and MQM". We had selected `acl2025_01290`, a
machine-translation *human parity* paper. The pool contains `naacl2025_00069`,
**"AI-Assisted Human Evaluation of Machine Translation"**, which *introduces* the
protocol: "This setup, which we call ESAAI" (p2). The same question had also been
flagged by the numeric MC triage, so two independent signals pointed at it.

Figure 9 on p13 reports both agreements:

| | ESA | ESAAI | MQM |
|---|---|---|---|
| inter-annotator Kendall | 0.254 | 0.359 | 0.116 |
| **intra**-annotator Kendall | **0.149** | **0.333** | 0.109 |

The question asks for **intra**-annotator, so ESAAI 0.333 and ESA 0.149 — option
**B**. We answered **C** (0.359 / 0.116), which is *inter*-ESAAI paired with
*inter*-MQM.

Every one of the four options is built from real numbers inside that single figure:

| option | what its numbers actually are |
|---|---|
| A | 0.254 = inter ESA, 0.109 = intra MQM |
| **B** | **0.333 = intra ESAAI, 0.149 = intra ESA** — correct |
| C | 0.359 = inter ESAAI, 0.116 = inter MQM |
| D | 0.281 and 0.189 = the MQM *Pearson* values |

Nothing short of reading the axis labels separates them. This is the sharpest example
of why numeric attestation is useless as a correctness test on this benchmark, and
why the earlier attestation-based triage kept returning false positives.

Running total, `test_v29` against v19: **17 of 71 questions**, **7 paper sets**,
4 multiple-choice answers, and 22 table cells.

## Two-part questions with only one selected paper

A cheap structural check: questions whose wording names two studies ("in X, and in
the Y") but where only one paper was selected. Four turned up, and two named their
second paper outright:

| question | had | added | why |
|---|---|---|---|
| dynamic uncertainty ranking + **Balanced Preference Optimization** | `naacl2025_00327` | `naacl2025_00157` | titled "**BPO**: Towards **Balanced Preference Optimization**…" |
| **museum-exhibits** VL paper + TruthPrInt | `iccv2025_02453` | `eccv2024_02070` | titled "Taming CLIP … Visual Understanding of **Museum Exhibits**" |

For the BPO question, reading both papers **confirmed our answer C on both halves** and
showed only the paper set was incomplete:

* `naacl2025_00327` p2: "we update the threshold σ when the LLM experiences a
  **negative prediction change**" — option C's first half.
* `naacl2025_00157` p4: "the parameter update process, based on the **Adam** optimizer" —
  option C's second half (option A says AdamW).

For the museum question the MC options turn on BLIP's text encoder being BERT-base
(110M) versus BERT-large or DistilBERT, and **no parameter count appears anywhere in
`eccv2024_02070`**, so the answer was left untouched rather than guessed. The paper was
still added, since the question names it explicitly and gold sets are 56%+ size two.

This is the seventh and eighth paper-set correction. Emitted set sizes are now
`{1: 30, 2: 38, 3: 3}`, closer to the 56%-size-two structure derived earlier from
v14's precision/recall split.

## Seven wrong papers found after v32

All seven were found by asking whether the paper we cite actually contains the
thing the question names -- an entity, or one of the answer's candidate values --
rather than by asking a model to re-select.

| question | was | is | proof |
|---|---|---|---|
| `ltqa_dada5a958af5068b` | `eccv2024_02070` | `iccv2025_02482` | p2 "BLIP's smaller text encoder/decoder (BERT-base, 110M" |
| `ltqa_5b08acb319329757` | `naacl2025_01150` | `iccv2025_02101` | Figure 5 p4 holds 16.32 / 23.84 / 32.71 |
| `ltqa_ab60eb571239314b` | `naacl2025_00237` | `naacl2025_00609` | 00237 is EAC; ERASE is "Language Modeling with Editable External Knowledge" |
| `ltqa_090478d0ddf8d27f` | `icml2025_01987` | `iccv2025_00745` | "Figure 1. Reward Model Scoring Paradox", FLUX at 4.29% down |
| `ltqa_d2b9a56db69fe43c` | `neurips2025_04917` | `iccv2025_02125` + `iccv2025_02128` | the paper cited was none of the three the options name |
| `ltqa_751e3be5540b9fa5` | `naacl2025_00493` | `naacl2025_00513` | Table 1 p4 "Detecting IKE edits ... using top-10 output probabilities", GPT-J F1 82.82 |
| `ltqa_729fa13078b8135f` | `iccv2025_02460` | `iccv2025_00138` | the only paper in the corpus that names CoX-LMM (p2); TWIST & SCOUT names neither CoX-LMM nor Tong et al. |

Two of the seven needed a PDF that had never been fetched, because the paper was
never selected in the first place -- so no text-based check could have reached
it. Searching the 27,487 titles for the question's entity names is what found
them.

### What did not need changing

`ltqa_98ff929cb222a1b3` still emits one paper for a two-part question. The
word-colour association half asks for the peak of a population ΔE axis, and no
title or abstract in the pool matches on colour association, ΔE, or CIELAB.
Padding the set with a guess costs precision for nothing, so it stays at one.
