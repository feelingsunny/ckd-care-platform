# Findings: NHANES 2011-2018 diet/activity vs. kidney markers

Four pooled cycles (2011-12, 2013-14, 2015-16, 2017-18). n=19,542 adults with valid
creatinine and a reliable day-1 diet recall; n=19,407 after dropping missing
diet/activity fields. CKD subgroup (eGFR<60): n=1,465 (up from 385 in the 2017-2018-only
first pass). eGFR computed via the race-free 2021 CKD-EPI creatinine equation.

Changes vs. the first pass (2017-2018 only):
- Diet is now the **mean of the day-1 and day-2 recalls** (88% of participants have a
  reliable day 2; day 1 alone otherwise), which reduces day-to-day noise.
- Added **urine albumin:creatinine ratio (UACR)** as a third marker, modeled as log(UACR).
- Added **medication flags** from the prescription file: ACE inhibitor/ARB,
  K-sparing diuretic/MRA, loop/thiazide diuretic, potassium supplement.

All models below are unweighted (the pooled 8-year MEC weight `WTMEC8YR` is in the
dataset for future survey-weighted estimates).

## eGFR

- Demographics alone (age + sex): R²=0.493. Age is 96% of gradient boosting importance.
- + diet: +0.004 R². + activity: +0.006 R².
- More sedentary time associates with lower eGFR (p<0.001), and higher protein intake
  with slightly lower creatinine-based eGFR (p<0.001; likely a creatinine artifact, see
  next steps).
- CKD subgroup (n=1,465): gradient boosting 5-fold CV R² = 0.004 (+/-0.008). With
  enough data the negative R² from the first pass is gone, but diet/activity still
  explain essentially none of the eGFR variation among people who already have CKD.
  That's a real (if disappointing) cross-sectional result now, not a sample-size artifact.

## Serum potassium

- Demographics alone: R²=0.053. + diet: +0.005. + activity: +0.001.
- Controlling for eGFR **and medications**, dietary potassium remains a significant,
  positive predictor of serum potassium (p<0.001). Medications behave as expected:
  loop/thiazide diuretics lower serum K (-0.20 mmol/L), ACE inhibitors/ARBs raise it
  (+0.06 mmol/L).
- Gradient boosting: 5-fold CV R²=0.114 (first pass: 0.087). Feature importance:
  eGFR (34%) > age (18%) > loop/thiazide diuretic (17%) > sex (16%) >
  sodium:potassium ratio (5%) > dietary potassium (4%) > others.
- CKD subgroup (n=1,461): CV R²=0.052 (first pass: negative). Dietary potassium and the
  Na:K ratio rank 4th-5th (8% each), behind eGFR, diuretics and age.

## UACR (new)

- Demographics alone: R²=0.082. + diet: +0.005. + activity: +0.001.
- Higher dietary potassium (p<0.001) and more weekly activity (p<0.001) associate with
  **lower** UACR. Plausible (potassium-rich diets and exercise lower BP), but likely
  confounded by overall health and diet quality in a cross-sectional sample.
- Gradient boosting: CV R²=0.190 all adults, 0.210 in the CKD subgroup, mostly driven
  by eGFR and age. Among CKD patients, dietary sodium and the Na:K ratio are the top
  diet features (8% and 5% importance).

## Interpretation

Pooling four cycles and averaging two diet days fixed the sample-size problem: every
CKD-subgroup model now has a non-negative out-of-sample R². The core mechanism holds
with tighter estimates: dietary potassium relates to serum potassium independent of
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

1. Survey-weighted estimates (`WTMEC8YR`, `SDMVSTRA`, `SDMVPSU`) for population-
   representative coefficients.
2. Objective activity: NHANES 2011-2014 wrist accelerometry (`PAXDAY_G/H`) in place of
   the self-reported questionnaire.
3. Cystatin C as a creatinine-independent kidney marker. It isn't affected by muscle
   mass or protein intake, which may explain the negative protein/eGFR association.
   NHANES only has cystatin C in 1988-1994 and 1999-2002 (surplus-specimen sub-study),
   so this needs a different/additional data source.
4. Design the personal (within-patient) calibration layer that uses this
   population-level analysis as a starting prior, then updates per patient as their
   own logs and lab draws accumulate.
