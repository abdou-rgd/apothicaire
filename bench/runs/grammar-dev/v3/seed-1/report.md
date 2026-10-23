# Apothicaire benchmark report

date: 2026-10-23, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v3

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **211 / 911 = 23.2 %** (95 % CI, exercises resampled: 20.0-26.9 %, descriptive)
- in the answers shown (gate in the loop): **8 / 896 = 0.9 %** (95 % CI, exercises resampled: 0.0-2.5 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 71 before, 2 after; regenerated 71 (regeneration kept 69); turns shown with the badge: 2

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **18 / 25 = 72.0 % (exact 95 % CI 50.6-87.9 %)** (ex01_iv_bolus, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex08_oral_1, ex09_pk2_oral_1, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex18_pk2_iv_bolus, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **2 / 25 = 8.0 % (exact 95 % CI 1.0-26.0 %)** (ex12_iv_infusion, ex20_iv_infusion)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 1 | 0 |
| unlabelled_misread | 14 | 0 |
| recall_error | 12 | 1 |
| other | 184 | 7 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 11.0 % | 3.9 % |
| arithmetic | 0.0 % | 24.4 % |
| unlabelled_misread | 11.8 % | 8.2 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.1 % | 63.5 % |

## Correctness (development scorer `score_turn`): 175 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 531 / 556; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 105 / 488 | 7 / 495 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 58 | 0 / 58 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 10 / 54 | 0 / 54 |
| half_life | 25 | 24 (96.0 %) | 48 / 50 | 51 / 122 | 0 / 117 |
| lambda_z_regression | 25 | 21 (84.0 %) | 43 / 50 | 13 / 50 | 0 / 48 |
| recall | 25 | 18 (72.0 %) | 25 / 25 | 12 / 33 | 1 / 28 |
| compare | 25 | 12 (48.0 %) | 82 / 98 | 17 / 103 | 0 / 96 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 3 / 3 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 24 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 168 / 200 turns CORRECT; exercises with all turns CORRECT 7 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 25 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 2 | 0 | 6 | 17 |
| lambda_z_regression | 0 | 0 | 4 | 0 | 1 | 20 |
| recall | 0 | 0 | 0 | 0 | 8 | 17 |
| compare | 0 | 0 | 1 | 0 | 10 | 14 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 7 | 0 | 25 | 168 |

## Oracle check: 138 / 175 turns = 78.9 % (95 % CI, exercises resampled: 74.9-83.4 %); 512 / 556 expected numbers = 92.1 % (95 % CI, exercises resampled: 90.3-93.9 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 22 (88.0 %) | 55 / 58 | 0 | 0 | 0 | 0 | 0 | 3 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 24 (96.0 %) | 48 / 50 | 0 | 0 | 0 | 0 | 0 | 2 |
| lambda_z_regression | 25 | 13 (52.0 %) | 35 / 50 | 0 | 0 | 0 | 0 | 0 | 15 |
| recall | 25 | 18 (72.0 %) | 18 / 25 | 0 | 0 | 0 | 7 | 0 | 0 |
| compare | 25 | 11 (44.0 %) | 81 / 98 | 0 | 6 | 0 | 0 | 0 | 11 |
| **total** | 175 | 138 (78.9 %) | 512 / 556 | 0 | 6 | 0 | 7 | 0 | 31 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 19 (ex01_iv_bolus t2 C0 (missing_value); ex02_oral_1 t5 lambda_z points (missing_value); ex04_oral_1_lag t6 dose (missing_unit); ex08_oral_1 t6 dose (missing_unit); ex09_pk2_oral_1 t5 lambda_z points (missing_value); ex10_oral_1_lag t5 lambda_z points (missing_value); ex11_pk2_iv_bolus t2 C0 (missing_value); ex11_pk2_iv_bolus t5 lambda_z points (missing_value); ex13_oral_1 t5 lambda_z points (missing_value); ex13_oral_1 t6 dose (missing_unit); ex14_iv_bolus t2 C0 (missing_value); ex14_iv_bolus t7 AUC difference (analysis_compare) (missing_value); ex15_oral_0 t5 lambda_z points (missing_value); ex16_pk2_oral_1 t5 lambda_z points (missing_value); ex20_iv_infusion t5 lambda_z points (missing_value); ex21_oral_0 t6 dose (missing_unit); ex22_pk2_oral_1 t6 dose (missing_unit); ex23_iv_bolus t6 dose (missing_unit); ex25_oral_1 t6 dose (missing_unit)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 12 (ex01_iv_bolus t2 cmax_tmax; ex02_oral_1 t5 lambda_z_regression; ex09_pk2_oral_1 t5 lambda_z_regression; ex10_oral_1_lag t5 lambda_z_regression; ex11_pk2_iv_bolus t2 cmax_tmax; ex11_pk2_iv_bolus t5 lambda_z_regression; ex13_oral_1 t5 lambda_z_regression; ex14_iv_bolus t2 cmax_tmax; ex14_iv_bolus t7 compare; ex15_oral_0 t5 lambda_z_regression; ex16_pk2_oral_1 t5 lambda_z_regression; ex20_iv_infusion t5 lambda_z_regression); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex01_iv_bolus | 4 half_life | t1/2 | missing_value |  | (none) |
| ex01_iv_bolus | 4 half_life | AUC % extrapolated | missing_value |  | (none) |
| ex02_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | 7,6 h, 21 h |
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 128,516 h*mg/l |
| ex04_oral_1_lag | 6 recall | dose | missing_unit |  | 300 |
| ex05_iv_infusion | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex05_iv_infusion | 5 lambda_z_regression | adjusted R2 | missing_value |  | (none) |
| ex06_oral_0 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex06_oral_0 | 5 lambda_z_regression | adjusted R2 | missing_value |  | (none) |
| ex06_oral_0 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 0, 3005,59 h*ng/ml |
| ex08_oral_1 | 6 recall | dose | missing_unit |  | 800 |
| ex08_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex09_pk2_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex10_oral_1_lag | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex12_iv_infusion | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex12_iv_infusion | 5 lambda_z_regression | adjusted R2 | missing_value |  | (none) |
| ex13_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex13_oral_1 | 6 recall | dose | missing_unit |  | 50 |
| ex14_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC difference (analysis_compare) | missing_value |  | (none) |
| ex15_oral_0 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex15_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex16_pk2_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 526,018 h*ng/ml |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 1701680 min*ng/ml |
| ex20_iv_infusion | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 0, 37854,6 h*ng/ml |
| ex21_oral_0 | 6 recall | dose | missing_unit |  | 5000 |
| ex21_oral_0 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 875,226 h*ng/ml, 0 |
| ex22_pk2_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex22_pk2_oral_1 | 6 recall | dose | missing_unit |  | 500 |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | (none) |
| ex23_iv_bolus | 6 recall | dose | missing_unit |  | 300 |
| ex25_oral_1 | 6 recall | dose | missing_unit |  | 100 |
| ex25_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex25_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 939,022 h*ng/ml |

## Tool calls: 208 valid, 3 invalid, 0 failed of 211 (validity 98.6 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 23; by tool: {'analysis_compare': 25, 'analysis_get': 80, 'data_import': 25, 'export_table': 31, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 3 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["h", "ng/mL"]) | 2 |
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 1 |

In exercises: ex13_oral_1, ex16_pk2_oral_1, ex24_pk2_iv_bolus. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 16.5 s per turn, mean 5660 prompt tokens (first call), total 83 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 17 / 32 | 0 / 33 | 7 / 8 | 0 | 8 / 8 | 17.0 |
| ex02_oral_1 | 400 mg | h, ng/mL | 4 / 33 | 0 / 34 | 7 / 8 | 0 | 8 / 8 | 11.1 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 7 / 42 | 0 / 41 | 7 / 8 | 0 | 8 / 8 | 16.1 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 15 / 38 | 0 / 38 | 7 / 8 | 0 | 10 / 10 | 19.6 |
| ex05_iv_infusion | 150 mg | h, mg/L | 9 / 42 | 0 / 40 | 7 / 8 | 0 | 7 / 7 | 18.9 |
| ex06_oral_0 | 100 mg | h, ng/mL | 3 / 34 | 0 / 34 | 6 / 8 | 0 | 8 / 8 | 16.4 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 7 / 34 | 0 / 34 | 8 / 8 | 0 | 4 / 4 | 9.7 |
| ex08_oral_1 | 800 ug | min, ng/mL | 10 / 37 | 0 / 38 | 6 / 8 | 0 | 9 / 9 | 16.2 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 8 / 33 | 0 / 31 | 7 / 8 | 0 | 9 / 9 | 16.5 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 7 / 41 | 0 / 37 | 7 / 8 | 0 | 8 / 8 | 15.3 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 7 / 37 | 0 / 34 | 8 / 8 | 0 | 8 / 8 | 16.7 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 7 / 37 | 1 / 36 | 7 / 8 | 1 | 12 / 12 | 23.9 |
| ex13_oral_1 | 50 mg | h, ng/mL | 7 / 37 | 0 / 37 | 7 / 8 | 0 | 12 / 12 | 18.5 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 9 / 36 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 13.3 |
| ex15_oral_0 | 400 mg | h, mg/L | 7 / 34 | 0 / 30 | 7 / 8 | 0 | 7 / 7 | 12.5 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 4 / 32 | 0 / 33 | 7 / 8 | 0 | 7 / 7 | 11.2 |
| ex17_oral_1 | 500 mg | h, mg/L | 7 / 36 | 0 / 38 | 8 / 8 | 0 | 12 / 12 | 17.4 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 7 / 33 | 0 / 35 | 7 / 8 | 0 | 9 / 9 | 19.4 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 10 / 37 | 0 / 36 | 8 / 8 | 0 | 8 / 8 | 13.5 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 10 / 42 | 7 / 42 | 7 / 8 | 1 | 6 / 6 | 11.8 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 10 / 40 | 0 / 39 | 6 / 8 | 0 | 11 / 12 | 25.3 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 6 / 31 | 0 / 31 | 5 / 8 | 0 | 8 / 8 | 16.4 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 16 / 40 | 0 / 38 | 7 / 8 | 0 | 8 / 9 | 21.9 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 9 / 41 | 0 / 40 | 8 / 8 | 0 | 8 / 8 | 17.8 |
| ex25_oral_1 | 100 mg | h, ng/mL | 8 / 32 | 0 / 32 | 6 / 8 | 0 | 8 / 9 | 15.6 |
