# Gate v3: the regeneration under a grammar (pre-registration, 2026-10-23)

Status: written before gate v3 has answered any exercise, and before the command that runs it exists (`bench/run_frozen.py` has no
`--gate v3` at this commit). It is binding from the commit that adds this file; nothing in it changes afterwards except through §9
and a dated entry in `bench/frozen/LEDGER.md`. It adds one exploratory configuration, `v3`, on the development tier only. It changes
nothing in the demo-gate decision of [`FROZEN_SET.md`](FROZEN_SET.md) §8 (the demo gate is v1 whatever this arm finds), in C1, in C2,
in the decider-only arm of [`NO_LM_ARM.md`](NO_LM_ARM.md) or in the frontier arm of [`FRONTIER_ARM.md`](FRONTIER_ARM.md), and it touches
no frozen exercise and no `wordings.json`. Gates v1 and v2 behave as they did.

## 1. Question

Gate v2 (typed rendering, [`GATE_V2.md`](../GATE_V2.md)) reads each final answer and, when it finds something, asks the model to write
it again, once, with a reminder in prose. On the development set that second call often repeats the mistake. In the stored v2 runs
(`bench/runs/decision/v2`, 600 turns): 188 turns were regenerated, 184 kept the regenerated answer and 4 the first one; 36 turns still
showed 93 findings after the regeneration (47 units printed next to a reference, 33 references that do not resolve, 8 arithmetic or
signs next to a reference, 5 numbers typed by hand), in 17 of the 25 exercises. v2 passes 6 of 25 exercises and 562 of 600 turns,
against 14 and 583 for v1.

The mistakes the reminder fails to stop are mechanical: a character that must not follow a reference, a path that does not exist, a
digit the client prints anyway. A model cannot be told in prose not to write a character; a sampler can refuse it.

> **G.** If the one regeneration of gate v2 is sampled under a grammar that allows digits only in a reference that resolves, in a
> closed label, or as an exact copy of a number the user typed, and allows no unit after a reference, then on the development set
> (25 exercises, seeds 1 to 3) no free digit is shown, an unverifiable quantity is shown in at most 3 exercises (v1: 3, v2: 17), at
> least 576 of 600 turns are CORRECT (v1: 583, v2: 562), at most 50 turns are regenerated (v1: 12, v2: 188) and the median turn takes
> at most 9 seconds (v1: 4.5, v2: 6.85).

The figure is read next to v1 and v2, always shown together:

| Configuration | Regeneration | What it says |
|---|---|---|
| v1 | gate v1: numbers checked against the tool texts | the shipped gate and the demo gate |
| v2 | typed rendering, regeneration with a reminder | what typing the values costs and gains |
| v3 | typed rendering, regeneration with a reminder under a grammar | what refusing the characters adds |

## 2. The arm

`APOTHICAIRE_GATE=v3` (or `Apothicaire(gate_version="v3")`) is gate v2 with one change. Everything the model sees before the
regeneration is gate v2's: the system prompt, the tools, the `{{call_N.path}}` references, the memory, the check of the draft, the
reminder. The first call of a turn carries no grammar. When gate v2 finds something in the draft, the regeneration request is the v2
request plus one field:

| Part | Same as v2 | Different, and why |
|---|---|---|
| prompts, tools, references, memory, compaction, caps, rubric | yes | |
| the draft (every call before a regeneration) | yes, no grammar | the grammar is built for a regeneration, which is the only call known to need it |
| when a regeneration happens, how many (one), the reminder, the "keep the better" rule | yes | |
| the regeneration request | no | one more field, `grammar`: the GBNF of `gate_v3.build(references, user messages)`. `tools` and `tool_choice` stay absent (a test asserts the exact body) |
| gate v2 on the regenerated text | yes | it still reads it; the grammar does not replace the check |
| the record of the turn | no | `gate["grammar"]`: sent or not, the sha256 of the text, its size and vocabulary, the text that came back (`text`) and `conformance`: did it obey the grammar |

**What the grammar allows** (`gate_v3.py`, tests in `tests/test_gate_v3.py`). A free digit is a digit that is none of (a) a digit inside
a reference `{{call_N.path}}` that gate v2 resolves against its closed tables and this chat's tool results (the references are
enumerated, not described), (b) a digit inside a closed label the renderer prints or gate v2 reads as notation (C0, t1/2, R²,
AUC(0-tlast), 1/h in a parenthesis), (c) a number the user typed, copied exactly (`12,5` is not `12.5`). One extension, switchable
(`idents`): an analysis or subject number that is in the tool results, after the word that names it ("analyse 3", "sujet 1"), which
gate v2 exempts. Without it the grammar refuses 95 of the 564 answers gate v2 passes instead of 23. Everything else is prose: no digit,
no brace. After a reference: nothing that reads as a unit (the atoms of `gate._ATOM_RE`, the words of `gate_v2._UNIT_WORD`), no digit,
operator, sign, exponent or glued second reference. Before a reference: no digit, operator, sign or emphasis mark. After a typed number:
nothing that would read as a longer number.

**Where the server stands.** llama.cpp b11700, read in the source at its tag; nothing has been run on a server. The benchmark's server
is `../optchat/start_servers_upstream.sh`, whose flags include `--jinja` and `--reasoning-budget 4096`.

1. The request is accepted. `tools/server/server-common.cpp` 1302-1306 refuses `grammar` together with `json_schema`, and 1398-1402
   (with `common/chat.cpp` 1371-1374) together with tools whose `tool_choice` is not `none`. The regeneration has neither: `optchat.LLM.chat`
   sends no `tools`, `tool_choice`, `json_schema` or `response_format` when `tools=None`.
2. The chat layer leaves the grammar alone. The 27B's chat template (read from the GGUF with llama.dll: it contains `<tool_call>`,
   `<function=` and `<parameter=`; of the 42 marker strings tested by `common_chat_template_detect_params_init`, `common/chat.cpp`
   1092-1249, only these three and `tool_calls` are in it; the string `'<tool_call><function=' ~ tool_call.name ~ '>'` that the Qwen3-Coder test
   excludes is not, and no earlier handler's condition is met) is handled by the Qwen3-Coder handler, `common/chat.cpp` 1238-1246. That handler builds a grammar only with tools or a response format
   (`common/parsers/qwen3-coder.cpp` 43 and 177-189). With neither, the chat session has no grammar of its own, and
   `tools/server/server-common.cpp` 1483-1486, which drops the client's `grammar` only when the session has one, keeps it. The
   request's `grammar_lazy` and `grammar_triggers` are dropped (1479-1482), so the grammar is not lazy.
3. It is a user grammar that starts at the first generated token. `tools/server/server-schema.cpp` 271-283 types it
   `COMMON_GRAMMAR_TYPE_USER`; only output-format and tool-call grammars are prefilled with the generation prompt (`common/common.h`
   219-224, `common/sampling.cpp` 298-312); the root rule is `root` (`common/sampling.cpp` 268-276).
4. A grammar that does not parse is an error, not a silent no-op. `common/sampling.cpp` 278-280 throws "failed to parse grammar";
   `tools/server/server-context.cpp` 1924-1931 answers HTTP 400 "Failed to initialize samplers: ..."; optchat raises
   `LLMError("HTTP 400: ...")`; the agent keeps the first answer and records the error.
5. It is applied at each step. This server has a reasoning-budget sampler for this template (`tools/server/server-common.cpp`
   1441-1456 passes the template's `<think>` tags and the budget of 4,096; `common/sampling.cpp` 314-327 builds it), and
   `grammar_should_apply` (`common/sampling.cpp` 461-474) returns true for a grammar that is not lazy, whatever the state of that
   sampler. The token is drawn by the usual chain, checked alone against the grammar, and only if refused is the grammar applied to
   the whole candidate list and the token drawn again (`common_sampler_sample`, `common/sampling.cpp` 606-688, called without
   `grammar_first` at `tools/server/server-context.cpp` 4468). An end-of-generation token is allowed only where the grammar can end.

What this does not reach: the HTTP and chat-session path was read, not run. The first GPU run checks it through `conformance`
(below), recorded for every regeneration, and §4 stops the reading on one violation.

**Checked offline** (before any run, no GPU, no server): the printed text against two readers written for this repository
(`gate_v3.Machine`, `tests/gbnf_reader.py`) and against llama.cpp b11700 itself (`bench/grammar_llamacpp.py`: llama.dll of the upstream
release through ctypes, the 27B's vocabulary opened vocab-only). Results in §7.

**Cost.** Checking a token that the grammar allows is cheap (190 to 200 microseconds per token in the harness, which also tokenises and
clones the sampler). A drawn token that it refuses costs one application of the grammar to the 248,320 candidates: 0.67 to 0.85 s in a
prose state and 0.06 s inside a reference (three measurements on this CPU, §7). The stored first drafts have 4.4 refused spans on average,
so a regeneration that wrote them again would cost 3 to 3.7 s more, on top of the 13.1 s median of a stored v2 regeneration call.
Building the grammar takes 16 ms (median; 95 ms at most) and happens only for a regeneration.

**If the grammar cannot be sent.** If `gate_v3.build` raises, or the text exceeds 1 MB (the largest of the 600 turns is 76 KB), no
grammar is sent, the regeneration is gate v2's, and the record says why (`gate["grammar"]["sent"]` false). Nothing about the grammar can
stop a chat.

## 3. Configuration of the run

Development tier only (`run_frozen.py` will refuse `--gate v3` on a frozen tier, with `--api-model` and with `--api-addendum`).

| | |
|---|---|
| exercises | the 25 of `bench/exercises/`, wordings of `scripts.py`, 8 turns each, 600 turns in all |
| model | Bonsai 2 27B Q2_0 (`Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf`), upstream llama.cpp b11700 (23f7aabc1), RTX 3060 |
| server | `../optchat/start_servers_upstream.sh`: `-c 24576 -np 2 -ngl 99 --jinja -fa on -ctk q8_0 -ctv q8_0 --slots --metrics --reasoning-budget 4096`, port 18435; the chat uses slot 0, so the regeneration reuses the prompt cache of the draft |
| sampling | temperature 0.3, thinking off, `max_tokens` 1,200, seeds 1, 2, 3 sent to the sampler in each request, run in sequence |
| engine | the `caladrius-mcp` of the stored v1 and v2 runs: `../caladrius/target/agent-apothicaire/release/caladrius-mcp.exe`, sha256 `e38211b5ce307acc0ccf2d51b76d65ab3e2050d3ecfc53b0e4f9b7e09a2f83c7`, modified 2026-10-21 17:22, built from caladrius f119618 (ledger of 2026-10-21), 4 minutes 40 seconds before the first v1 run; never rebuilt |
| rubric | `score.RUBRIC_VERSION` 2026-10-21, the scorer of the stored runs |
| v1, v2 | read from `bench/runs/decision/` by the analysis; never rerun, never rewritten |
| output | `bench/runs/grammar-dev/v3/seed-N/` (the default of `--gate v3`), with `-data/` folders: `gate.jsonl` holds the grammar records |

The code that runs is the head of the branch that merges this arm; its commit is recorded in `run.json` and named in the ledger entry
that follows the run. After this commit, a change to the behaviour of `gate_v3.py` or of the gate wiring in `apothicaire.py`, or to anything in this file
other than §9, is an amendment of §9, dated, and made before the run.

No interim look changes anything and there is no early stop ([`FROZEN_SET.md`](FROZEN_SET.md) §10.2). All 600 turns run whatever the
first exercises show. A turn is never rerun alone (§10.3), and an exercise by seed interrupted by an event outside the model is
restarted once from turn 1 as §10.3 says. A run that is invalid in the sense of §4 (Validity) is kept in its folder, a dated ledger
entry says why, the fix is a commit, and a new run of the whole configuration then starts from turn 1, in a new folder the entry names,
under the same thresholds.

## 4. Thresholds, fixed before the run

Measured on the 600 turns of `v3`, in `bench/runs/grammar-dev/ANALYSIS.md` (written by `analyse`, §8).

| Measure | v1 | v2 | Success | Kill |
|---|---|---|---|---|
| free digits shown | n/a | 5 | 0 | |
| exercises with an unverifiable quantity shown (endpoint 2 of §11.1) | 3 / 25 | 17 / 25 | at most 3 / 25 | |
| turns CORRECT | 583 / 600 | 562 / 600 | at least 576 / 600 | fewer than 562 / 600 |
| regenerations | 12 | 188 | at most 50 | |
| median time per turn | 4.5 s | 6.85 s | at most 9 s | more than 13.5 s |
| LOOP + ABSTAINED turns | 1 | 2 | | more than 2 % of the turns (more than 12 of 600) |
| the server enforces the grammar | | | | it does not (below) |

**Definitions.**

- *Free digit shown.* A finding of gate v2, left in an answer that was shown, that is a number typed by hand which is not the user's
  (`bare_number`) or a digit next to a reference (`adjacent_to_reference`, reason "digit after a reference"). Each finding counts once.
  Read in `findings` of `gate.jsonl`, which is what the answer shown still carries with its badge. The v2 figure, 5, is read the same
  way in the stored runs (bare numbers in 2 exercises, no digit after a reference).
- *Unverifiable quantity shown.* Endpoint 2 of [`FROZEN_SET.md`](FROZEN_SET.md) §11.1 as `run_frozen.py` computes it: an exercise with
  `numbers_unverified_after > 0` in a turn of any seed. In the stored v2 runs this is the same set of 17 exercises as "a gate v2
  finding left in a shown answer".
- *Turns CORRECT, LOOP, ABSTAINED, median time per turn.* As in `run_frozen.py` (§6.1 outcomes; `wall_s` of the 600 turns).
- *Regenerations.* Turns with `regenerated` true.
- *The server does not enforce the grammar.* At least one regeneration whose request the server answered with an error that mentions the
  grammar (`regen_stats["error"]` contains "grammar": the server did not parse it), or at least one regeneration whose text breaks the
  grammar it was sent (`conformance["violation"]`: a character the grammar refuses, or a stop where it cannot end; a text cut at
  `max_tokens` has only to be a valid prefix). The check is `gate_v3.Machine`, which agrees with llama.cpp on 13,644 texts (§7).
  Enforcement is deterministic: one violation is evidence, and no exception is declared after the fact.

**Validity.** The run is read only if all 600 turns were recorded, the llama.cpp build (`run.json`) and the engine hash (the ledger entry that
follows the run) are those of §3, and every regeneration was sent a grammar (`gate["grammar"]["sent"]` true). Otherwise the run is
invalid, not killed: §3 says what follows.

**Also printed, descriptive, no threshold:** the findings left in the shown answers by kind (in particular spelled-out numbers, which
a model refused every digit may turn to); the outcomes by turn kind; the time of the regeneration call against v2's; what was kept
(regenerated or first); the grammar sizes and build times; the paired comparisons of exercises passed, v3 against v2 and v3 against
v1 (exact McNemar, [`FROZEN_SET.md`](FROZEN_SET.md) §11.3).

**What is expected, written before the run.** The first draft is not under the grammar, so what makes gate v2 regenerate is untouched;
the count of regenerations moves only through the memory (an earlier answer that obeys the grammar is a better example for the later
drafts). I expect it to stay of the order of v2's 188 and not to reach 50; the threshold is kept as written. No violation is expected.
The extra time is expected to be about 3 s per regeneration, so the median turn stays near v2's. The run takes about 2.3 hours (v2: 2.17
hours over the same 600 turns, plus about 10 minutes).

**The analysis is declared here, implemented after.** The code that applies this section and §5 is `bench/grammar_arm.py`, added by the
commit after this one and tested on synthetic data for every row of §5. If its reading differs from this text, this text wins and the
difference is an amendment.

## 5. Reading, decided before any result

Let a *kill* be any one of the five kill conditions of §4, and let the *four effects* be: free digits 0, an unverifiable quantity shown
in at most 3 / 25 exercises, at least 576 / 600 turns CORRECT, median time per turn at most 9 s.

| Result | Reading |
|---|---|
| the run is invalid (§4) | **no reading**: nothing is concluded, the ledger says why, §3 says what follows |
| a kill condition holds | **killed**: the arm is dropped as designed. The outcomes by turn kind and the records say why; no tuning and no rerun on these exercises |
| no kill, the four effects hold, regenerations at most 50 | **success**, as declared in §4 |
| no kill, the four effects hold, regenerations above 50 | **the grammar does what it is for; the regeneration count is unchanged**. Not "success" in the words of §4, and not "no decision": the fifth threshold depends on something this arm does not change |
| no kill, one of the four effects missed | **no decision**: the measures say which; no claim |

Whatever the reading, the demo keeps gate v1 ([`FROZEN_SET.md`](FROZEN_SET.md) §8). A success on this arm is a result on the development
set, in-sample, exploratory: it would justify proposing the grammar on the first call, or on the frozen tier, by a dated amendment
before the system freeze, and nothing more.

## 6. What this arm does not measure

First, the grammar acts on the regeneration only. The draft, which decides whether there is a regeneration, is gate v2's, so the arm
changes the count of regenerations only through the memory, and makes each regeneration end differently. Second, the grammar is stricter
than gate v2 by design, and the stricter part is not neutral: of the 564 final answers v2 passes, 23 contain something the grammar
refuses (17 small integers such as "3 points" or "(2 ou 4)", 3 characters like "A²", 2 words that begin like a unit right after a
reference such as "(les", 1 label "1/h" outside a parenthesis). A regeneration that wants to write "3 points" must write something else.
Third, the grammar cannot see what it was not given: a quantity spelled out in words with a unit ("un d"), a unit written elsewhere in
the clause that contradicts the rendered one, a sign written in words ("négatif {{ref}}") and a unit in a table cell are still found by
gate v2 and still cost a regeneration. Of the 651 findings in the 188 first drafts, 5 are of the first kind. A model that is refused
every digit may also spell numbers out. Fourth, it constrains characters, not meaning: a text that cites the wrong parameter or the wrong
analysis obeys the grammar and is WRONG for the rubric. Fifth, one model, one vocabulary, 25 exercises written by the people who tuned
the prompts and the gate, and a grammar written while reading the 600 stored v2 turns: its one extension (identifiers) exists because 74
of the 95 answers refused by the strict grammar needed it. The offline acceptance of §7 is a fit, not a prediction, and every figure from
this arm is labelled "development set, in-sample, exploratory". Sixth, the time per turn is that of this PC and this llama.cpp build;
the cost of the grammar grows with the number of candidates the sampler checks and is not a property of the idea.

## 7. Results before the run

**The grammar on the answers already on disk** (`python bench/grammar_offline.py`, the 600 turns of `bench/runs/decision/v2`, each with
the grammar `gate_v3.build` would have built for it: 316 to 1,044 rules, median 418; 34.0 to 76.0 KB, median 39.8 KB):

| | texts | grammar of the arm (identifiers) | strict grammar (no identifiers) |
|---|---|---|---|
| final answers gate v2 passed without a finding: accepted | 564 | 541 (95.9 %) | 469 (83.2 %) |
| first drafts gate v2 found something in: refused | 188 | 184 | 184 |
| findings of those drafts: touched by a refused span | 651 | 646 | 647 |

The 651 findings by class, with the number the grammar catches (a refused span touches the finding, one character either side):

| finding of gate v2 | findings | caught |
|---|---|---|
| a unit next to a reference | 349 | 349 |
| a reference that does not resolve, or points at a raw path, a text or an export field | 224 | 224 |
| a digit after a reference, or arithmetic or a sign next to it | 20 | 20 |
| a number typed by hand that is not the user's | 53 | 53 |
| a quantity spelled in words with a unit | 5 | 0 |

The classes are those of the `kind` and `reason` of each finding in `gate.jsonl`. The 4 drafts the grammar accepts are 4 whose findings are all the spelled-out "un d". The 23 refusals of the
arm are listed, each at its first refused character, by `bench/grammar_offline.py`; the strict grammar refuses 95, 74 of them an analysis
or subject number.

**The printed text against llama.cpp b11700** (`python bench/grammar_llamacpp.py`; llama.dll of the upstream b11700 release, sha256
`1f25590ebf53ee63...`, 3,566,592 bytes; the 27B's vocabulary, 248,320 tokens, vocab-only, CPU, no backend loaded, no llama-server):
`llama_sampler_init_grammar` parses 600 of 600 grammars; 3,975 texts (564 final answers, 188 first drafts, and mutations of the finals: a
digit run, a unit, a sign after a reference, a wrong path, a cut reference, digits and letters of other scripts, characters of 2 to 4
bytes) and 360,932 tokens give the same verdict as `gate_v3.Machine` on "alive", on "accepted" and on the place of the refusal every
time; with `--mutations 4`, 13,644 texts and 1,204,927 tokens, again 0 disagreements. llama.cpp accepts 541 of 564 finals and 4 of 188
drafts, the numbers above. The same grammar text, parsed by the library the server calls, is therefore read the way `conformance` reads
it.

**The cost of a refused token**, same script, same CPU, largest grammar (1,044 rules, 76.0 KB), median of 5 applications to the 248,320
candidates, three measurements: 721, 722 and 790 ms at the start of an answer (162,028 candidates survive); 679, 670 and 734 ms after
"La valeur est "; 845, 766 and 810 ms after a reference (138,376 survive); 62, 62 and 63 ms inside a reference (6 survive). The stored
first drafts have 4.4 refused spans (median 3, 90th percentile 8, largest 18).

**Tests.** `tests/test_gate_v3.py` (the grammar: character sets, unit tables, vocabulary against `gate_v2.resolve`, the printed text
against the Earley reader, sentence tables, mutation families, a seeded random-walk fuzz whose every accepted text has no covered finding
and no free digit), `tests/test_grammar_offline.py`, `tests/test_agent_gate_v3.py` (the exact body of the regeneration request, the
fall-backs, gates v1 and v2 unchanged), `tests/test_grammar_llamacpp.py` (skipped where llama.dll is absent).

## 8. Running

On the PC, with the server of §3 running on port 18435 and the engine binary unchanged. Nothing is run elsewhere. The command is added by
the commit after this one; this text was committed first so that no threshold could be fitted to a command that already existed.

```bash
sha256sum ../caladrius/target/agent-apothicaire/release/caladrius-mcp.exe      # must print the hash of §3; never rebuild it
python bench/run_frozen.py run --tier dev --gate v3 --seeds 1,2,3             # -> bench/runs/grammar-dev/v3/seed-{1,2,3}/
python bench/run_frozen.py analyse --tier dev --c1 v2 --c2 v3                 # v1 and v2 read from bench/runs/decision (no rerun) -> bench/runs/grammar-dev/ANALYSIS.md
```

`--gate v3` writes to `bench/runs/grammar-dev/` unless `--out` says otherwise, so `bench/runs/decision/` and its `ANALYSIS.md`, the source
of the ledger entry of 2026-10-21, are not touched. `analyse` with `v3` among `--c1`, `--c2` reads that folder, adds `v1` and `v2` from
`bench/runs/decision` unless `--with` says otherwise, prints the three configurations side by side, the grammar section (regenerations
sent with a grammar, conformance, server errors, what was kept) and the reading of §5 with the value of every threshold.

After the run: commit `bench/runs/grammar-dev/`, and add a dated entry to `bench/frozen/LEDGER.md` with the figures and the reading of
§5 as `ANALYSIS.md` prints it, the apothicaire commit, the llama.cpp build string and the engine hash. A dry run of the pipeline without a
model is `python bench/run_frozen.py run --tier dev --gate v3 --seeds 1 --stub --out DIR` (the stub records the grammars it is sent; it
says nothing about a model).

## 9. Amendments

None.
