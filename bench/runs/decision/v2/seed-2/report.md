# Apothicaire benchmark report

date: 2026-10-21, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v2

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **223 / 828 = 26.9 %** (95 % CI, exercises resampled: 21.4-33.7 %, descriptive)
- in the answers shown (gate in the loop): **31 / 832 = 3.7 %** (95 % CI, exercises resampled: 1.7-6.2 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 59 before, 11 after; regenerated 59 (regeneration kept 58); turns shown with the badge: 11

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **10 / 25 = 40.0 % (exact 95 % CI 21.1-61.3 %)** (ex03_pk2_iv_bolus, ex07_iv_bolus, ex10_oral_1_lag, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex19_oral_1_lag, ex21_oral_0, ex23_iv_bolus)
- exercises in which an answer shown carried an unverified number or a marker: **10 / 25 = 40.0 % (exact 95 % CI 21.1-61.3 %)** (ex01_iv_bolus, ex03_pk2_iv_bolus, ex05_iv_infusion, ex09_pk2_oral_1, ex10_oral_1_lag, ex13_oral_1, ex14_iv_bolus, ex17_oral_1, ex22_pk2_oral_1, ex23_iv_bolus)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 3 | 0 |
| recall_error | 0 | 0 |
| other | 220 | 31 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.9 % |
| arithmetic | 0.0 % | 23.3 % |
| unlabelled_misread | 11.8 % | 8.4 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 64.4 % |

## Correctness (development scorer `score_turn`): 178 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 520 / 556; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 23 (92.0 %) | 216 / 225 | 132 / 419 | 24 / 436 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 60 | 0 / 60 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 4 / 50 | 0 / 50 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 52 / 116 | 1 / 112 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 22 / 66 | 2 / 66 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 5 (20.0 %) | 71 / 98 | 10 / 86 | 4 / 80 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 3 / 3 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 24 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 189 / 200 turns CORRECT; exercises with all turns CORRECT 15 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 2 | 23 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 1 | 24 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 8 | 17 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 0 | 0 | 11 | 189 |

## Oracle check: 151 / 175 turns = 86.3 % (95 % CI, exercises resampled: 83.4-89.1 %); 516 / 556 expected numbers = 92.8 % (95 % CI, exercises resampled: 89.6-95.4 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 23 (92.0 %) | 215 / 225 | 2 | 0 | 0 | 0 | 0 | 8 |
| cmax_tmax | 25 | 23 (92.0 %) | 56 / 58 | 0 | 0 | 0 | 0 | 0 | 2 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 5 (20.0 %) | 70 / 98 | 0 | 3 | 1 | 0 | 0 | 24 |
| **total** | 175 | 151 (86.3 %) | 516 / 556 | 2 | 3 | 1 | 0 | 0 | 34 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 4 (ex10_oral_1_lag t1 CL/F (missing_value); ex18_pk2_iv_bolus t2 C0 (missing_value); ex19_oral_1_lag t7 AUC(0-tlast) linear (missing_value); ex24_pk2_iv_bolus t2 C0 (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 2 (ex18_pk2_iv_bolus t2 cmax_tmax; ex24_pk2_iv_bolus t2 cmax_tmax); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 128,516 h*mg/l |
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | 4503 h*ng/ml, 6,13463 % |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex07_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex07_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 0 |
| ex08_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 1 import_nca | lambda_z | wrong_parameter | adj.r.squared | 4, 7,5 h, 24 h, 0,99777 |
| ex10_oral_1_lag | 1 import_nca | t1/2 | missing_value |  | (none) |
| ex10_oral_1_lag | 1 import_nca | CL/F | missing_value |  | (none) |
| ex10_oral_1_lag | 1 import_nca | Vz/F | missing_value |  | (none) |
| ex10_oral_1_lag | 1 import_nca | MRT | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 5,35867 h*ng/ml |
| ex12_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex13_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 0 l |
| ex13_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_option | options.units=None | 0 l |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC difference (analysis_compare) | missing_value |  | 1,9834, 2 min |
| ex14_iv_bolus | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex15_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | 6,46509 h*mg/l, 7,02331 % |
| ex15_oral_0 | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 6,46509 h*mg/l, 7,02331 % |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 526,018 h*ng/ml |
| ex17_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex19_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex19_oral_1_lag | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 99,4202 h*ng/ml |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 2297,84 h*ng/ml |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 3,84623 h*mg/l |
| ex23_iv_bolus | 1 import_nca | lambda_z | wrong_parameter | adj.r.squared | 4, 830 min, 2600 min, 0,999504 |
| ex23_iv_bolus | 1 import_nca | t1/2 | missing_value |  | (none) |
| ex23_iv_bolus | 1 import_nca | CL | missing_value |  | (none) |
| ex23_iv_bolus | 1 import_nca | Vz | missing_value |  | (none) |
| ex23_iv_bolus | 1 import_nca | MRT | missing_value |  | (none) |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 35789,1 min*ng/ml, 1,68122 % |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 35789,1 min*ng/ml, 1,68122 % |
| ex24_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex25_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |

## Tool calls: 152 valid, 0 invalid, 0 failed of 152 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 9; by tool: {'analysis_compare': 25, 'analysis_get': 52, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 2 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["h", "ng/mL"]) | 1 |
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 1 |

In exercises: ex13_oral_1, ex24_pk2_iv_bolus. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 10.8 s per turn, mean 5059 prompt tokens (first call), total 53 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 9 / 35 | 1 / 35 | 8 / 8 | 1 | 8 / 8 | 13.5 |
| ex02_oral_1 | 400 mg | h, ng/mL | 5 / 30 | 0 / 30 | 7 / 8 | 0 | 5 / 5 | 8.7 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 7 / 32 | 2 / 32 | 7 / 8 | 1 | 8 / 8 | 13.4 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 3 / 31 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 7.6 |
| ex05_iv_infusion | 150 mg | h, mg/L | 3 / 32 | 2 / 33 | 7 / 8 | 1 | 4 / 4 | 7.7 |
| ex06_oral_0 | 100 mg | h, ng/mL | 6 / 32 | 0 / 28 | 8 / 8 | 0 | 5 / 5 | 9.2 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 9 / 43 | 0 / 44 | 7 / 8 | 0 | 8 / 8 | 13.9 |
| ex08_oral_1 | 800 ug | min, ng/mL | 7 / 31 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 8.7 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 8 / 34 | 2 / 35 | 8 / 8 | 1 | 5 / 5 | 9.2 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 15 / 29 | 5 / 30 | 6 / 8 | 1 | 5 / 5 | 9.9 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 6 / 38 | 0 / 39 | 7 / 8 | 0 | 8 / 8 | 12.8 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 7 / 32 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 9.0 |
| ex13_oral_1 | 50 mg | h, ng/mL | 9 / 38 | 4 / 33 | 7 / 8 | 1 | 5 / 5 | 10.8 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 26 / 39 | 6 / 40 | 7 / 8 | 2 | 8 / 8 | 17.0 |
| ex15_oral_0 | 400 mg | h, mg/L | 12 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 7.6 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 4 / 26 | 0 / 26 | 7 / 8 | 0 | 7 / 7 | 10.8 |
| ex17_oral_1 | 500 mg | h, mg/L | 5 / 31 | 1 / 34 | 7 / 8 | 1 | 5 / 5 | 8.6 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 9 / 35 | 0 / 35 | 8 / 8 | 0 | 8 / 8 | 14.2 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 13 / 33 | 0 / 34 | 7 / 8 | 0 | 7 / 7 | 11.1 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 8 / 33 | 0 / 32 | 7 / 8 | 0 | 5 / 5 | 10.2 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 7 / 38 | 0 / 38 | 8 / 8 | 0 | 5 / 5 | 10.1 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 8 / 32 | 2 / 34 | 7 / 8 | 1 | 5 / 5 | 9.1 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 22 / 30 | 6 / 29 | 6 / 8 | 1 | 8 / 8 | 15.5 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 10 / 33 | 0 / 33 | 7 / 8 | 0 | 8 / 8 | 13.4 |
| ex25_oral_1 | 100 mg | h, ng/mL | 5 / 31 | 0 / 32 | 7 / 8 | 0 | 5 / 5 | 8.8 |
