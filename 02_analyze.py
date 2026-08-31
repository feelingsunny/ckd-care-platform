"""
Explore how much of the variance in kidney markers (eGFR, serum potassium,
serum phosphorus) is explained by self-reported diet and physical activity,
on top of demographics -- using the NHANES 2017-2018 analysis dataset built
by 01_build_dataset.py.

This is a cross-sectional, population-level analysis: it establishes whether
diet/activity variables carry real signal about kidney markers at all. It is
NOT a personal, longitudinal, causal model -- that needs per-patient logs
over time, which is the platform's own job once it has users.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.metrics import r2_score, mean_absolute_error
from pathlib import Path

DATA = Path(__file__).parent / "data" / "analysis_dataset.csv"
df = pd.read_csv(DATA)

# ---- clean / derive ----
df = df.dropna(subset=["protein_g", "sodium_mg", "potassium_intake_mg",
                        "phosphorus_intake_mg", "mvpa_min_wk", "sedentary_min_day",
                        "eGFR", "serum_potassium_mmol", "age"])
df["is_female"] = df["is_female"].astype(int)
df["ckd"] = df["eGFR"] < 60
df["na_k_ratio"] = df["sodium_mg"] / df["potassium_intake_mg"]

print(f"Analysis sample: n={len(df)}  (CKD subgroup eGFR<60: n={df['ckd'].sum()})")
print()

DIET = ["protein_g", "sodium_mg", "potassium_intake_mg", "phosphorus_intake_mg"]
ACTIVITY = ["mvpa_min_wk", "sedentary_min_day"]
DEMO = ["age", "is_female"]

# ============================================================
# 1. OLS: how much variance in eGFR do diet+activity explain,
#    on top of demographics alone?
# ============================================================
def r2_block(y_col, blocks, label):
    print(f"--- {label} ---")
    running = []
    prev_r2 = 0.0
    for name, cols in blocks:
        running += cols
        X = sm.add_constant(df[running])
        model = sm.OLS(df[y_col], X, missing="drop").fit()
        gained = model.rsquared - prev_r2
        print(f"  + {name:<22} cumulative R^2={model.rsquared:.3f}   "
              f"(+{gained:.3f} from this block)")
        prev_r2 = model.rsquared
    print(f"  Final model, n={int(model.nobs)}")
    print(model.summary().tables[1])
    print()
    return model

blocks = [("demographics", DEMO), ("diet", DIET), ("activity", ACTIVITY)]
m_egfr = r2_block("eGFR", blocks, "eGFR ~ demographics -> +diet -> +activity")
m_k = r2_block("serum_potassium_mmol", blocks, "Serum potassium ~ demographics -> +diet -> +activity")

# potassium is heavily gated by kidney function itself -- add eGFR as a covariate
print("--- Serum potassium, controlling for eGFR (mechanistic check) ---")
X = sm.add_constant(df[DEMO + ["eGFR"] + DIET + ACTIVITY])
m_k_adj = sm.OLS(df["serum_potassium_mmol"], X, missing="drop").fit()
print(m_k_adj.summary().tables[1])
print()

# ============================================================
# 2. Gradient boosting: nonlinear predictive capability check,
#    compared against a demographics-only baseline, in the full
#    sample and the CKD (eGFR<60) subgroup.
# ============================================================
FEATURES = DEMO + DIET + ACTIVITY + ["na_k_ratio"]

def eval_model(frame, target, features, label):
    sub = frame.dropna(subset=features + [target])
    if len(sub) < 60:
        print(f"  [{label}] n={len(sub)} too small, skipping")
        return
    X, y = sub[features], sub[target]
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    gbr = GradientBoostingRegressor(random_state=42, max_depth=2,
                                     n_estimators=200, learning_rate=0.05)
    r2s = cross_val_score(gbr, X, y, cv=kf, scoring="r2")
    maes = -cross_val_score(gbr, X, y, cv=kf, scoring="neg_mean_absolute_error")
    print(f"  [{label}] n={len(sub)}  5-fold CV R^2={r2s.mean():.3f} (+/-{r2s.std():.3f})"
          f"   MAE={maes.mean():.3f}")
    gbr.fit(X, y)
    importances = pd.Series(gbr.feature_importances_, index=features).sort_values(ascending=False)
    print("    feature importances:", dict(importances.round(3)))
    return gbr, sub, importances

print("=== Gradient boosting: eGFR ===")
eval_model(df, "eGFR", FEATURES, "all adults")
eval_model(df[df["ckd"]], "eGFR", FEATURES, "CKD subgroup (eGFR<60)")
print()

print("=== Gradient boosting: serum potassium (kidney function included as feature) ===")
FEATURES_K = FEATURES + ["eGFR"]
eval_model(df, "serum_potassium_mmol", FEATURES_K, "all adults")
res_ckd = eval_model(df[df["ckd"]], "serum_potassium_mmol", FEATURES_K, "CKD subgroup (eGFR<60)")

df.to_csv(Path(__file__).parent / "data" / "analysis_dataset_clean.csv", index=False)
print("\nSaved cleaned analysis frame to data/analysis_dataset_clean.csv")
