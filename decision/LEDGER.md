# Evaluation ledger (D-01)

Item 6 of the reordered next steps in `PLAN.md`, answering insight 6 of the Astra review (`notes/review-astra-2026-10-09.md`) and the
reviewer's attack on the calibration claim (`ood/REVIEW.md`): every counting population used in the READMEs and reports, with the exact rule
that produces it, the file or function that implements it, and the reconciliation of the figures that look inconsistent. Synthetic data only.

**How to read it.** A figure written here is either recomputed from files of the repository by `tests/test_ledger.py` (stored run JSON, the
exercises of `bench/exercises/`, the rows of `decision/data/`, the generator constants) or quoted from a report, and then the test checks
that the report still says so. The register at the end lists every key with its value; the test fails if the register, the recomputation
and the prose disagree, and fails on a fraction in the prose that the register does not hold. Run it with
`python -m unittest tests.test_ledger`. Files that are not on disk (`decision/data/` is git-ignored) skip their checks with a message.
Nothing here changes a report or a README; where a report is unclear the ledger says what the number is, and section 8 lists what it
could not reconcile.

Vocabulary used throughout, one word per unit, never mixed:

| word | unit | example |
|---|---|---|
| **turn** | one question of the scripted conversation of one benchmark exercise | 25 exercises x 8 turns |
| **row** | one record of a decision dataset (a state and its 20 closed questions) | 36 or 46 rows per exercise |
| **cell** or **decision** | one answer to one closed question of one row | a row has 20 cells |
| **slot** | one value a turn is required to contain (the oracle's `expect["must"]` item) | 558 and 556 |
| **number** | one numeric token of an answer text, extracted by `gate.extract_numbers` and not exempt | 691, 709, 926 |
| **call** | one `decide` call (20 answers) or one tool call | 225 decide calls, 250 tool calls |

## 1. Benchmark turns: 200 turns, 175 scored by the oracle

`bench/scripts.build_script(meta, csv)` writes, for each of the 25 exercises of `bench/exercises/`, the 8 turns of `scripts.KINDS`: `import_nca`,
`cmax_tmax`, `clearance_volume`, `half_life`, `lambda_z_regression`, `recall`, `compare`, `not_available`. So 25 x 8 = 200 turns, the same
200 for the 27B pipeline and for the decision harness.

Two judgements run on them, with two denominators:

| judgement | function | turns it covers | rule |
|---|---|---|---|
| **scorer** | `bench/score.score_turn` | all 200 | every `must` value present (gate rounding rule), no `must_not` value, every `words` pattern present, and `no_new_numbers` respected |
| **oracle** | `bench/score.oracle_turn`, `oracle_exercise` | the turns whose expectation has `must` items: 175 | each `must` item: the number written after the item's label is the engine's value, from the right analysis, with the engine's unit |

The 25 turns left out of the oracle are exactly the 25 `not_available` turns (kind 8 of each exercise). Their expectation has no `must` item,
because the right answer contains no number: `build_script` gives them `words` (a pattern of `scripts.NOT_AVAILABLE`, French and English
phrasings of "this parameter is not computed"), `no_new_numbers` and `not_calculated_parameter`, the parameter that `meta.json` lists in
`ground_truth.nca.linear.not_calculated` (C0 after an oral dose, Tlag after an IV dose or infusion; `build_script` asserts it). `oracle_turn`
returns `None` for them (`not_covered` in the reports).

What the 25 turns are scored on instead, therefore, is the scorer only: **the answer says the parameter is not available, and contains no
number that the gate cannot find in a tool result or a user message**. That is the whole check. It cannot see whether the answer is a
refusal or an ordinary reading: in the trained harness run, 19 of the 25 turns took the reading path (the engine's own "not calculated"
sentence with a header) and both judgements passed them (README Step 5). So the three lines of a report mean:

| line | denominator | covers the not-available turns? |
|---|---|---|
| turns fully correct, scorer | 200 | yes, by words and no new number |
| oracle-correct turns | 175 | no |
| oracle-correct numbers | slots, section 3 | no |

Stored runs, recomputed from the run JSON (`score.correct`, `oracle.correct`): 27B first run 193/200 scorer turns and 168/175 oracle turns;
27B second run (`analysis_compare` as seventh tool) 195/200 and 170/175; the decision harness 200/200 and 175/175 in every stored run.

## 2. Rows per exercise in the decision datasets

A row is one (exercise, turn kind, wording) triple: the state of the conversation at that turn and the 20 closed questions. The number of
rows of an exercise is the sum over turn kinds of the wordings drawn for that kind; the introduction line, the way the dose is written
(with its unit 60 %, in another unit 20 %, without a unit 20 %), the route phrase and the BLQ note are **draws inside a row**, not factors
that multiply rows (`make_dataset.build_row`, `exercise_rows`). Intros are therefore not a multiplier.

| version | kinds | wordings per kind | rows per exercise |
|---|---|---|---|
| v1 (2026-10-09, commit bc47025, `PARAPHRASES_PER_KIND` = 2) | 12: the 8 scripted kinds and `nca_other`, `fit_pk1`, `fit_pk2`, `simulate` | scripted kinds: the scripted wording and 2 paraphrases = 3; extra kinds: 3 paraphrases = 3 | 12 x 3 = **36** |
| v2 (2026-10-10, `make_dataset.PARAPHRASES`) | 15: the 8 scripted and 7 extra (`nca_other`, `fit_pk1`, `fit_pk2`, `simulate`, `nca_oneline`, `compare_directed`, `not_supported`) | scripted kinds: scripted + 2 = 3; six extra kinds: 3; `nca_oneline`: 4 | 8 x 3 + 6 x 3 + 4 = **46** |

v1 gives 720 held-out rows for 20 held-out exercises (36 each), 1980 train rows for 55 exercises and 900 bench rows for 25; the v1 held-out
file is still on disk (a stale copy, git-ignored), the v1 train and bench files were overwritten by v2, so only the stored run JSON supports
v1 bench figures. v2 per file, recomputed from `decision/data/*.jsonl`:

| file | exercises | rows per exercise | rows |
|---|---|---|---|
| `train.jsonl` | 55 train exercises | 46 | 2530 |
| `heldout_exercises.jsonl` | 20 held-out exercises | 46 | 920 |
| `heldout_wordings.jsonl` | the 55 train exercises, held-out wordings | 15 (one per kind) | 825 |
| `heldout_both.jsonl` | the 20 held-out exercises, held-out wordings | 30 (two per kind), 29 for 7 exercises where a kind has only one compatible held-out wording | 593 |
| `bench.jsonl` | the 25 benchmark exercises | 46 | 1150 |

**Relation to the 8 benchmark turns.** In `bench.jsonl`, 8 of the 46 rows of an exercise carry the scripted wording of `bench/scripts.py`
(`factors.scripted_wording`): 200 rows, one per benchmark turn, the rows the gold decider reads. The other 950 are paraphrases and extra
kinds that the benchmark never asks. Two numbers look alike and are unrelated: the 175 oracle turns, and the 175 `analysis` = `nca` rows
of `bench.jsonl` (7 NCA rows x 25 exercises). The 36 and 46 rows per exercise are not conversation turns; they are the dataset's coverage of
the question types.

## 3. The number populations

Four different things are called "numbers" in the READMEs. They never share a denominator.

| name | unit | counted by | rule | implemented in |
|---|---|---|---|---|
| **slots** (the "oracle numbers", 558, 556, 508) | a value that the turn is required to contain | the expectation of the turn, before the answer is read | `expect["must"]` items of the 175 oracle turns; per exercise 9 (turn 1) + 2 or 3 (turn 2: 3 after an IV bolus, which adds C0) + 2 + 2 + 2 + 1 (recall: the dose) + 2 (turn 7: both AUC) + 0 = 20 or 21 | `scripts.build_script`, `scripts.must` |
| **compare slots** | the engine's difference and percentage of the compare turn | added to turn 7 only when the model (or harness) used `analysis_compare` and the result holds the `auclast` row | +2 per usable compare turn | `scripts.resolve_compare` |
| **gate-checked numbers** ("rendered", "checked": 691, 709, 926, 932, 827, 1698, 778) | a numeric token written in an answer | the gate, on the text of the answer | every token except the exempt ones: integers 0 to 20 without a unit, years, ISO dates, label numbers ("step 3", list markers), a unit's own 1 or exponent, a bare power of ten | `gate.extract_numbers`, `gate.check` (`numbers_total`); stored as `numbers_total_before` and `numbers_total_after` in each turn |
| **tool calls** | one call to a Caladrius tool | the run record | valid, invalid, failed; the argument audit covers only `nca_run` and `data_import` calls | `bench/run_bench.py`, `score.tool_arg_audit` |

### 3.1 Slots: 558 against 556, and why the fixed maximum is 558

Static rule, before any run: 17 exercises x 20 slots + 8 IV-bolus exercises x 21 slots = **508** slots (the 8 IV-bolus exercises are those for which
`scripts.kind_of` gives `iv_bolus`, the two-compartment IV bolus included). With the compare turn resolved (+2 for each of the 25 compare
turns) the maximum is **558**.

| run | slots required | how | slots right | turns right |
|---|---|---|---|---|
| 27B, 2026-10-09 (six tools) | 508 | no `analysis_compare`: all 25 compare turns keep the strict static rule | 494/508 | 168/175 |
| 27B, 2026-10-09b (seventh tool) | 556 | 24 compare turns resolved (4 slots), 1 not (2 slots: ex12, which never produced a usable comparison) | 549/556 | 170/175 |
| decision harness, any stored run | 558 | the harness always calls `analysis_compare` on the decided pair: 25 resolved | 558/558 | 175/175 |

The denominator is **slots required, not numbers emitted**: a value the answer omits is a slot that is not met (the oracle class
`missing_value`), so an omission lowers the numerator and cannot hide behind a smaller denominator. The weak point is the other direction:
the compare slots are decided after the run, from what the model did, so 556 is not a denominator fixed before the outputs exist. Against
the fixed maximum of 558, the 27B's second run is at most 549/558 (the two slots of the unresolved turn were not met, since the turn never
obtained the engine's difference and percentage). A comparison of A and B should quote 558 for both, or both denominators.

The scorer counts the same slots, so scorer figures sit beside the oracle's: 496/508 and 552/556 for the 27B, 558/558 for the harness. They
differ from the oracle's only in what counts as a hit (the scorer looks for the value anywhere in the answer, the oracle for the value after
its label and with its unit).

### 3.2 Gate-checked numbers: 691, 709, 778, 1698, 926, 932, 827

This is the population of the "unverified numbers over numbers checked" lines. It counts what the answer **wrote**, so it depends on how
much the pipeline writes, and it is not the slot count (the answer also contains ids, doses, the second AUC value, units' numbers that are
not exempt). Per turn kind, from the stored run records (first drafts for the 27B; for the harness first draft and answer are the same):

<!-- bykind:begin -->
| run | import_nca | cmax_tmax | clearance_volume | half_life | lambda_z_regression | recall | compare | not_available | all |
|---|---|---|---|---|---|---|---|---|---|
| 27B, 2026-10-09 (first drafts) | 428 | 59 | 54 | 121 | 74 | 28 | 168 | 0 | 932 |
| 27B, 2026-10-09b | 421 | 63 | 53 | 137 | 80 | 28 | 141 | 3 | 926 |
| harness, gold, step 4 (`parameter_asked`) | 309 | 309 | 309 | 309 | 309 | 28 | 125 | 0 | 1698 |
| harness, gold, step 4b (`asked_<key>`) | 251 | 84 | 76 | 76 | 51 | 28 | 125 | 0 | 691 |
| harness, trained 0.8B (step 5) | 251 | 84 | 76 | 76 | 51 | 28 | 125 | 18 | 709 |
| harness, gold, 2026-10-10 (after the fixes) | 290 | 87 | 115 | 79 | 54 | 28 | 125 | 0 | 778 |
<!-- bykind:end -->

Why the figures differ:

- **Differences between the pipelines (B against A).** Pipeline A (the 27B) writes free text: its count is what the model chose to
  quote, and it quotes more where it explains (half_life 121 and 137 numbers against 76 for the gold harness). Pipeline B renders a template
  per decision: its count is the numbers of the parameters decided as asked, plus the header (analysis id, dose). B's population is therefore a
  function of the decisions, A's of the model's prose.
- **First drafts against answers shown (932 against 827, same run).** The gate is in the loop in A: a draft with an unverified number is
  regenerated once. In the first run 25 compare turns were regenerated; their numbers fell from 168 to 63, and 932 - 827 = 105 = 168 - 63. The
  76 unverified numbers are in the first drafts (76/932), none in the answers shown (0/827). In the second run no draft needed
  regeneration, so first drafts and answers shown are the same 926 (0/926). Of the 932 first-draft numbers, 168 are in the compare turn and 764 in the
  seven other kinds; all 76 failures are in the 168.
- **Step 4 against step 4b (1698 against 691, same 175/175 and 558/558).** Step 4 answered a reading turn with the whole table of 13
  parameters, so the five kinds that read the NCA result (`import_nca` to `lambda_z_regression`) each wrote 309 numbers and the slots were met by the
  table, not by a decision. Step 4b prints only the parameters decided as asked (`asked_<key>`): 691. The slots are unchanged (558), the numbers written
  fall by 1007. This is the correction of an inflated ceiling, not a change of the task.
- **Trained model against gold decisions (709 against 691).** The 18 extra numbers are all in the `not_available` kind (0 numbers for the gold
  harness, 18 for the trained one): the 19 turns where the model answered `is_not_available` = false took the reading path, whose header carries
  the analysis id and the dose. Other kinds are identical (251, 84, 76, 76, 51, 28, 125). None is unverified.
- **After the harness fixes (778 against 691, gold decisions).** The 2026-10-10 harness prints the dose with the user's unit and adds the
  engine's converted value after each "dose unit/..." value when the dose unit is not the concentrations' (README, "Harness fixes after the
  review"); the extra numbers are in `import_nca` (290 against 251), `clearance_volume` (115 against 76) and the smaller kinds. The README says all are engine values or user numbers.
- **The 27B's three numbers in the not-available turns of the second run** are numbers the model wrote in an answer that should contain none
  of its own; they are verified (0/926 unverified) and do not fail the scorer (`no_new_numbers` counts unverified numbers only).

Tool calls: 160/160 valid for the 27B second run (112/114 in the first, 2 invalid) and 0/250 invalid for every harness run; the argument
audit saw 77 `nca_run` and `data_import` calls of the 27B second run (2 deviating) and 75 of each harness run (0 deviating). The harness
makes 250 tool calls and the 27B 160 in the same 200 turns: call counts are not comparable across the two pipelines.

## 4. Decisions

A decision is one cell: one of the 20 closed questions of one row. The per-question and overall accuracies count cells; the denominator is
rows x 20.

| figure | arithmetic | what the rows are |
|---|---|---|
| 14,400 decisions | 720 rows x 20 | the v1 held-out file: 20 held-out exercises x 36 rows |
| 18,000 decisions | 900 rows x 20 | the v1 bench file: 25 exercises x 36 rows |
| 1480 decisions | 74 x 20 | the reviewer's 74 requests, converted to rows (`eval_ood.py`) |
| 4500 decisions | 225 x 20 | the 225 `decide` calls of one harness run: 200 turns, plus 25 second asks (the compare turn is decided again after its re-run, so 200 + 25) |

The rows of the v1 files are not 14,400 independent items: 36 rows share each of 20 exercises, and 20 cells share each row (section 7).
14 of the 20 questions are the `asked_<key>` booleans, mostly false, which is why an always-majority baseline scores 84.6 % on the 14,400
cells.

**Complete-vector accuracy** (all 20 answers of a row right) is the companion metric, because errors cluster: a row is wrong if any cell
is.

| set | cells right | complete vectors right | note |
|---|---|---|---|
| v1 held-out, trained 0.8B (Step 3) | 14386/14400 | 706/720 = 98.1 % | the 14 wrong cells are all `is_not_available`, on 14 different rows |
| v1 bench, trained 0.8B (Step 3) | 17982/18000 | 882/900 = 98.0 % | same: 18 wrong cells, 18 rows |
| 74 reviewer requests, trained 0.8B (Step 6) | 1337/1480 | 4/74 | quoted from the Step 6 tables; the gold decisions give 74/74 on the converter |
| harness run, trained 0.8B against the gold decisions (Step 5) | 44/4500 cells differ | 181/200 answerable calls | 44/225 calls differ: 25 are the compare first asks, whose gold lies outside the offered options (no model can match), 19 are `is_not_available` |

Reading of the held-out `is_not_available` weakness: 60 held-out rows are true, all of the `not_available` kind; the model found 47/60 (the
"recall 78 %"); on the bench 58/75 (77 %). The 14 wrong held-out rows are 13 missed positives and 1 false positive (a `cmax_tmax` row), on
12 of the 20 exercises. The micro accuracy 99.9 % hides that 14 of the 720 rows (1.9 %) have a wrong decision vector; the harness run of Step 5 shows
the same in another unit: 44/4500 cells (99.0 %) but 19 of 200 answerable calls (about 1 in 10) with a wrong vector.

## 5. The d1-3B subsample

Step 2 ran the 600M on the whole files and the 3B only on strided subsets, because the 3B ran on CPU at about 14 s per row. Rule
(`zero_shot_d1.load_rows(path, limit, stride)`): read the file line by line, keep the line with 0-based index `i` when `i % stride == 0`,
stop at `limit` rows. The id of a row is its 0-based position in the file (`<prefix>_pk_analysis_requests_<position>`), so the case ids are
a function of the rule.

| set | file | rule | rows | case ids | questions per row |
|---|---|---|---|---|---|
| held-out | v1 `heldout.jsonl`, 720 rows | stride 6, limit 120 | **120** | `te_pk_analysis_requests_000000`, `000006`, ..., `000714` | 7 (the question set of that time) |
| bench | v1 `bench.jsonl`, 900 rows | stride 8, limit 112 | **112** | `be_pk_analysis_requests_000000`, `000008`, ..., `000888` | 7 |

The bench file has 113 candidates (positions 0 to 896); the limit of 112 drops position 896. The ids are stored with every row in
`decision/runs/2026-10-09/d1-3B-heldout-limit120-stride6.json` and `d1-3B-bench-limit112-stride8.json`, and the 600M was rerun on the same ids
(`d1-omni-600M-*-limit*-stride*.json`) so the two models are compared on identical rows. Counted in cells: 840 (120 x 7) and 784 (112 x 7).

| model, rows | cells right | accuracy |
|---|---|---|
| d1-3B, held-out subsample | 557/840 | 66.3 % |
| d1-3B, bench subsample | 524/784 | 66.8 % |
| d1-omni-600M, held-out subsample | 530/840 | 63.1 % |
| d1-omni-600M, held-out whole file | 3115/5040 | 61.8 % |
| d1-omni-600M, bench subsample | 511/784 | 65.2 % |
| d1-omni-600M, bench whole file | 3917/6300 | 62.2 % |

**Bias risk, in one line:** the subsample is one fixed, unstratified draw of a seeded shuffle (13/120 positives of `is_not_available`
against 60/720 in the file, 3 to 12 rows per held-out exercise instead of 6), and on the 600M it moves the accuracy by +1.3 and +3.0 points
against the whole file, so the 3B's 66.3 % and 66.8 % are subset figures with an error of several points and must not be set against
whole-file figures.

Note on the periodicity worry (Astra: "every sixth to eighth row" could favour positions in the exercise blocks): the v1 generator shuffles
the rows of each file before assigning ids (`make_dataset.build`, seeded `shuffle`, present since the first version), so the file is not in
exercise blocks and a stride cannot lock onto a position inside a block; the 3 to 12 rows per exercise is the evidence. The sentence in the
Step 2 notes that the files "are ordered by exercise" does not describe what the code did (section 8). The Bonsai baseline uses a different
rule, the first 5 rows of each of the 20 held-out exercises in file order, 100 rows.

## 6. ECE

**Definition used everywhere** (`zero_shot_d1.calibration`, also called by `predict_unsloth.py`): top-label ECE, pooled over all (row,
question) cells, 10 equal-width bins on the probability of the chosen label, each bin weighted by its share of the cells; not per question.
For a `noul` question the probability of the chosen label is P(true) or 1 - P(true).

| report | rows scored | are they calibration rows? | ECE |
|---|---|---|---|
| Step 2, d1-omni-600M, whole held-out file / whole bench file | 720 and 900 | no calibration at all (zero-shot) | 0.084 / 0.076 |
| Step 2, d1-omni-600M, held-out subsample / bench subsample | 120 and 112 | no calibration at all | 0.083 / 0.087 |
| Step 2, d1-3B, held-out subsample / bench subsample | 120 and 112 | no calibration at all | 0.101 / 0.090 |
| Step 3, `FastDecisionModel.calibrate` (training report) | the 720 held-out rows | **yes**: `train_unsloth.py` evaluates and calibrates on `heldout.jsonl` (temperatures fitted by cross-fit halves) | 0.00012 |
| Step 3, `predict_unsloth.py` on the held-out file | the same 720 rows | **yes**, the same rows: a calibration-fit diagnostic | 0.0011 |
| Step 3, `predict_unsloth.py` on the bench file | 900 rows | no: never used for training or calibration; same generator and wordings as the training distribution | 0.0011 |
| Step 6, trained 0.8B on the 74 requests | 1480 cells (15 below 0.9, 1465 at or above) | no | 0.093 |
| Bonsai 27B baseline | | the server returns the chosen option, no probability | none |

The held-out ECE of Step 3 is the reviewer's point exactly: it is computed on the rows the temperatures were fitted on, so it is not an
independent calibration test, and the bench ECE, although on unseen rows, is in the same distribution, where the task is near
deterministic and the labels are one-hot. The v2 training run of 2026-10-10 is not covered here; its report has to say which file calibrated and
which file was scored before an ECE is quoted.

**The reviewer's counterexample, recomputed.** A classifier that gives confidence 1.0 to every one of the 14,400 held-out cells puts them
all in the top bin, whose accuracy is 14386/14400, so its ECE is 14/14400 = 0.000972, about 0.001. The trained model's ECE on the same cells
is 0.001115 (0.0011), slightly above that of the constant: the reported figure cannot tell a calibrated model from a model that is
sure of everything, including all of its 14 mistakes. The reliable calibration statements are the ones in a distribution that contains
errors, such as Step 6: 143 wrong decisions on 70 of the 74 requests, 135 of them at probability 0.90 or more, ECE 0.093.

## 7. Grouping: what is not independent

Units of dependence:

- **exercise**: the 8 turns of an exercise share its data, its engine analyses and its dose; the 36 or 46 rows of a dataset exercise share
  the data table. Benchmark: 25 exercises of 7 model families, single subject, one generator plan.
- **wording and wording family**: v1 has 83 distinct request sentences, and the reviewer found every held-out request verbatim in train
  (720/720). v2 has 246 wordings (62 held out) in 14 families (`wordings.json`); a held-out wording is the unit that tests new phrasing.
- **turn kind**: 8 scripted kinds in the benchmark, 15 in the datasets; the same question template runs on every exercise.
- **row**: 20 cells share one state and one request; 14 of them are `asked_<key>` booleans decided by the same sentence.
- **author and run**: one reviewer wrote the 74 requests; each pipeline was run once, one sampling for the 27B, deterministic otherwise.

| headline figure | counted items | grouping that applies | why the items are not independent trials |
|---|---|---|---|
| 27B first drafts 76/932, then 0/926 and 0/827 unverified numbers | numbers | exercise, and turn kind: all 76 failures are in the compare kind (76 of its 168 numbers, 0 of the other 764) | numbers of one turn are in one answer from one model call; 25 exercises are 25 clusters. The confidence interval of `docs/benchmark.md` resamples exercises. The rule of three on the numbers gives upper bounds of 0.32 % (926) and 0.36 % (827); with the exercise as the unit the same "all successes" count gives an upper bound of 0.113 only if the 25 exercises are independent and representative, which a generator plan does not establish: an illustration, not a bound |
| oracle 549/556 and 558/558 slots, 170/175 and 175/175 turns | slots, turns | exercise, then turn kind | 22 or 23 slots per exercise come from the same two analyses and the same CSV; a wrong `start: zero` option (ex07) fails 10 slots at once |
| harness 175/175 with gold or trained decisions | turns | exercise and kind | a template test: with gold decisions the result is a property of `harness.py`, with the trained model of one fixed decision vector per turn; the 225 calls differ from gold in 44 cells that did not change a scored answer |
| v1 held-out 14386/14400 cells, 706/720 vectors | cells, rows | exercise (20), wording (83 sentences, all in train) | 36 rows per exercise, 20 cells per row; the 14 errors fall on 14 rows in 12 exercises and 13 of them are in the `not_available` kind (60 rows): one question of one kind, not 14,400 trials |
| v2 held-out files | cells, rows | `heldout_exercises` by exercise (20), `heldout_wordings` by wording (62 held-out wordings over 55 exercises), `heldout_both` by both | report the three files separately; the wording is the unit for new phrasing, the exercise for new data |
| reviewer's 74 requests, 1337/1480 cells, 4/74 vectors | cells, requests | request, tag, turn (62 first requests, 12 follow-ups) | one author; the 16 requests on invented exercises are not the 58 on benchmark exercises; a request carries several tags, so per-tag tables count requests more than once; 20 cells per request |
| d1 subsample 66.3 % and 66.8 % | cells | exercise: 20 held-out exercises, 3 to 12 rows each | a subset, section 5 |
| ECE | cells | row (20 cells share one state) | section 6 |

Neither the 558 slots nor the 14,400 labels are that many independent demonstrations. The informative counts are 25 benchmark exercises, 20
held-out exercises, the held-out wordings, the 14 families, the 8 or 15 turn kinds and the 74 requests of one author. Cluster intervals
(resampling exercises, as `docs/benchmark.md` does for its 7.1 to 9.1 % and 89.7 to 100 %) are the right presentation; this ledger does
not compute new ones.

## 8. Not reconciled, and what the ledger could not do

1. **Step 3 reports two different vector accuracies.** The training report's `calibrate` line gives accuracy 0.99979 and record accuracy
   (all 20 answers of a row right) 0.9958, that is about 3 rows wrong of 720; the stored predictions of the same model give 14 wrong rows,
   706/720 = 0.9806. Two code paths (Unsloth's `calibrate` with its temperatures, and `predict_unsloth.py`) on the same 720 rows. The ledger
   uses the stored per-row predictions, which can be recomputed; the discrepancy is not explained.
2. **The Step 2 note says the data files are "ordered by exercise".** The generator shuffled them (section 5); the 3 to 12 rows per
   exercise confirm it. The conclusion (a stride spreads over all exercises) holds, the stated reason does not.
3. **The compare slots are decided after the run** (section 3.1); the fixed denominator is 558.
4. **v1 train and bench files are gone** (overwritten by v2); the v1 figures rest on the stored run JSON, and the exercise coverage of the
   d1 subsample on the stale v1 held-out file, whose row ids match the stored run.
5. **No confusion matrices or error-versus-coverage curves are in this ledger**; the per-question confusion tables are in the Step 3 and
   Step 6 reports. Insight 6 also asks for them (next step 6 of the plan); they need the v2 training run.
6. **The v2 trained model** (2026-10-10) and its reports are out of this ledger: its figures should be added with their denominators from
   sections 3 to 6 once the run is committed.

## Register

Every key below is checked by `tests/test_ledger.py`: keys `bench.`, `runs.`, `rows.`, `decisions.`, `harness.`, `errors.`, `ece.`, `d1.` and
`stats.` are recomputed from files; keys `quoted.` are tied to a sentence of the report named in the test.

<!-- register:begin -->
bench.exercises = 25
bench.turns_per_exercise = 8
bench.turns = 200
bench.oracle_turns = 175
bench.not_scored_by_oracle = 25
bench.not_scored_kind = not_available
bench.not_scored_with_words = 25
bench.exercises_iv_bolus = 8
bench.exercises_other = 17
bench.slots_t1 = 9
bench.slots_t2_bolus = 3
bench.slots_t2_other = 2
bench.slots_static = 508
bench.slots_compare_resolved_extra = 2
bench.slots_max = 558
bench.kinds = import_nca,cmax_tmax,clearance_volume,half_life,lambda_z_regression,recall,compare,not_available
runs.A1.turns = 200
runs.A1.gate_first_drafts = 932
runs.A1.gate_shown = 827
runs.A1.unverified_first_drafts = 76/932
runs.A1.unverified_shown = 0/827
runs.A1.regenerated_turns = 25
runs.A1.scorer_turns = 193/200
runs.A1.scorer_slots = 496/508
runs.A1.compare_numbers_first_drafts = 168
runs.A1.other_kinds_numbers_first_drafts = 764
runs.A1.oracle_turns = 168/175
runs.A1.oracle_slots = 494/508
runs.A1.compare_turns_with_2_slots = 25
runs.A1.tool_calls_valid = 112/114
runs.A2.turns = 200
runs.A2.gate_first_drafts = 926
runs.A2.gate_shown = 926
runs.A2.unverified_first_drafts = 0/926
runs.A2.compare_numbers_first_drafts = 141
runs.A2.scorer_turns = 195/200
runs.A2.scorer_slots = 552/556
runs.A2.oracle_turns = 170/175
runs.A2.oracle_slots = 549/556
runs.A2.compare_turns_with_4_slots = 24
runs.A2.compare_turns_with_2_slots = 1
runs.A2.numbers_in_not_available_turns = 3
runs.A2.tool_calls_valid = 160/160
runs.A2.audited_calls = 77
runs.A2.deviating_calls = 2
runs.A2.slots_against_fixed_max = 549/558
runs.B4.turns = 200
runs.B4.gate_numbers = 1698
runs.B4.unverified = 0/1698
runs.B4.oracle_turns = 175/175
runs.B4.oracle_slots = 558/558
runs.B4.compare_turns_with_4_slots = 25
runs.B4.scorer_turns = 200/200
runs.B4.scorer_slots = 558/558
runs.B4.decide_calls = 225
runs.B4.tool_calls_invalid = 0/250
runs.B4.audited_calls = 75
runs.B4.numbers_in_not_available_turns = 0
runs.B4b.turns = 200
runs.B4b.gate_numbers = 691
runs.B4b.unverified = 0/691
runs.B4b.oracle_turns = 175/175
runs.B4b.oracle_slots = 558/558
runs.B4b.compare_turns_with_4_slots = 25
runs.B4b.scorer_turns = 200/200
runs.B4b.scorer_slots = 558/558
runs.B4b.decide_calls = 225
runs.B4b.tool_calls_invalid = 0/250
runs.B4b.audited_calls = 75
runs.B4b.numbers_in_not_available_turns = 0
runs.Btr.turns = 200
runs.Btr.gate_numbers = 709
runs.Btr.unverified = 0/709
runs.Btr.oracle_turns = 175/175
runs.Btr.oracle_slots = 558/558
runs.Btr.compare_turns_with_4_slots = 25
runs.Btr.scorer_turns = 200/200
runs.Btr.scorer_slots = 558/558
runs.Btr.decide_calls = 225
runs.Btr.tool_calls_invalid = 0/250
runs.Btr.audited_calls = 75
runs.Btr.numbers_in_not_available_turns = 18
runs.B10.turns = 200
runs.B10.gate_numbers = 778
runs.B10.unverified = 0/778
runs.B10.oracle_turns = 175/175
runs.B10.oracle_slots = 558/558
runs.B10.compare_turns_with_4_slots = 25
runs.B10.scorer_turns = 200/200
runs.B10.scorer_slots = 558/558
runs.B10.decide_calls = 225
runs.B10.tool_calls_invalid = 0/250
runs.B10.audited_calls = 75
runs.B10.numbers_in_not_available_turns = 0
rows.v1_per_exercise = 36
rows.v2_per_exercise = 46
rows.v2_scripted_kinds = 8
rows.v2_extra_kinds = 7
rows.v2_kinds = 15
rows.v2_paraphrases_scripted_kinds = 2
rows.v2_paraphrases_extra_kinds = 3
rows.v2_paraphrases_nca_oneline = 4
rows.v2_paraphrase_rows = 38
rows.v2_heldout_wordings_per_exercise = 15
rows.v2_heldout_both_max_per_exercise = 30
rows.v2_wording_pools = 15
rows.v2_wordings_total = 246
rows.train_rows = 2530
rows.train_exercises = 55
rows.train_per_exercise = 46
rows.heldout_exercises_rows = 920
rows.heldout_exercises_exercises = 20
rows.heldout_exercises_per_exercise = 46
rows.bench_rows = 1150
rows.bench_exercises = 25
rows.bench_per_exercise = 46
rows.heldout_wordings_rows = 825
rows.heldout_wordings_exercises = 55
rows.heldout_wordings_per_exercise = 15
rows.heldout_both_rows = 593
rows.heldout_both_exercises = 20
rows.heldout_both_per_exercise = 29/30
rows.bench_scripted_rows = 200
rows.bench_scripted_kinds = clearance_volume,cmax_tmax,compare,half_life,import_nca,lambda_z_regression,not_available,recall
rows.v1_heldout_rows = 720
rows.v1_heldout_exercises = 20
rows.v1_heldout_per_exercise = 36
decisions.heldout_rows_x_questions = 720*20=14400
decisions.ood_requests_x_questions = 74*20=1480
decisions.harness_calls_x_questions = 225*20=4500
decisions.bench_rows_x_questions = 900*20=18000
decisions.heldout_questions_right = 14386/14400
decisions.bench_questions_right = 17982/18000
decisions.heldout_complete_vectors = 706/720
decisions.bench_complete_vectors = 882/900
decisions.heldout_complete_vectors_pct = 98.1
decisions.bench_complete_vectors_pct = 98.0
decisions.heldout_errors_questions = is_not_available
decisions.bench_errors_questions = is_not_available
decisions.heldout_is_not_available_found = 47/60
decisions.bench_is_not_available_found = 58/75
decisions.heldout_questions_pct = 99.9
harness.decide_calls = 225
harness.decide_calls_extra_compare = 25
harness.cells_differing = 44/4500
harness.calls_differing = 44/225
harness.cells_is_not_available = 19
harness.cells_compare_pair = 25
harness.complete_vectors_answerable = 181/200
harness.complete_vectors_all_calls = 181/225
errors.heldout_wrong_rows = 14
errors.heldout_wrong_rows_not_available_kind = 13
errors.heldout_wrong_rows_other_kind = 1
errors.heldout_wrong_rows_distinct_exercises = 12
errors.heldout_not_available_rows = 60
ece.heldout_trained = 0.0011
ece.bench_trained = 0.0011
ece.confidence_one_everywhere = 14/14400=0.000972
ece.confidence_one_everywhere_4dp = 0.0010
ece.heldout_trained_6dp = 0.001115
ece.d1_600M_heldout_720 = 0.084
ece.d1_600M_bench_900 = 0.076
ece.d1_600M_heldout_120 = 0.083
ece.d1_3B_heldout_120 = 0.101
ece.d1_600M_bench_112 = 0.087
ece.d1_3B_bench_112 = 0.090
d1.heldout_subsample_rows = 120
d1.heldout_stride = 6
d1.heldout_rule_holds = True
d1.heldout_first_last_ids = te_pk_analysis_requests_000000..te_pk_analysis_requests_000714
d1.bench_subsample_rows = 112
d1.bench_stride = 8
d1.bench_rule_holds = True
d1.bench_first_last_ids = be_pk_analysis_requests_000000..be_pk_analysis_requests_000888
d1.bench_rows_in_file = 900
d1.bench_stride_candidates = 113
d1.bench_row_cut_by_limit = be_pk_analysis_requests_000896
d1.questions_per_row = 7
d1.same_rows_both_models = True
d1.3B_heldout_subsample_acc = 557/840
d1.3B_bench_subsample_acc = 524/784
d1.600M_heldout_subsample_acc = 530/840
d1.600M_heldout_full_acc = 3115/5040
d1.600M_bench_subsample_acc = 511/784
d1.600M_bench_full_acc = 3917/6300
d1.600M_heldout_subsample_pct = 63.1
d1.600M_heldout_full_pct = 61.8
d1.600M_bench_subsample_pct = 65.2
d1.600M_bench_full_pct = 62.2
d1.3B_heldout_subsample_pct = 66.3
d1.3B_bench_subsample_pct = 66.8
d1.heldout_subsample_is_not_available_true = 13/120
d1.bench_subsample_is_not_available_true = 16/112
d1.heldout_full_is_not_available_true = 60/720
d1.bench_full_is_not_available_true = 75/900
d1.heldout_subsample_exercises = 20
d1.heldout_subsample_rows_per_exercise_min = 3
d1.heldout_subsample_rows_per_exercise_max = 12
d1.heldout_rows_per_exercise_expected = 6
stats.ood_requests = 74
stats.upper_bound_0_of_926 = 0.32
stats.upper_bound_0_of_827 = 0.36
stats.upper_bound_0_of_25_exercises = 0.113
stats.wording_families = 14
quoted.ood_complete_vectors = 4/74
quoted.ood_gold_vectors = 74/74
quoted.ood_decisions_right = 1337/1480
quoted.ood_ece = 0.093
quoted.ood_decisions_below_0.9 = 15
quoted.ood_decisions_at_or_above_0.9 = 1465
quoted.unsloth_calibrate_ece = 0.00012
quoted.unsloth_calibrate_record_accuracy = 0.9958
quoted.unsloth_calibrate_rows = 720
quoted.reviewer_verbatim_heldout_requests = 720/720
quoted.reviewer_distinct_requests = 83
quoted.reviewer_ece_counterexample_counts = 14386/14400
quoted.astra_rounded_bound = 0.113
quoted.ood_requests_on_benchmark_exercises = 58
quoted.ood_requests_on_invented_exercises = 16
quoted.ood_first_requests = 62
quoted.ood_follow_ups = 12
quoted.ood_wrong_decisions = 143
quoted.ood_wrong_decisions_at_least_0.9 = 135
quoted.hallucination_ci_exercises_resampled = 7.1-9.1
quoted.oracle_turns_ci_exercises_resampled = 89.7-100
quoted.ex07_wrong_option_slots = 10
quoted.majority_baseline_heldout = 84.6
quoted.v1_train_rows = 1980
quoted.bonsai_heldout_rows = 100
quoted.ood_requests_complete_vectors_27B_per_row = 7/74
quoted.heldout_100_complete_vectors_0.8B = 97/100
<!-- register:end -->
