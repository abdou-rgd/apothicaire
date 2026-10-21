# Apothicaire benchmark report

date: 2026-10-21, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v2

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **224 / 948 = 23.6 %** (95 % CI, exercises resampled: 20.0-27.5 %, descriptive)
- in the answers shown (gate in the loop): **30 / 927 = 3.2 %** (95 % CI, exercises resampled: 1.5-5.2 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 75 before, 13 after; regenerated 75 (regeneration kept 73); turns shown with the badge: 13

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **16 / 25 = 64.0 % (exact 95 % CI 42.5-82.0 %)** (ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex08_oral_1, ex10_oral_1_lag, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex17_oral_1, ex20_iv_infusion, ex21_oral_0, ex23_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **11 / 25 = 44.0 % (exact 95 % CI 24.4-65.1 %)** (ex01_iv_bolus, ex05_iv_infusion, ex07_iv_bolus, ex09_pk2_oral_1, ex11_pk2_iv_bolus, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex19_oral_1_lag, ex23_iv_bolus, ex25_oral_1)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 5 | 1 |
| recall_error | 11 | 0 |
| other | 208 | 29 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 11.0 % | 3.9 % |
| arithmetic | 0.0 % | 23.8 % |
| unlabelled_misread | 11.8 % | 8.4 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.1 % | 63.9 % |

## Correctness (development scorer `score_turn`): 179 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 534 / 550; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 95 / 494 | 14 / 499 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 61 | 0 / 61 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 6 / 51 | 0 / 51 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 46 / 124 | 6 / 118 |
| lambda_z_regression | 25 | 24 (96.0 %) | 49 / 50 | 40 / 83 | 10 / 80 |
| recall | 25 | 18 (72.0 %) | 25 / 25 | 11 / 32 | 0 / 28 |
| compare | 25 | 12 (48.0 %) | 77 / 92 | 23 / 100 | 0 / 90 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 3 / 3 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (26 calls, 26 valid; 26 calls in all turns); usable in 21 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 176 / 200 turns CORRECT; exercises with all turns CORRECT 9 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 25 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 1 | 0 | 3 | 21 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 1 | 24 |
| recall | 0 | 0 | 0 | 0 | 7 | 18 |
| compare | 0 | 0 | 1 | 0 | 11 | 13 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 2 | 0 | 22 | 176 |

## Oracle check: 142 / 175 turns = 81.1 % (95 % CI, exercises resampled: 77.7-84.6 %); 513 / 550 expected numbers = 93.3 % (95 % CI, exercises resampled: 91.9-94.6 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 21 (84.0 %) | 54 / 58 | 0 | 0 | 0 | 0 | 0 | 4 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 18 (72.0 %) | 43 / 50 | 0 | 0 | 0 | 0 | 0 | 7 |
| recall | 25 | 18 (72.0 %) | 18 / 25 | 0 | 0 | 0 | 7 | 0 | 0 |
| compare | 25 | 10 (40.0 %) | 73 / 92 | 0 | 4 | 0 | 0 | 0 | 15 |
| **total** | 175 | 142 (81.1 %) | 513 / 550 | 0 | 4 | 0 | 7 | 0 | 26 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 21 (ex01_iv_bolus t2 C0 (missing_value); ex02_oral_1 t5 lambda_z points (missing_value); ex05_iv_infusion t5 lambda_z points (missing_value); ex05_iv_infusion t7 AUC difference in % (analysis_compare) (missing_value); ex06_oral_0 t5 lambda_z points (missing_value); ex06_oral_0 t6 dose (missing_unit); ex08_oral_1 t6 dose (missing_unit); ex09_pk2_oral_1 t5 lambda_z points (missing_value); ex10_oral_1_lag t6 dose (missing_unit); ex11_pk2_iv_bolus t2 C0 (missing_value); ex11_pk2_iv_bolus t5 lambda_z points (missing_value); ex12_iv_infusion t7 AUC difference in % (analysis_compare) (missing_value); ex13_oral_1 t6 dose (missing_unit); ex14_iv_bolus t6 dose (missing_unit); ex14_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex15_oral_0 t6 dose (missing_unit); ex16_pk2_oral_1 t6 dose (missing_unit); ex18_pk2_iv_bolus t2 C0 (missing_value); ex18_pk2_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex19_oral_1_lag t5 lambda_z points (missing_value); ex23_iv_bolus t2 C0 (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 12 (ex01_iv_bolus t2 cmax_tmax; ex02_oral_1 t5 lambda_z_regression; ex05_iv_infusion t5 lambda_z_regression; ex06_oral_0 t5 lambda_z_regression; ex09_pk2_oral_1 t5 lambda_z_regression; ex11_pk2_iv_bolus t2 cmax_tmax; ex11_pk2_iv_bolus t5 lambda_z_regression; ex14_iv_bolus t7 compare; ex18_pk2_iv_bolus t2 cmax_tmax; ex18_pk2_iv_bolus t7 compare; ex19_oral_1_lag t5 lambda_z_regression; ex23_iv_bolus t2 cmax_tmax); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex02_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | 7,6 h, 21 h |
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 128,516 h*mg/l |
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex05_iv_infusion | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,297782 h*mg/l |
| ex05_iv_infusion | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex06_oral_0 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex06_oral_0 | 6 recall | dose | missing_unit |  | 100 |
| ex08_oral_1 | 6 recall | dose | missing_unit |  | 800 |
| ex08_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 46762,6 min*ng/ml, 0 |
| ex09_pk2_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex10_oral_1_lag | 6 recall | dose | missing_unit |  | 100 |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 5 lambda_z_regression | lambda_z points | missing_value |  | 6,5 h, 45 h |
| ex12_iv_infusion | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex12_iv_infusion | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex13_oral_1 | 6 recall | dose | missing_unit |  | 50 |
| ex14_iv_bolus | 6 recall | dose | missing_unit |  | 150 |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex15_oral_0 | 5 lambda_z_regression | lambda_z points | missing_value |  | 1, 1 h, 1 h, 1 |
| ex15_oral_0 | 6 recall | dose | missing_unit |  | 400 |
| ex16_pk2_oral_1 | 6 recall | dose | missing_unit |  | 2000 |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 0 |
| ex19_oral_1_lag | 5 lambda_z_regression | lambda_z points | missing_value |  | 5,8 h, 22 h |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 0 |
| ex21_oral_0 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 875,226 h*ng/ml |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex23_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex25_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 16951,2 h*ng/ml |

## Tool calls: 223 valid, 7 invalid, 0 failed of 230 (validity 97.0 %)

`nca_run` calls: 51, with the right dose 51, with the right route 51; memory calls (zoom / read_message): 17; by tool: {'analysis_compare': 26, 'analysis_get': 91, 'data_import': 25, 'export_table': 37, 'nca_run': 51}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 7 of 76 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| nca_run: options.units = null (intended {"time": "h", "concentration": "mg/L", "dose": "mg"}) | 3 |
| data_import: columns.unit = [] (intended ["h", "ng/mL"]) | 2 |
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 2 |

In exercises: ex04_oral_1_lag, ex10_oral_1_lag, ex13_oral_1, ex15_oral_0, ex16_pk2_oral_1, ex17_oral_1, ex24_pk2_iv_bolus. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 17.8 s per turn, mean 5998 prompt tokens (first call), total 96 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 11 / 36 | 5 / 35 | 8 / 8 | 1 | 8 / 8 | 15.3 |
| ex02_oral_1 | 400 mg | h, ng/mL | 13 / 35 | 0 / 36 | 8 / 8 | 0 | 9 / 9 | 19.4 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 15 / 38 | 0 / 38 | 7 / 8 | 0 | 7 / 8 | 15.2 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 7 / 30 | 0 / 30 | 7 / 8 | 0 | 8 / 8 | 13.6 |
| ex05_iv_infusion | 150 mg | h, mg/L | 6 / 38 | 2 / 38 | 7 / 8 | 1 | 10 / 11 | 39.5 |
| ex06_oral_0 | 100 mg | h, ng/mL | 10 / 32 | 0 / 32 | 7 / 8 | 0 | 9 / 9 | 16.9 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 5 / 34 | 2 / 34 | 8 / 8 | 1 | 5 / 5 | 10.5 |
| ex08_oral_1 | 800 ug | min, ng/mL | 11 / 35 | 0 / 35 | 6 / 8 | 0 | 11 / 11 | 16.6 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 11 / 38 | 4 / 36 | 8 / 8 | 2 | 10 / 10 | 14.7 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 5 / 34 | 0 / 30 | 6 / 8 | 0 | 9 / 9 | 11.6 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 6 / 37 | 1 / 37 | 8 / 8 | 1 | 8 / 8 | 13.9 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 6 / 40 | 0 / 39 | 7 / 8 | 0 | 7 / 7 | 15.1 |
| ex13_oral_1 | 50 mg | h, ng/mL | 8 / 38 | 4 / 37 | 7 / 8 | 2 | 10 / 10 | 16.3 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 10 / 41 | 2 / 42 | 7 / 8 | 1 | 6 / 6 | 15.7 |
| ex15_oral_0 | 400 mg | h, mg/L | 18 / 44 | 6 / 41 | 6 / 8 | 1 | 15 / 16 | 31.0 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 11 / 37 | 0 / 37 | 6 / 8 | 0 | 9 / 9 | 16.9 |
| ex17_oral_1 | 500 mg | h, mg/L | 8 / 39 | 0 / 36 | 8 / 8 | 0 | 11 / 11 | 19.6 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 8 / 44 | 0 / 42 | 8 / 8 | 0 | 6 / 6 | 15.6 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 9 / 40 | 2 / 38 | 8 / 8 | 1 | 8 / 8 | 14.9 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 7 / 36 | 0 / 36 | 7 / 8 | 0 | 10 / 11 | 22.0 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 4 / 36 | 0 / 36 | 7 / 8 | 0 | 11 / 12 | 18.2 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 7 / 38 | 0 / 38 | 7 / 8 | 0 | 9 / 9 | 16.4 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 17 / 43 | 1 / 40 | 7 / 8 | 1 | 8 / 8 | 16.3 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 4 / 48 | 0 / 49 | 7 / 8 | 0 | 7 / 8 | 14.7 |
| ex25_oral_1 | 100 mg | h, ng/mL | 7 / 37 | 1 / 35 | 7 / 8 | 1 | 12 / 13 | 25.6 |
