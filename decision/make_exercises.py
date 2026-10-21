#!/usr/bin/env python
"""More synthetic exercises for the decision-model dataset: the generator of bench/make_exercises.py, run with new seeds.

  python decision/make_exercises.py [out_dir]       (default decision/exercises/; needs caladrius-mcp built, see apothicaire.MCP_BIN)

Same PLAN (25 exercises per seed: families, units, BLQ), same simulation, same noise model, same oracle (data_import + nca_run on the
written CSV) as the benchmark; only the seed differs, so nothing under bench/ is touched. Three seeds give 75 new exercises, named
`s<k>_ex<NN>_<family>`. A plan row whose draw the oracle rejects (no half-life, no BLQ value produced) is redrawn with the next
attempt number, so each seed still yields 25 exercises. Deterministic: same seeds, same engine => byte-identical files.
"""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire  # noqa: E402
from bench import make_exercises as mk  # noqa: E402

SEEDS = (31415926, 27182818, 16180339)     # the benchmark uses 20261009
OUT = os.path.join(HERE, "exercises")
ATTEMPTS = 6

def generate(out_dir=OUT, seeds=SEEDS, mcp_bin=None):
    """Writes len(seeds) * 25 exercises into out_dir (emptied first). Returns the ids."""
    client = apothicaire.MCPClient([mcp_bin or apothicaire.MCP_BIN])
    if os.path.isdir(out_dir): shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    ids, bench_seed = [], mk.SEED
    try:
        for k, seed in enumerate(seeds, start=1):
            mk.SEED = seed
            for i, row in enumerate(mk.PLAN, start=1):
                for attempt in range(ATTEMPTS):
                    try:
                        meta, csv = mk.build(i + 100 * attempt, client.call, row)
                        meta["id"] = f"s{k}_ex{i:02d}_{meta['family']}"; meta["index"] = i
                        meta["seed"] = seed; meta["attempt"] = attempt
                        truth = mk.run_oracle(client.call, meta, csv, units=False)   # the harness's convention: dose amount alone
                        break
                    except RuntimeError as e:
                        print(f"seed {seed} plan row {i} attempt {attempt}: {e}", file=sys.stderr)
                else:
                    raise RuntimeError(f"seed {seed} plan row {i}: {ATTEMPTS} attempts failed")
                meta["ground_truth"] = {**truth, "fit_parameters": meta["simulation"]["parameters"]}
                d = os.path.join(out_dir, meta["id"]); os.makedirs(d)
                with open(os.path.join(d, "data.csv"), "w", encoding="utf-8", newline="\n") as f: f.write(csv)
                with open(os.path.join(d, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1); f.write("\n")
                ids.append(meta["id"])
    finally:
        mk.SEED = bench_seed
        client.close()
    return ids

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUT
    print(f"wrote {len(generate(out))} exercises to {out}")
