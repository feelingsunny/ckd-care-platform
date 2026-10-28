"""
Build a kidney-focused food database (SQLite) from USDA FoodData Central.

Uses three FoodData Central bulk CSV releases, unzipped into raw/fdc/
(download from https://fdc.nal.usda.gov/download-datasets/):
    FoodData_Central_foundation_food_csv_2026-04-30  - Foundation Foods (lab-analyzed)
    FoodData_Central_sr_legacy_food_csv_2018-04      - SR Legacy (classic USDA reference)
    FoodData_Central_survey_food_csv_2024-10-31      - FNDDS 2021-2023, the food database
                                                       behind NHANES 2021-2023 diet recalls

Produces: data/food.db with
    foods          - one row per food: name, source dataset, category, FNDDS food code
    nutrients      - the kidney-relevant nutrients kept (energy, protein, K, Na, P, Ca, water)
    food_nutrients - amount of each nutrient per 100 g of each food
    portions       - household portions ("1 cup, chopped") with their gram weight
    food_kidney    - view: one row per food, nutrients per 100 g as columns
"""
import sqlite3
import pandas as pd
from pathlib import Path

FDC_DIR = Path(__file__).parent / "raw" / "fdc"
DB_PATH = Path(__file__).parent / "data" / "food.db"

RELEASES = {
    "foundation": "FoodData_Central_foundation_food_csv_2026-04-30",
    "sr_legacy": "FoodData_Central_sr_legacy_food_csv_2018-04",
    "fndds": "FoodData_Central_survey_food_csv_2024-10-31",
}

# FDC nutrient id -> (column name, unit). FNDDS files use the older nutrient
# numbers instead (306 = potassium, ...), mapped in FNDDS_NUTRIENT_NBR below.
NUTRIENTS = {
    1008: ("energy_kcal", "kcal"),
    1003: ("protein_g", "g"),
    1092: ("potassium_mg", "mg"),
    1093: ("sodium_mg", "mg"),
    1091: ("phosphorus_mg", "mg"),
    1087: ("calcium_mg", "mg"),
    1051: ("water_g", "g"),
}
FNDDS_NUTRIENT_NBR = {208: 1008, 203: 1003, 306: 1092, 307: 1093, 305: 1091,
                      301: 1087, 255: 1051}
# Foundation Foods often report energy only as Atwater factors (2047/2048)
ENERGY_FALLBACKS = [2047, 2048]

SCHEMA = """
CREATE TABLE foods (
    fdc_id          INTEGER PRIMARY KEY,
    description     TEXT NOT NULL,
    dataset         TEXT NOT NULL CHECK (dataset IN ('foundation', 'sr_legacy', 'fndds')),
    category        TEXT,
    fndds_food_code INTEGER          -- links to NHANES 2021-2023 recall food codes
);
CREATE TABLE nutrients (
    nutrient_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL
);
CREATE TABLE food_nutrients (
    fdc_id          INTEGER NOT NULL REFERENCES foods (fdc_id),
    nutrient_id     INTEGER NOT NULL REFERENCES nutrients (nutrient_id),
    amount_per_100g REAL NOT NULL,
    PRIMARY KEY (fdc_id, nutrient_id)
);
CREATE TABLE portions (
    portion_id  INTEGER PRIMARY KEY,
    fdc_id      INTEGER NOT NULL REFERENCES foods (fdc_id),
    description TEXT NOT NULL,
    gram_weight REAL NOT NULL
);
CREATE INDEX idx_portions_fdc ON portions (fdc_id);
CREATE INDEX idx_foods_description ON foods (description);
"""


def read(release: str, table: str) -> pd.DataFrame:
    path = FDC_DIR / RELEASES[release] / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} -- download and unzip the release (see docstring).")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_release(release: str):
    food = read(release, "food")
    if release == "foundation":
        # the Foundation release also ships every lab sample, and superseded
        # versions of some foods, as their own "food"; foundation_food.csv
        # lists the current ones
        current = read(release, "foundation_food")["fdc_id"]
        food = food[food["fdc_id"].isin(current)]
    food["fdc_id"] = food["fdc_id"].astype(int)

    if release == "fndds":
        survey = read(release, "survey_fndds_food")
        cats = read(release, "wweia_food_category")
        food = (food.merge(survey[["fdc_id", "food_code", "wweia_category_number"]]
                           .astype({"fdc_id": int}), on="fdc_id", how="left")
                    .merge(cats, left_on="wweia_category_number",
                           right_on="wweia_food_category", how="left"))
        food["category"] = food["wweia_food_category_description"]
        food["fndds_food_code"] = pd.to_numeric(food["food_code"], errors="coerce")
    else:
        cats = read(release, "food_category").rename(columns={"id": "food_category_id"})
        food = food.merge(cats[["food_category_id", "description"]]
                          .rename(columns={"description": "category"}),
                          on="food_category_id", how="left")
        food["fndds_food_code"] = None
    food["dataset"] = release
    foods = food[["fdc_id", "description", "dataset", "category", "fndds_food_code"]]

    fn = read(release, "food_nutrient")[["fdc_id", "nutrient_id", "amount"]]
    fn = fn.astype({"fdc_id": int, "nutrient_id": int})
    fn["amount"] = pd.to_numeric(fn["amount"], errors="coerce")
    fn = fn[fn["fdc_id"].isin(foods["fdc_id"]) & fn["amount"].notna()]
    if release == "fndds":
        fn["nutrient_id"] = fn["nutrient_id"].map(FNDDS_NUTRIENT_NBR)
        fn = fn.dropna(subset=["nutrient_id"]).astype({"nutrient_id": int})
    else:
        # fill missing Energy (1008) from the Atwater energy values
        has_energy = set(fn.loc[fn["nutrient_id"] == 1008, "fdc_id"])
        for alt in ENERGY_FALLBACKS:
            fill = fn[(fn["nutrient_id"] == alt) & ~fn["fdc_id"].isin(has_energy)].copy()
            fill["nutrient_id"] = 1008
            fn = pd.concat([fn, fill])
            has_energy |= set(fill["fdc_id"])
        fn = fn[fn["nutrient_id"].isin(NUTRIENTS)]
    fn = fn.drop_duplicates(["fdc_id", "nutrient_id"])

    por = read(release, "food_portion")
    por = por[pd.to_numeric(por["fdc_id"], errors="coerce").isin(foods["fdc_id"])]
    units = read(release, "measure_unit").set_index("id")["name"]
    unit = por["measure_unit_id"].map(units).where(por["measure_unit_id"] != "9999", "")
    built = (por["amount"].str.replace(r"\.0$", "", regex=True) + " " + unit + " "
             + por["modifier"].where(~por["modifier"].str.fullmatch(r"\d+"), "")
             ).str.split().str.join(" ")
    por = por.assign(description=por["portion_description"].where(
        por["portion_description"] != "", built))
    por["gram_weight"] = pd.to_numeric(por["gram_weight"], errors="coerce")
    por = por[(por["description"] != "") & (por["gram_weight"] > 0)]
    portions = por.assign(fdc_id=por["fdc_id"].astype(int))[["fdc_id", "description", "gram_weight"]]

    return foods, fn.rename(columns={"amount": "amount_per_100g"}), portions


def main():
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO nutrients VALUES (?, ?, ?)",
                    [(i, name, unit) for i, (name, unit) in NUTRIENTS.items()])

    for release in RELEASES:
        foods, fn, portions = load_release(release)
        foods.to_sql("foods", con, if_exists="append", index=False)
        fn.to_sql("food_nutrients", con, if_exists="append", index=False)
        portions.to_sql("portions", con, if_exists="append", index=False)
        print(f"{release:<11} {len(foods):>6} foods  {len(fn):>7} nutrient values  "
              f"{len(portions):>6} portions")

    pivot = ",\n    ".join(
        f"MAX(CASE WHEN fn.nutrient_id = {i} THEN fn.amount_per_100g END) AS {name}"
        for i, (name, _) in NUTRIENTS.items())
    con.execute(f"""
CREATE VIEW food_kidney AS
SELECT f.fdc_id, f.description, f.dataset, f.category, f.fndds_food_code,
    {pivot}
FROM foods f
LEFT JOIN food_nutrients fn ON fn.fdc_id = f.fdc_id
GROUP BY f.fdc_id""")
    con.commit()

    k = con.execute("SELECT COUNT(*), SUM(potassium_mg IS NOT NULL), "
                    "SUM(phosphorus_mg IS NOT NULL) FROM food_kidney").fetchone()
    print(f"Wrote {DB_PATH}: {k[0]} foods, potassium known for {k[1]}, phosphorus for {k[2]}")
    con.close()


if __name__ == "__main__":
    main()
