# Apothicaire benchmark report

date: 2026-10-23, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v3

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **228 / 845 = 27.0 %** (95 % CI, exercises resampled: 22.2-32.3 %, descriptive)
- in the answers shown (gate in the loop): **2 / 863 = 0.2 %** (95 % CI, exercises resampled: 0.0-0.6 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 61 before, 2 after; regenerated 61 (regeneration kept 61); turns shown with the badge: 2

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **6 / 25 = 24.0 % (exact 95 % CI 9.4-45.1 %)** (ex03_pk2_iv_bolus, ex07_iv_bolus, ex13_oral_1, ex18_pk2_iv_bolus, ex19_oral_1_lag, ex20_iv_infusion)
- exercises in which an answer shown carried an unverified number or a marker: **2 / 25 = 8.0 % (exact 95 % CI 1.0-26.0 %)** (ex18_pk2_iv_bolus, ex23_iv_bolus)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 1 | 0 |
| unlabelled_misread | 4 | 0 |
| recall_error | 0 | 0 |
| other | 223 | 2 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.8 % |
| arithmetic | 0.0 % | 23.2 % |
| unlabelled_misread | 11.8 % | 8.5 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 64.5 % |

## Correctness (development scorer `score_turn`): 184 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 541 / 556; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 24 (96.0 %) | 224 / 225 | 133 / 434 | 0 / 466 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 2 / 64 | 0 / 60 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 50 | 0 / 50 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 49 / 109 | 0 / 105 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 22 / 62 | 0 / 62 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 12 (48.0 %) | 84 / 98 | 20 / 95 | 0 / 89 |
| not_available | 25 | 23 (92.0 %) | 0 / 0 | 2 / 3 | 2 / 3 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 24 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 193 / 200 turns CORRECT; exercises with all turns CORRECT 19 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 1 | 24 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 1 | 24 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 5 | 20 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 0 | 0 | 7 | 193 |

## Oracle check: 155 / 175 turns = 88.6 % (95 % CI, exercises resampled: 84.6-92.0 %); 535 / 556 expected numbers = 96.2 % (95 % CI, exercises resampled: 94.6-97.5 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 24 (96.0 %) | 224 / 225 | 1 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 21 (84.0 %) | 54 / 58 | 0 | 0 | 0 | 0 | 0 | 4 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 24 (96.0 %) | 49 / 50 | 0 | 0 | 0 | 0 | 0 | 1 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 11 (44.0 %) | 83 / 98 | 0 | 2 | 0 | 0 | 0 | 13 |
| **total** | 175 | 155 (88.6 %) | 535 / 556 | 1 | 2 | 0 | 0 | 0 | 18 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 6 (ex06_oral_0 t5 lambda_z points (missing_value); ex06_oral_0 t7 AUC difference in % (analysis_compare) (missing_value); ex07_iv_bolus t2 C0 (missing_value); ex11_pk2_iv_bolus t2 C0 (missing_value); ex18_pk2_iv_bolus t2 C0 (missing_value); ex24_pk2_iv_bolus t2 C0 (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 6 (ex06_oral_0 t5 lambda_z_regression; ex06_oral_0 t7 compare; ex07_iv_bolus t2 cmax_tmax; ex11_pk2_iv_bolus t2 cmax_tmax; ex18_pk2_iv_bolus t2 cmax_tmax; ex24_pk2_iv_bolus t2 cmax_tmax); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 1,2651 h*mg/l |
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 128,516 h*mg/l, 2,36999 %, 0 |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,297782 h*mg/l |
| ex06_oral_0 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex06_oral_0 | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex07_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex08_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 4082,31 min*ng/ml |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 3941,99 h*ng/ml |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,55696 h*mg/l |
| ex11_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex15_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex17_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 5,01375 h*mg/l |
| ex18_pk2_iv_bolus | 1 import_nca | lambda_z | wrong_parameter | adj.r.squared | 0,999861, 4, 730 min, 2900 min |
| ex18_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 41195,6 min*ng/ml, 2,42087 % |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 41195,6 min*ng/ml, 2,42087 % |
| ex19_oral_1_lag | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 99,4202 h*ng/ml |
| ex21_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex25_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |

## Tool calls: 148 valid, 0 invalid, 0 failed of 148 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 9; by tool: {'analysis_compare': 25, 'analysis_get': 48, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 2 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["h", "ng/mL"]) | 1 |
| nca_run: options.units = null (intended {"time": "h", "concentration": "ng/mL", "dose": "mg"}) | 1 |

In exercises: ex13_oral_1, ex24_pk2_iv_bolus. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 11.0 s per turn, mean 4998 prompt tokens (first call), total 52 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 7 / 34 | 0 / 32 | 7 / 8 | 0 | 8 / 8 | 13.2 |
| ex02_oral_1 | 400 mg | h, ng/mL | 8 / 33 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 9.1 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 7 / 35 | 0 / 36 | 7 / 8 | 0 | 8 / 8 | 12.2 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 4 / 29 | 0 / 30 | 8 / 8 | 0 | 5 / 5 | 8.6 |
| ex05_iv_infusion | 150 mg | h, mg/L | 4 / 33 | 0 / 34 | 7 / 8 | 0 | 4 / 4 | 8.8 |
| ex06_oral_0 | 100 mg | h, ng/mL | 5 / 32 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 8.7 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 15 / 41 | 0 / 42 | 8 / 8 | 0 | 8 / 8 | 18.3 |
| ex08_oral_1 | 800 ug | min, ng/mL | 5 / 29 | 0 / 30 | 7 / 8 | 0 | 5 / 5 | 8.5 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 8 / 33 | 0 / 34 | 7 / 8 | 0 | 5 / 5 | 9.3 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 13 / 30 | 0 / 30 | 7 / 8 | 0 | 5 / 5 | 9.4 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 9 / 36 | 0 / 36 | 8 / 8 | 0 | 6 / 6 | 11.2 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 8 / 35 | 0 / 37 | 8 / 8 | 0 | 5 / 5 | 9.6 |
| ex13_oral_1 | 50 mg | h, ng/mL | 9 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 10.5 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 20 / 40 | 0 / 40 | 8 / 8 | 0 | 8 / 8 | 16.9 |
| ex15_oral_0 | 400 mg | h, mg/L | 14 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 8.9 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 5 / 36 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 9.2 |
| ex17_oral_1 | 500 mg | h, mg/L | 4 / 29 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 8.2 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 8 / 34 | 1 / 35 | 5 / 8 | 1 | 8 / 8 | 13.8 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 13 / 35 | 0 / 36 | 7 / 8 | 0 | 7 / 7 | 11.4 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 8 / 38 | 0 / 40 | 8 / 8 | 0 | 5 / 5 | 9.8 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 8 / 34 | 0 / 36 | 7 / 8 | 0 | 5 / 5 | 9.6 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 9 / 35 | 0 / 36 | 8 / 8 | 0 | 5 / 5 | 11.1 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 22 / 34 | 1 / 35 | 7 / 8 | 1 | 8 / 8 | 15.3 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 10 / 33 | 0 / 33 | 8 / 8 | 0 | 8 / 8 | 13.6 |
| ex25_oral_1 | 100 mg | h, ng/mL | 5 / 33 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 8.7 |
