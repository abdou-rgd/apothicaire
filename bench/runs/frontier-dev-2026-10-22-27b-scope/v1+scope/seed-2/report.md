# Apothicaire benchmark report

date: 2026-10-22, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, prompt addendum scope, gate: v1

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **2 / 805 = 0.2 %** (95 % CI, exercises resampled: 0.0-0.6 %, descriptive)
- in the answers shown (gate in the loop): **0 / 799 = 0.0 %** (none observed; descriptive, see the exercise level below)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 2 before, 0 after; regenerated 2 (regeneration kept 2); turns shown with the badge: 0

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **1 / 25 = 4.0 % (exact 95 % CI 0.1-20.4 %)** (ex07_iv_bolus)
- exercises in which an answer shown carried an unverified number or a marker: **0 / 25 (one-sided 95 % upper bound 11.3 %)**

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 0 | 0 |
| recall_error | 0 | 0 |
| other | 2 | 0 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.8 % |
| arithmetic | 0.0 % | 22.6 % |
| unlabelled_misread | 11.7 % | 8.5 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 65.1 % |

## Correctness (development scorer `score_turn`): 200 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 558 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 / 336 | 0 / 336 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 58 | 0 / 58 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 52 | 0 / 52 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 / 139 | 0 / 139 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 2 / 80 | 0 / 74 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 25 (100.0 %) | 100 / 100 | 0 / 112 | 0 / 112 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 0 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (26 calls, 26 valid; 26 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 199 / 200 turns CORRECT; exercises with all turns CORRECT 24 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 25 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 1 | 24 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 0 | 25 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 0 | 0 | 1 | 199 |

## Oracle check: 172 / 175 turns = 98.3 % (95 % CI, exercises resampled: 96.6-100.0 %); 555 / 558 expected numbers = 99.5 % (95 % CI, exercises resampled: 98.9-100.0 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 22 (88.0 %) | 97 / 100 | 0 | 0 | 0 | 0 | 0 | 3 |
| **total** | 175 | 172 (98.3 %) | 555 / 558 | 0 | 0 | 0 | 0 | 0 | 3 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 3 (ex04_oral_1_lag t7 AUC(0-tlast) linear (missing_value); ex14_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex23_iv_bolus t7 AUC(0-tlast) linear (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 3 (ex04_oral_1_lag t7 compare; ex14_iv_bolus t7 compare; ex23_iv_bolus t7 compare); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |

## Tool calls: 169 valid, 1 invalid, 0 failed of 170 (validity 99.4 %)

`nca_run` calls: 51, with the right dose 51, with the right route 51; memory calls (zoom / read_message): 2; by tool: {'analysis_compare': 26, 'analysis_get': 66, 'data_import': 25, 'export_table': 2, 'nca_run': 51}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 1 of 76 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 1 |

In exercises: ex13_oral_1. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 7.7 s per turn, mean 5214 prompt tokens (first call), total 43 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 5 / 5 | 6.5 |
| ex02_oral_1 | 400 mg | h, ng/mL | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 6.2 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 6.3 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 1 / 27 | 0 / 24 | 8 / 8 | 0 | 7 / 7 | 8.5 |
| ex05_iv_infusion | 150 mg | h, mg/L | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 7 / 7 | 8.1 |
| ex06_oral_0 | 100 mg | h, ng/mL | 0 / 30 | 0 / 30 | 8 / 8 | 0 | 7 / 7 | 7.6 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 8 / 8 | 8.4 |
| ex08_oral_1 | 800 ug | min, ng/mL | 0 / 29 | 0 / 29 | 8 / 8 | 0 | 7 / 7 | 7.8 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 7 / 7 | 7.8 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 0 / 28 | 0 / 28 | 8 / 8 | 0 | 7 / 7 | 7.6 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 0 / 36 | 0 / 36 | 8 / 8 | 0 | 8 / 8 | 8.8 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 6.1 |
| ex13_oral_1 | 50 mg | h, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 9 / 9 | 8.9 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 0 / 37 | 0 / 37 | 8 / 8 | 0 | 8 / 8 | 9.1 |
| ex15_oral_0 | 400 mg | h, mg/L | 0 / 33 | 0 / 33 | 8 / 8 | 0 | 7 / 7 | 8.0 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 6 / 6 | 7.6 |
| ex17_oral_1 | 500 mg | h, mg/L | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 7 / 7 | 7.6 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 0 / 31 | 0 / 31 | 8 / 8 | 0 | 8 / 8 | 8.3 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 0 / 27 | 0 / 27 | 8 / 8 | 0 | 7 / 7 | 7.5 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 6 / 6 | 7.3 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 7 / 8 | 7.5 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 0 / 29 | 0 / 29 | 8 / 8 | 0 | 5 / 5 | 5.9 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 0 / 32 | 0 / 32 | 8 / 8 | 0 | 7 / 7 | 7.9 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 0 / 31 | 0 / 31 | 8 / 8 | 0 | 7 / 7 | 8.1 |
| ex25_oral_1 | 100 mg | h, ng/mL | 1 / 29 | 0 / 26 | 8 / 8 | 0 | 7 / 7 | 8.9 |
