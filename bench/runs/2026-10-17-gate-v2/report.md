# Apothicaire benchmark report

date: 2026-10-17-gate-v2, exercises_run: 25, model: Bonsai 2 27B (Ternary-Bonsai-2-27B-PTQ1_0), temperature 0.3, no fixed seed, gate v2, gate: v2

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **153 / 876 = 17.5 %** (95 % CI, exercises resampled: 15.6-19.4 %)
- in the answers shown (gate in the loop): **51 / 842 = 6.1 %** (95 % CI, exercises resampled: 4.6-7.6 %)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 62 before, 36 after; regenerated 62 (regeneration kept 61); turns shown with the badge: 36

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 1 | 2 |
| arithmetic | 15 | 1 |
| unlabelled_misread | 11 | 5 |
| recall_error | 2 | 0 |
| other | 124 | 43 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.9 % | 3.8 % |
| arithmetic | 0.0 % | 22.7 % |
| unlabelled_misread | 12.1 % | 8.5 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.0 % | 65.0 % |

## Correctness: 182 / 200 turns fully correct; expected numbers found 544 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 77 / 418 | 21 / 401 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 58 | 0 / 58 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 52 | 0 / 52 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 56 / 149 | 27 / 139 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 9 / 60 | 0 / 60 |
| recall | 25 | 21 (84.0 %) | 25 / 25 | 2 / 31 | 0 / 29 |
| compare | 25 | 11 (44.0 %) | 86 / 100 | 9 / 108 | 3 / 103 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 0 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Oracle check: 157 / 175 turns = 89.7 % (95 % CI, exercises resampled: 86.3-93.1 %); 540 / 558 expected numbers = 96.8 % (95 % CI, exercises resampled: 95.7-97.8 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 21 (84.0 %) | 21 / 25 | 0 | 0 | 0 | 4 | 0 | 0 |
| compare | 25 | 11 (44.0 %) | 86 / 100 | 0 | 0 | 0 | 0 | 0 | 14 |
| **total** | 175 | 157 (89.7 %) | 540 / 558 | 0 | 0 | 0 | 4 | 0 | 14 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 4 (ex06_oral_0 t6 dose (missing_unit); ex12_iv_infusion t6 dose (missing_unit); ex19_oral_1_lag t6 dose (missing_unit); ex24_pk2_iv_bolus t6 dose (missing_unit)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 0; turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 2, 1 |
| ex03_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,297782 h*mg/l, 2,03244 % |
| ex06_oral_0 | 6 recall | dose | missing_unit |  | 100 |
| ex07_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex08_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | 2 |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex12_iv_infusion | 6 recall | dose | missing_unit |  | 500 |
| ex15_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex16_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex18_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 2 |
| ex19_oral_1_lag | 6 recall | dose | missing_unit |  | 2000 |
| ex19_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex21_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex24_pk2_iv_bolus | 6 recall | dose | missing_unit |  | 150 |
| ex24_pk2_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |

## Tool calls: 149 valid, 0 invalid, 0 failed of 149 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 14; by tool: {'analysis_compare': 25, 'analysis_get': 48, 'data_import': 25, 'export_table': 1, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 4 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, AUC method alone as options; the CSV and the column units)

| deviation | calls |
|---|---|
| data_import: columns.unit = [] (intended ["h", "ng/mL"]) | 3 |
| data_import: columns.unit = [] (intended ["h", "mg/L"]) | 1 |

In exercises: ex05_iv_infusion, ex09_pk2_oral_1, ex11_pk2_iv_bolus, ex21_oral_0. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 13.7 s per turn, mean 4707 prompt tokens (first call), total 81 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 8 / 39 | 4 / 35 | 7 / 8 | 3 | 7 / 7 | 16.4 |
| ex02_oral_1 | 400 mg | h, ng/mL | 8 / 37 | 5 / 38 | 8 / 8 | 2 | 7 / 7 | 14.7 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 7 / 36 | 2 / 32 | 7 / 8 | 1 | 10 / 10 | 16.6 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 7 / 34 | 4 / 32 | 8 / 8 | 2 | 5 / 5 | 12.9 |
| ex05_iv_infusion | 150 mg | h, mg/L | 6 / 32 | 3 / 32 | 7 / 8 | 2 | 5 / 5 | 12.0 |
| ex06_oral_0 | 100 mg | h, ng/mL | 6 / 36 | 3 / 35 | 7 / 8 | 1 | 5 / 5 | 12.1 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 9 / 40 | 2 / 40 | 7 / 8 | 1 | 9 / 9 | 17.3 |
| ex08_oral_1 | 800 ug | min, ng/mL | 9 / 33 | 3 / 31 | 7 / 8 | 3 | 7 / 7 | 15.8 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 5 / 37 | 0 / 36 | 7 / 8 | 0 | 5 / 5 | 12.3 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 7 / 37 | 1 / 32 | 7 / 8 | 1 | 5 / 5 | 13.4 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 8 / 32 | 3 / 32 | 8 / 8 | 2 | 4 / 4 | 11.8 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 9 / 36 | 1 / 33 | 7 / 8 | 1 | 4 / 4 | 13.4 |
| ex13_oral_1 | 50 mg | h, ng/mL | 7 / 35 | 3 / 34 | 8 / 8 | 2 | 6 / 6 | 15.6 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 3 / 32 | 3 / 32 | 8 / 8 | 2 | 8 / 8 | 14.6 |
| ex15_oral_0 | 400 mg | h, mg/L | 5 / 33 | 1 / 31 | 7 / 8 | 1 | 5 / 5 | 11.6 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 4 / 33 | 1 / 33 | 7 / 8 | 1 | 5 / 5 | 12.2 |
| ex17_oral_1 | 500 mg | h, mg/L | 6 / 32 | 3 / 32 | 8 / 8 | 2 | 5 / 5 | 12.6 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 6 / 36 | 2 / 35 | 7 / 8 | 2 | 4 / 4 | 13.7 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 5 / 33 | 2 / 33 | 6 / 8 | 2 | 5 / 5 | 11.8 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 4 / 39 | 0 / 36 | 7 / 8 | 0 | 4 / 4 | 12.3 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 5 / 41 | 1 / 39 | 7 / 8 | 1 | 5 / 5 | 12.7 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 5 / 32 | 1 / 31 | 8 / 8 | 1 | 5 / 5 | 12.0 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 7 / 34 | 1 / 33 | 8 / 8 | 1 | 9 / 9 | 17.3 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 3 / 34 | 1 / 36 | 6 / 8 | 1 | 8 / 8 | 14.1 |
| ex25_oral_1 | 100 mg | h, ng/mL | 4 / 33 | 1 / 29 | 8 / 8 | 1 | 7 / 7 | 13.8 |
