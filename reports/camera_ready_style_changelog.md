# Style changelog

The language pass ran **after** all numerical, table, figure, citation and
disclosure work, so no wording change could alter a result. Rule followed
throughout: clearer prose must not become stronger prose.

## Measured

| | before | after |
|---|---|---|
| em dashes in prose | 22 | **2** |
| em dashes total (incl. the empty Table 3 cell) | 23 | 3 |
| sentences | 163 | 182 |
| sentences over 38 words | 25 | 20 |
| sentences beginning "We" | 7 | 9 |
| words of prose | 3,971 | 4,151 |

Sentence and word counts rose because overloaded sentences were split and
because the disclosure section gained exact model identifiers, flag strings and
two extra table rows. The paper is the same length in pages.

## Constructions removed

* **"This is the single most consequential fact about the task and it is easy to
  miss"** -> the claim now states the consequence directly.
* **"strikingly predictive"** -> "predictive on the development split, though on
  small denominators". This *weakens* the claim and adds the caveat the data
  supports.
* **"the decisive one being"** -> "The largest was".
* **"the useful part is where the gain came from"** (conclusion) -> deleted.
* **"These are the most transferable part of the paper"** (negative results)
  -> deleted.
* **"and are the reusable part of our tooling"** -> deleted.
* **"and we state it plainly"** -> deleted.
* **"We believe the findings are more transferable"** -> "The findings seem more
  transferable".
* **"Third, and we think most usefully for the workshop,"** -> "Third,".
* **"We record these because..."** -> the sentence now leads with its subject.
* **"not hallucination but the right paper and the wrong row"** (contribution 5)
  -> "the right paper and the wrong row rather than hallucination".
* **The closing "we would compress the task into one sentence: ..."** -> deleted.
  The conclusion now ends on what the paper reports.

## Sentences split

Four of the longest were broken up: the worked-example derivation (66 words), two
abstract sentences (61 and 54), and the `llama-server` configuration sentence
(60). One replacement created a broken `because ... so ... ,` clause chain, which
was rewritten into two sentences.

## Captions

Each was edited separately.

* **Figure 1** shortened; gained the sentence distinguishing test scores from the
  one `dev` annotation.
* **Figure 2** shortened; now states its scope (the 29 documented runs), what the shaded region
  means, what the `v19` gap is, and that it is drawn from the CSV.
* **Table 2** rewritten: names the generating script, defines rows 1 and 8, drops
  the unsupported "two largest jumps".
* **Table 3** rewritten: states the selection rule, the weights, macro vs micro,
  the rounding caveat, and why one cell is empty.

Captions 2--4 are longer than before, not shorter. They now carry disclosures the
paper needs, and that was judged more important than brevity.

## Terminology standardised

* "validation set" / "test set" -> **"development split"** / **"test split"**.
* "auditing", "audit loop", "score-guided attribution", "leaderboard feedback"
  each kept one meaning.

## Deliberately left unchanged

* **Every qualifier.** `0.5519` (fully automated) vs `0.7649` (with per-question
  intervention) appears in the abstract, Figure 1, Figure 2, Table 3 and the
  conclusion. The small-denominator caveats on Table 2, the "not attributable to
  the type change alone" hedge on the evidence gain, and the non-generalisation
  statement in the abstract and limitations all stand.
* **Technical terms**: `coarse_evidence_key`, `row_f1`, `cell_accuracy`,
  `text_span`, `equation_algorithm`, macro/micro.
* **The Disclosure paragraph** in §5, which states that this is adaptation to the
  held-out split. Softening it would have been the one edit that changed what the
  paper claims.
* **The long enumerations** in the error taxonomy and the 0-for-13 decomposition.
  They are lists; length is the content.
* **First-person voice.** Reduced where the subject could be the thing itself,
  kept where the agent matters.

No edit was made to defeat an AI-detection heuristic. Changes were made where the
prose was overloaded, self-congratulatory, or vague, and nowhere else.
