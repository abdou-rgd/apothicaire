# Apothicaire without a language model: the decider-only arm of the frozen set (pre-registration draft, 2026-10-21)

Status: draft, written before any decision-model prediction on a frozen exercise. It becomes binding with the system freeze of
[`FROZEN_SET.md`](FROZEN_SET.md) §9: the files and model hashes of §3 go into that freeze, and nothing in this file changes after it
except through dated entries in `bench/frozen/LEDGER.md`. It adds configurations to the frozen set; it changes nothing in the demo
decision of §8 and nothing in C1 or C2.

## 1. Question

Abdou's hypothesis (2026-10-21): pharmacometricians do not need a language model to explain results to them; a small decision
model that picks the tool and its arguments, with Caladrius computing and a typed template rendering, could replace the 27B.

The frozen set can test the narrow form of it:

> **H.** On the eight turn kinds of the frozen set (NCA, readings, recall, compare, a parameter not computed), the decider-only
> arm passes at least as many exercises as the configuration chosen for the demo (C1, the 27B with the gate of §8), under the
> same rubric, on the same exercises, wordings and seeds.

The frozen set scores tool calls and numbers, not prose (FROZEN_SET.md §6.2), so it is a fair ground for an arm that writes no
prose. It is not a ground for everything the 27B does (§5).

## 2. The arm

```
user message ──► deterministic reader ──► state ──► decision model ──► harness ──► Caladrius ──► templates ──► answer
                 (table, dose and unit,    (data     (20 closed          (data_import,   (engine     (engine values only,
                  infusion duration)        header,   questions, one      nca_run,        values)     French sentences
                                            dose      forward pass)       analysis_get,               written in advance)
                                            sentence,                     analysis_compare)
                                            request,
                                            analyses)
```

- **Decision model:** D-01 v2, Qwen3.5-0.8B trained on 2 530 synthetic states (decision/README.md, Step 7), served as its **LoRA
  adapters on the 4-bit base**, not the 16-bit merged file (the merged file never answers `is_not_available` true, a defect still
  open: decision/README.md, "Two forms of the model"). Labels: the likeliest option of each question, `true` when P(true) ≥ 0.5.
- **Harness:** `decision/harness.py` with three switches, all off by default so every earlier D-01 figure stays reproducible,
  all on in this arm (`bench/decider_arm.py`, `HARNESS_KW`):

  | Switch | Why the arm needs it | Measured on the development set |
  |---|---|---|
  | `engine_units` | the frozen gold has CL in L/time and V in L (the agent's client sends the dose unit since T-059); the harness sent the dose without its unit, so CL and V were labelled "dose unit/…" | without it, 25 of 25 turn 1 WRONG; with it, CL and V in litres and 25 of 25 CORRECT |
  | `extrapolation_verdict` | turn 4 must say whether the extrapolation is acceptable (rule 6); the 20 questions have none for it. The harness now follows the extrapolated percentage with **the engine's verdict**: "not acceptable" when Caladrius raised its `high_extrapolation` flag on `aucpext.obs`, "acceptable" otherwise, with the engine's threshold. The harness compares nothing | without it, 25 of 25 turn 4 WRONG; with it, 25 of 25 CORRECT |
  | `free_layout` | the frozen wordings place `{table}` where their authors want; the old reader expected sentence, table, notes, request, one per line. The new reader finds the table anywhere (words glued before its header up to ": " or after its last row are kept as text) and gives the old result on the old layout, so the model sees the states it was trained on | identical split on the 25 first messages (test) |

  These switches were written on the development set and on placeholder layouts, without any frozen wording (Claude never sees
  them, FROZEN_SET.md §5.3). A layout they do not read (for instance words glued before the header without ": ") fails, and the
  failure counts: reading free text is part of what this arm must do without a language model.
- **Memory between turns:** the typed state only (§7): the Caladrius project (analyses with their id, method, dose, route, units,
  results), the data header and the first message's dose sentence and notes. No conversation summary, no OptChat.
- **Gate:** none is needed (the harness writes engine values only); gate v1 still runs on every answer and counts any number found
  in no tool text and no user message, so endpoint 2 of §11.1 is defined for this arm too.

## 3. Frozen with the system freeze

In addition to FROZEN_SET.md §9, the system-freeze commit records the SHA-256 of:

- `decision/harness.py`, `decision/make_dataset.py` (state and questions), `decision/wordings.json` (imported by it),
  `decision/decider_unsloth.py`, `decision/run_harness.py`, `bench/decider_arm.py`, this file;
- every file of `decision/models/qwen35-0.8b-d01-v2/adapters/` and of the local 4-bit base snapshot it loads, and the
  `unsloth`, `transformers` and `torch` versions of the environment that runs it.

On the PC, before the freeze (PowerShell, from the repository root):

```powershell
Get-FileHash -Algorithm SHA256 decision\harness.py, decision\make_dataset.py, decision\wordings.json, decision\decider_unsloth.py, decision\run_harness.py, bench\decider_arm.py, bench\NO_LM_ARM.md
Get-ChildItem -Recurse -File decision\models\qwen35-0.8b-d01-v2\adapters | Get-FileHash -Algorithm SHA256
python -c "import unsloth, transformers, torch; print(unsloth.__version__, transformers.__version__, torch.__version__)"
```

The output goes into the ledger entry of the system freeze. If the adapters cannot be found or loaded on the PC, the arm is not run
and the ledger says so; it is never replaced by the merged file without a dated entry saying why.

## 4. What is measured

Exactly the endpoints of FROZEN_SET.md §11, computed by the same script (`run_frozen.py analyse`), with the arm under the
configuration name `nolm`:

| Endpoint | Definition | Role here |
|---|---|---|
| exercises failed (strict) | an exercise fails when one of its 8 turns is not CORRECT on any seed | **primary** (§6) |
| per-turn rate | CORRECT turns / planned turns, cluster bootstrap over exercises | secondary, descriptive |
| pass^k, k = 1..3 | mean over exercises of C(c, k) / C(3, k) | secondary, descriptive |
| outcomes by turn kind | ERROR, TIMEOUT, LOOP, ABSTAINED, WRONG, CORRECT | secondary, says where it breaks |
| unverifiable quantity shown | gate v1's definition (§2) | secondary; expected 0 by construction |
| decisions against gold decisions | per turn, the 20 answers against the gold decisions of the turn kind (`decider_arm.decision_check`) | diagnostic: splits each failure into **decision error** (the model) and **deterministic error** (reader, harness, template) |
| harness ceiling | the same run with the gold decisions (`--stub`), with the frozen wordings | diagnostic: the score the arm would reach with a perfect decision model; its failures are the reader's |
| time per turn, VRAM | wall clock, `decider_summary.json` | descriptive |

The decision model has no sampler: seeds 1 to 3 do not change its input, so its three runs should be identical. They are run anyway
so that the strict rule and pass^k are computed exactly as for C1, and any difference between seeds is reported as nondeterminism of
the forward passes on the PC.

## 5. What the frozen set does not measure

- **Long sessions and memory.** Eight turns, no turn pushes the first results out of a context; the subject never changes and the dose
  is never corrected. The challenge stratum of the PAGE tier (FROZEN_SET.md §5.2) is where memory is tested; this arm must be re-run
  there before any claim beyond the eight kinds.
- **Explanation quality.** The rubric reads labels, values, units and the verdict. A sentence the 27B writes well earns nothing; a
  template the user finds dry costs nothing. Whether pharmacometricians want sentences is a question for users, not for this set.
- **Requests outside the 20 closed questions:** fits, simulations, several subjects, bioequivalence, steady state, or a question the
  harness has no template for. The arm answers them with a fixed refusal; the 27B may answer them. None is in the demo tier.
- **Ambiguity handled by asking back.** A frozen wording is never ambiguous on purpose; asking back is not scored.

## 6. Comparison and thresholds (written before any result)

Reference: C1 as fixed by the decision of FROZEN_SET.md §8, same 40 exercises, same wordings file, same wording seed, seeds 1 to 3.
Let p(X) be the number of exercises configuration X passes under the strict rule.

| Result | Reading, decided now |
|---|---|
| p(nolm) ≥ p(C1) and 0 exercises with an unverifiable quantity shown | **H holds on the demo tier**: on these eight kinds the language model is not needed to get the numbers right |
| p(C1) − 5 ≤ p(nolm) < p(C1) | **no difference detected** (fewer than 6 discordant exercises cannot reach p < 0.05, FROZEN_SET.md §11.3); H is neither shown nor refuted |
| p(nolm) ≤ p(C1) − 6, and the discordant exercises all go to C1 | **H fails on the demo tier** |

Ties go to `nolm`, as ties go to the typed gate in §8: an arm that cannot write an unverified number by construction wins a tie.
The exact McNemar test on the discordant exercises and the per-turn difference with its paired bootstrap are printed next to the
reading and labelled exploratory: this arm is not confirmatory in the demo tier (FROZEN_SET.md §2), and the demo set becomes
development data once read.

Whatever the reading, the cause of each failure is read off the diagnostics, by this rule:

| Most failed exercises of `nolm` have... | Next step (after 2026-11-17) |
|---|---|
| at least one wrong decision, and the ceiling run passes them | the decision model: D-01 v3 (paraphrases from another model family) or the D-01 v2 recipe on Intern-Decision-0.8B (Library `veille/2026-10-21-modeles-de-decision.md`) |
| all decisions right, and the ceiling run fails them too | the deterministic reader or a template: fix on the development set, re-measure on the PAGE tier |
| a failure in both | both, in that order |

The demo itself is not changed by any of these readings: it shows the 27B with C1's gate (FROZEN_SET.md §8), and the decision model
appears as roadmap only.

## 7. Context of follow-up turns without a language model

Three ways to give turns 2 to 8 their context were considered:

| Option | What the decision model sees | Cost | Kept for this arm |
|---|---|---|---|
| (a) typed state from the Caladrius project | the list of analyses (id, kind, AUC method), the data header and first rows, the first message's dose sentence and notes, the current request | none: it is the state D-01 v2 was trained on | **yes** |
| (b) the last raw turns | (a) plus the last k user requests | a new state format, so a new training set and a new model (D-01 v3 at the earliest) | no, after the demo |
| (c) a language model kept for OptChat summaries only | (a): the summaries would have no reader on this path | the 27B or a smaller model in the background | no |

With (a), every follow-up of the frozen set is answerable: a reading turn reads the analysis of its AUC method from the project
(`analysis_get`), the recall reads the settings Caladrius recorded, the compare turn runs the missing method and picks the pair from
the analyses' ids. Nothing a follow-up needs lives only in the conversation.

**Is it a problem that the decision model does not write OptChat memory?** Not for this set, and not for numbers ever:

- OptChat's log (`log.jsonl`) is written verbatim by the client, without any model; only its summary lines need a model, and short
  messages already become verbatim lines without one. What the arm loses is not the writing of the memory, it is its **reading**:
  the 27B reads the digest and opens nodes with `zoom`; a decision model reads a fixed state and calls no memory tool. On this path
  a summary nobody reads is useless.
- The memory of the numbers is the Caladrius project, typed and exact, with the analysis ids the answers cite. That is better than
  any summary for what the frozen set asks.
- It becomes a problem when a follow-up refers to something said in words and never turned into an engine object: "the same thing for
  subject 3", "no, the dose was 20 mg", "as I said earlier". The frozen demo tier has none of these. The answer then is a typed
  conversation state (the decisions of each turn: subject, method, parameters asked, analysis ids, corrections), added to the state
  of option (a) and learned with D-01 v3, not a text summary. The PAGE tier's challenge stratum measures it.

## 8. Later arms (after the demo-tier reading)

Once the demo tier has been read it is development data (FROZEN_SET.md §2). The comparisons below are therefore declared for the
PAGE tier, with thresholds written in a dated amendment of this file before any of them runs, and all on the same exercises, wordings
and seeds:

| Arm | Answer path | What it tests | Needs | GPU memory (RTX 3060, 12 GB) |
|---|---|---|---|---|
| 27B alone | the agent with C1's gate | the reference | nothing new | 9.0 GB |
| `nolm` | §2 | H on the PAGE tier, with the challenge stratum | the PAGE tier | 1.9 GB |
| 0.8B + 27B | the decider picks tool and arguments, the harness calls Caladrius, the 27B writes the answer from the typed result through gate v2 | whether the 27B adds anything once the decisions are fixed | a harness that hands the typed result to the 27B | ≈ 11 GB, tight |
| 0.8B + 9B untrained | same, with a 9B writer (Qwen3.5-9B, Apache-2.0) | whether a smaller writer suffices | the 9B GGUF on llama.cpp b11700 | ≈ 8 GB |
| 0.8B + 9B QLoRA | same, the 9B trained on synthetic typed results | whether training the writer matters | a training set, 2 to 7 Colab units | ≈ 8 GB |
| 4B decider alone | §2 with a 4B decision model | whether a larger decider closes the gap of unseen wordings | a 4B trained on the D-01 data (Library `veille/2026-10-21-tuto-together-jev.md`) | ≈ 3 GB, fits only without the 27B |

Without the 27B, the memory budget no longer limits the decider to 2.5 GB: a 4B (Q4, about 2.7 GB) or a 9B fits alone on the RTX
3060. No arm of this section is trained or run before 2026-11-17.

## 9. Running on the PC, after the system freeze

Order (FROZEN_SET.md §10.2): C1 on every seed, then C2, then this arm, never two GPU jobs at once. The decision model runs in the
Unsloth environment of `decision/requirements-unsloth.txt` (it also needs `httpx`, which `apothicaire.py` imports through OptChat);
llama-server is not used by this arm and may stay stopped. About 960 turns at 0.3 to 0.4 s each: under 10 minutes per run.

```powershell
# 1. the arm (the output joins C1 and C2 under bench/frozen/demo/runs/nolm/)
python bench/run_frozen.py run --tier demo --gate nolm --seeds 1,2,3 --wordings bench/frozen/demo/wordings.json --wording-seed <N> --decider decider_unsloth:decide --decider-model decision/models/qwen35-0.8b-d01-v2/adapters

# 2. the harness ceiling with the same wordings (gold decisions, no model; kept apart so the analysis of step 3 does not mix it in)
python bench/run_frozen.py run --tier demo --gate nolm --seeds 1 --stub --wordings bench/frozen/demo/wordings.json --wording-seed <N> --out bench/frozen/demo/ceiling
python bench/run_frozen.py analyse --tier demo --out bench/frozen/demo/ceiling --c1 nolm --c2 none

# 3. the analysis of every configuration: nolm appears next to C1 and C2, with its decision table
python bench/run_frozen.py analyse --tier demo --c1 <C1> --c2 <C2>
```

`<N>` is the wording seed recorded in `MANIFEST.json`; `<C1>` and `<C2>` are the gates of the §8 decision. The reading of §6 is
written in `bench/frozen/demo/RESULTS.md` under its own heading, after the endpoints of C1 and C2, and labelled exploratory.

Dry run in the cloud (no GPU, no model, development set): `python bench/run_frozen.py run --tier dev --gate nolm --seeds 1,2,3 --stub
--out <tmp>`. On 2026-10-21 it gave 600 / 600 turns CORRECT, 25 / 25 exercises passed: the harness ceiling on the development set.
