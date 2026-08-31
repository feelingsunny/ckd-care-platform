# Findings: NHANES 2017-2018 diet/activity vs. kidney markers

n=5,154 adults with valid creatinine; n=4,653 after dropping missing diet/activity
fields. eGFR computed via the race-free 2021 CKD-EPI creatinine equation.

## eGFR

- Demographics alone (age + sex): R²=0.497 — age dominates (93% of feature
  importance in a gradient boosting model).
- + diet (protein, sodium, potassium, phosphorus intake): +0.005 R².
- + activity (weekly moderate/vigorous minutes, sedentary minutes/day): +0.005 R².
- Individual coefficients are statistically significant (e.g. more sedentary time
  associates with lower eGFR, p<0.001, consistent with published UK Biobank findings)
  but the practical signal from one day of data is small.
- CKD subgroup (eGFR<60, n=385): gradient boosting 5-fold CV R² = -0.168 (negative —
  overfitting noise on a subsample this small, not a real negative finding about
  diet/activity).

## Serum potassium

- Demographics alone: R²=0.051.
- + diet: +0.006 R². + activity: +0.001 R² — proportionally a much bigger relative
  gain than for eGFR.
- Dietary potassium intake is a significant, positive predictor of serum potassium
  (p<0.001) even after controlling for eGFR — independent of kidney function.
- Binned analysis: dietary potassium tracks serum potassium consistently across all
  three eGFR tertiles (low/mid/high kidney function).
- Gradient boosting: 5-fold CV R²=0.087 (modest, real, positive out-of-sample).
  Feature importance: eGFR (27%) > age (22%) > sex (18%) > dietary potassium (11%)
  > sodium:potassium ratio (8%) > other diet/activity variables.
- CKD subgroup (n=385): again too small for reliable nonlinear modeling (negative CV R²).

## Interpretation

The core mechanism holds: dietary potassium has a real, independent, mechanistically
sensible relationship with serum potassium, validated in real (not synthetic)
population data. But a single day's recall + coarse activity questionnaire is a noisy
proxy — explaining only a few points of R² beyond demographics. A personal model with
repeated logging over weeks/months should outperform this population snapshot,
because: (a) repeated measurements average out day-to-day noise, (b) it captures
individual sensitivity (how reactive *this* patient's potassium is to diet, which
varies a lot person to person), and (c) within-person tracking avoids the
between-person confounding (medications, unmeasured comorbidities, genetics) that
limits a cross-sectional regression like this one.

## Next steps

1. Pool additional NHANES cycles (2011-2012, 2013-2014, 2015-2016, optionally
   2021-2023) to grow the CKD subgroup (eGFR<60) from ~385 to several thousand, for a
   reliable CKD-specific model.
2. Consider cystatin C as a creatinine-independent kidney marker — mechanistically
   attractive because it isn't affected by muscle mass or protein intake the way
   creatinine is (which may explain the small negative association we found between
   protein intake and creatinine-based eGFR — a known creatinine artifact, not
   necessarily a true kidney effect). NHANES does not include cystatin C in any
   recent cycle (checked 2007-2008, 2015-2016, 2017-2018) — only in 1988-1994 and
   1999-2002 as a special surplus-specimen sub-study, so this would need a
   different/additional data source, not an extension of the current cohort.
3. Design the personal (within-patient) calibration layer that uses this
   population-level analysis as a starting prior, then updates per patient as their
   own logs and lab draws accumulate.
