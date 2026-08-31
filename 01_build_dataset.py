"""
Build an analysis dataset from NHANES 2017-2018 (_J cycle) extracts.

Expects these four files (as downloaded from wwwn.cdc.gov, .XPT format)
to be present in the RAW_DIR below:
    DEMO_J.XPT    - Demographics
    DR1TOT_J.XPT  - Dietary Interview, Total Nutrient Intakes Day 1
    BIOPRO_J.XPT  - Standard Biochemistry Profile
    PAQ_J.XPT     - Physical Activity Questionnaire

Produces: ckd_model/data/analysis_dataset.csv
one row per participant (SEQN), with:
  - demographics (age, sex, race, survey weights)
  - diet variables (energy, protein, sodium, potassium, phosphorus)
  - activity variables (vigorous/moderate minutes per week, sedentary minutes/day)
  - kidney markers (serum creatinine, potassium, phosphorus, albumin)
  - eGFR, computed via the race-free 2021 CKD-EPI creatinine equation
"""
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def read_xpt(name: str) -> pd.DataFrame:
    path = RAW_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {name} in {RAW_DIR} -- download it from wwwn.cdc.gov "
            f"(2017-2018 cycle) and place it there."
        )
    df = pd.read_sas(path, format="xport", encoding="utf-8")
    df["SEQN"] = df["SEQN"].astype(int)
    return df


def ckd_epi_2021_egfr(scr: float, age: float, sex_is_female: bool) -> float:
    """
    Race-free 2021 CKD-EPI creatinine equation (Inker et al., NEJM 2021).
    scr: serum creatinine, mg/dL
    age: years
    sex_is_female: bool
    """
    kappa = 0.7 if sex_is_female else 0.9
    alpha = -0.241 if sex_is_female else -0.302
    sex_mult = 1.012 if sex_is_female else 1.0
    min_term = min(scr / kappa, 1) ** alpha
    max_term = max(scr / kappa, 1) ** -1.200
    egfr = 142 * min_term * max_term * (0.9938 ** age) * sex_mult
    return egfr


def main():
    demo = read_xpt("DEMO_J.XPT")[
        ["SEQN", "RIDAGEYR", "RIAGENDR", "RIDRETH3", "WTINT2YR", "WTMEC2YR",
         "SDMVPSU", "SDMVSTRA"]
    ]
    diet = read_xpt("DR1TOT_J.XPT")[
        ["SEQN", "DR1TKCAL", "DR1TPROT", "DR1TSODI", "DR1TPOTA", "DR1TPHOS",
         "DR1TCALC", "DR1_320Z"]  # kcal, protein(g), sodium(mg), potassium(mg), phosphorus(mg), calcium(mg), total plain water (g)
    ]
    bio = read_xpt("BIOPRO_J.XPT")[
        ["SEQN", "LBXSCR", "LBXSKSI", "LBXSPH", "LBXSAL", "LBXSBU", "LBXSGL"]
        # creatinine mg/dL, potassium mmol/L, phosphorus mg/dL, albumin g/dL, BUN mg/dL, glucose mg/dL
    ]
    paq = read_xpt("PAQ_J.XPT")
    # Self-reported activity (GPAQ-style module, stable across recent cycles):
    #   PAQ605/610/615 = vigorous work: does any? / days per week / minutes per day
    #   PAQ620/625/630 = moderate work:  does any? / days per week / minutes per day
    #   PAQ650/655/660 = vigorous recreation: does any? / days per week / minutes per day
    #   PAQ665/670/675 = moderate recreation:  does any? / days per week / minutes per day
    #   PAD680         = minutes of sedentary activity per day
    paq_cols = [c for c in
                ["SEQN",
                 "PAQ605", "PAQ610", "PAD615",
                 "PAQ620", "PAQ625", "PAD630",
                 "PAQ650", "PAQ655", "PAD660",
                 "PAQ665", "PAQ670", "PAD675",
                 "PAD680"]
                if c in paq.columns]
    paq = paq[paq_cols]

    df = (demo.merge(diet, on="SEQN", how="inner")
               .merge(bio, on="SEQN", how="inner")
               .merge(paq, on="SEQN", how="left"))

    # restrict to adults with a valid creatinine reading
    df = df[(df["RIDAGEYR"] >= 18) & df["LBXSCR"].notna()].copy()

    df["is_female"] = df["RIAGENDR"] == 2
    df["eGFR"] = df.apply(
        lambda r: ckd_epi_2021_egfr(r["LBXSCR"], r["RIDAGEYR"], r["is_female"]),
        axis=1,
    )

    # Weekly minutes = (days/week) x (minutes/session), gated on the "does any?"
    # screener so a "no" (coded 2) or missing doesn't get treated as zero days.
    # NHANES codes 7777/9999 as refused/don't know -- treated as missing here.
    def clean(col, max_valid):
        if col not in df.columns:
            return None
        s = pd.to_numeric(df[col], errors="coerce")
        return s.where(s <= max_valid)

    def weekly_minutes(does_any_col, days_col, minutes_col):
        does_any = clean(does_any_col, 2)
        days = clean(days_col, 7)
        minutes = clean(minutes_col, 840)
        if does_any is None or days is None or minutes is None:
            return pd.Series(pd.NA, index=df.index, dtype="float")
        total = days * minutes
        return total.where(does_any == 1, 0)  # "no" -> 0 minutes, not missing

    vig_work = weekly_minutes("PAQ605", "PAQ610", "PAD615")
    mod_work = weekly_minutes("PAQ620", "PAQ625", "PAD630")
    vig_rec = weekly_minutes("PAQ650", "PAQ655", "PAD660")
    mod_rec = weekly_minutes("PAQ665", "PAQ670", "PAD675")

    df["vig_min_wk"] = vig_work.add(vig_rec, fill_value=0)
    df["mod_min_wk"] = mod_work.add(mod_rec, fill_value=0)
    df["mvpa_min_wk"] = df["vig_min_wk"] * 2 + df["mod_min_wk"]  # MET-weighted, WHO-style
    df["sedentary_min_day"] = clean("PAD680", 1320)

    df = df.rename(columns={
        "RIDAGEYR": "age", "RIDRETH3": "race_eth",
        "DR1TKCAL": "kcal", "DR1TPROT": "protein_g", "DR1TSODI": "sodium_mg",
        "DR1TPOTA": "potassium_intake_mg", "DR1TPHOS": "phosphorus_intake_mg",
        "LBXSCR": "creatinine_mgdl", "LBXSKSI": "serum_potassium_mmol",
        "LBXSPH": "serum_phosphorus_mgdl", "LBXSAL": "serum_albumin_gdl",
        "LBXSBU": "bun_mgdl", "LBXSGL": "glucose_mgdl",
    })

    keep = ["SEQN", "age", "is_female", "race_eth", "WTMEC2YR", "SDMVPSU", "SDMVSTRA",
            "kcal", "protein_g", "sodium_mg", "potassium_intake_mg", "phosphorus_intake_mg",
            "vig_min_wk", "mod_min_wk", "mvpa_min_wk", "sedentary_min_day",
            "creatinine_mgdl", "eGFR", "serum_potassium_mmol", "serum_phosphorus_mgdl",
            "serum_albumin_gdl", "bun_mgdl", "glucose_mgdl"]
    df = df[keep]

    out_path = OUT_DIR / "analysis_dataset.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} participants to {out_path}")
    print(df.describe(include="all").T)


if __name__ == "__main__":
    main()
