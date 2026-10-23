# Apothicaire benchmark report

date: 2026-10-23, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v3

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **199 / 831 = 23.9 %** (95 % CI, exercises resampled: 19.8-28.4 %, descriptive)
- in the answers shown (gate in the loop): **2 / 837 = 0.2 %** (95 % CI, exercises resampled: 0.0-0.6 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 51 before, 2 after; regenerated 51 (regeneration kept 51); turns shown with the badge: 2

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **4 / 25 = 16.0 % (exact 95 % CI 4.5-36.1 %)** (ex03_pk2_iv_bolus, ex12_iv_infusion, ex14_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **2 / 25 = 8.0 % (exact 95 % CI 1.0-26.0 %)** (ex14_iv_bolus, ex23_iv_bolus)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 1 | 0 |
| unlabelled_misread | 3 | 0 |
| recall_error | 0 | 0 |
| other | 195 | 2 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.9 % |
| arithmetic | 0.0 % | 23.0 % |
| unlabelled_misread | 11.8 % | 8.5 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 64.6 % |

## Correctness (development scorer `score_turn`): 182 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 540 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 23 (92.0 %) | 223 / 225 | 134 / 425 | 0 / 440 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 58 | 0 / 58 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 52 | 0 / 52 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 35 / 107 | 0 / 104 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 19 / 60 | 0 / 58 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 10 (40.0 %) | 84 / 100 | 8 / 98 | 1 / 96 |
| not_available | 25 | 24 (96.0 %) | 0 / 0 | 3 / 3 | 1 / 1 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 196 / 200 turns CORRECT; exercises with all turns CORRECT 21 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 3 | 22 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 0 | 25 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 1 | 24 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 0 | 0 | 4 | 196 |

## Oracle check: 157 / 175 turns = 89.7 % (95 % CI, exercises resampled: 86.9-92.6 %); 539 / 558 expected numbers = 96.6 % (95 % CI, exercises resampled: 95.5-97.7 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 22 (88.0 %) | 222 / 225 | 2 | 0 | 0 | 0 | 0 | 1 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 10 (40.0 %) | 84 / 100 | 0 | 0 | 0 | 0 | 0 | 16 |
| **total** | 175 | 157 (89.7 %) | 539 / 558 | 2 | 0 | 0 | 0 | 0 | 17 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 1 (ex25_oral_1 t1 t1/2 (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 1 (ex25_oral_1 t1 import_nca); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex03_pk2_iv_bolus | 1 import_nca | lambda_z | wrong_parameter | r.squared | 0,999335, 5, 13 h, 84 h |
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,297782 h*mg/l |
| ex06_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,55696 h*mg/l |
| ex11_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 5,35867 h*ng/ml |
| ex12_iv_infusion | 1 import_nca | lambda_z | wrong_parameter | adj.r.squared | 0,998321, 0,999161, 3, 590 min |
| ex12_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 246,834 min*ng/ml |
| ex13_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 0, 206,779 h*ng/ml, 0,872159 %, 0,991278 |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex15_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex17_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 5,01375 h*mg/l |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex21_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 35789,1 min*ng/ml |
| ex25_oral_1 | 1 import_nca | t1/2 | missing_value |  | 1 |

## Tool calls: 146 valid, 0 invalid, 0 failed of 146 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 8; by tool: {'analysis_compare': 25, 'analysis_get': 46, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 1 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["min", "ng/mL"]) | 1 |

In exercises: ex12_iv_infusion. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 10.5 s per turn, mean 4997 prompt tokens (first call), total 53 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 3 / 31 | 0 / 32 | 7 / 8 | 0 | 8 / 8 | 10.0 |
| ex02_oral_1 | 400 mg | h, ng/mL | 6 / 33 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 9.6 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 8 / 34 | 0 / 33 | 7 / 8 | 0 | 8 / 8 | 12.4 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 7 / 34 | 0 / 34 | 7 / 8 | 0 | 7 / 7 | 11.3 |
| ex05_iv_infusion | 150 mg | h, mg/L | 14 / 33 | 0 / 33 | 7 / 8 | 0 | 4 / 4 | 8.8 |
| ex06_oral_0 | 100 mg | h, ng/mL | 5 / 26 | 0 / 27 | 7 / 8 | 0 | 5 / 5 | 8.4 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 8 / 34 | 0 / 35 | 8 / 8 | 0 | 8 / 8 | 14.0 |
| ex08_oral_1 | 800 ug | min, ng/mL | 6 / 32 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 9.0 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 5 / 33 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 7.9 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 12 / 31 | 0 / 32 | 7 / 8 | 0 | 5 / 5 | 8.4 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 4 / 32 | 0 / 31 | 7 / 8 | 0 | 8 / 8 | 11.6 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 6 / 34 | 0 / 34 | 6 / 8 | 0 | 5 / 5 | 9.1 |
| ex13_oral_1 | 50 mg | h, ng/mL | 7 / 37 | 0 / 37 | 7 / 8 | 0 | 5 / 5 | 10.1 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 18 / 44 | 1 / 43 | 7 / 8 | 1 | 8 / 8 | 17.6 |
| ex15_oral_0 | 400 mg | h, mg/L | 12 / 32 | 0 / 32 | 7 / 8 | 0 | 5 / 5 | 8.1 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 6 / 31 | 0 / 32 | 8 / 8 | 0 | 5 / 5 | 9.1 |
| ex17_oral_1 | 500 mg | h, mg/L | 16 / 31 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 9.5 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 4 / 31 | 0 / 32 | 8 / 8 | 0 | 4 / 4 | 8.9 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 13 / 41 | 0 / 38 | 8 / 8 | 0 | 5 / 5 | 10.2 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 5 / 39 | 0 / 39 | 7 / 8 | 0 | 5 / 5 | 9.8 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 7 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 9.7 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 6 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 9.8 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 10 / 35 | 1 / 36 | 6 / 8 | 1 | 8 / 8 | 15.9 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 7 / 32 | 0 / 32 | 8 / 8 | 0 | 8 / 8 | 14.3 |
| ex25_oral_1 | 100 mg | h, ng/mL | 4 / 31 | 0 / 31 | 8 / 8 | 0 | 5 / 5 | 7.9 |
