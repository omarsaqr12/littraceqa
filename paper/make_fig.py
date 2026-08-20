import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# official evaluator output, in submission order
runs = [
 ("initial pipeline",              0.6324,0.3587,0.68,0.3221,0.1310,0.4563),
 ("+selector, visual tables",      0.7991,0.4737,0.78,0.2738,0.0952,0.5519),
 ("+hand row keys",                0.7991,0.4737,0.78,0.3405,0.0952,0.5602),
 ("+answer audit",                 0.8554,0.5347,0.84,0.3405,0.1984,0.6166),
 ("+audit cont.",                  0.8789,0.5606,0.86,0.3405,0.2103,0.6366),
 ("+7 paper fixes",                0.9704,0.6610,0.94,0.3405,0.2103,0.7095),
 ("+equation evidence",            0.9704,0.7121,0.96,0.3405,0.2103,0.7287),
 ("+figure reading",               0.9704,0.7121,0.98,0.3516,0.2103,0.7322),
 ("+short row keys",               0.9704,0.7121,0.98,0.4283,0.2262,0.7425),
 ("-proven-wrong rows",            0.9704,0.7121,0.98,0.4675,0.2262,0.7468),
 ("+cell rewrites",                0.9704,0.7192,0.98,0.4675,0.2500,0.7518),
 ("+printed labels",               0.9704,0.7262,0.98,0.4873,0.2976,0.7617),
 ("-proven-wrong rows (2)",        0.9704,0.7262,0.98,0.5032,0.2976,0.7634),
 ("+rows restored",                0.9704,0.7262,0.98,0.5151,0.2976,0.7647),
 ("+caption swap",                 0.9704,0.7178,0.98,0.5151,0.2976,0.7619),
 ("-swap, +unions",                0.9704,0.7319,0.98,0.4992,0.2976,0.7649),
]
x = range(1, len(runs)+1)
fig, ax = plt.subplots(figsize=(7.1, 2.95))
series = [("paper F1", 1, "#1f4e79", "o", 1/3),
          ("evidence F1", 2, "#2e8b57", "s", 1/3),
          ("MC acc", 3, "#b8860b", "^", 1/9),
          ("table row F1", 4, "#c0392b", "v", 1/9),
          ("table cell acc", 5, "#7d3c98", "D", 1/9)]
for label, idx, col, mk, w in series:
    ax.plot(x, [r[idx] for r in runs], marker=mk, ms=3.1, lw=1.15, color=col,
            label=f"{label}  (w={'1/3' if w>0.2 else '1/9'})")
ax.plot(x, [r[6] for r in runs], marker="o", ms=4.2, lw=2.3, color="black",
        label="overall", zorder=5)

ax.annotate("best fully automated\n0.5519", xy=(2, 0.5519), xytext=(3.15, 0.655),
            fontsize=6.5, ha="left", arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
ax.annotate("caption semantics\nmistaken for proof", xy=(15, 0.7619), xytext=(10.5, 0.885),
            fontsize=6.4, ha="left", arrowprops=dict(arrowstyle="->", lw=0.7, color="0.35"))
ax.axvspan(0.5, 2.5, color="0.90", zorder=0)
ax.text(1.5, 0.035, "pipeline", fontsize=6.5, ha="center", color="0.35")
ax.text(9.6, 0.035, "audit loop + score-guided attribution", fontsize=6.5, ha="center", color="0.35")

ax.set_xlim(0.5, len(runs)+0.5); ax.set_ylim(0, 1.0)
ax.set_xticks(list(x)); ax.set_xticklabels([str(i) for i in x], fontsize=6.6)
ax.set_yticks([0,0.2,0.4,0.6,0.8,1.0]); ax.tick_params(labelsize=6.8)
ax.set_xlabel("submission (in order)", fontsize=7.6)
ax.set_ylabel("official score", fontsize=7.6)
ax.grid(axis="y", lw=0.4, color="0.88")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
ax.legend(fontsize=6.6, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.155),
          frameon=False, handlelength=1.5, columnspacing=1.1, borderaxespad=0.0)
fig.tight_layout(pad=0.35)
fig.savefig("progress.pdf", bbox_inches="tight")
print("wrote progress.pdf")
