# Findings: NHANES 2011-2023 diet/activity vs. kidney markers

Five pooled cycles (2011-12, 2013-14, 2015-16, 2017-18, 2021-23). n=24,047 adults with
valid creatinine and a reliable day-1 diet recall; n=23,779 after dropping missing
diet/activity fields. CKD subgroup (eGFR<60): n=1,839 (385 in the 2017-2018-only first
pass, 1,465 with 2011-2018). eGFR computed via the race-free 2021 CKD-EPI creatinine
equation.

How the analysis has grown:
- First pass: 2017-2018 only, day-1 diet, eGFR and serum potassium.
- Second pass: pooled 2011-2018; diet is the **mean of the day-1 and day-2 recalls**
  (88% of participants have a reliable day 2; day 1 alone otherwise); added **UACR**
  (modeled as log(UACR)) and **medication flags** (ACE inhibitor/ARB, K-sparing
  diuretic/MRA, loop/thiazide diuretic, potassium supplement).
- This pass: added **2021-2023**. Two things changed in that cycle:
  - **Activity:** the questionnaire was redesigned and asks about leisure-time activity
    only (no work activity). All cycles now use **leisure-time activity**
    (`rec_mvpa_min_wk`) so they stay comparable; the work + leisure measure is kept in
    the dataset for 2011-2018. The redesigned question still differs: 17% of 2021-2023
    adults report no leisure activity, against about 50% in earlier cycles.
  - **Medications:** the public 2021-2023 prescription file has no drug names, so the
    medication flags are missing for that cycle. Models that include medications
    (adjusted potassium OLS; potassium and UACR gradient boosting) use 2011-2018 only.

All models below are unweighted (the pooled MEC weight `WTMEC_POOLED` is in the
dataset for future survey-weighted estimates).

## eGFR

- Demographics alone (age + sex): R²=0.495. Age is 96% of gradient boosting importance.
- + diet: +0.004 R². + activity: +0.008 R².
- More sedentary time associates with lower eGFR (p<0.001). Higher protein intake and
  more leisure activity both associate with slightly lower creatinine-based eGFR
  (p<0.001). Both are likely creatinine artifacts (more muscle and more meat raise
  creatinine), not true kidney effects; see next steps.
- CKD subgroup (n=1,839): gradient boosting 5-fold CV R² = -0.002 (+/-0.027), i.e. no
  better than predicting the average. Diet and activity explain essentially none of
  the eGFR variation among people who already have CKD.

## Serum potassium

- Demographics alone: R²=0.055. + diet: +0.005. + activity: +0.001.
- Controlling for eGFR **and medications** (2011-2018), dietary potassium remains a
  significant, positive predictor of serum potassium (p<0.001). Medications behave as
  expected: loop/thiazide diuretics lower serum K (-0.20 mmol/L), ACE inhibitors/ARBs
  raise it (+0.06 mmol/L). Activity is not significant once these are accounted for.
- Gradient boosting (2011-2018): 5-fold CV R²=0.113 overall. Feature importance:
  eGFR (34%) > age (18%) > loop/thiazide diuretic (17%) > sex (16%) >
  sodium:potassium ratio (5%) > dietary potassium (5%) > others.
- CKD subgroup (n=1,460): CV R²=0.027 (0.052 with the work + leisure activity measure
  in the second pass). Na:K ratio and dietary potassium rank 4th-5th (9% and 7%),
  behind eGFR, diuretics and age.

## UACR

- Demographics alone: R²=0.073. + diet: +0.005. + activity: +0.003.
- Higher dietary potassium (p<0.001) and more leisure activity (p<0.001) associate with
  **lower** UACR. Plausible (potassium-rich diets and exercise lower BP), but likely
  confounded by overall health and diet quality in a cross-sectional sample.
- Gradient boosting (2011-2018): CV R²=0.190 all adults, 0.198 in the CKD subgroup,
  mostly driven by eGFR and age. Among CKD patients, dietary sodium and the Na:K ratio
  are the top diet features (6% each).

## Interpretation

Adding 2021-2023 grows the sample by about 23% and leaves the conclusions unchanged.
The core mechanism holds: dietary potassium relates to serum potassium independent of
kidney function and potassium-affecting drugs. UACR looks like the marker most
responsive to modifiable behavior (sodium, potassium, activity). That's worth
prioritizing in the platform, since albuminuria can move within weeks or months,
while eGFR moves over years.

But a between-person snapshot still explains only a few points of R² beyond
demographics. A personal model with repeated logging over weeks or months should do
better, because: (a) repeated measurements average out day-to-day noise, (b) it captures
individual sensitivity (how reactive *this* patient's potassium is to diet), and (c)
within-person tracking avoids the between-person confounding (unmeasured comorbidities,
genetics, diet quality as a marker of overall health) that limits this regression.

## Next steps

1. Survey-weighted estimates (`WTMEC_POOLED`, `SDMVSTRA`, `SDMVPSU`) for population-
   representative coefficients.
2. Objective activity: NHANES 2011-2014 wrist accelerometry (`PAXDAY_G/H`) in place of
   the self-reported questionnaire.
3. Add the 2021-2023 prescription drug names if NCHS releases them, so the medication-
   adjusted models can use all five cycles.
4. Cystatin C as a creatinine-independent kidney marker. It isn't affected by muscle
   mass or protein intake, which may explain the negative protein/eGFR and
   activity/eGFR associations. NHANES only has cystatin C in 1988-1994 and 1999-2002
   (surplus-specimen sub-study), so this needs a different/additional data source.
5. Design the personal (within-patient) calibration layer that uses this
   population-level analysis as a starting prior, then updates per patient as their
   own logs and lab draws accumulate.
