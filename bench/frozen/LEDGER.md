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
