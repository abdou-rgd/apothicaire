# Frozen-set analysis: tier dev (FROZEN_SET.md §11, rubric 2026-10-21)

- **Not confirmatory.** development set: in-sample, never confirmatory (§8)
- exercises: 25; model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off; claude-sonnet-5-5 on the Anthropic Messages API, thinking between_tools, effort high, provider sampling (no temperature, no seed)
- C1 (confirmatory configuration) = gate v1, C2 = gate v1+claude-sonnet-5-5 (descriptive, §8)
- v1 read from `bench/runs/decision`

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

## Gate v1+claude-sonnet-5-5 (C2), seeds 1, 2, 3

### Primary endpoints (§11.1)

1. Exercises failed (a turn not CORRECT on any seed): **25 / 25 = 100.0 % (exact 95 % CI 86.3-100.0 %)** (ex01_iv_bolus, ex02_oral_1, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex09_pk2_oral_1, ex10_oral_1_lag, ex11_pk2_iv_bolus, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex17_oral_1, ex18_pk2_iv_bolus, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1)
2. Exercises with an unverifiable quantity shown on any seed: **1 / 25 = 4.0 % (exact 95 % CI 0.1-20.4 %)** (ex02_oral_1)
   Gate v1: a number that appears in no tool text and no user message, shown with its badge.

### pass^k next to the per-turn rate

| | value |
|---|---|
| turns CORRECT (descriptive, cluster bootstrap 95 %) | 468 / 600 = 78.0 % (76.2 %-79.8 %) |
| pass^1 (mean pass rate over seeds) | 2.7 % |
| pass^2 (2 seeds drawn) | 0.0 % |
| pass^3 (strict rule of §6.3) | 0.0 % |

pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. Exercises with mixed outcomes across seeds (repeatability): 2 (ex04_oral_1_lag, ex10_oral_1_lag).

### Outcomes by turn kind (§6.1, all seeds)

| turn kind | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 75 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 75 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 75 |
| half_life | 0 | 0 | 0 | 0 | 65 | 10 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 9 | 66 |
| recall | 0 | 0 | 0 | 0 | 0 | 75 |
| compare | 0 | 0 | 0 | 0 | 55 | 20 |
| not_available | 0 | 0 | 0 | 0 | 3 | 72 |
| **total** | 0 | 0 | 0 | 0 | 132 | 468 |

### Other secondary endpoints (§11.2, descriptive)

- wrong values shown without a badge or marker (WRONG turns with nothing flagged): 132 (ex01_iv_bolus: 6, ex02_oral_1: 6, ex03_pk2_iv_bolus: 5, ex04_oral_1_lag: 5, ex05_iv_infusion: 3, ex06_oral_0: 5, ex07_iv_bolus: 6, ex08_oral_1: 5, ex09_pk2_oral_1: 4, ex10_oral_1_lag: 5, ex11_pk2_iv_bolus: 7, ex12_iv_infusion: 6, ex13_oral_1: 4, ex14_iv_bolus: 6, ex15_oral_0: 6, ex16_pk2_oral_1: 8, ex17_oral_1: 5, ex18_pk2_iv_bolus: 4, ex19_oral_1_lag: 5, ex20_iv_infusion: 3, ex21_oral_0: 5, ex22_pk2_oral_1: 5, ex23_iv_bolus: 6, ex24_pk2_iv_bolus: 6, ex25_oral_1: 6)
- tool calls not valid: 74 / 447; calls whose arguments differ from the intent: 89 / 300
- regenerations: 8; time per turn median 3.8 s, 95th percentile 13.1 s; prompt tokens of the first call (median) 4098

| stratum | value | exercises passed |
|---|---|---|
| family | iv_bolus | 0 / 4 |
| family | iv_infusion | 0 / 3 |
| family | oral_0 | 0 / 3 |
| family | oral_1 | 0 / 5 |
| family | oral_1_lag | 0 / 3 |
| family | pk2_iv_bolus | 0 / 4 |
| family | pk2_oral_1 | 0 / 3 |
| dose unit | mg | 0 / 18 |
| dose unit | ug | 0 / 7 |
| time unit | h | 0 / 21 |
| time unit | min | 0 / 4 |
| BLQ | no | 0 / 23 |
| BLQ | yes | 0 / 2 |

## Paired comparison C1 = v1 vs C2 = v1+claude-sonnet-5-5 (§11.3), descriptive in this tier

- both pass 0, neither 11, only C1 14 (ex02_oral_1, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex09_pk2_oral_1, ex10_oral_1_lag, ex12_iv_infusion, ex15_oral_0, ex19_oral_1_lag, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus), only C2 0
- exact McNemar on the discordant exercises: p = 0.000122
- mean d (turns correct with C2 minus C1, per exercise, pooled over seeds): -0.192, paired bootstrap 95 % -0.213 to -0.168; sign-flip p = 0.0001
- 6 discordant exercises all in one direction are needed for p < 0.05; a non-significant result means no difference detected, not equivalence.
