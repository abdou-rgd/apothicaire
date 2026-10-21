# Frozen test set: pre-registration protocol, version 2 (draft, 2026-10-19)

Status: version 2 of the draft, rewritten after the red-team triage of 2026-10-19. Nothing in it is frozen yet. It
becomes binding in two stages (section 9): the **case freeze** (cases, gold, wordings, scorer, this plan) and the
**system freeze** (gate, prompts, harness, model, runtime, seeds, the demo-gate decision), each a commit whose
SHA-256 manifest is pushed before the first prediction on the frozen cases. After that it is amended only through
dated entries in `bench/frozen/LEDGER.md`, never edited in place.

What changed from version 1 (commit 490e693):

| Red-team point | Board card | Version 1 | Version 2 |
|---|---|---|---|
| RT-B4: correlated numbers treated as independent (the 0.32 % bound) | T-083 | per-number rates next to a cluster bootstrap; McNemar on turns "for the record" | the exercise is the only unit of inference; per-number and per-turn rates are descriptive; McNemar on turns is dropped (§3, §11) |
| RT-B5: 60 exercises that are 20 cells × 3 noise seeds; no aggregation rule, no success definition, no precision target | T-070 | 60 = 20 × 3; bound quoted as 4.9 % | every exercise is an independent draw; noise seeds do not multiply cases; success and aggregation over sampling seeds defined; precision target with its computation (§3, §4, §6) |
| RT-B9: error turns leave the denominator | T-071 | not addressed | errors, timeouts, tool loops and abstentions stay in the denominator as failures and are reported by class (§6.1) |
| RT-B10: the demo gate is chosen on the frozen set ("the better of 1–2") | T-072 | configuration 3 = better of 1–2 on the frozen exercises | the gate is chosen on the development set by a rule written here, committed before any frozen prediction; only that configuration is confirmatory (§8) |
| RT-B3: the scorer accepts a wrong sign, a negation, a contradiction, a table dump, a reversed verdict | T-066 | not addressed | the rubric is written here (§6.2) and must reject a mutation suite before the case freeze (§7) |

## 1. Why

Every figure published so far is in-sample: the 25 exercises of `bench/exercises/`, their French wordings in
`bench/scripts.py` and the scoring rules of `bench/score.py` were written by the same people, at the same time, as the
gate they measure, and were run many times while the gate and the prompts were being tuned. The 2026-10-09b run
(195/200 turns correct, 0/926 unverified numbers after gate v1), the 2026-10-17 upstream run (193/200, 0/897) and the
two gate v2 runs (182/200 and 183/200) are development figures. The frozen sets are the only measurements that may
be quoted outside the repository: the minimal set for the demo of 2026-11-17, the full set for a PAGE 2027 abstract.

## 2. Two tiers

The demo tier is what one person with one RTX 3060 can finish before 2026-11-17 without cutting a corner the red team
named. The PAGE tier is the version an outside reviewer can hold to account. Once the demo-tier results are read, the
demo set becomes development data for the PAGE tier: nothing measured on it is confirmatory again.

| | Demo tier (`frozen-set-demo`) | PAGE tier (`frozen-set-page`) |
|---|---|---|
| Purpose | one confirmatory figure for the demo configuration | the figure and the v1/v2 comparison for PAGE 2027 |
| Target sample | 40 independent exercises, one per draw (§5.1) | 60 independent exercises, new generator seed (§5.1) |
| Challenge stratum | none | ≥ 15 cases reported apart, never pooled (§5.2) |
| Wordings | 3 new French wordings per turn kind (2 by Abdou, 1 by dsh) | ≥ 3 French + 1 English per turn kind, at least one external author if one is found (§5.3) |
| Gold | Caladrius, as today | Caladrius, cross-checked with the PKNCA oracle script (§5.4) |
| Sampling seeds | 3 (1, 2, 3) | 5 (1–5) |
| Success of an exercise | all 8 turns correct on every seed (§6.3) | same |
| Precision target (zero failures) | upper bound 7.2 % | upper bound 4.9 % |
| Configurations | C1 = chosen gate (confirmatory), C2 = the other gate (descriptive) | C1 confirmatory, C1 vs C2 paired comparison (declared), others exploratory |
| Scorer validation | mutation suite + 40 turns labelled by Abdou (§7) | same, plus the challenge-stratum mutations (stale result, subject switch) |
| Freeze | case freeze then system freeze, by hash (§9) | same |
| GPU time (27B Q2_0, upstream b11700) | ≈ 3 h development + ≈ 5 h frozen | ≈ 15 h frozen + exploratory |
| Abdou's time | ≈ 2 h wordings, ≈ 1 h labelling, ≈ 1 h review | the same plus the search for an external author |
| Deadline | system freeze by 2026-11-06, results by 2026-11-12 | case freeze by 2026-12-15, results by 2027-01-15 |

GPU time is estimated from the measured times per turn: 8.0 s for gate v1 on the upstream runtime (run
2026-10-17-27b-upstream-full) and about 10.7 s for gate v2 (the fork ratio 13.9 / 10.4 applied to 8.0 s). One seed of
the demo set is 40 × 8 = 320 turns: about 43 min with v1 and 57 min with v2.

## 3. Unit of analysis

Turns of one exercise share the data, the memory and the prompt prefix; numbers of one turn share one tool result;
421 of the 926 numbers of run 2026-10-09b come from turn 1 alone. None of these is an independent trial. The unit of
inference is therefore the **exercise**: every interval and every test in §11 is computed over exercises. Per-turn
and per-number rates are still reported, as ratios with a cluster bootstrap over exercises, and are labelled
descriptive. The rule of three is never applied to numbers or turns.

Exercises are independent only if each one is its own draw. Version 1 planned 20 design cells × 3 noise seeds; three
noise realisations of one cell share the family, the parameters' design, the units and the BLQ rule, so they count as
one exercise, not three (the family-level bound of that plan was 13.9 %, not 4.9 %). In version 2 each exercise draws
its own family, units, time unit, BLQ rule, parameters, sampling times and noise exactly once (§5.1). Sampling seeds
of the model (§10) measure repeatability; they never add exercises.

What the frozen sets generalise to: new draws of the same synthetic generator, asked with wordings the system never
saw. They do not measure new clinical workflows, real data or other sponsors' conventions (RT-B6, §13).

## 4. Size and precision target

With n independent exercises and zero failures, the one-sided 95 % upper bound on the probability that an exercise
fails is 1 − 0.05^(1/n). With f failures, the exact two-sided 95 % interval is Clopper–Pearson.

| n | bound with 0 failures | interval with 1 failure | interval with 2 failures | interval with 4 failures |
|---|---|---|---|---|
| 25 (the in-sample set) | 11.3 % | | | |
| 40 (demo tier) | 7.2 % | 0.1–13.2 % | 0.6–16.9 % | 2.8–23.7 % |
| 60 (PAGE tier) | 4.9 % | 0.0–8.9 % | 0.4–11.5 % | 1.8–16.2 % |
| 299 | 1.0 % | | | |

Targets: the demo tier is sized for a bound below 8 % with zero failures (n ≥ 37, rounded to 40); the PAGE tier for a
bound below 5 % (n ≥ 59, rounded to 60). A bound below 1 % would need 299 exercises and is not claimed by either tier.
The target is a precision target, not a success criterion: the result is published whatever it is, with its interval.

## 5. Cases

### 5.1 Target sample

Generated by `make_exercises.py` with a new `SEED` per tier (never 20261009) and a new plan. The plan is itself drawn
by the generator from the seed: each row picks a family among the seven of today (pk1 iv_bolus, iv_infusion, oral_1,
oral_1_lag, oral_0; pk2 iv_bolus, oral_1) with stratified counts (demo: 6, 6, 6, 6, 6, 5, 5; PAGE: 9, 9, 9, 9, 8, 8,
8), then dose unit, concentration unit, time unit and BLQ independently with fixed shares (at least 25 % µg doses,
25 % minute time units, 20 % BLQ). Each row then draws its parameters, sampling times and noise once. No exercise is a
noise replicate of another.

Today the generator rejects any profile where Caladrius cannot compute the half-life
(`make_exercises.py:188`). The target sample keeps that rule in the demo tier and states it; the PAGE tier moves those
profiles into the challenge stratum (T-073).

### 5.2 Challenge stratum (PAGE tier only)

At least 15 cases built to break an assistant, reported in their own table and never pooled with the target sample:
no computable λz or extrapolation above the threshold (T-073), a stale result asked after a re-analysis (T-067), a
switch of subject or a correction of the dose mid-conversation, a long conversation that pushes the first results out
of the context, and, if the external author agrees, cases they write. Their failure rate has no target and no bound;
it is a list of what breaks.

### 5.3 Wordings

`bench/frozen/<tier>/wordings.json`: for each of the 8 turn kinds of `scripts.py` (import_nca, cmax_tmax,
clearance_volume, half_life, lambda_z_regression, recall, compare, not_available), new wordings, none copied from
`scripts.py`. Demo tier: 3 French wordings per kind, 2 written by Abdou and 1 by dsh (DeepSeek). PAGE tier: at least
3 French and 1 English per kind; at least one external author (a pharmacometrician) writes one wording per kind if
one is found by 2026-12-01, otherwise the abstract states that all wordings come from the author of the system and
from dsh. Each exercise gets one wording per kind by a seeded draw recorded in the manifest (in the PAGE tier, each
exercise also draws its language: French 75 %, English 25 %).

Claude (the orchestrator and every subagent) writes no wording and does not read `wordings.json` before the system
freeze: Claude tunes the system, so seeing the wordings would leak them into the prompts. Until the system freeze the
repository holds only the SHA-256 of `wordings.json`; the file stays on Abdou's PC and is committed at the system
freeze, where its hash must match.

### 5.4 Gold

The truth is the engine's output (`model_simulate` then `nca_run`), as today: the benchmark measures how faithfully
the assistant relays the engine, not the engine, which is validated separately against R oracles. The acceptability
verdict of turn 4 is part of the gold: acceptable when AUC % extrapolated ≤ 20 % (the named convention
`max_extrapolated_percent` of `GATE_V2.md`). The gold is computed with the units the assistant's calls now send:
since `nca_run` takes `dose_unit` (apothicaire PR #3), CL is reported in L/h and V in L instead of `dose unit/…`, so
the `meta.json` of `bench/exercises/` (computed without units) are regenerated with `dose_unit` before the
development runs, and the frozen exercises are generated the same way; the generator commit and the regenerated gold
are hashed at the case freeze. In the PAGE tier every frozen exercise is also run through
`caladrius/oracle/scripts/nca_pknca.R` before the case freeze; any disagreement beyond the conformance tolerance is a
ledger entry and the exercise is replaced before the freeze, never after (RT-B8).

## 6. Scoring

### 6.1 Outcome of a turn

Every planned turn gets exactly one outcome, assigned in this order. All outcomes other than CORRECT are failures, all
stay in the denominator (200 planned turns are 200 in the denominator), and the report gives the count of each.

| Outcome | Definition |
|---|---|
| ERROR | the harness, the engine or the server raised an exception, or returned no answer |
| TIMEOUT | the turn exceeded the wall-clock cap (300 s, frozen in the bundle) |
| LOOP | the turn was ended by the tool-round cap or the repeated-call guard (T-062) |
| ABSTAINED | values were expected and the answer states none of them, saying it cannot or will not answer |
| WRONG | an answer was given and fails the rubric of §6.2 |
| CORRECT | the answer passes the rubric of §6.2 |

The `not_available` turn is the one turn where saying "not calculated" is the correct answer; there it is CORRECT, not
ABSTAINED. A gate marker or badge is not a value: if it replaces an expected value the turn is WRONG on that value, and
markers are counted apart (§11.2).

### 6.2 Rubric of a turn (written before the scorer is changed, T-066)

A quantity is **stated** when a number is attached to its label in the same clause or table row. Matching is done on
the text the user sees.

1. **Label-bound.** Each expected quantity must be stated with its label. A number without a label never counts, and
   the old fallback on the whole answer (`score.py:348`) is removed.
2. **Signed value.** The stated value equals the engine value under the gate's rounding rule, sign included (the
   absolute-value comparison of `score.py:54` is removed). The unit, when written, is the engine's unit or an exact
   rewriting of it.
3. **Negation.** A value stated in a negated or disowned clause (not, is not, n'est pas, ne … pas, wrong, faux,
   incorrect, obsolete, previous, ancienne) does not count. If it is the only statement of the quantity, the turn is
   WRONG.
4. **Contradiction.** Two different values for the same asked quantity (outside the rounding rule) make the turn WRONG,
   even when one of them is right.
5. **No dump.** Outside turn 1, which asks for the whole set, an answer that states more than 3 quantities the turn did
   not ask for fails: dumping the table earns no credit. A forbidden value (computed or converted by the model, the
   `must_not` lists of `scripts.py`) fails at any count.
6. **Verdict.** Turn 4 must state whether the extrapolation is acceptable, and the verdict must match the gold. When
   the gold extrapolation lies between 18 % and 22 %, either verdict passes if the value is stated.
7. **Turn specifics.** Recall: dose with its unit, route and AUC method, with no contradicting statement. Compare: the
   lin-up/log-down AUC(0-tlast), the absolute difference and the percentage; the linear AUC is no longer required
   (version 1 already planned this change) but, if stated, must be right; a value of the linear analysis given as the
   lin-up/log-down one is WRONG (stale result). Not available: says the parameter is not calculated and states no
   value labelled with it.

The rubric is implemented in `score.py` and `scripts.py` before the case freeze; from then on both files are frozen.
In-sample runs are rescored with the new rubric and both figures are kept side by side, as T-066 requires.

Implementation (2026-10-21, `score.rubric_turn`, version string `RUBRIC_VERSION`). Where the rules above needed a reading,
the code takes this one; each is tested in `tests/test_bench_score.py` (class `TestRubric`):

- Labels are the closed table `score.RUBRIC_ALIASES` (the oracle's, plus Tlag, tlast, Clast, AUMC, Vss and a stricter
  label for the extrapolated percentage, so that "C0 (extrapolée)" is not read as it). A label of another parameter
  written inside the label of an asked one ("Nombre de points pour la régression de λz : 3") is part of that label.
- Rule 2: the scored text is the answer shown without gate v1's badge; gate v2's rendered values are scored like any
  other. A unit is an exact rewriting when it normalises to the same string after merging factor-1 concentrations
  (µg/mL = mg/L, µg/L = ng/mL) and sorting the factors of a product (ng·h/mL = h·ng/mL).
- Rule 3: the negation words are searched in the clause before the number (from the start of the clause holding the
  label) and in the words right after it, up to the next comma, parenthesis or end of clause.
- Rule 4: a contradicting value has 3 significant digits or more, the asked unit or none, and is no other number of
  the exercise (another parameter of either analysis, the analysis_compare row, the dose, the data, the quality
  thresholds 20 %, 0.9, 2): "AUC(0-inf) = 3170,4 (observée) ; 3172,2 (prédite)" states two quantities, not two values
  of one.
- Rule 5 counts values, not names: each other computed parameter whose value is written (3 digits or more), or each
  other label with a number attached, counts once; the dose and the thresholds do not count.
- Rule 6: the echo of the question ("Est-ce acceptable ?", "Acceptabilité :") is not a verdict; a "oui" or "non" right
  after it is.
- Rule 7, compare: the difference and the percentage pass as the engine's signed values (b − a over a, a = the linear
  analysis, or a = the lin-up/log-down one when the model's `analysis_compare` call took it as reference) or as their
  absolute values, since the question asks for the difference "en valeur absolue". A percentage is labelled by its %
  sign; a difference by its label or by the AUC unit in a clause that says it is a difference ("de moins", "écart").

On the development set the mutation suite (`bench/mutations.py`, run by the tests) builds 1 024 correct answers and
variants and 1 525 mutations from the gold of the 25 exercises: all 1 024 score CORRECT and all 1 525 score WRONG. The
seven probes of the triage (RT-B3) are among the tests.

### 6.3 Success of an exercise and aggregation over sampling seeds

An exercise **passes on a seed** when its 8 turns are CORRECT. An exercise **passes** when it passes on every seed
(3 in the demo tier, 5 in the PAGE tier); one failed turn on one seed fails the exercise. This strict rule is the
primary endpoint. The mean pass rate over seeds and the number of exercises with mixed outcomes across seeds are
reported as repeatability, never as the headline.

## 7. Scorer validation before the case freeze

The scorer is frozen only after it passes two checks, both run without any model.

**Mutation suite** (in `tests/test_bench_score.py`). For every exercise of the development set and of the frozen set
(only the gold is used, no prediction), a canonical correct answer per turn is built from the gold, and must score
CORRECT, together with legitimate variants: three significant digits, a decimal comma, a unit written another way, a
sentence of explanation, a Markdown table. Each of the following mutations must score WRONG:

| Mutation | Example (ex01, Cmax = 3.679 mg/L) |
|---|---|
| sign | "Cmax = -3.679 mg/L" |
| negation | "Cmax is not 3.679 mg/L" |
| contradiction | "Cmax = 999 mg/L; the old, wrong Cmax was 3.679" |
| wrong label | the Tmax value under the Cmax label, or two asked values swapped |
| stale result | the linear AUC given as the lin-up/log-down one |
| unit | the value × 1000 with the same unit, or the right value with another unit |
| unlabelled | the expected numbers without their labels |
| dump | the 46 values of the table followed by a verdict |
| verdict | the right values with the reversed acceptability verdict |
| not available | any number labelled with the not-calculated parameter |

Pass criterion: 100 % of the canonical answers and variants CORRECT, 100 % of the mutations WRONG. The kill rate and
the list of mutations are part of the report. The seven probes of the triage (RT-B3) are in the suite.

**Agreement with a human.** Abdou labels 40 turns drawn at random (seeded) from the development runs, without seeing
the scorer's verdict. Every disagreement is resolved before the freeze, by fixing the scorer or by writing the case
into the rubric; the agreement before resolution is reported.

## 8. Development set, confirmation set and the demo-gate decision

Development set: the 25 exercises of `bench/exercises/` with the wordings of `scripts.py`. All tuning (prompts, gate
rules, aliases, harness caps) happens there and only there. The confirmation sets are the frozen sets of §5.

**Demo-gate decision rule** (replaces "the better of 1–2" of version 1, and, for the demo, the turn-level rule written
in the status of `GATE_V2.md`). Once the typed rendering of gate v2 is merged, both gates run on the development set,
same model (27B Q2_0, upstream llama.cpp b11700), same sampling, seeds 1–3, scored with the frozen scorer:

- **v2 is the demo gate** if the number of development exercises it passes (strict rule of §6.3) is at least the
  number v1 passes. Ties go to v2, which carries the typed channel the red team asked for.
- **Otherwise v1** is the demo gate.
- **Fallback**: if the typed rendering is not merged by 2026-11-04, the demo gate is v1 and v2 is not run on the
  frozen set before the demo.

The decision, its development figures and the commit it was made on are written in `bench/frozen/LEDGER.md` and
included in the system freeze, before any prediction on the frozen set. On the frozen set, only the chosen
configuration (C1) is confirmatory; the other gate (C2) may run on the same exercises and seeds, and its result is
descriptive and cannot change the demo choice.

After the demo-tier results are read, any change to the system makes a new confirmation necessary: the PAGE tier uses
a new set (§2).

## 9. Freeze by hash

`bench/frozen/<tier>/MANIFEST.json` lists the SHA-256 of every item below. Before the first prediction, the runner
recomputes every hash and refuses to start on any mismatch (to add to `run_bench.py`, T-082). Each freeze commit is
pushed to GitHub, which timestamps it publicly.

| Item | Stage |
|---|---|
| exercises (`data.csv`, `meta.json` with the gold computed with `dose_unit`) and the generator commit, seed and plan | case freeze |
| PKNCA cross-check output (PAGE tier) | case freeze |
| `wordings.json` (hash only at the case freeze, file at the system freeze) and the wording assignment | case freeze |
| `score.py`, `scripts.py`, the mutation suite and its expected verdicts | case freeze |
| this file (the analysis plan) and the analysis script | case freeze |
| `gate.py`, `gate_v2.py`, `numtext.py`, `apothicaire.py` (system prompts, exposed tools, caps), the OptChat commit | system freeze |
| Caladrius commit and the SHA-256 of the MCP binary (tool schemas) | system freeze |
| model file name and SHA-256, llama.cpp build string from `/props`, server flags | system freeze |
| sampling (temperature 0.3, top-p, top-k, min-p as sent), `max_tokens`, thinking off, seeds, wall-clock and tool-round caps | system freeze |
| `run_bench.py` and the demo-gate decision of §8 | system freeze |

Between the case freeze and the system freeze, the system may still change on the development set; the case files
may not. The tag `frozen-set-<tier>` is set on the system-freeze commit and is never moved.

## 10. Running

1. Seeds are passed to llama.cpp in each request (`run_bench.py --seed`, T-069). The seeds fix the sampler; bitwise
   replay across hardware is not claimed. After the run, two exercises × one seed are replayed and the report says
   whether the transcripts are identical.
2. C1 runs first, all seeds, then C2, then any exploratory configuration. No interim look changes anything: all
   planned runs are executed whatever the early results, and there is no early stop.
3. No turn is ever rerun. One exception: an exercise × seed interrupted by an event outside the model (power cut,
   operating-system reboot, server process killed by the system) may be restarted once from turn 1, with the
   interrupted attempt kept in the run folder and a ledger entry; a second interruption counts as ERROR on every turn
   not completed.
4. No exclusion. A defect found in a frozen file after the tag stays in the primary analysis; a sensitivity analysis
   without the affected exercises is reported next to it, never instead of it. The tag is not moved.
5. Every run folder (JSON per exercise and `report.md`) is committed when it finishes; transcripts of the frozen runs
   are committed too, not ignored, so a reader can check any verdict.
6. Any deviation is a dated entry in `bench/frozen/LEDGER.md`.

## 11. Analysis, declared before the run

Implemented in one script, frozen at the case freeze. No test is run that is not listed here; anything else is
exploratory and labelled so.

### 11.1 Primary endpoints, per configuration

1. **Exercise failure rate**: failed exercises (§6.3) / exercises, with the exact Clopper–Pearson 95 % interval, or the
   one-sided bound 1 − 0.05^(1/n) when no exercise fails.
2. **Exercises with an unverifiable quantity shown**: exercises in which at least one answer shown to the user, on any
   seed, contained an unverified number (v1, shown with its badge) or a marker (v2), with the same interval. The two
   gates do not define "verified" the same way (v1: the number appears in a tool text or the user's message; v2: the
   quantity is resolved and typed from the structured result); both definitions are printed next to the figures, and
   neither is called a "hallucination rate" without its definition.

### 11.2 Secondary endpoints, descriptive

- Turn correctness and number counts as ratios, with a 95 % percentile cluster bootstrap over exercises (10 000
  resamples, seed 0).
- Turn outcomes by class (§6.1) and by turn kind.
- Wrong values shown without a badge or marker: values that pass the gate and fail the rubric (the right number on the
  wrong parameter, from the wrong call), per exercise.
- Selection errors (v2): per turn that expects a parameter, whether the reference cited names the asked parameter,
  the asked call and the asked subject, read from the raw answer's references (`GATE_V2.md`, next measurement).
- Tool-argument audit: calls whose arguments differ from the turn's intent (AUC method, dose, route, analysis ids),
  per call and per exercise.
- Invalid or failed tool calls / calls; markers by cause (v2); regenerations; time per turn (median, 95th percentile);
  prompt tokens of the first call.
- Repeatability (§6.3); results by family, route, units and BLQ, without tests.

### 11.3 Paired comparison

Declared in the PAGE tier only (C1 vs C2, same exercises, same seeds); in the demo tier the same numbers are printed
and labelled descriptive, because the demo gate was chosen on the development set and the set is not sized for it.

- **Test**: exact McNemar on the strict exercise outcomes (the discordant exercises, binomial with p = 0.5,
  two-sided, α = 0.05). The McNemar test on turns of version 1 is dropped.
- **Effect size**: per exercise, d = (turns correct with C2 − turns correct with C1) / turns, pooled over seeds; mean d
  with a paired cluster bootstrap 95 % interval (exercises resampled, all seeds and turns of an exercise kept
  together), and a sign-flip randomisation test on the d (10 000 random sign flips, seed 0) as a check of the McNemar
  test.
- **Power**: with exact McNemar, 6 discordant exercises all in one direction are needed for p < 0.05, 9 with one
  against, 12 with two against. Only a large difference can be detected; a non-significant result is reported as
  "no difference detected", never as equivalence.

## 12. Calendar of the demo tier

| Step | Where | Who | Done by |
|---|---|---|---|
| Review and merge of this protocol | cloud | Abdou | 2026-10-24 |
| Rubric in `score.py`, outcome classes and denominators in `run_bench.py`, exercise-level report, `--seed`, manifest check, mutation suite (T-066, T-071, T-083, T-069, T-082) | cloud | Claude | 2026-10-30 |
| Wordings (24 sentences), hash committed | PC | Abdou, dsh | 2026-10-30 |
| Human labelling of 40 development turns | anywhere | Abdou | 2026-10-31 |
| 40 exercises generated with `dose_unit` (gold in L/h and L), gold hashed, mutation suite green on them, case freeze pushed | cloud | Claude | 2026-11-02 |
| Typed rendering of gate v2 merged (else fallback of §8) | cloud | other thread | 2026-11-04 |
| Gold of the 25 development exercises regenerated with `dose_unit` (§5.4), rescored in-sample runs kept next to the old ones | cloud | Claude | 2026-11-04 |
| Development runs v1 and v2, 3 seeds (≈ 3 h GPU), decision in the ledger, system freeze and tag | PC | Abdou launches | 2026-11-06 |
| Frozen runs C1 then C2, 3 seeds (≈ 5 h GPU) | PC | Abdou launches | 2026-11-10 |
| `bench/frozen/demo/RESULTS.md` (endpoints of §11 only; exploratory findings in their own section) | cloud | Claude | 2026-11-12 |

The recorded backup run of the demo is a separate recording; it is not part of the frozen measurement.

## 13. What this protocol does not cover

- New clinical workflows, several subjects per exercise, fitting questions and the 20-tool surface (`fit_run` is
  still excluded for context reasons): the challenge stratum touches some of them, a later set covers them.
- Real data: everything is synthetic, by the rule of 2026-10-09.
- A comparison with any commercial software.
- The decision model: its 74 free-form requests by dsh, with gold decisions adjudicated by Abdou before he sees any
  prediction, are frozen under the same rules but analysed in `decision/` (`decision/PLAN.md`), not here. The gold of
  these 74 requests was adjudicated on 2026-10-21 by two models, blind to dsh's answers, with human arbitration of the
  27 requests on which the three sources differed (`decision/ood/adjudication/`); no prediction of the trained model
  on these 74 requests may be shown before the frozen run.

## 14. Objections taken into account

From the red-team triage of 2026-10-19 (reports DeepSeek 4.1 Flash, Gemini 4 Argon, GLM, Astra6, ChatGPT Sol6.1).

| Point | Objection | Verdict | What changed here |
|---|---|---|---|
| RT-B1 | scorer and labels widened after reading the runs | confirmed | case freeze of the scorer before any frozen prediction (§9); in-sample figures stay labelled as development (§1) |
| RT-B2 | the compare criterion changed after the v2 run | refuted (draft, nothing frozen) | the change is declared before the freeze and the in-sample runs are rescored both ways (§6.2) |
| RT-B3 | no precision, sign, negation, contradiction or verdict in the scorer | confirmed | rubric (§6.2) and mutation suite (§7) |
| RT-B4 | per-number bound of 0.32 % is pseudo-replication | confirmed | exercise as the unit, no rule of three on numbers or turns, no McNemar on turns (§3, §11) |
| RT-B5 | 60 = 20 × 3, no aggregation, no success definition, no target | confirmed | independent draws, strict success over seeds, targets 7.2 % and 4.9 % (§3, §4, §6.3) |
| RT-B6 | out of sample for the data only; wordings by the system's author | plausible | Claude never sees the wordings before the freeze; external author sought for the PAGE tier; the generalisation claim is stated narrowly (§3, §5.3) |
| RT-B7 | no profile without a computable half-life | confirmed | stated for the demo tier; challenge stratum in the PAGE tier (§5.1, §5.2) |
| RT-B8 | the engine is its own truth | plausible | PKNCA cross-check of the PAGE gold before the freeze (§5.4) |
| RT-B9 | error turns leave the denominator | confirmed | outcome classes, all in the denominator (§6.1) |
| RT-B10 | the demo gate chosen on the frozen set | confirmed | decision rule on the development set, committed before the frozen run; one confirmatory configuration (§8) |
| RT-C3, RT-E1 | stale references, tool loops | confirmed | stale-result mutation (§7), LOOP outcome (§6.1); the fixes themselves are T-067 and T-062 |
| RT-E5 | no seed, no trace | confirmed | seeds in each request, transcripts committed, replay check (§10) |
