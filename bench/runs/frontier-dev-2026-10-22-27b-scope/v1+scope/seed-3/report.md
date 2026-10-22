# Apothicaire benchmark report

date: 2026-10-22, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, prompt addendum scope, gate: v1

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **8 / 881 = 0.9 %** (95 % CI, exercises resampled: 0.2-1.8 %, descriptive)
- in the answers shown (gate in the loop): **0 / 873 = 0.0 %** (none observed; descriptive, see the exercise level below)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 5 before, 0 after; regenerated 5 (regeneration kept 5); turns shown with the badge: 0

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **7 / 25 = 28.0 % (exact 95 % CI 12.1-49.4 %)** (ex09_pk2_oral_1, ex14_iv_bolus, ex18_pk2_iv_bolus, ex20_iv_infusion, ex22_pk2_oral_1, ex24_pk2_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **0 / 25 (one-sided 95 % upper bound 11.3 %)**

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 8 | 0 |
| unlabelled_misread | 0 | 0 |
| recall_error | 0 | 0 |
| other | 0 | 0 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.8 % | 3.8 % |
| arithmetic | 0.0 % | 22.0 % |
| unlabelled_misread | 11.6 % | 8.4 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.6 % | 65.8 % |

## Correctness (development scorer `score_turn`): 197 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 542 / 550; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 24 (96.0 %) | 221 / 225 | 2 / 409 | 0 / 407 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 58 | 0 / 58 |
| clearance_volume | 25 | 24 (96.0 %) | 48 / 50 | 0 / 52 | 0 / 52 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 / 146 | 0 / 146 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 / 78 | 0 / 78 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 24 (96.0 %) | 90 / 92 | 6 / 110 | 0 / 104 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 0 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (26 calls, 26 valid; 26 calls in all turns); usable in 21 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 192 / 200 turns CORRECT; exercises with all turns CORRECT 18 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 1 | 24 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 1 | 24 |
| half_life | 0 | 0 | 0 | 0 | 2 | 23 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 1 | 0 | 3 | 21 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 1 | 0 | 7 | 192 |

## Oracle check: 171 / 175 turns = 97.7 % (95 % CI, exercises resampled: 94.9-100.0 %); 541 / 550 expected numbers = 98.4 % (95 % CI, exercises resampled: 95.8-100.0 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 24 (96.0 %) | 221 / 225 | 4 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 25 | 24 (96.0 %) | 48 / 50 | 2 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 23 (92.0 %) | 89 / 92 | 0 | 0 | 0 | 0 | 0 | 3 |
| **total** | 175 | 171 (97.7 %) | 541 / 550 | 6 | 0 | 0 | 0 | 0 | 3 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 1 (ex03_pk2_iv_bolus t7 AUC(0-tlast) linear (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 1 (ex03_pk2_iv_bolus t7 compare); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 1 import_nca | AUC(0-inf) | wrong_parameter | aucinf.pred | 24546.3 h*ng/ml |
| ex14_iv_bolus | 1 import_nca | CL | wrong_parameter | cl.pred | 6.11091 l/h |
| ex14_iv_bolus | 1 import_nca | Vz | wrong_parameter | vz.pred | 44.4499 l |
| ex14_iv_bolus | 1 import_nca | MRT | wrong_parameter | mrt.iv.pred | 7.07313 h |
| ex14_iv_bolus | 3 clearance_volume | CL | wrong_parameter | cl.pred | 6.11091 l/h |
| ex14_iv_bolus | 3 clearance_volume | Vz | wrong_parameter | vz.pred | 44.4499 l |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |

## Tool calls: 160 valid, 0 invalid, 0 failed of 160 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 0; by tool: {'analysis_compare': 26, 'analysis_get': 59, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 6 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 3 |
| data_import: columns.unit = [] (intended ["min", "ng/mL"]) | 1 |
| nca_run: name = "NCA exercice lin_up_log_down" (intended null) | 1 |
| nca_run: options.units = null (intended {"time": "min", "concentration": "ng/mL", "dose": "mg"}) | 1 |

In exercises: ex05_iv_infusion, ex12_iv_infusion, ex18_pk2_iv_bolus, ex20_iv_infusion, ex24_pk2_iv_bolus, ex25_oral_1. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 7.9 s per turn, mean 5153 prompt tokens (first call), total 44 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 0 / 38 | 0 / 38 | 8 / 8 | 0 | 8 / 8 | 8.9 |
| ex02_oral_1 | 400 mg | h, ng/mL | 0 / 39 | 0 / 39 | 8 / 8 | 0 | 5 / 5 | 6.5 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 7 / 7 | 8.6 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 0 / 37 | 0 / 37 | 8 / 8 | 0 | 5 / 5 | 5.9 |
| ex05_iv_infusion | 150 mg | h, mg/L | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 7 / 7 | 8.2 |
| ex06_oral_0 | 100 mg | h, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 6.2 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 0 / 47 | 0 / 47 | 8 / 8 | 0 | 7 / 7 | 9.5 |
| ex08_oral_1 | 800 ug | min, ng/mL | 0 / 29 | 0 / 29 | 8 / 8 | 0 | 7 / 7 | 7.8 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 7 / 7 | 7.6 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 5 / 5 | 6.2 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 0 / 38 | 0 / 38 | 8 / 8 | 0 | 8 / 8 | 9.6 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 1 / 37 | 0 / 36 | 8 / 8 | 0 | 7 / 7 | 10.0 |
| ex13_oral_1 | 50 mg | h, ng/mL | 1 / 27 | 0 / 26 | 8 / 8 | 0 | 7 / 7 | 9.1 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 0 / 29 | 0 / 29 | 6 / 8 | 0 | 8 / 8 | 8.8 |
| ex15_oral_0 | 400 mg | h, mg/L | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 6 / 6 | 6.7 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 0 / 30 | 0 / 30 | 8 / 8 | 0 | 7 / 7 | 7.4 |
| ex17_oral_1 | 500 mg | h, mg/L | 0 / 38 | 0 / 38 | 8 / 8 | 0 | 5 / 5 | 6.3 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 0 / 34 | 0 / 34 | 7 / 8 | 0 | 6 / 6 | 8.8 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 7 / 7 | 7.7 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 3 / 39 | 0 / 36 | 8 / 8 | 0 | 5 / 5 | 7.2 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 0 / 33 | 0 / 33 | 8 / 8 | 0 | 7 / 7 | 7.7 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 6.5 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 0 / 39 | 0 / 39 | 8 / 8 | 0 | 7 / 7 | 8.6 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 1 / 32 | 0 / 31 | 8 / 8 | 0 | 7 / 7 | 9.7 |
| ex25_oral_1 | 100 mg | h, ng/mL | 2 / 35 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 7.4 |
