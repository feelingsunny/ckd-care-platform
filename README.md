# CKD Diet & Activity Marker Forecasting — Data Exploration

Early-stage data science for a chronic kidney disease (CKD) management platform: exploring
how much diet and physical activity behavior actually explains/predicts kidney markers
(eGFR, serum potassium), as groundwork for a personal, longitudinal forecasting model.

## Status

First pass, cross-sectional, population-level analysis using real public NHANES data
(not synthetic). Establishes that the mechanism is real (diet, especially potassium
intake, measurably relates to serum potassium independent of kidney function) while
showing why a population snapshot alone isn't enough to forecast an individual patient —
see `data/FINDINGS.md` for the full write-up.

## Data source

[NHANES](https://www.cdc.gov/nchs/nhanes/) (National Health and Nutrition Examination
Survey), U.S. CDC/NCHS. Public domain — no commercial-use restriction, only standard
confidentiality terms (no re-identification, no linking to identify individuals, cite
the source).

Raw `.XPT` files are **not** committed to this repo (they're a few MB each and easy to
re-download). To reproduce from scratch, download these four files per NHANES cycle from
`https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/<year>/DataFiles/<FILE>.xpt` and place them
in `raw/`:

| Component | 2017-2018 | 2015-2016 | 2013-2014 | 2011-2012 |
|---|---|---|---|---|
| Demographics | DEMO_J | DEMO_I | DEMO_H | DEMO_G |
| Diet (Day 1 totals) | DR1TOT_J | DR1TOT_I | DR1TOT_H | DR1TOT_G |
| Standard Biochemistry Profile | BIOPRO_J | BIOPRO_I | BIOPRO_H | BIOPRO_G |
| Physical Activity Questionnaire | PAQ_J | PAQ_I | PAQ_H | PAQ_G |

(Folder in the URL = the first year of the cycle, e.g. `.../Public/2017/DataFiles/DEMO_J.xpt`.)

## Pipeline

1. `01_build_dataset.py` — merges the four raw files on participant ID (`SEQN`), computes
   eGFR via the race-free 2021 CKD-EPI creatinine equation, derives weekly
   moderate/vigorous activity minutes from the GPAQ-style questionnaire fields. Writes
   `data/analysis_dataset.csv`.
2. `02_analyze.py` — OLS variance-decomposition (demographics -> +diet -> +activity) for
   eGFR and serum potassium, plus gradient boosting models (overall and CKD subgroup,
   eGFR<60) with 5-fold cross-validation and feature importances. Writes
   `data/analysis_dataset_clean.csv`.
3. `03_plots.py` — generates the three figures in `figures/`.

```bash
pip install pandas pyreadstat scikit-learn statsmodels matplotlib
python 01_build_dataset.py
python 02_analyze.py
python 03_plots.py
```

## Key finding (2017-2018 cycle, n=4,653 adults)

- eGFR is ~93% explained by age alone; one day of diet + self-reported activity adds
  only ~0.01 R² beyond demographics.
- Dietary potassium intake is a significant, independent predictor of serum potassium
  (p<0.001) even after controlling for eGFR — the mechanism holds in real population
  data, but the practical signal from a single snapshot is small.
- The CKD-specific subgroup (eGFR<60) was too small in one cycle (n=385) for the
  nonlinear model to generalize (negative cross-validated R²) — a sample-size problem,
  not a mechanism problem. Next step: pool additional NHANES cycles (2011-2018,
  optionally 2021-2023) to grow this subgroup into the thousands.

Full write-up: `data/FINDINGS.md`.

## Data use note

NHANES data itself is public domain. Other CKD-related research datasets referenced in
project planning (CRIC, Look AHEAD, MDRD via the NIDDK Central Repository; UK Biobank)
carry data-use agreements that restrict commercial redistribution — read those closely
before relying on them for anything beyond research validation.
