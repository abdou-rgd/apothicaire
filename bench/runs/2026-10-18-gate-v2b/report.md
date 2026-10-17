# Apothicaire benchmark report

date: 2026-10-18-gate-v2b, exercises_run: 25, model: Ternary-Bonsai-2-27B-PTQ1_0.gguf (PTQ1_0) on llama-server b10743-adfffbe41, temperature 0.3, no fixed seed, gate v2, gate: v2

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **221 / 869 = 25.4 %** (95 % CI, exercises resampled: 20.6-30.4 %)
- in the answers shown (gate in the loop): **17 / 874 = 1.9 %** (95 % CI, exercises resampled: 0.9-3.1 %)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 48 before, 9 after; regenerated 48 (regeneration kept 48); turns shown with the badge: 9

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 6 | 0 |
| recall_error | 2 | 0 |
| other | 213 | 17 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 11.0 % | 3.8 % |
| arithmetic | 0.0 % | 23.0 % |
| unlabelled_misread | 11.8 % | 8.3 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.2 % | 64.9 % |

## Correctness: 183 / 200 turns fully correct; expected numbers found 545 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 162 / 436 | 17 / 449 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 2 / 59 | 0 / 59 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 53 | 0 / 53 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 39 / 132 | 0 / 130 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 11 / 61 | 0 / 60 |
| recall | 25 | 21 (84.0 %) | 25 / 25 | 2 / 29 | 0 / 27 |
| compare | 25 | 12 (48.0 %) | 87 / 100 | 5 / 99 | 0 / 96 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 0 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Oracle check: 157 / 175 turns = 89.7 % (95 % CI, exercises resampled: 85.1-93.7 %); 540 / 558 expected numbers = 96.8 % (95 % CI, exercises resampled: 95.3-98.0 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 24 (96.0 %) | 57 / 58 | 0 | 0 | 1 | 0 | 0 | 0 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 21 (84.0 %) | 21 / 25 | 0 | 0 | 0 | 4 | 0 | 0 |
| compare | 25 | 12 (48.0 %) | 87 / 100 | 0 | 3 | 1 | 0 | 0 | 9 |
| **total** | 175 | 157 (89.7 %) | 540 / 558 | 0 | 3 | 2 | 4 | 0 | 9 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 5 (ex08_oral_1 t6 dose (missing_unit); ex09_pk2_oral_1 t6 dose (missing_unit); ex12_iv_infusion t6 dose (missing_unit); ex14_iv_bolus t2 C0 (wrong_option); ex14_iv_bolus t6 dose (missing_unit)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 1 (ex14_iv_bolus t2 cmax_tmax); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex02_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex05_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 0,297782 h*mg/l |
| ex06_oral_0 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex08_oral_1 | 6 recall | dose | missing_unit |  | 800 |
| ex08_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 3, 3 min*ng/ml, 46762,6 min*ng/ml, 0 |
| ex09_pk2_oral_1 | 6 recall | dose | missing_unit |  | 300 |
| ex09_pk2_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex12_iv_infusion | 6 recall | dose | missing_unit |  | 500 |
| ex12_iv_infusion | 7 compare | AUC(0-tlast) linear | missing_value |  | 246,834 min*ng/ml |
| ex13_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex14_iv_bolus | 2 cmax_tmax | C0 | wrong_option | analysis=2 | 0, 1,2 h |
| ex14_iv_bolus | 6 recall | dose | missing_unit |  | 150 |
| ex14_iv_bolus | 7 compare | AUC(0-tlast) linear | wrong_option | analysis=2 | 206,779 h*ng/ml |
| ex20_iv_infusion | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 37854,6 h*ng/ml |
| ex22_pk2_oral_1 | 7 compare | AUC(0-tlast) lin-up/log-down | wrong_method | auclast of linear | 114,931 h*mg/l |
| ex23_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | 35789,1 min*ng/ml |

## Tool calls: 163 valid, 1 invalid, 0 failed of 164 (validity 99.4 %)

`nca_run` calls: 53, with the right dose 53, with the right route 53; memory calls (zoom / read_message): 10; by tool: {'analysis_compare': 25, 'analysis_get': 61, 'data_import': 25, 'nca_run': 53}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 4 of 78 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, AUC method alone as options; the CSV and the column units)

| deviation | calls |
|---|---|
| nca_run: options.start = "zero" (intended null) | 2 |
| nca_run: analysis = 2 (intended null) | 1 |
| nca_run: options.start = "c0" (intended null) | 1 |

In exercises: ex10_oral_1_lag, ex14_iv_bolus. A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).

## Time: mean 13.9 s per turn, mean 4845 prompt tokens (first call), total 80 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 9 / 37 | 1 / 35 | 7 / 8 | 1 | 9 / 9 | 18.6 |
| ex02_oral_1 | 400 mg | h, ng/mL | 4 / 32 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 11.4 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 18 / 42 | 4 / 43 | 8 / 8 | 1 | 8 / 8 | 16.6 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 5 / 33 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 10.8 |
| ex05_iv_infusion | 150 mg | h, mg/L | 12 / 34 | 0 / 31 | 7 / 8 | 0 | 5 / 5 | 9.9 |
| ex06_oral_0 | 100 mg | h, ng/mL | 6 / 31 | 0 / 31 | 7 / 8 | 0 | 7 / 7 | 14.4 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 8 / 41 | 2 / 42 | 8 / 8 | 1 | 9 / 9 | 15.9 |
| ex08_oral_1 | 800 ug | min, ng/mL | 5 / 43 | 0 / 43 | 6 / 8 | 0 | 8 / 8 | 16.4 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 5 / 35 | 0 / 35 | 6 / 8 | 0 | 5 / 5 | 10.7 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 15 / 37 | 0 / 36 | 7 / 8 | 0 | 5 / 5 | 12.0 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 10 / 33 | 2 / 34 | 8 / 8 | 1 | 8 / 8 | 15.9 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 6 / 33 | 0 / 34 | 6 / 8 | 0 | 7 / 7 | 14.5 |
| ex13_oral_1 | 50 mg | h, ng/mL | 5 / 34 | 0 / 35 | 7 / 8 | 0 | 5 / 5 | 11.8 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 21 / 42 | 1 / 41 | 6 / 8 | 1 | 12 / 12 | 27.1 |
| ex15_oral_0 | 400 mg | h, mg/L | 8 / 31 | 0 / 31 | 8 / 8 | 0 | 5 / 5 | 10.7 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 5 / 33 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 12.0 |
| ex17_oral_1 | 500 mg | h, mg/L | 8 / 36 | 2 / 37 | 8 / 8 | 1 | 5 / 5 | 13.1 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 6 / 33 | 0 / 34 | 8 / 8 | 0 | 4 / 4 | 11.7 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 8 / 31 | 0 / 29 | 8 / 8 | 0 | 5 / 5 | 11.0 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 4 / 31 | 0 / 31 | 7 / 8 | 0 | 6 / 7 | 12.6 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 6 / 36 | 2 / 37 | 8 / 8 | 1 | 5 / 5 | 11.1 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 18 / 32 | 0 / 33 | 7 / 8 | 0 | 6 / 6 | 14.2 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 10 / 31 | 1 / 32 | 7 / 8 | 1 | 9 / 9 | 12.9 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 8 / 34 | 0 / 34 | 8 / 8 | 0 | 10 / 10 | 17.3 |
| ex25_oral_1 | 100 mg | h, ng/mL | 11 / 34 | 2 / 35 | 8 / 8 | 1 | 5 / 5 | 13.6 |
