import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import statsmodels.api as sm
from pathlib import Path

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
df = pd.read_csv(Path(__file__).parent / "data" / "analysis_dataset_clean.csv")

INK = "#1b1d19"
INK2 = "#52564d"
MUTED = "#8a8d82"
ACCENT = "#1f6f68"
ACCENT_L = "#9fc9c3"
RUST = "#b3502f"
GRID = "#dcdfd6"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "text.color": INK,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

DIET = ["protein_g", "sodium_mg", "potassium_intake_mg", "phosphorus_intake_mg"]
ACTIVITY = ["mvpa_min_wk", "sedentary_min_day"]
DEMO = ["age", "is_female"]
MEDS = ["acei_arb", "k_sparing", "k_wasting_diuretic", "k_supplement"]
CYCLES = "NHANES 2011–2018"

# ---------- Figure 1: R^2 waterfall for eGFR and serum potassium ----------
def r2_series(y_col):
    running, out = [], []
    for cols in (DEMO, DIET, ACTIVITY):
        running += cols
        X = sm.add_constant(df[running])
        model = sm.OLS(df[y_col], X, missing="drop").fit()
        out.append(model.rsquared)
    return out  # [demo, demo+diet, demo+diet+activity]

egfr_r2 = r2_series("eGFR")
k_r2 = r2_series("serum_potassium_mmol")
uacr_r2 = r2_series("log_uacr")

fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
labels = ["Demographics\n(age, sex)", "+ Diet\n(2-day recall)", "+ Activity\n(self-report)"]
for ax, r2s, title, color in zip(
    axes, [egfr_r2, k_r2, uacr_r2], ["eGFR", "Serum potassium", "log(UACR)"],
    [ACCENT, RUST, MUTED]
):
    bars = ax.bar(labels, r2s, color=color, width=0.55, zorder=3)
    for b, v in zip(bars, r2s):
        ax.text(b.get_x() + b.get_width()/2, v + 0.01, f"{v:.3f}", ha="center",
                 fontsize=10, color=INK, fontweight="bold")
    ax.set_ylim(0, max(r2s) * 1.35 + 0.02)
    ax.set_title(f"{title}: cumulative R²", fontsize=12, fontweight="bold", color=INK, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
fig.suptitle("How much of the variance in each marker does diet + activity explain,\non top of demographics alone? ({}, n={:,} adults)".format(CYCLES, len(df)),
             fontsize=11.5, color=INK2, y=1.04)
fig.tight_layout()
fig.savefig(OUT / "r2_waterfall.png", dpi=200, bbox_inches="tight")
plt.close(fig)

# ---------- Figure 2: dietary potassium vs serum potassium, by eGFR tertile ----------
d = df.dropna(subset=["potassium_intake_mg", "serum_potassium_mmol", "eGFR"]).copy()
d["egfr_tertile"] = pd.qcut(d["eGFR"], 3, labels=["Lower eGFR (tertile 1)", "Mid eGFR (tertile 2)", "Higher eGFR (tertile 3)"])
d["k_bin"] = pd.qcut(d["potassium_intake_mg"], 8, duplicates="drop")
grp = d.groupby(["egfr_tertile", "k_bin"], observed=True).agg(
    k_intake=("potassium_intake_mg", "mean"),
    serum_k=("serum_potassium_mmol", "mean"),
    n=("serum_potassium_mmol", "size"),
).reset_index()

fig, ax = plt.subplots(figsize=(7.2, 5))
colors = {"Lower eGFR (tertile 1)": RUST, "Mid eGFR (tertile 2)": MUTED, "Higher eGFR (tertile 3)": ACCENT}
for tertile, sub in grp.groupby("egfr_tertile", observed=True):
    sub = sub.sort_values("k_intake")
    ax.plot(sub["k_intake"], sub["serum_k"], "-o", color=colors[tertile], label=tertile,
            linewidth=2, markersize=5, zorder=3)
ax.set_xlabel("Mean dietary potassium intake per bin (mg/day, 2-day recall mean)")
ax.set_ylabel("Mean serum potassium (mmol/L)")
ax.set_title("Dietary potassium tracks serum potassium at every kidney-function level\n(binned means, {})".format(CYCLES),
              fontsize=11.5, fontweight="bold", color=INK, pad=12)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=9.5, loc="upper left")
fig.tight_layout()
fig.savefig(OUT / "potassium_binned.png", dpi=200, bbox_inches="tight")
plt.close(fig)

# ---------- Figure 3: feature importances, GBM serum potassium model ----------
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_score
FEATURES_K = DEMO + DIET + ACTIVITY + ["na_k_ratio", "eGFR"] + MEDS
sub = df.dropna(subset=FEATURES_K + ["serum_potassium_mmol"])
gbr = GradientBoostingRegressor(random_state=42, max_depth=2, n_estimators=200, learning_rate=0.05)
cv_r2 = cross_val_score(gbr, sub[FEATURES_K], sub["serum_potassium_mmol"],
                        cv=KFold(n_splits=5, shuffle=True, random_state=42), scoring="r2").mean()
gbr.fit(sub[FEATURES_K], sub["serum_potassium_mmol"])
imp = pd.Series(gbr.feature_importances_, index=FEATURES_K).sort_values()
NAME_MAP = {
    "eGFR": "Kidney function (eGFR)", "age": "Age", "is_female": "Sex (female)",
    "potassium_intake_mg": "Dietary potassium", "na_k_ratio": "Sodium:potassium ratio",
    "sodium_mg": "Dietary sodium", "protein_g": "Dietary protein",
    "phosphorus_intake_mg": "Dietary phosphorus", "sedentary_min_day": "Sedentary min/day",
    "mvpa_min_wk": "Active min/week",
    "acei_arb": "ACE inhibitor / ARB", "k_sparing": "K-sparing diuretic / MRA",
    "k_wasting_diuretic": "Loop / thiazide diuretic", "k_supplement": "Potassium supplement",
}
imp.index = [NAME_MAP.get(i, i) for i in imp.index]

fig, ax = plt.subplots(figsize=(7, 5.5))
bar_colors = [ACCENT if v == imp.max() else ACCENT_L for v in imp.values]
ax.barh(imp.index, imp.values, color=bar_colors, zorder=3)
ax.set_xlabel("Relative importance (gradient boosting model)")
ax.set_title("What predicts serum potassium best, in this single-snapshot data?\n({}, n={:,} adults, 5-fold CV R²={:.3f})".format(CYCLES, len(sub), cv_r2),
              fontsize=11.5, fontweight="bold", color=INK, pad=12)
ax.spines[["top", "right"]].set_visible(False)
ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(OUT / "feature_importance_potassium.png", dpi=200, bbox_inches="tight")
plt.close(fig)

print("Saved 3 figures to", OUT)
