# PKNCA cross-check of the frozen gold

The gold of a frozen exercise is what Caladrius computes. That is fair for a benchmark of the assistant (it measures how faithfully the assistant relays the engine), but it leaves one question open: is the engine's answer right on these exercises? This folder answers it outside the engine, with PKNCA, an R package that Caladrius does not share code with.

## What runs

| Step | File | Output |
|---|---|---|
| NCA of every frozen exercise, both AUC methods | `frozen_nca_pknca.R` (R, PKNCA 0.12.1) | `bench/frozen/<tier>/pknca/pknca.csv`, `pknca.json` |
| Comparison with the gold of each `meta.json` | `../pknca_check.py` | `CHECK.md`, `check.json` beside it |

The R script reuses the choices of Caladrius's public NCA oracle (`caladrius/oracle/scripts/nca_pknca.R`): the same PKNCA version, every option set explicitly, the same handling of IV bolus data without a sample at the dose time (C0 back-extrapolated and added at t = 0, kept out of the terminal phase). Two steps are specific to the frozen exercises. First, the dose is converted to the mass unit of the concentration before PKNCA sees it, so CL comes out in L/time and V in L, as in the gold computed with `options.units`; dose-normalised values are converted back. Second, values below the limit of quantification are written as 0 in the CSV and go through PKNCA's default rule (first kept, middle dropped, last kept), which is also the engine's default.

The comparison uses the tolerance of Caladrius's conformance tests against PKNCA: relative 1e-6, absolute 1e-12 at an expected zero. Each gold value ends in one of four classes: agree, differ, gold only (PKNCA returned nothing), PKNCA only (PKNCA computed a value that Caladrius reported as not calculated).

## Result, demo tier (2026-10-21)

| | values |
|---|---|
| computed by both, within tolerance | 3770 / 3770 |
| beyond tolerance | 0 |
| gold only | 0 |
| PKNCA only | 0 |
| largest relative gap | 1.2e-13 (fd38_pk2_oral_1, lin-up/log-down, AUMCall) |

40 exercises, two AUC methods, 46 parameters per extravascular profile, 48 per infusion and 49 per IV bolus. Run in the cloud container with R 4.3.3; the caladrius oracle was produced with R 4.5.2, and PKNCA is the same version in both. Full table: [`../frozen/demo/pknca/CHECK.md`](../frozen/demo/pknca/CHECK.md).

## How it feeds the freeze

1. The check runs on the generated exercises before the case freeze (FROZEN_SET.md §5.4).
2. A value beyond tolerance is a ledger entry (`bench/frozen/LEDGER.md`). The exercise is replaced before the freeze, never after, and the engine question goes to the Caladrius board.
3. `pknca.csv`, `pknca.json` and `check.json` are hashed in `MANIFEST.json` with the exercises (`make_frozen.py --manifest` adds them when they exist), so the gold that the rubric scores against is the gold that PKNCA checked.
4. The tag `frozen-set-<tier>` is set later, at the system freeze; nothing in this folder changes after the case freeze.

The protocol asked for this check in the PAGE tier only. It costs a few seconds, so the demo tier has it too.

## Run it again

```bash
# once: R 4.3 or later, then in R
install.packages(c("PKNCA", "jsonlite"))           # PKNCA 0.12.1 is the current CRAN version as of 2026-10-21

# from the repository root
Rscript bench/pknca/frozen_nca_pknca.R bench/frozen/demo/exercises bench/frozen/demo/pknca/pknca.csv
python bench/pknca_check.py --tier demo            # exit code 1 if any value differs
```

On Windows, `Rscript` must be on the PATH (or called by its full path under `C:\Program Files\R\R-4.x.x\bin`).

## Limits

First, PKNCA and Caladrius agree here because Caladrius was built to match PKNCA on these rules: the check shows that the frozen exercises stay inside the behaviour the conformance suite covers, not that both are right where both could be wrong. Second, the IV bolus C0 step mirrors the oracle's own preprocessing, so a shared misreading of that step would not show. Third, the check covers the NCA values only, not the acceptability verdict or the wording of the gold.
