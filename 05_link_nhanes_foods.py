"""
Link NHANES 2021-2023 individual-food recall records to the food database.

NHANES 2021-2023 dietary recalls are coded with FNDDS 2021-2023 food codes, the
same release loaded into data/food.db by 04_build_food_db.py, so every food a
participant reported can be matched to a food in the app's database.

Expects in RAW_DIR:
    DR1IFF_L.xpt, DR2IFF_L.xpt - Individual Foods, day 1 and day 2 (2021-2023)
and data/food.db (04_build_food_db.py) and data/analysis_dataset.csv
(01_build_dataset.py).

Does three things:
  1. Coverage: share of reported foods whose food code is in food.db.
  2. Agreement: potassium recomputed from food.db (grams x per-100 g value)
     vs. the potassium NHANES reports for the same records.
  3. Writes a food_popularity table into food.db (how many people reported
     each food), used to rank food-search results by how commonly the food
     is eaten, and prints the top potassium sources among adults with CKD.
"""
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
DB_PATH = Path(__file__).parent / "data" / "food.db"
ANALYSIS = Path(__file__).parent / "data" / "analysis_dataset.csv"


def read_day(day: int) -> pd.DataFrame:
    p = f"DR{day}I"
    df = pd.read_sas(RAW_DIR / f"DR{day}IFF_L.xpt", format="xport", encoding="latin-1")
    # DRxDRSTZ == 1: reliable recall that met the minimum criteria
    df = df[df[f"DR{day}DRSTZ"] == 1]
    df = df.rename(columns={"SEQN": "seqn", f"{p}FDCD": "food_code", f"{p}GRMS": "grams",
                            f"{p}POTA": "potassium_mg"})
    df = df[["seqn", "food_code", "grams", "potassium_mg"]].copy()
    # SAS stores some zeros as ~5e-79
    df[["grams", "potassium_mg"]] = df[["grams", "potassium_mg"]].round(4)
    df["food_code"] = df["food_code"].astype("Int64")
    df["day"] = day
    return df


def main():
    rec = pd.concat([read_day(1), read_day(2)], ignore_index=True)
    con = sqlite3.connect(DB_PATH)
    foods = pd.read_sql("SELECT fdc_id, fndds_food_code AS food_code, description, "
                        "potassium_mg AS k_per_100g FROM food_kidney "
                        "WHERE dataset = 'fndds'", con)
    foods["food_code"] = foods["food_code"].astype("Int64")
    rec = rec.merge(foods, on="food_code", how="left")

    # 1. coverage
    matched = rec["fdc_id"].notna()
    print(f"Records: {len(rec):,} foods reported by {rec['seqn'].nunique():,} people "
          f"(day 1 + day 2)")
    print(f"Coverage: {matched.mean():.1%} of records and "
          f"{rec.loc[matched, 'food_code'].nunique() / rec['food_code'].nunique():.1%} "
          f"of distinct food codes match a food in food.db")

    # 2. agreement on potassium
    m = rec[matched].copy()
    m["k_from_db"] = m["grams"] * m["k_per_100g"] / 100
    diff = (m["k_from_db"] - m["potassium_mg"]).abs()
    print(f"Potassium agreement: {(diff <= 1).mean():.1%} of matched records within 1 mg; "
          f"correlation r = {np.corrcoef(m['k_from_db'], m['potassium_mg'])[0, 1]:.4f}")

    # 3. popularity table for search ranking
    pop = (m.groupby("fdc_id")
             .agg(nhanes_people=("seqn", "nunique"), nhanes_reports=("seqn", "size"),
                  median_grams=("grams", "median"))
             .reset_index())
    con.execute("DROP TABLE IF EXISTS food_popularity")
    con.execute("""
CREATE TABLE food_popularity (
    fdc_id         INTEGER PRIMARY KEY REFERENCES foods (fdc_id),
    nhanes_people  INTEGER NOT NULL,   -- people reporting the food, 2021-2023 recalls
    nhanes_reports INTEGER NOT NULL,   -- times reported (a person can report it twice)
    median_grams   REAL                -- typical amount eaten per report
)""")
    pop.to_sql("food_popularity", con, if_exists="append", index=False)
    con.commit()
    print(f"Wrote food_popularity: {len(pop):,} foods reported at least once")

    # top potassium sources among adults with CKD (eGFR < 60) in 2021-2023
    adults = pd.read_csv(ANALYSIS, usecols=["SEQN", "cycle", "eGFR"])
    ckd = adults.loc[(adults["cycle"] == "2021-2023") & (adults["eGFR"] < 60), "SEQN"]
    c = m[m["seqn"].isin(ckd)]
    top = (c.groupby("description")["potassium_mg"].sum()
             .div(c["potassium_mg"].sum()).sort_values(ascending=False).head(10))
    print(f"\nTop potassium sources, adults with CKD in 2021-2023 "
          f"(n={c['seqn'].nunique()}), share of all potassium reported:")
    for name, share in top.items():
        print(f"  {share:5.1%}  {name}")
    con.close()


if __name__ == "__main__":
    main()
