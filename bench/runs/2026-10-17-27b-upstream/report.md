# Apothicaire benchmark report

date: 2026-10-17-27b-upstream, exercises_run: 5, model: Bonsai 2 27B (Ternary-Bonsai-2-27B-PTQ1_0), temperature 0.3, no fixed seed, gate v1, gate: v1

**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**

- before the gate's regeneration (first drafts): **0 / 176 = 0.0 %** (none observed: upper 95 % bound by the rule of three 3/176 = 1.70 %)
- in the answers shown (gate in the loop): **0 / 176 = 0.0 %** (none observed: upper 95 % bound by the rule of three 3/176 = 1.70 %)
- 5 exercises, 40 turns (0 failed by an error); turns with an unverified number: 0 before, 0 after; regenerated 0 (regeneration kept 0); turns shown with the badge: 0

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
| unit_conversion | 10.4 % | 4.4 % |
| arithmetic | 0.0 % | 26.0 % |
| unlabelled_misread | 11.2 % | 7.2 % |
| recall_error | 0.0 % | 0.0 % |
| other | 78.4 % | 62.4 % |

## Correctness: 38 / 40 turns fully correct; expected numbers found 107 / 110; forbidden (converted or computed) values present in 0 answers

| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |
|---|---|---|---|---|---|
| import_nca | 5 | 5 (100.0 %) | 45 / 45 | 0 / 81 | 0 / 81 |
| cmax_tmax | 5 | 5 (100.0 %) | 12 / 12 | 0 / 12 | 0 / 12 |
| clearance_volume | 5 | 5 (100.0 %) | 10 / 10 | 0 / 10 | 0 / 10 |
| half_life | 5 | 5 (100.0 %) | 10 / 10 | 0 / 29 | 0 / 29 |
| lambda_z_regression | 5 | 5 (100.0 %) | 10 / 10 | 0 / 15 | 0 / 15 |
| recall | 5 | 5 (100.0 %) | 5 / 5 | 0 / 6 | 0 / 6 |
| compare | 5 | 3 (60.0 %) | 15 / 18 | 0 / 21 | 0 / 21 |
| not_available | 5 | 5 (100.0 %) | 0 / 0 | 0 / 2 | 0 / 2 |

## Compare turn and `analysis_compare`: called in 5 of 5 compare turns (10 calls, 10 valid; 10 calls in all turns); usable in 4 (the two analyses of the exercise, the auclast row with difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); row disagreeing with the ground truth: 0; no call: 0


## Oracle check: 33 / 35 turns = 94.3 % (95 % CI, exercises resampled: 88.6-100.0 %); 107 / 110 expected numbers = 97.3 % (95 % CI, exercises resampled: 93.3-100.0 %)

Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect (not covered: not_available, no value to check).

| question type | turns | oracle-correct | expected numbers ok | wrong_parameter | wrong_method | wrong_option | missing_unit | wrong_unit | missing_value |
|---|---|---|---|---|---|---|---|---|---|
| import_nca | 5 | 5 (100.0 %) | 45 / 45 | 0 | 0 | 0 | 0 | 0 | 0 |
| cmax_tmax | 5 | 5 (100.0 %) | 12 / 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| clearance_volume | 5 | 5 (100.0 %) | 10 / 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| half_life | 5 | 5 (100.0 %) | 10 / 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| lambda_z_regression | 5 | 5 (100.0 %) | 10 / 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| recall | 5 | 5 (100.0 %) | 5 / 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| compare | 5 | 3 (60.0 %) | 15 / 18 | 0 | 0 | 0 | 0 | 0 | 3 |
| **total** | 35 | 33 (94.3 %) | 107 / 110 | 0 | 0 | 0 | 0 | 0 | 3 |

Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects 0; items the scorer missed but the oracle accepts 0; turns oracle-wrong but scorer-correct 0; turns oracle-correct but scorer-incorrect 0.

Every expected number the oracle rejects:

| exercise | turn | expected | class | detail | numbers written after the label |
|---|---|---|---|---|---|
| ex01_iv_bolus | 7 compare | AUC(0-tlast) linear | missing_value |  | (none) |
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) linear | missing_value |  | 3, 3 |
| ex04_oral_1_lag | 7 compare | AUC(0-tlast) lin-up/log-down | missing_value |  | 3, 3 |

## Tool calls: 31 valid, 0 invalid, 0 failed of 31 (validity 100.0 %)

`nca_run` calls: 10, with the right dose 10, with the right route 10; memory calls (zoom / read_message): 1; by tool: {'analysis_compare': 10, 'analysis_get': 6, 'data_import': 5, 'nca_run': 10}. invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.

## Tool-call argument audit: 0 of 15 `nca_run` / `data_import` calls differ from the exercise's intent (dose, route, AUC method alone as options; the CSV and the column units)

No deviation.

## Time: mean 8.0 s per turn, mean 4558 prompt tokens (first call), total 11 min

## Per exercise

| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |
|---|---|---|---|---|---|---|---|---|
| ex01_iv_bolus | 200 mg | h, mg/L | 0 / 40 | 0 / 40 | 7 / 8 | 0 | 4 / 4 | 7.6 |
| ex02_oral_1 | 400 mg | h, ng/mL | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 7 / 7 | 9.1 |
| ex03_pk2_iv_bolus | 300 mg | h, mg/L | 0 / 38 | 0 / 38 | 8 / 8 | 0 | 5 / 5 | 7.2 |
| ex04_oral_1_lag | 300 mg | h, ng/mL | 0 / 30 | 0 / 30 | 7 / 8 | 0 | 10 / 10 | 9.7 |
| ex05_iv_infusion | 150 mg | h, mg/L | 0 / 34 | 0 / 34 | 8 / 8 | 0 | 5 / 5 | 6.2 |
