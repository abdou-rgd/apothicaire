# Frozen-set ledger

Dated entries, never edited in place (FROZEN_SET.md, header and §9).

## 2026-10-21: demo-gate decision of §8: v1

- Run on the development set (25 exercises, `bench/exercises/`, gold with units), gates v1 and v2, seeds 1, 2, 3,
  rubric 2026-10-21. In-sample, not confirmatory.
- System: Bonsai 2 27B Q2_0 on upstream llama.cpp b11700 (23f7aabc1), RTX 3060, temperature 0.3, thinking off;
  apothicaire 703fca1 (main a4e6483 plus LF in `bench/`), caladrius-mcp built from caladrius f119618.
- Figures (`bench/runs/decision/ANALYSIS.md`):

| | v1 | v2 |
|---|---|---|
| exercises passed, strict rule of §6.3 (pass^3) | 14 / 25 | 6 / 25 |
| pass^1 / pass^2 | 80.0 % / 66.7 % | 61.3 % / 37.3 % |
| turns CORRECT | 583 / 600 (97.2 %) | 562 / 600 (93.7 %) |
| exercises with an unverifiable quantity shown | 3 / 25 | 17 / 25 |
| WRONG turns with nothing flagged | 13 | 28 |
| regenerations | 12 | 188 |

- Rule: v2 only if it passes at least as many exercises as v1. 6 < 14, so **v1 is the demo gate** (C1); v2 runs on
  the frozen set as C2, descriptive only.
- Paired: 11 exercises pass only with v1, 3 only with v2 (exact McNemar p = 0.057); mean difference in correct turns
  per exercise -0.035 (paired bootstrap 95 % -0.062 to -0.010).

## 2026-10-22: frontier API arm declared, before any run

- `bench/FRONTIER_ARM.md` (draft, binding at the system freeze) declares a configuration `v1+<model>`: the same agent, prompts,
  tools and gate v1 on a hosted model through `bench/api_model.py`, read as the triplet `nolm` / C1 / frontier. Models, settings,
  order and the reading table (§5) are written before any hosted model has answered any exercise.
- Development tier first, exploratory and in-sample for the 27B (§3); demo tier after C1, C2 and `nolm`, descriptive (§4);
  declared comparison in the PAGE tier only. Nothing in §8, C1, C2 or NO_LM_ARM.md changes.

## 2026-10-22: frontier API arm, development runs (§3) and amendment §8

- Runs `bench/runs/frontier-dev-2026-10-22/` (apothicaire da70317, cloud session, caladrius-mcp from caladrius 1be2078), seeds 1, 2,
  3, one process per seed. Development set, in-sample for the 27B, exploratory. v1 read from `bench/runs/decision/v1`.

| | v1 (27B) | Claude Sonnet 5.5 | Claude Opus 5.5 |
|---|---|---|---|
| exercises passed (pass^3) | 14 / 25 | 0 / 25 | 0 / 25 |
| pass^1 | 80.0 % | 2.7 % | 4.0 % |
| turns CORRECT | 583 / 600 | 468 / 600 | 481 / 600 |
| exercises with an unverifiable quantity shown | 3 / 25 | 1 / 25 | 0 / 25 |
| regenerations | 12 | 8 | 20 |
| cost, refusals | | 12.17 USD, 0 | 20.96 USD, 0 |

- Opus ran because Sonnet passed at most 3 more exercises than v1 (§3). Reading of §5: the harness is fitted to the 27B. Most WRONG
  turns are the dump rule and both verdicts on `half_life`; the oracle check finds the values right in about 99 % (Sonnet) and
  94 % (Opus) of the turns.
- Amendment `FRONTIER_ARM.md` §8 written before any run with it: configuration `v1+<model>+scope` (two sentences appended to the
  hosted model's system prompt), Sonnet only on the development tier, reading fixed in advance.

## 2026-10-22: frontier API arm, development run with the scope instruction (§8)

- Run `bench/runs/frontier-dev-2026-10-22/v1+claude-sonnet-5-5+scope/` (apothicaire 5090868, the amendment's commit), seeds 1, 2,
  3. Development set, exploratory, scope instruction written after the first run.
- Claude Sonnet 5.5 + scope: 21 / 25 exercises passed (pass^3), pass^1 94.7 %, 596 / 600 turns CORRECT, 0 / 25 with an
  unverifiable quantity shown, 3 regenerations, 10.30 USD, 0 refusals.
- Reading of §8 (fixed before the run): 21 ≥ 6, so the first run measured, at least in part, the prompt's fit to the 27B. Against
  v1 (14 / 25): 8 exercises pass only with Sonnet + scope, 1 only with v1, exact McNemar p = 0.039: the row "the 27B is behind" on
  the development set, under the limits of §8 (instruction tuned on these exercises for the hosted model, not given to the 27B).
- Claude Opus 5.5 with the instruction is not run without Abdou's word (§8).

## 2026-10-22: frontier API arm, amendment §9 (the 27B with the scope instruction)

- Amendment `FRONTIER_ARM.md` §9 written before any run with it: configuration `v1+scope`, the 27B with the same two sentences as
  §8 at the same place in the system prompt (`api_model.with_addendum`, apothicaire e462095), development tier, seeds 1 to 3 on the
  PC. Reading fixed in advance: p(v1+scope) ≥ 19 no difference detected against Sonnet + scope (21); 14 to 18 the exact McNemar p
  decides; ≤ 13 the instruction does not help the 27B.

## 2026-10-22: frontier API arm, development run of the 27B with the scope instruction (§9)

- Run `bench/runs/frontier-dev-2026-10-22-27b-scope/v1+scope/` (apothicaire f7e9939, the amendment's commit; PC, llama.cpp
  b11700, the 27B Q2_0), seeds 1, 2, 3 in sequence. Development set, in-sample, exploratory.

| | v1 | Sonnet 5.5 | Opus 5.5 | Sonnet 5.5 + scope | 27B + scope |
|---|---|---|---|---|---|
| exercises passed (pass^3) | 14 / 25 | 0 / 25 | 0 / 25 | 21 / 25 | 14 / 25 |
| pass^1 | 80.0 % | 2.7 % | 4.0 % | 94.7 % | 84.0 % |
| turns CORRECT | 583 / 600 | 468 / 600 | 481 / 600 | 596 / 600 | 587 / 600 |
| exercises with an unverifiable quantity shown | 3 / 25 | 1 / 25 | 0 / 25 | 0 / 25 | 0 / 25 |
| regenerations | 12 | 8 | 20 | 3 | 7 |

- Reading of §9 (fixed before the run): 14 is in the row "14 to 18". Against Sonnet + scope: 11 both, 10 only Sonnet, 3 only the
  27B, exact McNemar p = 0.092 ≥ 0.05: no difference detected with the same instruction, gap 7 exercises (21 against 14).
- The instruction's effect on the 27B, against v1: 8 exercises pass with both, 6 only with the instruction, 6 only without it,
  exact McNemar p = 1.0: no effect on the exercises passed; turns CORRECT 587 against 583, unverifiable quantity shown 0 against 3,
  regenerations 7 against 12. 10 of the 11 exercises the 27B + scope fails, it fails on one seed of three.

## 2026-10-23: grammar arm (gate v3) declared, before any run

- `bench/GRAMMAR_ARM.md` (binding from the commit that adds it) declares one exploratory configuration, `v3`: gate v2 with its one
  regeneration sampled under a GBNF grammar built per turn (`gate_v3.py`). Digits are allowed only inside a reference that resolves, a
  closed label or a number the user typed; no unit may follow a reference. Development tier only, 25 exercises, seeds 1, 2, 3, the 27B
  Q2_0 on upstream llama.cpp b11700 (23f7aabc1), the `caladrius-mcp` of the stored runs (sha256 `e38211b5ce30...`, built from caladrius
  f119618 and never rebuilt). v1 and v2 are read from `bench/runs/decision`, not rerun. No run has been made and no llama-server started.
- Declared before the run command exists (§4). Success: 0 free digits shown, an unverifiable quantity shown in at most 3 / 25 exercises,
  at least 576 / 600 turns CORRECT, at most 50 regenerations, median at most 9 s per turn. Kill: fewer than 562 / 600 turns CORRECT,
  median above 13.5 s per turn, LOOP + ABSTAINED above 2 % of the turns (more than 12), or a server that does not enforce the grammar
  (an error that mentions the grammar, or one regeneration whose text breaks the grammar it was sent). Baselines: v1 583 / 600, 14 / 25
  exercises passed, 3 / 25 unverifiable shown, 12 regenerations, 4.5 s; v2 562 / 600, 6 / 25, 17 / 25, 188 regenerations, 6.85 s.
- Reading (§5): the four effects without the 50-regeneration bound are read as "the grammar does what it is for, the regeneration count
  is unchanged", not as success. The first drafts are not under the grammar, so I expect regenerations of the order of v2's 188.
- Offline, no GPU (§7): the grammar accepts 541 of the 564 final answers gate v2 passed and refuses 184 of the 188 first drafts that had
  findings, touching 646 of their 651 findings; the 5 it cannot see are spelled-out numbers. llama.cpp b11700's own sampler (llama.dll,
  vocabulary only) agrees with `gate_v3.Machine` on 13,644 texts, 0 disagreements. What no offline check reaches is the HTTP path of the
  server; the first run checks it through the `conformance` field recorded for every regeneration.
- Nothing in §8, C1, C2, `NO_LM_ARM.md` or `FRONTIER_ARM.md` changes. The demo gate stays v1 whatever this arm finds.
