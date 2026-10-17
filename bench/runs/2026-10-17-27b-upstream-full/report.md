# Apothicaire benchmark report

date: 2026-10-17-27b-upstream-full, exercises_run: 25, model: Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf (Q2_0) on llama-server b11700-23f7aabc1, temperature 0.3, no fixed seed, gate v1, gate: v1

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **0 / 897 = 0.0 %** (none observed: upper 95 % bound by the rule of three 3/897 = 0.33 %)
- in the answers shown (gate in the loop): **0 / 897 = 0.0 %** (none observed: upper 95 % bound by the rule of three 3/897 = 0.33 %)
- 25 exercises, 200 turns (0 failed by an error); turns with an unverified number: 0 before, 0 after; regenerated 0 (regeneration kept 0); turns shown with the badge: 0

## Failure taxonomy (unverified numbers)

| class | before the gate | in the answers shown |
|---|---|---|
| unit_conversion | 0 | 0 |
| arithmetic | 0 | 0 |
| unlabelled_misread | 0 | 0 |
| recall_error | 0 | 0 |
| other | 0 | 0 |

Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values (a class whose baseline share is large is weak evidence at that precision):

| class | random 3-digit numbers | random 4-digit numbers |
|---|---|---|
| unit_conversion | 10.8 % | 3.7 % |
| arithmetic | 0.0 % | 22.2 % |
| unlabelled_misread | 11.8 % | 8.4 % |
| recall_error | 0.0 % | 0.0 % |
| other | 77.4 % | 65.7 % |

## Correctness: 193 / 200 turns fully correct; expected numbers found 556 / 558; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 / 423 | 0 / 423 |
| cmax_tmax | 25 | 25 (100.0 %) | 58 / 58 | 0 / 62 | 0 / 62 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 / 52 | 0 / 52 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 / 135 | 0 / 135 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 / 75 | 0 / 75 |
| recall | 25 | 20 (80.0 %) | 25 / 25 | 0 / 27 | 0 / 27 |
| compare | 25 | 23 (92.0 %) | 98 / 100 | 0 / 123 | 0 / 123 |
| not_available | 25 | 25 (100.0 %) | 0 / 0 | 0 / 0 | 0 / 0 |

## Compare turn and `analysis_compare`: called in 25 of 25 compare turns (25 calls, 25 valid; 25 calls in all turns); usable in 25 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Oracle check: 166 / 175 turns = 94.9 % (95 % CI, exercises resampled: 92.0-97.1 %); 549 / 558 expected numbers = 98.4 % (95 % CI, exercises resampled: 97.5-99.1 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 25 | 25 (100.0 %) | 225 / 225 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 25 | 23 (92.0 %) | 56 / 58 | 0 | 0 | 0 | 0 | 0 | 2 |
| clearance_volume | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 25 | 25 (100.0 %) | 50 / 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 25 | 20 (80.0 %) | 20 / 25 | 0 | 0 | 0 | 5 | 0 | 0 |
| compare | 25 | 23 (92.0 %) | 98 / 100 | 0 | 0 | 0 | 0 | 0 | 2 |
| **total** | 175 | 166 (94.9 %) | 549 / 558 | 0 | 0 | 0 | 5 | 0 | 4 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 7 (ex02_oral_1 t6 dose (missing_unit); ex07_iv_bolus t2 C0 (missing_value); ex11_pk2_iv_bolus t2 C0 (missing_value); ex12_iv_infusion t6 dose (missing_unit); ex14_iv_bolus t6 dose (missing_unit); ex16_pk2_oral_1 t6 dose (missing_unit); ex22_pk2_oral_1 t6 dose (missing_unit)); items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 2 (ex07_iv_bolus t2 cmax_tmax; ex11_pk2_iv_bolus t2 cmax_tmax); turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex02_oral_1 | 6 recall | dose | missing_unit |  | 400 |
| ex07_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex08_oral_1 | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex10_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex11_pk2_iv_bolus | 2 cmax_tmax | C0 | missing_value |  | (none) |
| ex12_iv_infusion | 6 recall | dose | missing_unit |  | 500 |
| ex14_iv_bolus | 6 recall | dose | missing_unit |  | 150 |
| ex16_pk2_oral_1 | 6 recall | dose | missing_unit |  | 2000 |
| ex22_pk2_oral_1 | 6 recall | dose | missing_unit |  | 500 |

## Tool calls: 141 valid, 0 invalid, 0 failed of 141 (validity 100.0 %)

`nca_run` calls: 50, with the right dose 50, with the right route 50; memory calls (zoom / read_message): 12; by tool: {'analysis_compare': 25, 'analysis_get': 41, 'data_import': 25, 'nca_run': 50}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 0 of 75 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, AUC method alone as options; the CSV and the column units)

No deviation.

## Time: mean 8.0 s per turn, mean 4569 prompt tokens (first call), total 56 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 0 / 38 | 0 / 38 | 8 / 8 | 0 | 5 / 5 | 8.7 |
| ex02_oral_1 | 400 mg | h, ng/mL | 0 / 35 | 0 / 35 | 7 / 8 | 0 | 7 / 7 | 10.0 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 0 / 42 | 0 / 42 | 8 / 8 | 0 | 8 / 8 | 11.2 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 0 / 28 | 0 / 28 | 8 / 8 | 0 | 5 / 5 | 6.6 |
| ex05_iv_infusion | 150 mg | h, mg/L | 0 / 39 | 0 / 39 | 8 / 8 | 0 | 5 / 5 | 7.8 |
| ex06_oral_0 | 100 mg | h, ng/mL | 0 / 33 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 6.7 |
| ex07_iv_bolus | 2000 ug | h, ng/mL | 0 / 42 | 0 / 42 | 8 / 8 | 0 | 5 / 5 | 8.9 |
| ex08_oral_1 | 800 ug | min, ng/mL | 0 / 33 | 0 / 33 | 7 / 8 | 0 | 5 / 5 | 7.2 |
| ex09_pk2_oral_1 | 300 mg | h, ng/mL | 0 / 27 | 0 / 27 | 8 / 8 | 0 | 5 / 5 | 6.2 |
| ex10_oral_1_lag | 100 mg | h, mg/L | 0 / 38 | 0 / 38 | 7 / 8 | 0 | 5 / 5 | 7.4 |
| ex11_pk2_iv_bolus | 1000 ug | h, ng/mL | 0 / 44 | 0 / 44 | 8 / 8 | 0 | 9 / 9 | 12.0 |
| ex12_iv_infusion | 500 ug | min, ng/mL | 0 / 46 | 0 / 46 | 7 / 8 | 0 | 7 / 7 | 11.2 |
| ex13_oral_1 | 50 mg | h, ng/mL | 0 / 40 | 0 / 40 | 8 / 8 | 0 | 5 / 5 | 7.7 |
| ex14_iv_bolus | 150 mg | h, ng/mL | 0 / 30 | 0 / 30 | 7 / 8 | 0 | 10 / 10 | 9.9 |
| ex15_oral_0 | 400 mg | h, mg/L | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 6.4 |
| ex16_pk2_oral_1 | 2000 ug | h, ng/mL | 0 / 31 | 0 / 31 | 7 / 8 | 0 | 6 / 6 | 9.1 |
| ex17_oral_1 | 500 mg | h, mg/L | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 7.0 |
| ex18_pk2_iv_bolus | 200 mg | min, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 4 / 4 | 7.4 |
| ex19_oral_1_lag | 2000 ug | h, ng/mL | 0 / 29 | 0 / 29 | 8 / 8 | 0 | 5 / 5 | 6.4 |
| ex20_iv_infusion | 150 mg | h, ng/mL | 0 / 35 | 0 / 35 | 8 / 8 | 0 | 5 / 5 | 6.4 |
| ex21_oral_0 | 5000 ug | h, ng/mL | 0 / 33 | 0 / 33 | 8 / 8 | 0 | 5 / 5 | 6.5 |
| ex22_pk2_oral_1 | 500 mg | h, mg/L | 0 / 40 | 0 / 40 | 7 / 8 | 0 | 5 / 5 | 7.0 |
| ex23_iv_bolus | 300 mg | min, ng/mL | 0 / 37 | 0 / 37 | 8 / 8 | 0 | 5 / 5 | 7.8 |
| ex24_pk2_iv_bolus | 150 mg | h, ng/mL | 0 / 44 | 0 / 44 | 8 / 8 | 0 | 5 / 5 | 8.2 |
| ex25_oral_1 | 100 mg | h, ng/mL | 0 / 30 | 0 / 30 | 8 / 8 | 0 | 5 / 5 | 6.4 |
