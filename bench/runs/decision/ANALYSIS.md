# Frozen-set analysis: tier dev (FROZEN_SET.md §11, rubric 2026-10-21)

- **Not confirmatory.** development set: in-sample, never confirmatory (§8)
- exercises: 25; model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off
- C1 (confirmatory configuration) = gate v1, C2 = gate v2 (descriptive, §8)

## Demo-gate decision (§8): **v1**

v1 passes 14 / 25 development exercises, v2 passes 6 (strict rule: the 8 turns CORRECT on every seed). Rule: v2 if it passes at least as many development exercises as v1 (strict rule of §6.3), ties to v2 (§8). In-sample figures.

## Gate v1 (C1), seeds 1, 2, 3

### Primary endpoints (§11.1)

1. Exercises failed (a turn not CORRECT on any seed): **11 / 25 = 44.0 % (exact 95 % CI 24.4-65.1 %)** (ex01_iv_bolus, ex08_oral_1, ex11_pk2_iv_bolus, ex13_oral_1, ex14_iv_bolus, ex16_pk2_oral_1, ex17_oral_1, ex18_pk2_iv_bolus, ex20_iv_infusion, ex24_pk2_iv_bolus, ex25_oral_1)
2. Exercises with an unverifiable quantity shown on any seed: **3 / 25 = 12.0 % (exact 95 % CI 2.5-31.2 %)** (ex14_iv_bolus, ex20_iv_infusion, ex25_oral_1)
   Gate v1: a number that appears in no tool text and no user message, shown with its badge.

### pass^k next to the per-turn rate

| | value |
|---|---|
| turns CORRECT (descriptive, cluster bootstrap 95 %) | 583 / 600 = 97.2 % (95.7 %-98.7 %) |
| pass^1 (mean pass rate over seeds) | 80.0 % |
| pass^2 (2 seeds drawn) | 66.7 % |
| pass^3 (strict rule of §6.3) | 56.0 % |

pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. Exercises with mixed outcomes across seeds (repeatability): 10 (ex01_iv_bolus, ex08_oral_1, ex11_pk2_iv_bolus, ex13_oral_1, ex16_pk2_oral_1, ex17_oral_1, ex18_pk2_iv_bolus, ex20_iv_infusion, ex24_pk2_iv_bolus, ex25_oral_1).

### Outcomes by turn kind (§6.1, all seeds)

| turn kind | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 2 | 73 |
| cmax_tmax | 0 | 0 | 0 | 0 | 1 | 74 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 75 |
| half_life | 0 | 0 | 0 | 0 | 4 | 71 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 75 |
| recall | 0 | 0 | 0 | 0 | 0 | 75 |
| compare | 0 | 0 | 1 | 0 | 9 | 65 |
| not_available | 0 | 0 | 0 | 0 | 0 | 75 |
| **total** | 0 | 0 | 1 | 0 | 16 | 583 |

### Other secondary endpoints (§11.2, descriptive)

- wrong values shown without a badge or marker (WRONG turns with nothing flagged): 13 (ex01_iv_bolus: 1, ex08_oral_1: 1, ex11_pk2_iv_bolus: 1, ex13_oral_1: 1, ex14_iv_bolus: 2, ex16_pk2_oral_1: 1, ex17_oral_1: 2, ex18_pk2_iv_bolus: 2, ex24_pk2_iv_bolus: 1, ex25_oral_1: 1)
- tool calls not valid: 0 / 421; calls whose arguments differ from the intent: 8 / 226
- regenerations: 12; time per turn median 4.5 s, 95th percentile 24.3 s; prompt tokens of the first call (median) 2964

| stratum | value | exercises passed |
|---|---|---|
| family | iv_bolus | 2 / 4 |
| family | iv_infusion | 2 / 3 |
| family | oral_0 | 3 / 3 |
| family | oral_1 | 1 / 5 |
| family | oral_1_lag | 3 / 3 |
| family | pk2_iv_bolus | 1 / 4 |
| family | pk2_oral_1 | 2 / 3 |
| dose unit | mg | 10 / 18 |
| dose unit | ug | 4 / 7 |
| time unit | h | 12 / 21 |
| time unit | min | 2 / 4 |
| BLQ | no | 13 / 23 |
| BLQ | yes | 1 / 2 |

## Gate v2 (C2), seeds 1, 2, 3

### Primary endpoints (§11.1)

1. Exercises failed (a turn not CORRECT on any seed): **19 / 25 = 76.0 % (exact 95 % CI 54.9-90.6 %)** (ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex10_oral_1_lag, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex17_oral_1, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1)
2. Exercises with an unverifiable quantity shown on any seed: **17 / 25 = 68.0 % (exact 95 % CI 46.5-85.1 %)** (ex01_iv_bolus, ex03_pk2_iv_bolus, ex05_iv_infusion, ex07_iv_bolus, ex09_pk2_oral_1, ex10_oral_1_lag, ex11_pk2_iv_bolus, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex17_oral_1, ex19_oral_1_lag, ex22_pk2_oral_1, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1)
   Gate v2: a quantity not resolved and typed from a structured result, shown as a marker.

### pass^k next to the per-turn rate

| | value |
|---|---|
| turns CORRECT (descriptive, cluster bootstrap 95 %) | 562 / 600 = 93.7 % (91.7 %-95.5 %) |
| pass^1 (mean pass rate over seeds) | 61.3 % |
| pass^2 (2 seeds drawn) | 37.3 % |
| pass^3 (strict rule of §6.3) | 24.0 % |

pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. Exercises with mixed outcomes across seeds (repeatability): 18 (ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex10_oral_1_lag, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex16_pk2_oral_1, ex17_oral_1, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1).

### Outcomes by turn kind (§6.1, all seeds)

| turn kind | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 4 | 71 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 75 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 75 |
| half_life | 0 | 0 | 1 | 0 | 4 | 70 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 1 | 74 |
| recall | 0 | 0 | 0 | 0 | 7 | 68 |
| compare | 0 | 0 | 1 | 0 | 20 | 54 |
| not_available | 0 | 0 | 0 | 0 | 0 | 75 |
| **total** | 0 | 0 | 2 | 0 | 36 | 562 |

### Other secondary endpoints (§11.2, descriptive)

- wrong values shown without a badge or marker (WRONG turns with nothing flagged): 28 (ex03_pk2_iv_bolus: 2, ex04_oral_1_lag: 1, ex06_oral_0: 1, ex07_iv_bolus: 1, ex08_oral_1: 2, ex10_oral_1_lag: 2, ex12_iv_infusion: 2, ex13_oral_1: 3, ex14_iv_bolus: 1, ex15_oral_0: 2, ex16_pk2_oral_1: 2, ex17_oral_1: 1, ex19_oral_1_lag: 1, ex20_iv_infusion: 1, ex21_oral_0: 2, ex23_iv_bolus: 2, ex25_oral_1: 2)
- tool calls not valid: 7 / 526; calls whose arguments differ from the intent: 10 / 226
- regenerations: 188; time per turn median 6.85 s, 95th percentile 43.6 s; prompt tokens of the first call (median) 3030

| stratum | value | exercises passed |
|---|---|---|
| family | iv_bolus | 1 / 4 |
| family | iv_infusion | 0 / 3 |
| family | oral_0 | 0 / 3 |
| family | oral_1 | 1 / 5 |
| family | oral_1_lag | 0 / 3 |
| family | pk2_iv_bolus | 2 / 4 |
| family | pk2_oral_1 | 2 / 3 |
| dose unit | mg | 5 / 18 |
| dose unit | ug | 1 / 7 |
| time unit | h | 5 / 21 |
| time unit | min | 1 / 4 |
| BLQ | no | 6 / 23 |
| BLQ | yes | 0 / 2 |

## Paired comparison C1 = v1 vs C2 = v2 (§11.3), descriptive in this tier

- both pass 3, neither 8, only C1 11 (ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex10_oral_1_lag, ex12_iv_infusion, ex15_oral_0, ex19_oral_1_lag, ex21_oral_0, ex23_iv_bolus), only C2 3 (ex01_iv_bolus, ex11_pk2_iv_bolus, ex18_pk2_iv_bolus)
- exact McNemar on the discordant exercises: p = 0.0574
- mean d (turns correct with C2 minus C1, per exercise, pooled over seeds): -0.035, paired bootstrap 95 % -0.062 to -0.010; sign-flip p = 0.0212
- 6 discordant exercises all in one direction are needed for p < 0.05; a non-significant result means no difference detected, not equivalence.
