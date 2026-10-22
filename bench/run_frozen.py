#!/usr/bin/env python
"""Runner and analysis of the frozen sets and of the demo-gate decision (FROZEN_SET.md §6.3, §8, §10, §11; T-099, T-100).

One run = one tier x one gate x one sampling seed, every exercise of the tier, 8 turns each, scored with the rubric of §6.2.
The records are written per exercise as run_bench writes them, with the gate and the seed:

  <base>/<gate>/seed-<s>/<id>.json, report.md, report.json, run.json
  <base>/ANALYSIS.md, analysis.json          (python bench/run_frozen.py analyse)

<base> is bench/frozen/<tier>/runs for a frozen tier and bench/runs/decision for the development set (tier `dev`, the
demo-gate decision of §8). The analysis takes the exercise as the unit: an exercise passes when its 8 turns are CORRECT on
every seed (§6.3, the strict endpoint); pass^k (stats.pass_k_curve) is printed next to the per-turn rate so the gap between
"right once" and "right every time" is visible.

  python bench/run_frozen.py run --tier dev  --gate v1 --seeds 1,2,3                     development set (decision of §8)
  python bench/run_frozen.py run --tier demo --gate v1 --seeds 1,2,3 --wordings PATH      a frozen tier (wordings required)
  python bench/run_frozen.py run --tier demo --gate v1 --seeds 1,2 --stub --out DIR       dry run without a model (cloud)
  python bench/run_frozen.py replay --tier demo --gate v1 --seed 1 --ids fd01_oral_1,fd02_oral_0   replay check of §10.1
  python bench/run_frozen.py analyse --tier demo --c1 v1 --c2 v2 [--out DIR]
  python bench/run_frozen.py run --tier demo --gate nolm --seeds 1,2,3 --wordings PATH --wording-seed N --decider-model DIR
                                                    the decider-only arm, no language model (bench/decider_arm.py, NO_LM_ARM.md)
  python bench/run_frozen.py run --tier dev --gate v1 --seeds 1,2,3 --api-model claude-sonnet-5-5 --out DIR
                                                    the frontier API arm: the same agent on a hosted model (bench/api_model.py,
                                                    FRONTIER_ARM.md), stored as configuration v1+claude-sonnet-5-5
  python bench/run_frozen.py analyse --tier dev --out DIR --with bench/runs/decision:v1 --c1 v1 --c2 v1+claude-sonnet-5-5
                                                    an analysis that reads configurations of another run folder too

The frozen runs refuse to start when MANIFEST.json exists and a hashed file differs (§9, T-082); without a manifest
(before the case freeze) they run and every output says "not confirmatory". A stub run is never confirmatory.
"""
import argparse, datetime, json, os, shutil, statistics, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire, optchat  # noqa: E402,F401  (apothicaire puts optchat on the path)
from bench import make_exercises as mk, make_frozen as mf, run_bench as rb, score, scripts, stats  # noqa: E402
from bench import api_model as api_model_mod, decider_arm  # noqa: E402

DEV_BASE = os.path.join(HERE, "runs", "decision")
SAMPLING = "temperature 0.3, thinking off"

def base_dir(tier): return DEV_BASE if tier == "dev" else os.path.join(mf.tier_dir(tier), "runs")
def tier_exercises(tier): return mk.list_exercises() if tier == "dev" else mf.list_exercises(tier)
def run_dir(base, gate, seed): return os.path.join(base, gate, f"seed-{seed}")
def config_name(gate, api_model=None, api_addendum=None):
    return "+".join([gate] + ([api_model] if api_model else []) + ([api_addendum] if api_addendum else []))
def gate_of(config): return config.split("+")[0]           # v1+claude-sonnet-5-5: the agent with gate v1 on that hosted model

def load_wordings(path):
    """The wordings file of §5.3, validated (scripts.validate_wordings), with its SHA-256."""
    with open(path, encoding="utf-8") as f: w = json.load(f)
    errs = scripts.validate_wordings(w)
    if errs: raise SystemExit("wordings rejected:\n  " + "\n  ".join(errs))
    return w, mf.sha256_file(path)

def preflight(tier, wordings_path, stub, gate=None):
    """(confirmatory, notes): refuses a frozen run whose hashed files differ from MANIFEST.json (§9)."""
    if tier == "dev": return False, ["development set: in-sample, never confirmatory (§8)"]
    notes = []
    bad = mf.verify_manifest(tier, wordings_path)
    if bad: raise SystemExit(f"MANIFEST.json mismatch, the run does not start (§9): {', '.join(bad)}")
    if bad is None: notes.append("no MANIFEST.json yet (before the case freeze): not confirmatory")
    if stub and gate == decider_arm.ARM: notes.append("stub decider (bench/decider_arm.py, gold decisions): the harness ceiling, says nothing about a model")
    elif stub: notes.append("stub model (bench/stub_model.py): a dry run of the pipeline, says nothing about a model")
    if wordings_path is None: notes.append("development wordings of scripts.py instead of wordings.json: not confirmatory")
    return not notes, notes

def exercise_script(meta, csv_text, wordings, wording_seed):
    script = scripts.build_script(meta, csv_text)
    return scripts.apply_wordings(script, meta, csv_text, wordings, wording_seed) if wordings else script

def run_one(ex_dir, out, gate, seed, wordings=None, wording_seed=0, stub=None, cfg_base=None, verbose=False, llm=None, addendum=None):
    """One exercise on one seed: run_bench.run_exercise with the frozen script; a failure of the whole exercise (the agent or
    the engine did not start) is a record whose 8 turns are ERROR, so it stays in every denominator (§6.1). `llm`: a model
    client standing in for llama-server (api_model.AnthropicLLM, the frontier API arm); `addendum`: the 27B's prompt addendum
    (FRONTIER_ARM.md §9)."""
    meta, csv_text = mk.load(ex_dir)
    script = exercise_script(meta, csv_text, wordings, wording_seed)
    kw = {"llm": llm} if llm is not None else {"prompt_addendum": addendum} if addendum else {}
    if stub is not None:
        stub.begin(meta, csv_text); kw = {"llm": stub, "on_turn": stub.on_turn}
    try:
        return rb.run_exercise(ex_dir, out, cfg_base=cfg_base, verbose=verbose, script=script, seed=seed, gate_version=gate,
                               allow_frozen=True, **kw)
    except Exception as e:
        rec = rb.planned_error_record(meta, script, f"{type(e).__name__}: {e}")
        rec.update(gate=gate, seed=seed)
        with open(os.path.join(out, meta["id"] + ".json"), "w", encoding="utf-8") as f: json.dump(rec, f, ensure_ascii=False, indent=1)
        return rec

def run(tier, gate, seeds, wordings_path=None, wording_seed=None, ids=None, resume=False, stub=False, stub_error_rate=0.0,
        base=None, verbose=False, out=print, decider="decider_unsloth:decide", decider_model=None, api_model=None, api_thinking=None,
        api_effort=None, api_client=None, api_addendum=None):
    """Runs every exercise of the tier with one gate, seed after seed (C1 first, all seeds, then C2: §10.2). Returns the base.
    gate `nolm` is the decider-only arm (bench/decider_arm.py): `decider` (module:function) and `decider_model` (its folder) pick the
    decision model, `stub` the gold decisions. `api_model` runs the agent on a hosted model instead of llama-server (the frontier
    API arm, FRONTIER_ARM.md), stored as configuration <gate>+<api_model> with its token use and cost in api_usage.json;
    `api_client` replaces the Anthropic client (tests)."""
    if tier != "dev" and wordings_path is None and not stub:
        raise SystemExit("a frozen tier runs with its wordings (--wordings PATH, FROZEN_SET.md §5.3); --stub for a dry run")
    confirmatory, notes = preflight(tier, wordings_path, stub, gate)
    nolm = gate == decider_arm.ARM
    if api_model and (nolm or stub): raise SystemExit("--api-model runs the agent itself: not with --gate nolm or --stub")
    if api_addendum and (nolm or stub): raise SystemExit("--api-addendum goes to a model's prompt: not with --gate nolm or --stub")
    if api_addendum and api_addendum not in api_model_mod.ADDENDA: raise SystemExit(f"unknown prompt addendum {api_addendum!r}")
    api = lambda: api_model and api_model_mod.AnthropicLLM(api_model, api_thinking, api_effort, client=api_client, addendum=api_addendum)
    llm = api()
    config = config_name(gate, api_model, api_addendum)
    decide = None
    if nolm: decide = decider_arm.StubDecider() if stub else decider_arm.load_decider(decider, decider_model)
    wordings, w_sha = load_wordings(wordings_path) if wordings_path else (None, None)
    if wordings and wording_seed is None: raise SystemExit("--wording-seed is required with --wordings (recorded in the manifest)")
    base = base or base_dir(tier)
    dirs = [d for d in tier_exercises(tier) if not ids or os.path.basename(d) in ids]
    cfg = dict(optchat.CFG, raw_max=1000, raw_max_chars=10 ** 9) if stub else None     # the stub has no compaction to do
    label = ("stub model (bench/stub_model.py), no language model" if stub and not nolm else
             f"decision harness (decision/harness.py), decider {getattr(decide, 'name', decider)}, no language model" if nolm else
             llm.label() if llm else f"{rb.model_label()}, {SAMPLING}" + (f", prompt addendum {api_addendum}" if api_addendum else ""))
    for seed in seeds:
        rd = run_dir(base, config, seed); os.makedirs(rd, exist_ok=True)
        if llm and seed != seeds[0]: llm = api()                     # one client per seed: its usage is the seed's
        info = {"tier": tier, "gate": gate, "config": config, "seed": seed, "model": label,
                "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "wordings_sha256": w_sha, "wording_seed": wording_seed, "confirmatory": confirmatory, "notes": notes,
                "apothicaire_commit": mf._git("rev-parse", "HEAD", cwd=AGENT), "exercises": [os.path.basename(d) for d in dirs]}
        if llm: info["api"] = llm.config()
        elif api_addendum: info["prompt_addendum"] = {"name": api_addendum, "text": api_model_mod.ADDENDA[api_addendum]}
        with open(os.path.join(rd, "run.json"), "w", encoding="utf-8") as f: json.dump(info, f, ensure_ascii=False, indent=1)
        for d in dirs:
            i = os.path.basename(d)
            if resume and os.path.exists(os.path.join(rd, i + ".json")): out(f"skip {config} seed {seed} {i}"); continue
            t0 = time.time()
            if nolm:
                script = exercise_script(*mk.load(d), wordings, wording_seed)
                r = decider_arm.run_one(d, rd, seed, script, decide, decide if stub else None)
                oc = [t.get("outcome", "ERROR") for t in r["turns"]]
                out(f"{gate} seed {seed} {i}: {oc.count('CORRECT')}/{len(oc)} CORRECT, {time.time() - t0:.0f} s"); continue
            model = None
            if stub:
                from bench.stub_model import StubModel
                model = StubModel(gate, seed, stub_error_rate)
            r = run_one(d, rd, gate, seed, wordings, wording_seed, model, cfg, verbose, llm=llm or None, addendum=None if llm else api_addendum)
            oc = [t.get("outcome", "ERROR") for t in r["turns"]]
            out(f"{config} seed {seed} {i}: {oc.count('CORRECT')}/{len(oc)} CORRECT, {time.time() - t0:.0f} s"
                + (f", {llm.usage['cost_usd']:.2f} USD so far this seed" if llm else ""))
        meta = {"date": info["started"][:10], "exercises_run": len(dirs), "model": label, "gate": gate}
        rb.write_report(rd, rb.load_records(rd, info["exercises"]), meta)
        if llm:
            with open(os.path.join(rd, "api_usage.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump({**llm.config(), **llm.usage, "refusals": llm.refusals}, f, ensure_ascii=False, indent=1); f.write("\n")
            out(f"{config} seed {seed}: {llm.usage['calls']} calls, {llm.usage['cost_usd']:.2f} USD, {len(llm.refusals)} refusals")
    if nolm and hasattr(decide, "summary"):
        with open(os.path.join(base, gate, "decider_summary.json"), "w", encoding="utf-8") as f: json.dump(decide.summary(), f, indent=1)
    return base

# ---------------------------------------------------------------- analysis (§11)
NOT_RECORDS = ("report.json", "run.json", "api_usage.json")

def _load(path):
    with open(path, encoding="utf-8") as f: return json.load(f)

def load_runs(base, gates=None):
    """{gate: {seed: {id: record}}} for every run folder under base."""
    out = {}
    for g in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if gates and g not in gates or not os.path.isdir(os.path.join(base, g)): continue
        for s in sorted(os.listdir(os.path.join(base, g))):
            if not s.startswith("seed-"): continue
            rd = os.path.join(base, g, s)
            recs = {fn[:-5]: _load(os.path.join(rd, fn))
                    for fn in sorted(os.listdir(rd)) if fn.endswith(".json") and fn not in NOT_RECORDS}
            if recs: out.setdefault(g, {})[int(s[5:])] = recs
    return out

def _correct(t): return t.get("outcome") == "CORRECT"
def _passes(rec): return bool(rec["turns"]) and all(_correct(t) for t in rec["turns"])
def _shown_unverified(rec): return any(t.get("numbers_unverified_after") for t in rec["turns"] if "error" not in t)

def config_section(runs_g, ids):
    """The endpoints of §11.1 and §11.2 for one configuration (one gate, all its seeds). An exercise missing on a seed fails
    it (no exclusion, §10.4)."""
    seeds = sorted(runs_g)
    per = {}
    for i in ids:
        recs = [runs_g[s].get(i) for s in seeds]
        per[i] = {"seeds_passed": sum(1 for r in recs if r and _passes(r)), "missing_seeds": [s for s, r in zip(seeds, recs) if r is None],
                  "turns_correct": sum(sum(1 for t in r["turns"] if _correct(t)) for r in recs if r),
                  "turns": sum(8 if r is None else len(r["turns"]) for r in recs),
                  "unverified_shown": any(r and _shown_unverified(r) for r in recs),
                  "wrong_unflagged": sum(sum(1 for t in r["turns"] if t.get("outcome") == "WRONG" and not t.get("numbers_unverified_after"))
                                         for r in recs if r)}
    n, k = len(ids), len(seeds)
    failed = sorted(i for i in ids if per[i]["seeds_passed"] < k)
    shown = sorted(i for i in ids if per[i]["unverified_shown"])
    turns = [t for s in seeds for r in runs_g[s].values() if r["id"] in per for t in r["turns"]]
    classes = {c: sum(1 for t in turns if t.get("outcome", "ERROR") == c) for c in score.OUTCOMES}
    byk = {}
    for t in turns:
        b = byk.setdefault(t["kind"], {c: 0 for c in score.OUTCOMES}); b[t.get("outcome", "ERROR")] += 1
    walls = sorted(t["wall_s"] for t in turns if "error" not in t and t.get("wall_s") is not None)
    first = [r["turns"][0]["prompt_tokens"] for s in seeds for r in runs_g[s].values() if r["turns"] and "prompt_tokens" in r["turns"][0]]
    audit = [r.get("tool_arg_audit") or {} for s in seeds for r in runs_g[s].values()]
    calls = [c for t in turns for c in t.get("tool_calls", [])]
    strata = {}
    for i in ids:
        r = next((runs_g[s][i] for s in seeds if i in runs_g[s]), None)
        if r is None: continue
        for name, val in (("family", r["family"]), ("dose unit", r["dose"]["unit"]), ("time unit", r["units"]["time"]),
                          ("BLQ", "yes" if r["blq"] else "no")):
            b = strata.setdefault(name, {}).setdefault(val, [0, 0]); b[1] += 1; b[0] += per[i]["seeds_passed"] == k
    pairs = [(per[i]["turns_correct"], per[i]["turns"]) for i in ids]
    checks = [(t["kind"], t["outcome"], t["decision_check"]) for t in turns if "decision_check" in t]
    decisions = {kk: {"turns": sum(1 for k2, _, _ in checks if k2 == kk),
                      "decisions_all_right": sum(1 for k2, _, c in checks if k2 == kk and c["asks"] == c["asks_right"]),
                      "failed_with_right_decisions": sum(1 for k2, o, c in checks if k2 == kk and o != "CORRECT" and c["asks"] == c["asks_right"]),
                      "questions_wrong": sorted({w["question"] for k2, _, c in checks if k2 == kk for w in c["wrong"]})}
                 for kk in scripts.KINDS if any(k2 == kk for k2, _, _ in checks)}
    return {
        "seeds": seeds, "exercises": n,
        "failed": stats.failure_interval(len(failed), n), "failed_ids": failed,
        "unverified_shown": stats.failure_interval(len(shown), n), "unverified_shown_ids": shown,
        "pass_k": stats.pass_k_curve([per[i]["seeds_passed"] for i in ids], k) if n and k else {},
        "turns_correct": sum(p[0] for p in pairs), "turns": sum(p[1] for p in pairs),
        "turn_rate_ci": stats.cluster_bootstrap(pairs),
        "mixed_across_seeds": sorted(i for i in ids if 0 < per[i]["seeds_passed"] < k),
        "outcomes": classes, "outcomes_by_kind": {kk: byk[kk] for kk in scripts.KINDS if kk in byk},
        "wrong_unflagged": {i: per[i]["wrong_unflagged"] for i in ids if per[i]["wrong_unflagged"]},
        "tool_calls": len(calls), "tool_calls_not_valid": sum(1 for c in calls if c.get("status") != "valid"),
        "tool_arg_deviating_calls": sum(a.get("deviating_calls", 0) for a in audit), "tool_arg_audited_calls": sum(a.get("calls", 0) for a in audit),
        "regenerations": sum(1 for t in turns if t.get("regenerated")),
        "wall_s_median": statistics.median(walls) if walls else None,
        "wall_s_p95": walls[min(len(walls) - 1, int(0.95 * len(walls)))] if walls else None,
        "first_prompt_tokens_median": statistics.median(first) if first else None,
        "strata": strata, "per_exercise": per, "decisions": decisions}

def paired_section(c1, c2, ids):
    """§11.3: exact McNemar on the strict exercise outcomes, mean d with a paired bootstrap, sign-flip test, over the
    exercises and seeds both configurations ran."""
    k1, k2 = len(c1["seeds"]), len(c2["seeds"])
    p1 = {i: c1["per_exercise"][i]["seeds_passed"] == k1 for i in ids}
    p2 = {i: c2["per_exercise"][i]["seeds_passed"] == k2 for i in ids}
    b = sorted(i for i in ids if p1[i] and not p2[i]); c = sorted(i for i in ids if p2[i] and not p1[i])
    d = [c2["per_exercise"][i]["turns_correct"] / c2["per_exercise"][i]["turns"] - c1["per_exercise"][i]["turns_correct"] / c1["per_exercise"][i]["turns"]
         for i in ids]
    return {"only_c1_passes": b, "only_c2_passes": c, "both_pass": sum(1 for i in ids if p1[i] and p2[i]),
            "neither_passes": sum(1 for i in ids if not p1[i] and not p2[i]), "mcnemar_p": stats.mcnemar_exact(len(b), len(c)),
            "mean_d": sum(d) / len(d) if d else None, "mean_d_ci": stats.paired_bootstrap_mean(d), "sign_flip_p": stats.sign_flip_test(d),
            "same_seeds": c1["seeds"] == c2["seeds"]}

def replay_section(base, runs):
    """§10.1: replayed exercise x seed against the original run, answers compared turn by turn."""
    out = []
    for g in sorted(runs):
        rp = os.path.join(base, g, "replay")
        if not os.path.isdir(rp): continue
        for s_dir in sorted(os.listdir(rp)):
            seed = int(s_dir[5:])
            for fn in sorted(os.listdir(os.path.join(rp, s_dir))):
                if not fn.endswith(".json") or fn in NOT_RECORDS: continue
                a = _load(os.path.join(rp, s_dir, fn))
                o = runs[g].get(seed, {}).get(a["id"])
                same = o is not None and [t.get("answer") for t in o["turns"]] == [t.get("answer") for t in a["turns"]]
                out.append({"gate": g, "seed": seed, "id": a["id"], "identical": same,
                            "turns_differing": None if o is None else [t["turn"] for t, u in zip(a["turns"], o["turns"]) if t.get("answer") != u.get("answer")]})
    return out

def analyse(tier, c1="v1", c2="v2", base=None, extra=()):
    """The analysis of §11 over the stored runs; writes ANALYSIS.md and analysis.json in base. Returns the dict. `extra`:
    (folder, [configurations]) read from another base too, without writing there (a new arm next to the stored v1 runs)."""
    base = base or base_dir(tier)
    runs = load_runs(base)
    where = {g: base for g in runs}
    for xb, gs in extra:
        xr = load_runs(xb, gs or None)
        missing = sorted(set(gs or []) - set(xr))
        if missing: raise SystemExit(f"no run of {', '.join(missing)} under {xb}")
        for g in xr:
            if g in runs: raise SystemExit(f"configuration {g} is both under {base} and under {xb}")
            runs[g], where[g] = xr[g], xb
    if not runs: raise SystemExit(f"no run under {base}")
    infos = [_load(os.path.join(where[g], g, f"seed-{s}", "run.json"))
             for g in runs for s in runs[g] if os.path.exists(os.path.join(where[g], g, f"seed-{s}", "run.json"))]
    ids = sorted({i for i in (infos[0]["exercises"] if infos else [])} | {i for g in runs for s in runs[g] for i in runs[g][s]})
    configs = {g: config_section(runs[g], ids) for g in runs}
    res = {"tier": tier, "base": os.path.relpath(base, AGENT).replace(os.sep, "/"), "rubric": score.RUBRIC_VERSION, "exercises": ids,
           "confirmatory": bool(infos) and all(x.get("confirmatory") for x in infos),
           "notes": sorted({n for x in infos for n in x.get("notes", [])}), "models": sorted({x["model"] for x in infos}),
           "c1": c1, "c2": c2, "configurations": configs, "replay": replay_section(base, runs),
           "sources": {g: os.path.relpath(where[g], AGENT).replace(os.sep, "/") for g in sorted(runs) if where[g] != base}}
    if c1 in configs and c2 in configs: res["paired"] = paired_section(configs[c1], configs[c2], ids)
    if tier == "dev" and "v1" in configs and "v2" in configs:
        p1, p2 = (configs[g]["exercises"] - configs[g]["failed"]["failed"] for g in ("v1", "v2"))
        res["demo_gate_decision"] = {"v1_exercises_passed": p1, "v2_exercises_passed": p2, "demo_gate": "v2" if p2 >= p1 else "v1",
                                     "rule": "v2 if it passes at least as many development exercises as v1 (strict rule of §6.3), ties to v2 (§8)"}
    with open(os.path.join(base, "analysis.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1); f.write("\n")
    with open(os.path.join(base, "ANALYSIS.md"), "w", encoding="utf-8", newline="\n") as f: f.write(render_md(res))
    return res

# ---------------------------------------------------------------- rendering
def _pct(x): return "n/a" if x is None else f"{100 * x:.1f} %"

def render_md(res):
    L = [f"# Frozen-set analysis: tier {res['tier']} (FROZEN_SET.md §11, rubric {res['rubric']})", ""]
    L += [f"- {'**Confirmatory.**' if res['confirmatory'] else '**Not confirmatory.**'} " + "; ".join(res["notes"] or ["case and system freeze verified"]),
          f"- exercises: {len(res['exercises'])}; model: {'; '.join(res['models']) or 'n/a'}",
          f"- C1 (confirmatory configuration) = gate {res['c1']}, C2 = gate {res['c2']} (descriptive, §8)"]
    L += [f"- {g} read from `{src}`" for g, src in res.get("sources", {}).items()] + [""]
    if "demo_gate_decision" in res:
        d = res["demo_gate_decision"]
        L += [f"## Demo-gate decision (§8): **{d['demo_gate']}**", "",
              f"v1 passes {d['v1_exercises_passed']} / {len(res['exercises'])} development exercises, v2 passes {d['v2_exercises_passed']} "
              f"(strict rule: the 8 turns CORRECT on every seed). Rule: {d['rule']}. In-sample figures.", ""]
    for g, c in sorted(res["configurations"].items(), key=lambda x: (x[0] != res["c1"], x[0])):
        role = "C1" if g == res["c1"] else "C2" if g == res["c2"] else "exploratory"
        k = len(c["seeds"])
        L += [f"## Gate {g} ({role}), seeds {', '.join(map(str, c['seeds']))}", "",
              "### Primary endpoints (§11.1)", "",
              f"1. Exercises failed (a turn not CORRECT on any seed): **{rb._interval_text(c['failed'])}**"
              + (f" ({', '.join(c['failed_ids'])})" if c["failed_ids"] else ""),
              f"2. Exercises with an unverifiable quantity shown on any seed: **{rb._interval_text(c['unverified_shown'])}**"
              + (f" ({', '.join(c['unverified_shown_ids'])})" if c["unverified_shown_ids"] else ""),
              "   " + ("Gate v1: a number that appears in no tool text and no user message, shown with its badge."
                       if gate_of(g) == "v1" else "Decider-only arm: the harness writes engine values only; gate v1 is run on its answers and "
                       "counts a number found in no tool text and no user message." if g == decider_arm.ARM
                       else "Gate v2: a quantity not resolved and typed from a structured result, shown as a marker."), "",
              "### pass^k next to the per-turn rate", "",
              "| | value |", "|---|---|",
              f"| turns CORRECT (descriptive, cluster bootstrap 95 %) | {c['turns_correct']} / {c['turns']} = {_pct(c['turns_correct'] / c['turns'] if c['turns'] else None)}"
              + (f" ({_pct(c['turn_rate_ci'][0])}-{_pct(c['turn_rate_ci'][1])})" if c["turn_rate_ci"] else "") + " |"]
        for kk, v in c["pass_k"].items():
            what = "mean pass rate over seeds" if kk == 1 else "strict rule of §6.3" if kk == k else f"{kk} seeds drawn"
            L.append(f"| pass^{kk} ({what}) | {_pct(v)} |")
        L += ["", f"pass^k = C(c, k) / C(n, k) per exercise (c seeds passed out of n), averaged over exercises. "
              f"Exercises with mixed outcomes across seeds (repeatability): {len(c['mixed_across_seeds'])}"
              + (f" ({', '.join(c['mixed_across_seeds'])})" if c["mixed_across_seeds"] else "") + ".", "",
              "### Outcomes by turn kind (§6.1, all seeds)", "",
              "| turn kind | " + " | ".join(score.OUTCOMES) + " |", "|---|" + "---|" * len(score.OUTCOMES)]
        for kk, b in c["outcomes_by_kind"].items(): L.append(f"| {kk} | " + " | ".join(str(b[x]) for x in score.OUTCOMES) + " |")
        L += ["| **total** | " + " | ".join(str(c["outcomes"][x]) for x in score.OUTCOMES) + " |", "",
              "### Other secondary endpoints (§11.2, descriptive)", "",
              f"- wrong values shown without a badge or marker (WRONG turns with nothing flagged): {sum(c['wrong_unflagged'].values())}"
              + (" (" + ", ".join(f"{i}: {v}" for i, v in c["wrong_unflagged"].items()) + ")" if c["wrong_unflagged"] else ""),
              f"- tool calls not valid: {c['tool_calls_not_valid']} / {c['tool_calls']}; calls whose arguments differ from the intent: "
              f"{c['tool_arg_deviating_calls']} / {c['tool_arg_audited_calls']}",
              f"- regenerations: {c['regenerations']}; time per turn median {c['wall_s_median']} s, 95th percentile {c['wall_s_p95']} s; "
              f"prompt tokens of the first call (median) {c['first_prompt_tokens_median']}", "",
              "| stratum | value | exercises passed |", "|---|---|---|"]
        for name, vals in c["strata"].items():
            for v, (p, n) in sorted(vals.items()): L.append(f"| {name} | {v} | {p} / {n} |")
        L.append("")
        if c.get("decisions"):
            L += ["### Decisions against the gold decisions of each turn kind (decider-only arm, NO_LM_ARM.md §6)", "",
                  "A failed turn whose decisions were all right failed in the deterministic part (reader, harness, templates), not in the "
                  "decision model.", "",
                  "| turn kind | turns | decisions all right | failed with right decisions | questions answered wrong |", "|---|---|---|---|---|"]
            for kk, b in c["decisions"].items():
                L.append(f"| {kk} | {b['turns']} | {b['decisions_all_right']} | {b['failed_with_right_decisions']} | "
                         f"{', '.join(b['questions_wrong']) or '-'} |")
            L.append("")
    if "paired" in res:
        p = res["paired"]
        L += [f"## Paired comparison C1 = {res['c1']} vs C2 = {res['c2']} (§11.3)" + (", descriptive in this tier" if res["tier"] != "page" else ""), "",
              f"- both pass {p['both_pass']}, neither {p['neither_passes']}, only C1 {len(p['only_c1_passes'])}"
              + (f" ({', '.join(p['only_c1_passes'])})" if p["only_c1_passes"] else "") + f", only C2 {len(p['only_c2_passes'])}"
              + (f" ({', '.join(p['only_c2_passes'])})" if p["only_c2_passes"] else ""),
              f"- exact McNemar on the discordant exercises: p = {p['mcnemar_p']:.3g}",
              f"- mean d (turns correct with C2 minus C1, per exercise, pooled over seeds): {p['mean_d']:+.3f}"
              + (f", paired bootstrap 95 % {p['mean_d_ci'][0]:+.3f} to {p['mean_d_ci'][1]:+.3f}" if p["mean_d_ci"] else "")
              + f"; sign-flip p = {p['sign_flip_p']:.3g}",
              "- 6 discordant exercises all in one direction are needed for p < 0.05; a non-significant result means no difference "
              "detected, not equivalence." + ("" if p["same_seeds"] else " The two configurations did not run the same seeds."), ""]
    if res["replay"]:
        L += ["## Replay check (§10.1)", ""]
        for r in res["replay"]:
            L.append(f"- gate {r['gate']} seed {r['seed']} {r['id']}: " + ("transcript identical" if r["identical"]
                     else f"answers differ on turns {r['turns_differing']}"))
        L.append("")
    return "\n".join(L)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); rp = sub.add_parser("replay"); an = sub.add_parser("analyse")
    for p in (r, rp, an):
        p.add_argument("--tier", default="demo", choices=["dev"] + sorted(mf.TIERS))
        p.add_argument("--out", default=None, help="base folder (default bench/frozen/<tier>/runs, or bench/runs/decision for dev)")
    for p in (r, rp):
        p.add_argument("--gate", required=True, choices=["v1", "v2", decider_arm.ARM],
                       help=f"v1, v2 (the 27B agent with that gate) or {decider_arm.ARM} (the decider-only arm, no language model)")
        p.add_argument("--decider", default="decider_unsloth:decide", help=f"{decider_arm.ARM}: the decision model, module:function")
        p.add_argument("--decider-model", default=None, help=f"{decider_arm.ARM}: its folder (sets $D01_MODEL; serve the adapters)")
        p.add_argument("--wordings", default=None, help="wordings.json (FROZEN_SET.md §5.3), required for a frozen tier")
        p.add_argument("--wording-seed", type=int, default=None)
        p.add_argument("--ids", default="", help="comma-separated exercise ids")
        p.add_argument("--stub", action="store_true", help="dry run with bench/stub_model.py instead of llama-server")
        p.add_argument("--stub-error-rate", type=float, default=0.0)
        p.add_argument("--verbose", action="store_true")
    r.add_argument("--seeds", default="1,2,3"); r.add_argument("--resume", action="store_true")
    rp.add_argument("--seed", type=int, required=True)
    for p in (r, rp):
        p.add_argument("--api-model", default=None, help="run the agent on this hosted model (Anthropic Messages API, key in "
                       "$APOTHICAIRE_API_KEY or $ANTHROPIC_API_KEY) instead of llama-server: the frontier API arm, FRONTIER_ARM.md")
        p.add_argument("--api-thinking", default=None, choices=["between_tools", "adaptive"], help="default: the model's row of FRONTIER_ARM.md §2")
        p.add_argument("--api-effort", default=None, choices=["low", "medium", "high", "xhigh", "max"], help="default: the model's row of FRONTIER_ARM.md §2")
        p.add_argument("--api-addendum", default=None, choices=sorted(api_model_mod.ADDENDA),
                       help="a prompt addendum (FRONTIER_ARM.md §8, §9): stored as <gate>+<model>+<name>, or <gate>+<name> on the 27B")
    an.add_argument("--c1", default="v1"); an.add_argument("--c2", default="v2")
    an.add_argument("--with", dest="with_", action="append", default=[], metavar="BASE:CONFIG[,CONFIG]",
                    help="also read these configurations from another run folder (read only), e.g. bench/runs/decision:v1")
    a = ap.parse_args(); optchat._utf8_stdout()
    base = a.out or base_dir(a.tier)
    if a.cmd == "analyse":
        extra = [(w.rsplit(":", 1)[0], [g for g in w.rsplit(":", 1)[1].split(",") if g]) if ":" in w else (w, []) for w in a.with_]
        res = analyse(a.tier, a.c1, a.c2, base, extra)
        for g, c in res["configurations"].items():
            print(f"gate {g}: failed {rb._interval_text(c['failed'])}; pass^k {', '.join(f'{k}: {_pct(v)}' for k, v in c['pass_k'].items())}")
        print("written", os.path.join(base, "ANALYSIS.md")); return
    ids = [x for x in a.ids.split(",") if x]
    if a.cmd == "replay":
        if not ids: raise SystemExit("--ids: the exercises to replay (two exercises x one seed, §10.1)")
        cfg = config_name(a.gate, a.api_model, a.api_addendum)
        tmp = os.path.join(base, cfg, "replay")
        run(a.tier, a.gate, [a.seed], a.wordings, a.wording_seed, ids, False, a.stub, a.stub_error_rate,
            base=os.path.join(base, cfg, "_replay"), verbose=a.verbose, decider=a.decider, decider_model=a.decider_model,
            api_model=a.api_model, api_thinking=a.api_thinking, api_effort=a.api_effort, api_addendum=a.api_addendum)
        src = run_dir(os.path.join(base, cfg, "_replay"), cfg, a.seed)
        dst = os.path.join(tmp, f"seed-{a.seed}")
        if os.path.exists(dst): shutil.rmtree(dst)
        shutil.move(src, dst); shutil.rmtree(os.path.join(base, cfg, "_replay"), ignore_errors=True)
        print("replayed into", dst); return
    run(a.tier, a.gate, [int(s) for s in a.seeds.split(",")], a.wordings, a.wording_seed, ids, a.resume, a.stub,
        a.stub_error_rate, base=base, verbose=a.verbose, decider=a.decider, decider_model=a.decider_model,
        api_model=a.api_model, api_thinking=a.api_thinking, api_effort=a.api_effort, api_addendum=a.api_addendum)
    print("runs under", base, "- then: python bench/run_frozen.py analyse --tier", a.tier, *(["--out", a.out] if a.out else []))

if __name__ == "__main__":
    main()
