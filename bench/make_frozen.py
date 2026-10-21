#!/usr/bin/env python
"""Generator of the frozen test sets (FROZEN_SET.md §5.1): confirmation exercises, never development data.

Each tier has its own seed, never the development seed 20261009. The plan is itself drawn from that seed: the families in the
stratified counts of §5.1, then the dose unit, the time unit and BLQ with fixed shares, assigned independently, and the
concentration unit (ng/mL for a µg dose; mg/L or ng/mL at random for a mg dose). Each exercise then draws its parameters, its
sampling times and its noise exactly once (make_exercises.build). A draw the generator cannot use (no BLQ value when BLQ is
wanted, a number in exponent form, no half-life computable by Caladrius) is redrawn with the next attempt seed of the same
exercise and the rejection is recorded in PLAN.json (§5.1 states the half-life rule for the demo tier).

The gold is computed with the units the assistant's calls send since apothicaire PR #3 (options.units: CL in L/time, V in L;
§5.4). Every meta.json carries `frozen` (tier, tag, "confirmation only"): bench/run_bench.py refuses these folders, only
bench/run_frozen.py runs them.

  python bench/make_frozen.py --tier demo                   writes bench/frozen/demo/exercises/ and PLAN.json (needs caladrius-mcp)
  python bench/make_frozen.py --tier demo --check           regenerates in a temporary folder and compares byte for byte
  python bench/make_frozen.py --tier demo --manifest --wordings-sha256 HEX [--wording-seed N]
                                                             writes MANIFEST.json, the case freeze of §9 (hashes only)
"""
import argparse, hashlib, json, os, random, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire  # noqa: E402
from bench import make_exercises as mk  # noqa: E402

FROZEN = os.path.join(HERE, "frozen")
FAMILIES = [("iv_bolus", "pk1.iv_bolus"), ("iv_infusion", "pk1.iv_infusion"), ("oral_1", "pk1.oral_1"),
            ("oral_1_lag", "pk1.oral_1_lag"), ("oral_0", "pk1.oral_0"), ("pk2_iv_bolus", "pk2.iv_bolus"), ("pk2_oral_1", "pk2.oral_1")]
# §5.1: stratified family counts (in the order of FAMILIES) and fixed shares (at least 25 % µg doses, 25 % minutes, 20 % BLQ)
TIERS = {
    "demo": {"seed": 20261021, "prefix": "fd", "counts": [6, 6, 6, 6, 6, 5, 5], "ug": 10, "min": 10, "blq": 8,
             "tag": "frozen-set-demo"},
    "page": {"seed": None, "prefix": "fp", "counts": [9, 9, 9, 9, 8, 8, 8], "ug": 15, "min": 15, "blq": 12,
             "tag": "frozen-set-page"},           # the PAGE seed is chosen at its case freeze (§2), not before
}
MAX_ATTEMPTS = 20
# The files the case freeze hashes besides the exercises (§9): the scorer, the scripts, the mutation suite, the statistics and
# the analysis, the protocol itself, and the generator.
CASE_FILES = ["bench/score.py", "bench/scripts.py", "bench/mutations.py", "bench/stats.py", "bench/run_frozen.py",
              "bench/pknca/frozen_nca_pknca.R", "bench/pknca_check.py",
              "bench/FROZEN_SET.md", "bench/make_frozen.py", "bench/make_exercises.py", "tests/test_bench_score.py"]

def tier_dir(tier): return os.path.join(FROZEN, tier)
def exercises_dir(tier): return os.path.join(tier_dir(tier), "exercises")

def draw_plan(tier):
    """The plan rows of a tier, from its seed alone: [(family, model, dose unit, conc unit, time unit, BLQ)]."""
    t = TIERS[tier]
    if t["seed"] is None: raise SystemExit(f"tier {tier}: no seed chosen yet (FROZEN_SET.md §2)")
    rng = random.Random(t["seed"])
    fams = [f for f, c in zip(FAMILIES, t["counts"]) for _ in range(c)]
    rng.shuffle(fams)
    n = len(fams)
    pick = lambda k: set(rng.sample(range(n), k))
    ug, mins, blq = pick(t["ug"]), pick(t["min"]), pick(t["blq"])
    rows = []
    for i, (family, model) in enumerate(fams):
        dose_unit = "ug" if i in ug else "mg"
        conc = "ng/mL" if dose_unit == "ug" else rng.choice(["mg/L", "ng/mL"])
        rows.append((family, model, dose_unit, conc, "min" if i in mins else "h", i in blq))
    return rows

def exercise_seed(tier, index, attempt):
    """The seed of one draw: the tier seed, the exercise index (1..n) and the attempt (0, 1, ...), never a development seed."""
    return TIERS[tier]["seed"] * 1000 + index * 20 + attempt

def _git(*args, cwd):
    try: return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20).stdout.strip() or None
    except Exception: return None

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def engine_identity(mcp_bin):
    caladrius = os.path.join(os.path.dirname(AGENT), "caladrius")
    return {"caladrius_commit": _git("rev-parse", "HEAD", cwd=caladrius), "mcp_binary_sha256": sha256_file(mcp_bin) if os.path.exists(mcp_bin) else None}

def generate(tier, out_dir=None, mcp_bin=None, verbose=True):
    """Writes the exercises of a tier into out_dir (emptied first) and PLAN.json next to it. Returns the plan record."""
    t = TIERS[tier]; out_dir = out_dir or exercises_dir(tier)
    mcp_bin = mcp_bin or apothicaire.MCP_BIN
    rows = draw_plan(tier)
    client = mk.apothicaire.MCPClient([mcp_bin])
    if os.path.isdir(out_dir): shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    plan = {"tier": tier, "tag": t["tag"], "seed": t["seed"], "n": len(rows), "generator": "bench/make_frozen.py",
            "development_seed_excluded": mk.SEED, **engine_identity(mcp_bin), "exercises": []}
    try:
        for i, row in enumerate(rows, start=1):
            rejected = []
            for attempt in range(MAX_ATTEMPTS):
                seed = exercise_seed(tier, i, attempt)
                ex_id = f"{t['prefix']}{i:02d}_{row[0]}"
                try:
                    meta, csv = mk.build(i, client.call, row, seed=seed, ex_id=ex_id)
                    truth = mk.run_oracle(client.call, meta, csv, units=True)
                except RuntimeError as e:
                    rejected.append({"attempt": attempt, "seed": seed, "reason": str(e).split(": ", 1)[-1]}); continue
                break
            else:
                raise RuntimeError(f"{tier} exercise {i}: no usable draw in {MAX_ATTEMPTS} attempts")
            meta["ground_truth"] = {**truth, "fit_parameters": meta["simulation"]["parameters"], "units_in_nca_run": True}
            meta["frozen"] = {"tier": tier, "tag": t["tag"], "use": "confirmation only, never development (FROZEN_SET.md §8)",
                              "plan_row": list(row), "attempt": attempt}
            d = os.path.join(out_dir, meta["id"]); os.makedirs(d)
            with open(os.path.join(d, "data.csv"), "w", encoding="utf-8", newline="\n") as f: f.write(csv)
            with open(os.path.join(d, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1); f.write("\n")
            plan["exercises"].append({"id": meta["id"], "plan_row": list(row), "seed": seed, "attempt": attempt, "rejected": rejected})
            if verbose: print(f"{meta['id']}: {row[2]} dose, {row[3]}, {row[4]}, BLQ {row[5]}, attempt {attempt}", flush=True)
    finally:
        client.close()
    with open(os.path.join(os.path.dirname(out_dir), "PLAN.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1); f.write("\n")
    return plan

def _close(a, b, rel=1e-12):
    """True when two meta.json files differ only in the last digits of floats (engines built on other platforms or compilers
    round differently in the last bit: 184.80246263636596 against 184.802462636366)."""
    if not a.endswith(".json"): return False
    def same(x, y):
        if isinstance(x, float) and isinstance(y, (int, float)): return abs(x - y) <= rel * max(abs(x), abs(y))
        if isinstance(x, dict): return isinstance(y, dict) and x.keys() == y.keys() and all(same(x[k], y[k]) for k in x)
        if isinstance(x, list): return isinstance(y, list) and len(x) == len(y) and all(map(same, x, y))
        return x == y
    with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb: return same(json.load(fa), json.load(fb))

def check(tier, mcp_bin=None):
    """Regenerates the tier in a temporary folder and compares every file with the committed one. Returns the differing paths;
    a meta.json that differs only by float rounding in the last bit is listed without the suffix " (beyond float rounding)"."""
    tmp = tempfile.mkdtemp(prefix=f"frozen_{tier}_")
    try:
        generate(tier, os.path.join(tmp, "exercises"), mcp_bin, verbose=False)
        diffs = []
        for root in (os.path.join(tmp, "exercises"), exercises_dir(tier)):
            for d, _, files in os.walk(root):
                for fn in files:
                    rel = os.path.relpath(os.path.join(d, fn), root)
                    a, b = os.path.join(tmp, "exercises", rel), os.path.join(exercises_dir(tier), rel)
                    if not (os.path.exists(a) and os.path.exists(b)): diffs.append(rel)
                    elif sha256_file(a) != sha256_file(b): diffs.append(rel + ("" if _close(a, b) else " (beyond float rounding)"))
        return sorted(set(diffs))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def list_exercises(tier):
    return mk.list_exercises(exercises_dir(tier))

def manifest(tier, wordings_sha256=None, wording_seed=None):
    """The case-freeze manifest of §9: SHA-256 of every exercise file, of PLAN.json and of CASE_FILES, the hash of the
    wordings file (the file itself stays on Abdou's PC until the system freeze, §5.3) and the wording seed."""
    files = {}
    for d in list_exercises(tier):
        for fn in ("data.csv", "meta.json"):
            p = os.path.join(d, fn); files[os.path.relpath(p, AGENT).replace(os.sep, "/")] = sha256_file(p)
    pk = os.path.join(tier_dir(tier), "pknca")                     # the PKNCA cross-check of §5.4 (T-101), when it has run
    pk_files = [os.path.relpath(os.path.join(pk, fn), AGENT) for fn in ("pknca.csv", "pknca.json", "check.json") if os.path.exists(os.path.join(pk, fn))]
    for rel in [os.path.relpath(os.path.join(tier_dir(tier), "PLAN.json"), AGENT)] + CASE_FILES + pk_files:
        p = os.path.join(AGENT, rel); files[rel.replace(os.sep, "/")] = sha256_file(p)
    return {"tier": tier, "tag": TIERS[tier]["tag"], "stage": "case freeze", "wordings_sha256": wordings_sha256,
            "wording_seed": wording_seed, "apothicaire_commit": _git("rev-parse", "HEAD", cwd=AGENT), "files": files}

def verify_manifest(tier, wordings_path=None):
    """Mismatches between the files on disk and MANIFEST.json ([] when everything matches); None when there is no manifest yet
    (before the case freeze: no run on the frozen set is confirmatory)."""
    p = os.path.join(tier_dir(tier), "MANIFEST.json")
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: m = json.load(f)
    bad = [rel for rel, h in m["files"].items() if not os.path.exists(os.path.join(AGENT, rel)) or sha256_file(os.path.join(AGENT, rel)) != h]
    if wordings_path and m.get("wordings_sha256") and sha256_file(wordings_path) != m["wordings_sha256"]: bad.append("wordings")
    return bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="demo", choices=sorted(TIERS))
    ap.add_argument("--check", action="store_true", help="regenerate in a temporary folder and compare byte for byte")
    ap.add_argument("--manifest", action="store_true", help="write MANIFEST.json (case freeze)")
    ap.add_argument("--wordings-sha256", default=None); ap.add_argument("--wording-seed", type=int, default=None)
    a = ap.parse_args()
    if a.check:
        diffs = check(a.tier)
        real = [d for d in diffs if d.endswith("(beyond float rounding)")]
        print("identical" if not diffs else f"DIFFERENT: {', '.join(diffs)}" if real else
              f"identical up to float rounding in the last bit ({len(diffs)} files): the hashes of the case freeze are the committed files'")
        sys.exit(1 if real else 0)
    if a.manifest:
        if not a.wordings_sha256 or a.wording_seed is None: raise SystemExit("--manifest needs --wordings-sha256 and --wording-seed")
        m = manifest(a.tier, a.wordings_sha256, a.wording_seed)
        with open(os.path.join(tier_dir(a.tier), "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(m, f, ensure_ascii=False, indent=1); f.write("\n")
        print(f"MANIFEST.json: {len(m['files'])} files hashed"); return
    plan = generate(a.tier)
    print(f"wrote {plan['n']} exercises of tier {a.tier} (seed {plan['seed']}), "
          f"{sum(len(e['rejected']) for e in plan['exercises'])} draws rejected and redrawn")

if __name__ == "__main__":
    main()
