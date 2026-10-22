# Apothicaire benchmark report

date: 2026-10-22, exercises_run: 25, model: claude-opus-5-5 on the Anthropic Messages API, thinking adaptive, effort medium, provider sampling (no temperature, no seed), gate: v1

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **11 / 1682 = 0.7 %** (95 % CI, exercises resampled: 0.3-1.1 %, descriptive)
- in the answers shown (gate in the loop): **0 / 1678 = 0.0 %** (none observed; descriptive, see the exercise level below)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 10 before, 0 after; regenerated 10 (regeneration kept 10); turns shown with the badge: 0

## Exercise level (the unit of inference, FROZEN_SET.md §3)

- exercises not passed (a turn not correct, judged by the rubric outcomes): **23 / 25 = 92.0 % (exact 95 % CI 74.0-99.0 %)** (ex01_iv_bolus, ex02_oral_1, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex09_pk2_oral_1, ex10_oral_1_lag, ex11_pk2_iv_bolus, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex18_pk2_iv_bolus, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1)
- exercises in which an answer shown carried an unverified number or a marker: **0 / 25 (one-sided 95 % upper bound 11.3 %)**

Per-turn and per-number rates in this report are descriptive: turns of one exercise share the data and the memory, numbers of one turn share one tool result, so no bound is computed on them (no rule of three on numbers).

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 2 | 0 |
| recall_error | 0 | 0 |
| other | 9 | 0 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.9 % |
| arithmetic | 0.0 % | 22.7 % |
| unlabelled_misread | 11.7 % | 8.3 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 65.0 % |

## Correctness (development scorer `score_turn`): 200 / 200 turns fully correct (0 turns failed by an error count as incorrect); expected numbers found 558 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 / 537 | 0 / 537 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 98 | 0 / 98 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 98 | 0 / 98 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 8 / 297 | 0 / 291 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 / 140 | 0 / 140 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 / 37 | 0 / 37 |
| compare | 25 | 25 (100.0 %) | 100 / 100 | 3 / 399 | 0 / 401 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 76 | 0 / 76 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Outcomes (FROZEN_SET.md §6.1, rubric 2026-10-21): 159 / 200 turns CORRECT; exercises with all turns CORRECT 2 / 25

Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of §6.2 (`score.rubric_turn`) says CORRECT or WRONG.

| question type | ERROR | TIMEOUT | LOOP | ABSTAINED | WRONG | CORRECT |
|---|---|---|---|---|---|---|
| import_nca | 0 | 0 | 0 | 0 | 0 | 25 |
| cmax_tmax | 0 | 0 | 0 | 0 | 1 | 24 |
| clearance_volume | 0 | 0 | 0 | 0 | 0 | 25 |
| half_life | 0 | 0 | 0 | 0 | 16 | 9 |
| lambda_z_regression | 0 | 0 | 0 | 0 | 0 | 25 |
| recall | 0 | 0 | 0 | 0 | 0 | 25 |
| compare | 0 | 0 | 0 | 0 | 20 | 5 |
| not_available | 0 | 0 | 0 | 0 | 4 | 21 |
| **total** | 0 | 0 | 0 | 0 | 41 | 159 |

## Oracle check: 166 / 175 turns = 94.9 % (95 % CI, exercises resampled: 92.0-97.1 %); 547 / 558 expected numbers = 98.0 % (95 % CI, exercises resampled: 96.8-99.1 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 25 (100.0 %) | 25 / 25 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 25 | 16 (64.0 %) | 89 / 100 | 0 | 0 | 0 | 0 | 0 | 11 |
| **total** | 175 | 166 (94.9 %) | 547 / 558 | 0 | 0 | 0 | 0 | 0 | 11 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 11 (ex01_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex02_oral_1 t7 AUC(0-tlast) linear (missing_value); ex03_pk2_iv_bolus t7 AUC difference (analysis_compare) (missing_value); ex08_oral_1 t7 AUC difference (analysis_compare) (missing_value); ex11_pk2_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex13_oral_1 t7 AUC(0-tlast) linear (missing_value); ex14_iv_bolus t7 AUC(0-tlast) linear (missing_value); ex14_iv_bolus t7 AUC difference (analysis_compare) (missing_value); ex14_iv_bolus t7 AUC difference in % (analysis_compare) (missing_value); ex16_pk2_oral_1 t7 AUC(0-tlast) linear (missing_value); ex25_oral_1 t7 AUC(0-tlast) linear (missing_value)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 9 (ex01_iv_bolus t7 compare; ex02_oral_1 t7 compare; ex03_pk2_iv_bolus t7 compare; ex08_oral_1 t7 compare; ex11_pk2_iv_bolus t7 compare; ex13_oral_1 t7 compare; ex14_iv_bolus t7 compare; ex16_pk2_oral_1 t7 compare; ex25_oral_1 t7 compare); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 0, 2854 h*ng/ml, 3,7 % |
| ex03_pk2_iv_bolus | 7 compare | AUC difference (analysis_compare) | missing_value |  | (none) |
| ex08_oral_1 | 7 compare | AUC difference (analysis_compare) | missing_value |  | 220, 3100 min, 530 min, 1300 min |
| ex11_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 23 h, 45 h |
| ex13_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 7 compare | AUC difference (analysis_compare) | missing_value |  | 1 % |
| ex14_iv_bolus | 7 compare | AUC difference in % (analysis_compare) | missing_value |  | 0.842236 % |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 21.0786 h*ng/ml, 14, 79 h |
| ex25_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |

## Tool calls: 100 valid, 21 invalid, 0 failed of 121 (validity 82.6 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 10; by tool: {'analysis_compare': 25, 'data_import': 46, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 30 of 96 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, the AUC method and the units as options; the CSV and the column units)

| deviation | calls |
|---|---|
| nca_run: name = "Bolus IV 150 mg - lin-up/log-down" (intended null) | 2 |
| nca_run: name = "Exercice bolus IV 200 mg - lin-up/log-down" (intended null) | 2 |
| nca_run: name = "Exercice bolus IV 300 mg - lin-up/log-down" (intended null) | 2 |
| nca_run: name = "Exercice oral 2000 ug - lin-up/log-down" (intended null) | 2 |
| nca_run: name = "Exercice oral 400 mg - lin-up/log-down" (intended null) | 2 |
| nca_run: name = "Exercice perfusion 150 mg - lin-up/log-down" (intended null) | 2 |
| data_import: csv = "<101 chars, DIFFERENT from the exercise CSV>" (intended "identical to the exercise CSV") | 1 |
| data_import: csv = "<106 chars, DIFFERENT from the exercise CSV>" (intended "identical to the exercise CSV") | 1 |
| data_import: csv = "<111 chars, DIFFERENT from the exercise CSV>" (intended "identical to the exercise CSV") | 1 |
| data_import: csv = "<113 chars, DIFFERENT from the exercise CSV>" (intended "identical to the exercise CSV") | 1 |
| nca_run: name = "Bolus IV 1000 µg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice IV bolus - lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 100 mg - lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 300 mg - lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 50 mg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 500 mg - lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 500 mg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 5000 µg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice oral 800 µg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "Exercice perfusion 500 µg – lin-up/log-down" (intended null) | 1 |
| nca_run: name = "NCA lin-up/log-down 300 mg PO" (intended null) | 1 |
| nca_run: name = "NCA lin-up/log-down" (intended null) | 1 |
| nca_run: name = "NCA linéaire 300 mg PO" (intended null) | 1 |
| nca_run: name = "NCA oral 100 mg lin-up/log-down" (intended null) | 1 |

In exercises: ex01_iv_bolus, ex02_oral_1, ex03_pk2_iv_bolus, ex04_oral_1_lag, ex05_iv_infusion, ex06_oral_0, ex07_iv_bolus, ex08_oral_1, ex09_pk2_oral_1, ex10_oral_1_lag, ex11_pk2_iv_bolus, ex12_iv_infusion, ex13_oral_1, ex14_iv_bolus, ex15_oral_0, ex16_pk2_oral_1, ex17_oral_1, ex18_pk2_iv_bolus, ex19_oral_1_lag, ex20_iv_infusion, ex21_oral_0, ex22_pk2_oral_1, ex23_iv_bolus, ex24_pk2_iv_bolus, ex25_oral_1. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 6.7 s per turn, mean 6954 prompt tokens (first call), total 30 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 0 / 72 | 0 / 72 | 8 / 8 | 0 | 4 / 5 | 7.1 |
| ex02_oral_1 | 400 mg | h, ng/mL | 0 / 60 | 0 / 60 | 8 / 8 | 0 | 4 / 4 | 5.4 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 0 / 65 | 0 / 65 | 8 / 8 | 0 | 4 / 5 | 6.8 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 0 / 75 | 0 / 75 | 8 / 8 | 0 | 4 / 5 | 6.4 |
| ex05_iv_infusion | 150 mg | h, mg/L | 0 / 73 | 0 / 73 | 8 / 8 | 0 | 4 / 4 | 6.2 |
| ex06_oral_0 | 100 mg | h, ng/mL | 1 / 70 | 0 / 69 | 8 / 8 | 0 | 4 / 5 | 7.1 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 0 / 80 | 0 / 80 | 8 / 8 | 0 | 4 / 4 | 7.5 |
| ex08_oral_1 | 800 ug | min, ng/mL | 0 / 66 | 0 / 66 | 8 / 8 | 0 | 4 / 5 | 6.5 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 0 / 65 | 0 / 65 | 8 / 8 | 0 | 4 / 5 | 5.4 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 0 / 73 | 0 / 73 | 8 / 8 | 0 | 4 / 5 | 7.8 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 1 / 62 | 0 / 62 | 8 / 8 | 0 | 4 / 5 | 6.7 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 3 / 63 | 0 / 64 | 8 / 8 | 0 | 4 / 5 | 7.0 |
| ex13_oral_1 | 50 mg | h, ng/mL | 1 / 75 | 0 / 73 | 8 / 8 | 0 | 4 / 4 | 6.5 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 0 / 84 | 0 / 84 | 8 / 8 | 0 | 4 / 5 | 8.5 |
| ex15_oral_0 | 400 mg | h, mg/L | 0 / 64 | 0 / 64 | 8 / 8 | 0 | 4 / 5 | 6.5 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 1 / 64 | 0 / 64 | 8 / 8 | 0 | 4 / 5 | 6.6 |
| ex17_oral_1 | 500 mg | h, mg/L | 0 / 60 | 0 / 60 | 8 / 8 | 0 | 4 / 5 | 5.6 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 0 / 65 | 0 / 65 | 8 / 8 | 0 | 4 / 5 | 6.4 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 0 / 58 | 0 / 58 | 8 / 8 | 0 | 4 / 5 | 5.7 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 1 / 64 | 0 / 63 | 8 / 8 | 0 | 4 / 5 | 6.2 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 0 / 63 | 0 / 63 | 8 / 8 | 0 | 4 / 5 | 6.0 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 1 / 59 | 0 / 60 | 8 / 8 | 0 | 4 / 5 | 7.8 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 1 / 69 | 0 / 68 | 8 / 8 | 0 | 4 / 5 | 7.9 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 1 / 65 | 0 / 64 | 8 / 8 | 0 | 4 / 5 | 6.7 |
| ex25_oral_1 | 100 mg | h, ng/mL | 0 / 68 | 0 / 68 | 8 / 8 | 0 | 4 / 5 | 6.7 |
