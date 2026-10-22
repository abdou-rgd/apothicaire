# Apothicaire benchmark report

date: 2026-10-21, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, thinking off, gate: v2

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **204 / 845 = 24.1 %** (95 % CI, exercises resampled: 19.5-29.3 %, descriptive)
- in the answers shown (gate in the loop): **32 / 851 = 3.8 %** (95 % CI, exercises resampled: 1.7-6.2 %, descriptive)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 54 before, 12 after; regenerated 54 (regeneration kept 53); turns shown with the badge: 12

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **3 / 25 = 12.0 % (exact 95 % CI 2.5-31.2 %)** (ex15_oral_0, ex24_pk2_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **11 / 25 = 44.0 % (exact 95 % CI 24.4-65.1 %)** (ex03_pk2_iv_bolus, ex07_iv_bolus, ex10_oral_1_lag, ex11_pk2_iv_bolus, ex12_iv_infusion, ex14_iv_bolus, ex15_oral_0, ex17_oral_1, ex19_oral_1_lag, ex22_pk2_oral_1, ex24_pk2_iv_bolus)

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 3 | 0 |
| unlabelled_misread | 7 | 0 |
| recall_error | 0 | 0 |
| other | 194 | 32 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.8 % |
| arithmetic | 0.0 % | 22.8 % |
| unlabelled_misread | 11.8 % | 8.6 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 64.8 % |

## Correctness (development scorer `score_turn`): 184 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 538 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 24 (96.0 %) | 223 / 225 | 131 / 436 | 25 / 453 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 2 / 61 | 0 / 59 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 2 / 54 | 0 / 54 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 49 / 110 | 0 / 107 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 10 / 58 | 2 / 56 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 28 | 0 / 28 |
| compare | 25 | 10 (40.0 %) | 82 / 100 | 9 / 97 | 5 / 94 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 1 / 1 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 197 / 200 turns CORRECT; exercises with all turns CORRECT 22 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 2 | 23 |
| cmax_tmax | 0 | 0 | 0 | 0 | 0 | 25 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 0 | 25 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 1 | 24 |
| not_available | 0 | 0 | 0 | 0 | 0 | 25 |
| **total** | 0 | 0 | 0 | 0 | 3 | 197 |

## Oracle check: 156 / 175 turns = 89.1 % (95 % CI, exercises resampled: 85.7-92.6 %); 534 / 558 expected numbers = 95.7 % (95 % CI, exercises resampled: 93.9-97.3 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 23 (92.0 %) | 222 / 225 | 1 | 0 | 0 | 0 | 0 | 2 |
| cmax_tmax | 25 | 24 (96.0 %) | 57 / 58 | 0 | 0 | 0 | 0 | 0 | 1 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 24 (96.0 %) | 49 / 50 | 0 | 0 | 0 | 0 | 0 | 1 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 10 (40.0 %) | 81 / 100 | 0 | 1 | 0 | 0 | 0 | 18 |
| **total** | 175 | 156 (89.1 %) | 534 / 558 | 1 | 1 | 0 | 0 | 0 | 22 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 4 (ex03_pk2_iv_bolus t2 C0 (missing_value); ex22_pk2_oral_1 t5 lambda_z points (missing_value); ex22_pk2_oral_1 t7 AUC difference in % (analysis_compare) (missing_value); ex25_oral_1 t1 t1/2 (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 3 (ex03_pk2_iv_bolus t2 cmax_tmax; ex22_pk2_oral_1 t5 lambda_z_regression; ex25_oral_1 t1 import_nca); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex03_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex06_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | 78,4058 h*ng/ml |
| ex07_iv_bolus | 7 compare | AUC(0-tlast) linear | wrong_method | auclast of lin_up_log_down | 174,333 h*ng/ml |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex12_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex15_oral_0 | 1 import_nca | lambda_z | wrong_parameter | r.squared | 4, 5,2 h, 54 h, 0,99991 |
| ex15_oral_0 | 1 import_nca | t1/2 | missing_value |  | (none) |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex19_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex21_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex22_pk2_oral_1 | 5 lambda_z_regression | lambda_z points | missing_value |  | (none) |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex22_pk2_oral_1 | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 0 l |
| ex24_pk2_iv_bolus | 7 compare | AUC difference (analysis_compare) | missing_value |  | 0 |
| ex24_pk2_iv_bolus | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | (none) |
| ex25_oral_1 | 1 import_nca | t1/2 | missing_value |  | 1 |
| ex25_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 939,022 h*ng/ml |

## Tool calls: 144 valid, 0 invalid, 0 failed of 144 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 6; by tool: {'analysis_compare': 25, 'analysis_get': 44, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 1 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["min", "ng/mL"]) | 1 |

In exercises: ex12_iv_infusion. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 10.3 s per turn, mean 4955 prompt tokens (first call), total 52 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 4 / 32 | 0 / 31 | 8 / 8 | 0 | 8 / 8 | 11.6 |
| ex02_oral_1 | 400 mg | h, ng/mL | 6 / 33 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 9.5 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 9 / 43 | 3 / 41 | 8 / 8 | 1 | 8 / 8 | 16.3 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 7 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 9.0 |
| ex05_iv_infusion | 150 mg | h, mg/L | 17 / 34 | 0 / 35 | 7 / 8 | 0 | 5 / 5 | 9.5 |
| ex06_oral_0 | 100 mg | h, ng/mL | 5 / 29 | 0 / 29 | 7 / 8 | 0 | 5 / 5 | 8.6 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 8 / 34 | 1 / 35 | 7 / 8 | 1 | 8 / 8 | 13.9 |
| ex08_oral_1 | 800 ug | min, ng/mL | 7 / 31 | 0 / 32 | 8 / 8 | 0 | 5 / 5 | 8.9 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 5 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 8.7 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 18 / 35 | 2 / 34 | 7 / 8 | 1 | 5 / 5 | 9.7 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 4 / 31 | 1 / 32 | 7 / 8 | 1 | 5 / 5 | 8.9 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 6 / 33 | 3 / 33 | 7 / 8 | 1 | 5 / 5 | 8.5 |
| ex13_oral_1 | 50 mg | h, ng/mL | 4 / 37 | 0 / 39 | 8 / 8 | 0 | 5 / 5 | 8.3 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 10 / 39 | 2 / 38 | 8 / 8 | 1 | 8 / 8 | 15.7 |
| ex15_oral_0 | 400 mg | h, mg/L | 15 / 30 | 2 / 30 | 7 / 8 | 1 | 5 / 5 | 9.2 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 6 / 32 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 9.3 |
| ex17_oral_1 | 500 mg | h, mg/L | 15 / 30 | 1 / 32 | 8 / 8 | 1 | 5 / 5 | 9.0 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 2 / 31 | 0 / 32 | 8 / 8 | 0 | 6 / 6 | 9.1 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 17 / 50 | 8 / 48 | 7 / 8 | 1 | 5 / 5 | 11.8 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 6 / 32 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 8.8 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 7 / 30 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 8.7 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 5 / 29 | 2 / 30 | 7 / 8 | 1 | 5 / 5 | 8.1 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 7 / 32 | 0 / 31 | 8 / 8 | 0 | 8 / 8 | 13.0 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 10 / 42 | 7 / 42 | 7 / 8 | 2 | 8 / 8 | 16.2 |
| ex25_oral_1 | 100 mg | h, ng/mL | 4 / 32 | 0 / 32 | 7 / 8 | 0 | 5 / 5 | 7.7 |
