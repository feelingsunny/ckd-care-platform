# CKD Diet & Activity Marker Forecasting — Data Exploration

Early-stage data science for a chronic kidney disease (CKD) management platform: exploring
how much diet and physical activity behavior actually explains/predicts kidney markers
(eGFR, serum potassium, urine albumin:creatinine ratio), as groundwork for a personal, longitudinal forecasting model.

## Status

Cross-sectional, population-level analysis using real public NHANES data (not
synthetic), pooled across four cycles (2011-2018). Establishes that the mechanism is real (diet, especially potassium
intake, measurably relates to serum potassium independent of kidney function) while
showing why a population snapshot alone isn't enough to forecast an individual patient —
see `data/FINDINGS.md` for the full write-up.

## Data source

[NHANES](https://www.cdc.gov/nchs/nhanes/) (National Health and Nutrition Examination
Survey), U.S. CDC/NCHS. Public domain — no commercial-use restriction, only standard
confidentiality terms (no re-identification, no linking to identify individuals, cite
the source).

Raw `.XPT` files are **not** committed to this repo (they're a few MB each and easy to
re-download). To reproduce from scratch, download these seven files per NHANES cycle from
`https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/<year>/DataFiles/<FILE>.xpt` and place them
in `raw/`:

| Component | 2017-2018 | 2015-2016 | 2013-2014 | 2011-2012 |
|---|---|---|---|---|
| Demographics | DEMO_J | DEMO_I | DEMO_H | DEMO_G |
| Diet (Day 1 totals) | DR1TOT_J | DR1TOT_I | DR1TOT_H | DR1TOT_G |
| Standard Biochemistry Profile | BIOPRO_J | BIOPRO_I | BIOPRO_H | BIOPRO_G |
| Physical Activity Questionnaire | PAQ_J | PAQ_I | PAQ_H | PAQ_G |
| Diet (Day 2 totals) | DR2TOT_J | DR2TOT_I | DR2TOT_H | DR2TOT_G |
| Urine Albumin & Creatinine | ALB_CR_J | ALB_CR_I | ALB_CR_H | ALB_CR_G |
| Prescription Medications | RXQ_RX_J | RXQ_RX_I | RXQ_RX_H | RXQ_RX_G |

(Folder in the URL = the first year of the cycle, e.g. `.../Public/2017/DataFiles/DEMO_J.xpt`.)

## Pipeline

1. `01_build_dataset.py` — for each of the four cycles, merges the raw files on
   participant ID (`SEQN`), then stacks the cycles. Averages day-1 and day-2 diet
   recalls, computes eGFR via the race-free 2021 CKD-EPI creatinine equation, derives
   weekly moderate/vigorous activity minutes from the GPAQ-style questionnaire fields,
   adds UACR and medication flags (ACE inhibitor/ARB, K-sparing diuretic, loop/thiazide
   diuretic, potassium supplement), and a pooled 8-year MEC weight. Writes
   `data/analysis_dataset.csv`.
2. `02_analyze.py` — OLS variance-decomposition (demographics -> +diet -> +activity) for
   eGFR, serum potassium and log(UACR), plus gradient boosting models (overall and CKD subgroup,
   eGFR<60) with 5-fold cross-validation and feature importances. Writes
   `data/analysis_dataset_clean.csv`.
3. `03_plots.py` — generates the three figures in `figures/`.

```bash
pip install pandas pyreadstat scikit-learn statsmodels matplotlib
python 01_build_dataset.py
python 02_analyze.py
python 03_plots.py
```

## Key findings (2011-2018 pooled, n=19,407 adults; CKD subgroup n=1,465)

- eGFR is dominated by age; two days of diet + self-reported activity add only ~0.01 R²
  beyond demographics, and essentially nothing within the CKD subgroup.
- Dietary potassium is a significant, independent predictor of serum potassium
  (p<0.001) after controlling for eGFR **and** potassium-affecting medications.
  Serum potassium model CV R² = 0.114 overall, 0.052 in CKD (first pass: negative in CKD).
- UACR (new) is the marker most linked to modifiable behavior: higher potassium intake
  and more activity associate with lower UACR; in CKD patients, dietary sodium and the
  Na:K ratio are the top diet features.
- Pooling fixed the sample-size problem (all CKD-subgroup models now have non-negative
  CV R²), but a between-person snapshot still explains little. That's the case for
  personal, longitudinal tracking.

Full write-up: `data/FINDINGS.md`.

## Data use note

NHANES data itself is public domain. Other CKD-related research datasets referenced in
project planning (CRIC, Look AHEAD, MDRD via the NIDDK Central Repository; UK Biobank)
carry data-use agreements that restrict commercial redistribution — read those closely
before relying on them for anything beyond research validation.
