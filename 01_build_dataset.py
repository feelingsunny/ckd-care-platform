"""
Build a pooled analysis dataset from four NHANES cycles (2011-2018).

Expects these files (as downloaded from wwwn.cdc.gov, .XPT format) for each
cycle suffix G (2011-12), H (2013-14), I (2015-16), J (2017-18) in RAW_DIR:
    DEMO_x    - Demographics
    DR1TOT_x  - Dietary Interview, Total Nutrient Intakes Day 1
    DR2TOT_x  - Dietary Interview, Total Nutrient Intakes Day 2
    BIOPRO_x  - Standard Biochemistry Profile
    PAQ_x     - Physical Activity Questionnaire
    ALB_CR_x  - Urine albumin & creatinine (UACR)
    RXQ_RX_x  - Prescription medications (past 30 days)

Produces: data/analysis_dataset.csv
one row per participant (SEQN), with:
  - cycle, demographics (age, sex, race, survey weights incl. pooled 8-year MEC weight)
  - diet variables averaged over day 1 + day 2 recalls where day 2 is reliable
  - activity variables (vigorous/moderate minutes per week, sedentary minutes/day)
  - kidney markers (serum creatinine, potassium, phosphorus, albumin, UACR)
  - eGFR, computed via the race-free 2021 CKD-EPI creatinine equation
  - medication flags that directly affect potassium / albuminuria
"""
import numpy as np
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

CYCLES = {"G": "2011-2012", "H": "2013-2014", "I": "2015-2016", "J": "2017-2018"}

# nutrient suffixes shared by DR1T*/DR2T*: kcal, protein(g), sodium(mg),
# potassium(mg), phosphorus(mg), calcium(mg)
NUTRIENTS = {"KCAL": "kcal", "PROT": "protein_g", "SODI": "sodium_mg",
             "POTA": "potassium_intake_mg", "PHOS": "phosphorus_intake_mg",
             "CALC": "calcium_mg"}

# Generic names as they appear in RXDDRUG (combination products are listed as
# "A; B", so substring matching catches them).
DRUG_CLASSES = {
    "acei_arb": ["BENAZEPRIL", "CAPTOPRIL", "ENALAPRIL", "FOSINOPRIL", "LISINOPRIL",
                 "MOEXIPRIL", "PERINDOPRIL", "QUINAPRIL", "RAMIPRIL", "TRANDOLAPRIL",
                 "AZILSARTAN", "CANDESARTAN", "EPROSARTAN", "IRBESARTAN", "LOSARTAN",
                 "OLMESARTAN", "TELMISARTAN", "VALSARTAN"],
    "k_sparing": ["SPIRONOLACTONE", "EPLERENONE", "AMILORIDE", "TRIAMTERENE",
                  "FINERENONE"],
    "k_wasting_diuretic": ["FUROSEMIDE", "BUMETANIDE", "TORSEMIDE", "ETHACRYNIC",
                           "HYDROCHLOROTHIAZIDE", "CHLORTHALIDONE", "CHLOROTHIAZIDE",
                           "INDAPAMIDE", "METOLAZONE"],
    "k_supplement": ["POTASSIUM CHLORIDE", "POTASSIUM CITRATE", "POTASSIUM BICARBONATE",
                     "POTASSIUM GLUCONATE"],
}


def read_xpt(name: str) -> pd.DataFrame:
    path = RAW_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {name} in {RAW_DIR} -- download it from wwwn.cdc.gov "
            f"and place it there (see README)."
        )
    # latin-1: some RXQ_RX drug names contain non-UTF-8 bytes
    df = pd.read_sas(path, format="xport", encoding="latin-1")
    df["SEQN"] = df["SEQN"].astype(int)
    return df


def ckd_epi_2021_egfr(scr, age, sex_is_female):
    """
    Race-free 2021 CKD-EPI creatinine equation (Inker et al., NEJM 2021).
    Vectorized: scr (mg/dL), age (years), sex_is_female (bool) as arrays/Series.
    """
    kappa = np.where(sex_is_female, 0.7, 0.9)
    alpha = np.where(sex_is_female, -0.241, -0.302)
    sex_mult = np.where(sex_is_female, 1.012, 1.0)
    ratio = scr / kappa
    min_term = np.minimum(ratio, 1) ** alpha
    max_term = np.maximum(ratio, 1) ** -1.200
    return 142 * min_term * max_term * (0.9938 ** age) * sex_mult


def diet_two_day(s: str) -> pd.DataFrame:
    """Mean of day 1 and day 2 recalls; day 1 alone if day 2 is missing/unreliable."""
    d1 = read_xpt(f"DR1TOT_{s}.xpt")
    d2 = read_xpt(f"DR2TOT_{s}.xpt")
    # DRxDRSTZ == 1: reliable recall that met the minimum criteria
    d1 = d1[d1["DR1DRSTZ"] == 1]
    d2 = d2[d2["DR2DRSTZ"] == 1]
    d1 = d1[["SEQN", "DR1_320Z"] + [f"DR1T{k}" for k in NUTRIENTS]]
    d2 = d2[["SEQN"] + [f"DR2T{k}" for k in NUTRIENTS]]
    diet = d1.merge(d2, on="SEQN", how="left")
    for k, name in NUTRIENTS.items():
        diet[name] = diet[[f"DR1T{k}", f"DR2T{k}"]].mean(axis=1)
    diet["diet_days"] = 1 + diet[f"DR2T{next(iter(NUTRIENTS))}"].notna().astype(int)
    diet = diet.rename(columns={"DR1_320Z": "water_day1_g"})
    return diet[["SEQN", "diet_days", "water_day1_g"] + list(NUTRIENTS.values())]


def medication_flags(s: str) -> pd.DataFrame:
    rx = read_xpt(f"RXQ_RX_{s}.xpt")[["SEQN", "RXDUSE", "RXDDRUG"]]
    rx["RXDDRUG"] = rx["RXDDRUG"].fillna("").str.upper()
    # RXDUSE 7/9 = refused/don't know -> flags unknown for that person
    known = rx.groupby("SEQN")["RXDUSE"].apply(lambda u: u.isin([1, 2]).all())
    out = pd.DataFrame(index=known.index)
    for cls, names in DRUG_CLASSES.items():
        pattern = "|".join(names)
        hit = rx["RXDDRUG"].str.contains(pattern, regex=True)
        out[cls] = hit.groupby(rx["SEQN"]).any().astype(float)
    out.loc[~known] = np.nan
    return out.reset_index()


def paq_activity(s: str) -> pd.DataFrame:
    paq = read_xpt(f"PAQ_{s}.xpt")
    # Self-reported activity (GPAQ-style module, stable across 2011-2018):
    #   PAQ605/610/615 = vigorous work: does any? / days per week / minutes per day
    #   PAQ620/625/630 = moderate work:  does any? / days per week / minutes per day
    #   PAQ650/655/660 = vigorous recreation: does any? / days per week / minutes per day
    #   PAQ665/670/675 = moderate recreation:  does any? / days per week / minutes per day
    #   PAD680         = minutes of sedentary activity per day
    # NHANES codes 7777/9999 as refused/don't know -- treated as missing here.
    def clean(col, max_valid):
        if col not in paq.columns:
            return None
        s_ = pd.to_numeric(paq[col], errors="coerce")
        return s_.where(s_ <= max_valid)

    # Weekly minutes = (days/week) x (minutes/session), gated on the "does any?"
    # screener so a "no" (coded 2) or missing doesn't get treated as zero days.
    def weekly_minutes(does_any_col, days_col, minutes_col):
        does_any = clean(does_any_col, 2)
        days = clean(days_col, 7)
        minutes = clean(minutes_col, 840)
        if does_any is None or days is None or minutes is None:
            return pd.Series(pd.NA, index=paq.index, dtype="float")
        total = days * minutes
        return total.where(does_any == 1, 0)  # "no" -> 0 minutes, not missing

    vig_work = weekly_minutes("PAQ605", "PAQ610", "PAD615")
    mod_work = weekly_minutes("PAQ620", "PAQ625", "PAD630")
    vig_rec = weekly_minutes("PAQ650", "PAQ655", "PAD660")
    mod_rec = weekly_minutes("PAQ665", "PAQ670", "PAD675")

    out = paq[["SEQN"]].copy()
    out["vig_min_wk"] = vig_work.add(vig_rec, fill_value=0)
    out["mod_min_wk"] = mod_work.add(mod_rec, fill_value=0)
    out["mvpa_min_wk"] = out["vig_min_wk"] * 2 + out["mod_min_wk"]  # MET-weighted, WHO-style
    out["sedentary_min_day"] = clean("PAD680", 1320)
    return out


def build_cycle(s: str) -> pd.DataFrame:
    demo = read_xpt(f"DEMO_{s}.xpt")[
        ["SEQN", "RIDAGEYR", "RIAGENDR", "RIDRETH3", "WTINT2YR", "WTMEC2YR",
         "SDMVPSU", "SDMVSTRA"]
    ]
    bio = read_xpt(f"BIOPRO_{s}.xpt")[
        ["SEQN", "LBXSCR", "LBXSKSI", "LBXSPH", "LBXSAL", "LBXSBU", "LBXSGL"]
        # creatinine mg/dL, potassium mmol/L, phosphorus mg/dL, albumin g/dL, BUN mg/dL, glucose mg/dL
    ]
    alb = read_xpt(f"ALB_CR_{s}.xpt")[["SEQN", "URDACT"]]  # UACR, mg/g

    df = (demo.merge(diet_two_day(s), on="SEQN", how="inner")
              .merge(bio, on="SEQN", how="inner")
              .merge(paq_activity(s), on="SEQN", how="left")
              .merge(alb, on="SEQN", how="left")
              .merge(medication_flags(s), on="SEQN", how="left"))
    df["cycle"] = CYCLES[s]
    return df


def main():
    df = pd.concat([build_cycle(s) for s in CYCLES], ignore_index=True)

    # restrict to adults with a valid creatinine reading
    df = df[(df["RIDAGEYR"] >= 18) & df["LBXSCR"].notna()].copy()

    # pooled MEC weight for 4 combined 2-year cycles (NCHS guidance: divide by # cycles)
    df["WTMEC8YR"] = df["WTMEC2YR"] / len(CYCLES)

    df["is_female"] = df["RIAGENDR"] == 2
    df["eGFR"] = ckd_epi_2021_egfr(df["LBXSCR"], df["RIDAGEYR"], df["is_female"])

    df = df.rename(columns={
        "RIDAGEYR": "age", "RIDRETH3": "race_eth",
        "LBXSCR": "creatinine_mgdl", "LBXSKSI": "serum_potassium_mmol",
        "LBXSPH": "serum_phosphorus_mgdl", "LBXSAL": "serum_albumin_gdl",
        "LBXSBU": "bun_mgdl", "LBXSGL": "glucose_mgdl", "URDACT": "uacr_mg_g",
    })

    keep = ["SEQN", "cycle", "age", "is_female", "race_eth",
            "WTMEC2YR", "WTMEC8YR", "SDMVPSU", "SDMVSTRA",
            "diet_days", "kcal", "protein_g", "sodium_mg", "potassium_intake_mg",
            "phosphorus_intake_mg", "calcium_mg", "water_day1_g",
            "vig_min_wk", "mod_min_wk", "mvpa_min_wk", "sedentary_min_day",
            "creatinine_mgdl", "eGFR", "uacr_mg_g", "serum_potassium_mmol",
            "serum_phosphorus_mgdl", "serum_albumin_gdl", "bun_mgdl", "glucose_mgdl",
            *DRUG_CLASSES]
    df = df[keep]

    out_path = OUT_DIR / "analysis_dataset.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} participants to {out_path}")
    print(df.groupby("cycle").size().rename("n").to_string())
    print(f"CKD by eGFR<60: n={(df['eGFR'] < 60).sum()}   "
          f"albuminuria (UACR>=30): n={(df['uacr_mg_g'] >= 30).sum()}   "
          f"2-day diet: {(df['diet_days'] == 2).mean():.0%}")
    print(df.describe(include="all").T)


if __name__ == "__main__":
    main()
