#!/usr/bin/env python3
"""Generate progress.pdf from results/official_scores.csv.

The figure is drawn from the same file that results/validate_table3.py checks,
so it cannot drift from Table 3. Fonts are embedded as Type 42 (TrueType) rather
than matplotlib's default Type 3, which ACL PubCheck rejects and which produces
unsearchable text. Colours are the Okabe-Ito colour-blind-safe palette and every
series also carries its own marker and dash pattern, so the plot survives
grayscale printing.

Usage:  python3 paper/make_fig.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt

CSV = Path(__file__).resolve().parent.parent / "results" / "official_scores.csv"
OUT = Path(__file__).resolve().parent / "progress.pdf"

rows = list(csv.DictReader(open(CSV)))


def val(r, k):
    return float(r[k]) if r[k].strip() else float("nan")


x = list(range(1, len(rows) + 1))
labels = [r["run"] for r in rows]

# first submission carrying a per-question intervention: everything before it is
# the fully automated pipeline.
first_manual = labels.index("v19") + 1

fig, ax = plt.subplots(figsize=(7.1, 2.78))
series = [
    ("paper F1",       "paper_f1",     "#0072B2", "o", (0, ()),        "1/3"),
    ("evidence F1",    "evidence_f1",  "#009E73", "s", (0, (4, 1.4)),  "1/3"),
    ("MC acc",         "mc",           "#E69F00", "^", (0, (1, 1.2)),  "1/9"),
    ("table row F1",   "row_f1",       "#D55E00", "v", (0, (5, 1.2, 1, 1.2)), "1/9"),
    ("table cell acc", "cell_acc",     "#CC79A7", "D", (0, (3, 1.2, 1, 1.2, 1, 1.2)), "1/9"),
]
for label, key, colour, marker, dash, weight in series:
    ax.plot(x, [val(r, key) for r in rows], marker=marker, ms=3.1, lw=1.15,
            color=colour, linestyle=dash, label=f"{label} (w={weight})")
ax.plot(x, [val(r, "overall_shown") for r in rows], marker="o", ms=4.2, lw=2.3,
        color="black", label="overall", zorder=5)

i9 = labels.index("v9") + 1
i55 = labels.index("v55") + 1
ax.annotate("best fully automated\n0.5519", xy=(i9, 0.5519), xytext=(i9 + 1.1, 0.655),
            fontsize=6.5, ha="left",
            arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
ax.annotate("caption semantics\nmistaken for proof", xy=(i55, 0.7619),
            xytext=(i55 - 6.4, 0.885), fontsize=6.4, ha="left",
            arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))

ax.axvspan(0.5, first_manual - 0.5, color="0.90", zorder=0)
ax.text((0.5 + first_manual - 0.5) / 2, 0.035, "fully automated pipeline",
        fontsize=6.5, ha="center", color="0.35")
ax.text((first_manual - 0.5 + len(rows) + 0.5) / 2, 0.035,
        "audit loop + score-guided attribution", fontsize=6.5, ha="center", color="0.35")

ax.set_xlim(0.5, len(rows) + 0.5)
ax.set_ylim(0, 1.0)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=6.0, rotation=90)
ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax.tick_params(labelsize=6.8)
ax.set_xlabel("submission to the official evaluator, in order", fontsize=7.6)
ax.set_ylabel("official score", fontsize=7.6)
ax.grid(axis="y", lw=0.4, color="0.88")
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
ax.legend(fontsize=6.6, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.30),
          frameon=False, handlelength=2.0, columnspacing=1.1, borderaxespad=0.0)
fig.tight_layout(pad=0.35)
fig.savefig(OUT, bbox_inches="tight")
print(f"wrote {OUT} from {CSV} ({len(rows)} submissions)")
