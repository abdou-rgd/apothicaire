# Frozen-set analysis: tier dev (FROZEN_SET.md §11, rubric 2026-10-21)

- **Not confirmatory.** development set: in-sample, never confirmatory (§8)
- exercises: 25; model: decision harness (decision/harness.py), decider qwen35-0.8b-d01-v2-adapters, no language model
- C1 (confirmatory configuration) = gate nolm, C2 = gate none (descriptive, §8)

## Gate nolm (C1), seeds 1, 2, 3

### Primary endpoints (§11.1)

1. Exercises failed (a turn not CORRECT on any seed): **0 / 25 (one-sided 95 % upper bound 11.3 %)**
2. Exercises with an unverifiable quantity shown on any seed: **0 / 25 (one-sided 95 % upper bound 11.3 %)**
   Decider-only arm: the harness writes engine values only; gate v1 is run on its answers and counts a number found in no tool text and no user message.

### pass^k next to the per-turn rate

| | value |
|---|---|
| turns CORRECT (descriptive, cluster bootstrap 95 %) | 600 / 600 = 100.0 % (100.0 %-100.0 %) |
| pass^1 (mean pass rate over seeds) | 100.0 % |
| pass^2 (2 seeds drawn) | 100.0 % |
| pass^3 (strict rule of §6.3) | 100.0 % |

pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. Exercises with mixed outcomes across seeds (repeatability): 0.

### Outcomes by turn kind (§6.1, all seeds)

| turn kind | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 75 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 75 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 75 |
| half_life | 0 | 0 | 0 | 0 | 0 | 75 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 75 |
| recall | 0 | 0 | 0 | 0 | 0 | 75 |
| compare | 0 | 0 | 0 | 0 | 0 | 75 |
| not_available | 0 | 0 | 0 | 0 | 0 | 75 |
| **total** | 0 | 0 | 0 | 0 | 0 | 600 |

### Other secondary endpoints (§11.2, descriptive)

- wrong values shown without a badge or marker (WRONG turns with nothing flagged): 0
- tool calls not valid: 0 / 750; calls whose arguments differ from the intent: 0 / 225
- regenerations: 0; time per turn median 0.205 s, 95th percentile 0.415 s; prompt tokens of the first call (median) 0

| stratum | value | exercises passed |
|---|---|---|
| family | iv_bolus | 4 / 4 |
| family | iv_infusion | 3 / 3 |
| family | oral_0 | 3 / 3 |
| family | oral_1 | 5 / 5 |
| family | oral_1_lag | 3 / 3 |
| family | pk2_iv_bolus | 4 / 4 |
| family | pk2_oral_1 | 3 / 3 |
| dose unit | mg | 18 / 18 |
| dose unit | ug | 7 / 7 |
| time unit | h | 21 / 21 |
| time unit | min | 4 / 4 |
| BLQ | no | 23 / 23 |
| BLQ | yes | 2 / 2 |

### Decisions against the gold decisions of each turn kind (decider-only arm, NO_LM_ARM.md §6)

A failed turn whose decisions were all right failed in the deterministic part (reader, harness, templates), not in the decision model.

| turn kind | turns | decisions all right | failed with right decisions | questions answered wrong |
|---|---|---|---|---|
| import_nca | 75 | 75 | 0 | - |
| cmax_tmax | 75 | 75 | 0 | - |
| clearance_volume | 75 | 75 | 0 | - |
| half_life | 75 | 75 | 0 | - |
| lambda_z_regression | 75 | 75 | 0 | - |
| recall | 75 | 75 | 0 | - |
| compare | 75 | 75 | 0 | - |
| not_available | 75 | 75 | 0 | - |
