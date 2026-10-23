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

## 2026-10-23: gold regenerated after Caladrius T-111 (the same bits on every platform)

- Cause: Caladrius main took merge 634ad58 (T-111): every platform-dependent float function of the engine (exp, ln, pow...) now goes
  through the pure-Rust `libm`, so `caladrius-mcp` gives the same bits on Linux, Windows, macOS and wasm32. The gold had been computed
  with each platform's own maths library and moved in the last bits. Merge cb327a0 (T-112, the seals under MCP `_meta`) changes
  nothing Apothicaire reads: the client takes `content` and `structuredContent` only.
- Engine: caladrius cb327a0 (main, contains 634ad58), `caladrius-mcp` built with Rust 1.99.1 on Windows 11 (x86_64-pc-windows-msvc),
  SHA-256 `2b246b5dedf3bf7554b163127917d57f1e0f96ecabf0ff5cf450f73bdbdc041c`. The gold it replaces came from caladrius da818d2 (the
  old `PLAN.json`). The binary hash of a Linux build differs; the bits of the answers do not (T-111's digest matrix), and
  `make_frozen.py --check` compares the exercise files only.
- Before: `python bench/make_frozen.py --tier demo --check` printed "identical up to float rounding in the last bit (12 files)". The
  case freeze has not happened (no `MANIFEST.json`), so the gold was still free to move; it is logged because it is a change under
  `bench/frozen/`.
- Regenerated with the committed generator and seed, no hand edit: `python bench/make_frozen.py --tier demo` (seed 20261021, same
  plan, 0 draws rejected). `--check` now prints "identical". Changed: 12 of the 40 `meta.json` and the two engine fields of
  `PLAN.json` (`caladrius_commit`, `mcp_binary_sha256`). Unchanged, byte for byte: the 40 `data.csv`, the 28 other `meta.json`, the plan,
  the seeds, the attempts, the rejected draws and the whole of `pknca/`.
- Size of the change: 226 floats move, 208 of them among the 3770 gold parameter values and the others in the selected lambda_z
  regression (R2, adjusted R2, intercept, lambda_z) and in the flags. 121 move by one ulp, 177 by at most 3, 224 by at most 8, the last two by
  12 and 25. Largest absolute change 9.5e-7 (`aumcinf.pred` of fd37_iv_bolus, a value of 6.4e9: one ulp); largest relative change 2.9e-15
  (`aucpext.obs` of fd35_oral_0, lin-up/log-down, a percentage of 3.81 made from two areas that each moved by an ulp). No integer,
  string, key or list length changes. A throwaway check (not committed) found that every changed value, here and in the development
  set, rounds to the same digits before and after (2 to 9 significant digits, half-up and half-even, and the digest's 6), so no
  verdict of `bench/score.py` can move.
- PKNCA (T-101), run again: R 4.5.2 and PKNCA 0.12.1 on this PC. The new recomputation of the 40 exercises is byte for byte the committed
  `pknca.csv` (made with R 4.3.3 in the cloud), so `pknca.csv` and `pknca.json` stay. `python bench/pknca_check.py --tier demo` against
  the regenerated gold: 3770 of 3770 within 1e-6, 0 differ, 0 gold only, 0 PKNCA only, largest relative gap 1.24e-13 (fd38_pk2_oral_1,
  lin-up/log-down, AUMCall, an exercise this change did not touch). `check.json` and `CHECK.md` are byte for byte the committed ones.
- Development set, same cause, outside `bench/frozen/`: `bench/exercises/` regenerated with `python bench/make_exercises.py` (seed 20261009).
  11 of the 25 `meta.json` change, 183 floats, at most 8 ulps (relative 9e-16); no `data.csv`. The runs in `bench/runs/` are untouched
  and keep the gold they were scored with.
- New hashes (the 28 other `meta.json`, the 40 `data.csv` and `pknca/` keep theirs):

| file (under `bench/frozen/demo/`) | SHA-256 before | SHA-256 after |
|---|---|---|
| `PLAN.json` | `0658961059b5787a3fd105ed0a2aeeab90ef9e2f5a307a9840f8efd45a5f31ba` | `1d747c13199a811bafacfe6d351bab5c1ba1618647246deb93cec0754bc1ef59` |
| `exercises/fd05_iv_infusion/meta.json` | `f119198bc0b4c25a29a23fd4364f58069614cf7a19ace829476548d145c2cc82` | `e5e0e9977e9df4e40487384afac9d28c2726e6a763010f8b8ceb255cf8368565` |
| `exercises/fd15_iv_bolus/meta.json` | `362227b2d83a87b5f6e30e9f989b1693ac4b56ef6dab8a4831bb0caa368703a0` | `a4a43ec28bf044eb588f8e09b70bb0ad6f7035b613d45b00eb9189700f4d2670` |
| `exercises/fd19_pk2_iv_bolus/meta.json` | `55db713f40c73d498d6d48ec441dfba2b0c659860aae204a9fcf3b95fb5ffec0` | `4e123bcb50e3c2563c6440e1be7033c1960eadcb53a07a6bdc6962141e23bd0d` |
| `exercises/fd20_iv_bolus/meta.json` | `1e066023ac78119cccc5e1ca34cb2157ff469951cdab005b1660df8b2ab91055` | `f0abe90fff3f23046e3fbc41553b831937142e5aa7460ace897762124284cdff` |
| `exercises/fd23_oral_1_lag/meta.json` | `3a644f75c6f93aa4e0c81358e6b77f4d91670aa92428d63571bca5ed5dedc5bb` | `bfeb7b1fe94b424f317a53ebc0ded939b03a93ee39b142c4113e07552d05d597` |
| `exercises/fd27_oral_0/meta.json` | `88c7cdd6a505cdb4bed4897a0d09b271b5332044a2a3d26a0c08593229da3fb0` | `5feb45251d926c660d665f2b3159b8fc4f244fa7f1c7e77c38e9cb0d9e2d0cdb` |
| `exercises/fd28_iv_infusion/meta.json` | `27944b96019a1568d811d1a90c54bcc7eeb6677c6274ded9e86f7ff12c632945` | `e322b57fcbfb4c7da0acce427c2a3f89c82121dd5ba26a47b8257d9e2a87850c` |
| `exercises/fd31_oral_1/meta.json` | `f7da617cceb559b8be3f5d8e9c98a51e983dabdd3d4dfeea260ee54274fc42ed` | `50aeab373d352eb1304b6955cdc51878c4fbd721d64911589ea4c37751ca3c84` |
| `exercises/fd35_oral_0/meta.json` | `5dc0ca5a57aa26a1c15b53e873808c184e8fb34ea7a4564bb0b25060b729c952` | `aa1a8c7e2f3e1e7a99e011e38884342c237467efcbd19da22a20f679b8cfd2d6` |
| `exercises/fd36_pk2_oral_1/meta.json` | `6de23abdde4ae804c9d2b26494de7617d9c0b430fdc0d52133ea0be58afe5259` | `ba8d33f5f5345f4f2c061aa38247aa56e7dbec31db1f1023962fab72e1e3b08d` |
| `exercises/fd37_iv_bolus/meta.json` | `ce3ce800870126225e3a98f3ff08b19522793df09151f22e34c712c7bc9c5996` | `fdf6b13db0a638f026e7a249954d7f6beef80b8b9a6bc87b20ffef8edc7b83ff` |
| `exercises/fd40_pk2_iv_bolus/meta.json` | `09813c580d5f2f750563c862e4c0ab97b512f0961d5c031a58fd4d5beb48c99d` | `71d655485e7ea5691c75c464aa527232170f963c84392870556a2b9407576ae9` |
