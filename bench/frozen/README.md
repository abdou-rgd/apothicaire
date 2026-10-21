# Frozen test sets

This folder holds confirmation exercises: synthetic NCA (non-compartmental analysis) problems that the system is measured on once, after it stops changing. They are never development data. Nothing here is tuned on, and nothing here is read to write a prompt. The rules come from [`../FROZEN_SET.md`](../FROZEN_SET.md); this page says where the files are and how to run them.

## Layout

| Path | What it is | Written by |
|---|---|---|
| `demo/exercises/fdNN_<family>/` | 40 exercises (`data.csv`, `meta.json` with the gold and a `frozen` tag) | `bench/make_frozen.py`, tier seed 20261021 |
| `demo/PLAN.json` | the drawn plan, the seed of every exercise, any redrawn attempt, the engine commit and binary hash | `bench/make_frozen.py` |
| `demo/pknca/` | the PKNCA recomputation of the gold and its comparison (`CHECK.md`) | `bench/pknca/frozen_nca_pknca.R`, `bench/pknca_check.py` |
| `demo/MANIFEST.json` | SHA-256 of every case file, the wordings hash and the wording seed (case freeze, §9) | `bench/make_frozen.py --manifest` |
| `demo/wordings.json` | the questions, committed only at the system freeze (§5.3) | Abdou and dsh |
| `demo/runs/<gate>/seed-<s>/` | one JSON per exercise, `report.md`, `run.json` | `bench/run_frozen.py run` |
| `demo/runs/ANALYSIS.md` | the analysis of §11 | `bench/run_frozen.py analyse` |
| `LEDGER.md` | dated deviations and the gate decision of §8 | by hand |

The plan is stratified by family (6, 6, 6, 6, 6, 5, 5 over the seven families), with 10 of 40 doses in µg, 10 of 40 time courses in minutes and 8 of 40 with values below the limit of quantification. Each exercise draws its own parameters, sampling times and noise once. The gold is computed with the units the assistant's client sends (`options.units`: CL in L/time, V in L).

`bench/run_bench.py` refuses these folders. Only `bench/run_frozen.py` runs them.

## Wordings file

The questions of a frozen run are not the development questions of `bench/scripts.py`. They come from `wordings.json`, written by people who do not tune the system. Claude writes none of them and does not open the file before the system freeze.

```json
{
  "wordings": {
    "import_nca": [ {"text": "...", "author": "abdou", "lang": "fr"}, ... ],
    "cmax_tmax": [ ... ],
    "clearance_volume": [ ... ],
    "half_life": [ ... ],
    "lambda_z_regression": [ ... ],
    "recall": [ ... ],
    "compare": [ ... ],
    "not_available": [ ... ]
  }
}
```

Each of the 8 kinds needs at least 3 wordings. A wording is a template: the runner fills the placeholders below from the exercise, in the wording's language (`fr` or `en`). The expected answer never depends on the wording; it is built from the gold first, then the question is replaced.

| Kind | Placeholders allowed | Required | Must also say |
|---|---|---|---|
| `import_nca` | `{table}` `{dose}` `{route}` `{blq_note}` `{param_list}` `{time_unit}` `{conc_unit}` `{cl_name}` `{vz_name}` | `{table}` `{dose}` `{route}` `{blq_note}` `{param_list}` | the linear method (linéaire, linear, trapèzes) |
| `cmax_tmax` | `{cmax_params}` | `{cmax_params}` | |
| `clearance_volume` | `{cl_name}` `{vz_name}` | both | |
| `half_life` | none | | whether it is acceptable (accept…) |
| `lambda_z_regression` | none | | |
| `recall` | none | | |
| `compare` | none | | lin-up/log-down (log-down) |
| `not_available` | `{missing_param}` | `{missing_param}` | |

`{blq_note}` is empty when the exercise has no value below the limit; `{cmax_params}` names C0 too for an intravenous bolus; `{missing_param}` is C0 for an oral exercise and Tlag otherwise. Each exercise gets one wording per kind by a seeded draw (`scripts.wording_choice`), the same on every machine.

Check a file without running anything:

```bash
python -c "import json, sys; sys.path.insert(0, '.'); from bench import scripts; print(scripts.validate_wordings(json.load(open(sys.argv[1], encoding='utf-8'))) or 'ok')" path/to/wordings.json
```

## Commands

Run them from the repository root.

```bash
# regenerate the 40 exercises in a temporary folder and compare byte for byte (needs caladrius-mcp)
python bench/make_frozen.py --tier demo --check

# case freeze: hash the case files, the wordings file and the wording seed
python bench/make_frozen.py --tier demo --manifest --wordings-sha256 <sha256 of wordings.json> --wording-seed <N>

# development set, both gates, seeds 1 to 3: the gate decision of §8 (llama-server running)
python bench/run_frozen.py run --tier dev --gate v1 --seeds 1,2,3
python bench/run_frozen.py run --tier dev --gate v2 --seeds 1,2,3
python bench/run_frozen.py analyse --tier dev

# frozen runs: C1 first, every seed, then C2; then the replay check of §10.1 and the analysis
python bench/run_frozen.py run --tier demo --gate <C1> --seeds 1,2,3 --wordings <path> --wording-seed <N>
python bench/run_frozen.py run --tier demo --gate <C2> --seeds 1,2,3 --wordings <path> --wording-seed <N>
python bench/run_frozen.py replay --tier demo --gate <C1> --seed 1 --ids <two exercise ids> --wordings <path> --wording-seed <N>
python bench/run_frozen.py analyse --tier demo --c1 <C1> --c2 <C2>
```

The decider-only arm (no language model: the D-01 decision model, the deterministic harness and Caladrius) runs under the configuration name `nolm`, after C1 and C2; its protocol, thresholds and PC commands are in [`../NO_LM_ARM.md`](../NO_LM_ARM.md).

A frozen run stops before its first exercise if `MANIFEST.json` exists and any hashed file differs. Without a manifest it runs, and every output says it is not confirmatory. `--resume` skips the exercises already written, after a power cut for instance (§10.3 says when a restart is allowed).

## Dry run without a model

`--stub` replaces llama-server with `bench/stub_model.py`, a scripted stand-in that calls the tools a correct assistant calls and answers from the gold. The real client, the real engine, both gates, the rubric, the reports and the analysis run around it, so the whole pipeline can be checked in a container without a GPU.

```bash
python bench/run_frozen.py run --tier demo --gate v1 --seeds 1,2,3 --stub --stub-error-rate 0.03 --out /tmp/dry
python bench/run_frozen.py run --tier demo --gate v2 --seeds 1,2,3 --stub --stub-error-rate 0.03 --out /tmp/dry
python bench/run_frozen.py analyse --tier demo --out /tmp/dry
```

With `--stub-error-rate` the stub errs on purpose (a value times 1.37 under gate v1, the wrong parameter under gate v2), so the statistics see mixed outcomes. A stub run says nothing about a model and is never confirmatory.

## Limits

First, the exercises are new draws of the same generator as the development set: they test the system on unseen data and unseen wordings, not on new clinical workflows or real data. Second, the gold is the engine's own output; PKNCA recomputes it independently and agrees on 3770 of 3770 values ([`../pknca/README.md`](../pknca/README.md)), which checks the engine on these exercises but not where both tools could share a mistake. Third, 40 exercises bound a failure rate at 7.2 % at best (no failure, one-sided 95 %), so a small difference between the two gates cannot be seen here, and the paired comparison stays descriptive in this tier.
