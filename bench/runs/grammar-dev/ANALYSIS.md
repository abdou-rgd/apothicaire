# Frozen-set analysis: tier dev (FROZEN_SET.md §11, rubric 2026-10-21)

- **Not confirmatory.** development set: in-sample, never confirmatory (§8); gate v3: exploratory arm (GRAMMAR_ARM.md), v2 plus a grammar on the one regeneration
- exercises: 25; model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off
- exploratory arm: gate v3 (GRAMMAR_ARM.md); the other configurations are stored runs, read and not rerun
- v1 read from `bench/runs/decision`
- v2 read from `bench/runs/decision`

## Grammar arm: gate v3 next to v1 and v2 (GRAMMAR_ARM.md §4 and §5)

Development set, in-sample, exploratory. The thresholds were fixed before the run command existed (`bench/GRAMMAR_ARM.md`, `bench/frozen/LEDGER.md` of 2026-10-23); if this section and that text disagree, the text wins. v1 and v2 are the stored runs of the demo-gate decision, read here and not rerun.

| Measure | v1 | v2 | v3 | Success | Kill |
|---|---|---|---|---|---|
| free digits shown | n/a | 5 | 2 | 0 |  |
| exercises with an unverifiable quantity shown | 3 / 25 | 17 / 25 | 5 / 25 | at most 3 / 25 |  |
| turns CORRECT | 583 / 600 | 562 / 600 | 557 / 600 | at least 576 / 600 | fewer than 562 / 600 |
| regenerations | 12 | 188 | 183 | at most 50 |  |
| median time per turn | 4.5 s | 6.85 s | 6.2 s | at most 9 s | more than 13.5 s |
| LOOP + ABSTAINED turns | 1 | 2 | 7 |  | more than 12 of 600 |
| the server enforces the grammar | n/a | n/a | yes | | it does not |
| exercises passed (strict rule of §6.3, descriptive) | 14 / 25 | 6 / 25 | 5 / 25 |  |  |
| 95th percentile time per turn (descriptive) | 24.3 s | 43.6 s | 42.8 s |  |  |

**Validity:** valid.
**Kill conditions:** 557 / 600 turns CORRECT, fewer than 562 / 600.

| Success threshold of §4 | gate v3 | rule | met |
|---|---|---|---|
| free digits shown | 2 | 0 | no |
| exercises with an unverifiable quantity shown | 5 / 25 | at most 3 / 25 | no |
| turns CORRECT | 557 / 600 | at least 576 / 600 | no |
| median time per turn | 6.2 s | at most 9 s | yes |
| regenerations | 183 | at most 50 | no |

**Reading (GRAMMAR_ARM.md §5): killed.**

### What the regenerations say about the grammar (gate v3)

| | |
|---|---|
| gate records / of which not gate v3 | 600 / 0 |
| regenerations / sent with a grammar | 183 / 183 |
| server errors (the first answer is kept) / of which mention the grammar | 0 / 0 |
| text obeyed the grammar (accepted) | 183 |
| text cut at max_tokens (only a valid prefix is owed) | 0 |
| violations (a refused character, or a stop where the grammar cannot end) | 0 |
| kept | first: 2, regenerated: 181 |
| regeneration call, median wall time | 13.15 s (v2: 13.13 s) |
| grammar, rules / bytes / build ms: median (largest) | 414 (953) / 39620 (71332) / 16.2 (54.4) |

### Findings of gate v2 left in the answers shown, by kind

| kind | v2 | v3 |
|---|---|---|
| adjacent_to_reference | 55 | 5 |
| bare_number | 5 | 2 |
| number_word | 0 | 4 |
| unresolved_reference | 33 | 0 |
| untyped_reference | 0 | 1 |

- v3 against v2 (exact McNemar on the exercises passed, descriptive): both pass 2, neither 16, only v2 4, only v3 3; p = 1
- v3 against v1 (exact McNemar on the exercises passed, descriptive): both pass 2, neither 8, only v1 12, only v3 3; p = 0.0352

The `caladrius-mcp` hash is not recorded in the run folder: check it with `sha256sum` before the run (GRAMMAR_ARM.md §3) and write it in the ledger entry that follows the run.

## Gate v1 (stored run), seeds 1, 2, 3

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

## Gate v2 (stored run), seeds 1, 2, 3

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

## Gate v3 (exploratory arm), seeds 1, 2, 3

### Primary endpoints (§11.1)

1. Exercises failed (a turn not CORRECT on any seed): **20 / 25 = 80.0 % (exact 95 % CI 59.3-93.2 %)** (ex01_iv_bolus, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex09_pk2_oral_1, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex18_pk2_iv_bolus, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex25_oral_1)
2. Exercises with an unverifiable quantity shown on any seed: **5 / 25 = 20.0 % (exact 95 % CI 6.8-40.7 %)** (ex12_iv_infusion, ex14_iv_bolus, ex18_pk2_iv_bolus, ex20_iv_infusion, ex23_iv_bolus)
   Gate v2: a quantity not resolved and typed from a structured result, shown as a marker. Gate v3 reads every answer with gate v2.

### pass^k next to the per-turn rate

| | value |
|---|---|
| turns CORRECT (descriptive, cluster bootstrap 95 %) | 557 / 600 = 92.8 % (90.7 %-95.0 %) |
| pass^1 (mean pass rate over seeds) | 62.7 % |
| pass^2 (2 seeds drawn) | 37.3 % |
| pass^3 (strict rule of §6.3) | 20.0 % |

pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. Exercises with mixed outcomes across seeds (repeatability): 19 (ex01_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex09_pk2_oral_1, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex18_pk2_iv_bolus, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex25_oral_1).

### Outcomes by turn kind (§6.1, all seeds)

| turn kind | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 4 | 71 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 75 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 75 |
| half_life | 0 | 0 | 2 | 0 | 7 | 66 |
| lambda_z_regression | 0 | 0 | 4 | 0 | 1 | 70 |
| recall | 0 | 0 | 0 | 0 | 8 | 67 |
| compare | 0 | 0 | 1 | 0 | 16 | 58 |
| not_available | 0 | 0 | 0 | 0 | 0 | 75 |
| **total** | 0 | 0 | 7 | 0 | 36 | 557 |

### Other secondary endpoints (§11.2, descriptive)

- wrong values shown without a badge or marker (WRONG turns with nothing flagged): 34 (ex03_pk2_iv_bolus: 3, ex04_oral_1_lag: 1, ex06_oral_0: 2, ex07_iv_bolus: 1, ex08_oral_1: 2, ex09_pk2_oral_1: 1, ex12_iv_infusion: 1, ex13_oral_1: 4, ex14_iv_bolus: 1, ex15_oral_0: 1, ex16_pk2_oral_1: 2, ex18_pk2_iv_bolus: 3, ex19_oral_1_lag: 1, ex20_iv_infusion: 3, ex21_oral_0: 2, ex22_pk2_oral_1: 2, ex23_iv_bolus: 1, ex25_oral_1: 3)
- tool calls not valid: 3 / 505; calls whose arguments differ from the intent: 6 / 225
- regenerations: 183; time per turn median 6.2 s, 95th percentile 42.8 s; prompt tokens of the first call (median) 3030

| stratum | value | exercises passed |
|---|---|---|
| family | iv_bolus | 0 / 4 |
| family | iv_infusion | 0 / 3 |
| family | oral_0 | 0 / 3 |
| family | oral_1 | 2 / 5 |
| family | oral_1_lag | 1 / 3 |
| family | pk2_iv_bolus | 2 / 4 |
| family | pk2_oral_1 | 0 / 3 |
| dose unit | mg | 4 / 18 |
| dose unit | ug | 1 / 7 |
| time unit | h | 5 / 21 |
| time unit | min | 0 / 4 |
| BLQ | no | 5 / 23 |
| BLQ | yes | 0 / 2 |
