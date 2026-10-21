#!/usr/bin/env python
"""Runs the 25 benchmark exercises through the decision harness (D-01, step 4) and scores them like bench/run_bench.py.

  python decision/run_harness.py [--decider gold | module:function] [--date YYYY-MM-DD] [--ids ex01_iv_bolus,...] [--first N]

--decider gold (also accepted: gold-asked, the name of its run folder): the answers are the gold labels of decision/data/bench.jsonl (the scripted-wording row of the same exercise and turn,
found by the state without its analyses), i.e. perfect decisions: the run measures the ceiling of the decision pipeline.
--decider module:function: any `function(state, questions) -> {question: label}` (decision/ and the agent folder are on sys.path).

For each exercise (bench/exercises/, sorted ids) one Harness (one fresh Caladrius MCP session), the 8 scripted turns of
bench/scripts.py, one record per turn in the format of bench/run_bench.py, so that the same scorer judges it: score.score_turn (the
expected numbers), the compare turn resolved from the analysis_compare call (run_bench.resolve_turn), the oracle check and the
tool-call argument audit (run_bench.attach_oracle). The gate (gate.py) is run on every answer for completeness: the harness writes
only engine values, so it should find 0 unverified numbers; its allowed numbers are those of both Caladrius sessions (the calls of the
units session, which converts CL and V when the dose unit is not the concentrations' mass unit, are recorded per turn as `unit_calls`
with their results and kept out of the tool-call counts and audit, which describe the conversation's own session). The results of
the turn's calls and of the units session so far (a cache the harness reuses on later turns) are passed to score.score_turn, which
does not count a `must_not` value copied verbatim from them. Writes decision/runs/<date>-harness-<decider>/<id>.json, report.json
and report.md (the report of run_bench.py, plus a section on the decisions).
"""
import argparse, datetime, importlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
for p in (AGENT, HERE):
    if p not in sys.path: sys.path.insert(0, p)
import apothicaire, gate  # noqa: E402
import harness  # noqa: E402
from bench import make_exercises as mk, run_bench, scripts, score  # noqa: E402

RUNS = os.path.join(HERE, "runs")
BENCH_JSONL = os.path.join(HERE, "data", "bench.jsonl")

# ---------------------------------------------------------------- deciders
def state_key(state):
    """A state without its analyses: the data, the notes, the dose sentence and the request identify an (exercise, turn) row."""
    d = state["data"]
    return json.dumps([d["header"], d["first_rows"], d["n_rows"], state["notes"], state["user_dose_sentence"], state["request"]],
                      ensure_ascii=False)

def gold_decider(path=BENCH_JSONL):
    """decide(state, questions) answering the gold labels of the scripted-wording rows of bench.jsonl. The analyses are left out of
    the key: the dataset draws some reading turns "late" (both analyses present) and describes the compare turn after its re-run."""
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing: run `python decision/make_dataset.py` first")
    index = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not json.loads(r["factors"])["scripted_wording"]: continue
            k = state_key(json.loads(r["state"]))
            gold = {q: g["label"] for q, g in json.loads(r["gold"]).items()}
            assert index.setdefault(k, gold) == gold, "two gold answers for one state"
            index[k] = gold
    def decide(state, questions):
        return index[state_key(state)]
    decide.name = "gold-asked"          # the gold answers include the asked_<parameter> questions (step 4b); step 4 was the run "gold"
    return decide

def load_decider(spec):
    if spec in ("gold", "gold-asked"): return gold_decider()       # gold-asked: the name of its run folder, which an earlier brief used
    mod, _, fn = spec.partition(":")
    f = getattr(importlib.import_module(mod), fn)
    get_name = getattr(f, "get_name", None)        # decider_unsloth: the name follows $D01_MODEL
    f.name = get_name() if callable(get_name) else getattr(f, "name", fn)
    return f

# ---------------------------------------------------------------- one exercise
def run_exercise(ex_dir, run_dir, decide, mcp_bin=None, script=None, harness_kw=None, on_turn=None):
    """The 8 scripted turns of one exercise through a fresh Harness; returns the record (also written to <run_dir>/<id>.json).
    `script` (default scripts.build_script), `harness_kw` (Harness switches) and `on_turn(k, turn)`: for bench/decider_arm.py."""
    meta, csv_text = mk.load(ex_dir)
    script = script or scripts.build_script(meta, csv_text)
    h = harness.Harness(decide, mcp_bin=mcp_bin, **(harness_kw or {}))
    turns, t_ex = [], time.time()
    try:
        for k, t in enumerate(script):
            if on_turn is not None: on_turn(k, t)
            n_log, n_units = len(h.tool_log), len(h.unit_log)
            rec = {"exercise": meta["id"], "turn": k + 1, "id": t["id"], "kind": t["kind"], "question": t["question"]}
            if t.get("wording"): rec["wording"] = t["wording"]
            t0 = time.time()
            try:
                ans, info = h.turn(t["question"])
            except Exception as e:                                       # recorded, the exercise continues
                rec.update(error=f"{type(e).__name__}: {e}", wall_s=round(time.time() - t0, 3)); turns.append(rec); continue
            wall = time.time() - t0
            allowed = gate.allowed_numbers([c["shown"] for c in h.tool_log + h.unit_log], h.user_texts)
            g = gate.check(ans, allowed=allowed)
            cls = [{"text": f["text"], "value": f["value"], "significant_digits": f.get("significant_digits"), "position": f.get("position"),
                    "nearest": f.get("nearest_allowed"), "class": score.classify(f, allowed, t["kind"], ans)} for f in g["findings"]]
            tool_recs = run_bench.tool_records(h.tool_log[n_log:], meta, csv_text, set(h.mcp.tools))
            st_resolved, usage = run_bench.resolve_turn(meta, t, turns, tool_recs)
            # the tool results of the turn: its calls, and the units session's results, which the harness caches and reuses on later
            # turns (the clearance turn shows the conversion made on the first turn)
            sc = score.score_turn(ans, st_resolved["expect"], g["numbers_unverified"], [c["shown"] for c in h.tool_log[n_log:] + h.unit_log])
            rec.update(answer=ans + ("\n\n" + gate.badge(g["findings"]) if g["findings"] else ""),
                       wall_s=round(wall, 3), prompt_tokens=0, rounds=len(info["decisions"]),
                       numbers_total_before=g["numbers_total"], numbers_unverified_before=g["numbers_unverified"],
                       numbers_total_after=g["numbers_total"], numbers_unverified_after=g["numbers_unverified"],
                       regenerated=False, kept="first", badge=bool(g["findings"]), findings_before=cls, findings_after=cls,
                       first_answer=None, tool_calls=tool_recs, memory_calls=0, score=sc,
                       decisions=[{"answers": d["answers"], "outside_options": d["outside_options"],
                                   "analyses_in_state": [x["id"] for x in d["state"]["analyses"]],
                                   **({"model_info": d["model_info"]} if d.get("model_info") else {})} for d in info["decisions"]],
                       harness_notes=info["notes"],
                       unit_calls=[{"name": c["name"], "args": run_bench.elide(c["args"], csv_text), "ok": c["ok"], "shown": c["shown"][:6000]}
                                   for c in h.unit_log[n_units:]])
            if usage is not None: rec["compare_tool"] = usage
            turns.append(rec)
        allowed = gate.allowed_numbers([c["shown"] for c in h.tool_log + h.unit_log], h.user_texts)
        baseline = {str(d): score.chance_baseline(allowed, n=50, seed=meta["index"], digits=d) for d in (3, 4)}
    finally:
        h.close()
    record = {"id": meta["id"], "family": meta["family"], "model": meta["model"], "units": meta["units"], "dose": meta["dose"],
              "blq": bool(meta.get("blq")), "wall_s": round(time.time() - t_ex, 3), "decider": getattr(decide, "name", "?"),
              "taxonomy_chance_baseline": baseline, "turns": turns}
    run_bench.attach_oracle(record, meta, script)
    with open(os.path.join(run_dir, meta["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    return record

# ---------------------------------------------------------------- report
def decision_section(records):
    """Markdown lines on the decisions: decide calls, answers outside the offered options, harness notes, exact time per turn."""
    turns = [t for r in records for t in r["turns"] if "error" not in t]
    decs = [d for t in turns for d in t.get("decisions", [])]
    outside = {}
    for t in turns:
        for i, d in enumerate(t.get("decisions", [])):
            for q in d["outside_options"]: outside.setdefault(f"{q} ({t['kind']}, ask {i + 1})", []).append(t["exercise"])
    notes = [f"{t['exercise']} t{t['turn']}: {n}" for t in turns for n in t.get("harness_notes", [])]
    walls = [t["wall_s"] for t in turns]
    units = [c for t in turns for c in t.get("unit_calls", [])]
    L = ["## Decision harness", "",
         f"{len(decs)} decide calls in {len(turns)} turns; mean {sum(walls) / len(walls):.3f} s per turn (engine calls and rendering; "
         f"no prompt tokens; with a trained decider the time includes its forward passes, see the decision model section if any)." if walls else "No turn.", "",
         "Answers outside the options offered by the question set (left unused by the harness): " +
         ("; ".join(f"{k}: {len(v)}" for k, v in sorted(outside.items())) if outside else "none") + ".", "",
         "Harness notes: " + ("; ".join(notes) if notes else "none") + ".", "",
         f"Units session (dose unit given to Caladrius to convert CL and V; not in the tool-call counts above): {len(units)} calls in "
         f"{len({t['exercise'] for t in turns if t.get('unit_calls')})} exercises, {sum(1 for c in units if not c['ok'])} refused.", ""]
    return L

def write_report(run_dir, records, meta):
    rep = run_bench.build_report(records, meta)
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as f: json.dump(rep, f, ensure_ascii=False, indent=1)
    md = run_bench.render_md(rep).replace("# Apothicaire benchmark report", "# Apothicaire benchmark report: decision harness", 1)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f: f.write(md + "\n" + "\n".join(decision_section(records)))
    return rep

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decider", default="gold", help="gold, or module:function with function(state, questions) -> answers")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--model", default=None, help="model folder for decider_unsloth (sets $D01_MODEL; the run folder is named after the model)")
    a = ap.parse_args()
    if a.model: os.environ["D01_MODEL"] = os.path.abspath(a.model)
    decide = load_decider(a.decider)
    name = "".join(c if c.isalnum() or c in "-_." else "-" for c in getattr(decide, "name", "custom"))
    run_dir = os.path.join(RUNS, f"{a.date}-harness-{name}"); os.makedirs(run_dir, exist_ok=True)
    dirs = mk.list_exercises()
    if a.ids: dirs = [d for d in dirs if os.path.basename(d) in a.ids.split(",")]
    if a.first: dirs = dirs[:a.first]
    records = []
    for d in dirs:
        r = run_exercise(d, run_dir, decide)
        records.append(r)
        ok = [t for t in r["turns"] if "error" not in t]
        print(f"{r['id']}: {len(ok)}/{len(r['turns'])} turns, oracle-correct {sum(1 for t in ok if (t.get('oracle') or {}).get('correct'))}"
              f"/{sum(1 for t in ok if t.get('oracle'))}, {r['wall_s']:.2f} s", flush=True)
    uses_model = hasattr(decide, "summary")       # a trained decider reports its own calls, seconds and GPU memory
    rep = write_report(run_dir, records, {"date": a.date, "exercises_run": len(records),
                                          "model": f"decision harness (decision/harness.py), decider {a.decider}" +
                                                   ("" if uses_model else ", no language model")})
    if uses_model:
        summ = decide.summary()
        with open(os.path.join(run_dir, "decider_summary.json"), "w", encoding="utf-8") as f: json.dump(summ, f, indent=1)
        with open(os.path.join(run_dir, "report.md"), "a", encoding="utf-8") as f:
            f.write("\n## Decision model\n\n" + "\n".join(f"- {k}: {v}" for k, v in summ.items()) + "\n")
        print("decider:", summ)
    o, tc = rep["oracle"], rep["tool_calls"]
    print(f"oracle {o['correct_turns']}/{o['turns']} turns, {o['numbers_ok']}/{o['numbers']} numbers; tool calls invalid {tc['invalid']}, "
          f"failed {tc['failed']} of {tc['total']}; gate unverified {rep['hallucination']['after_gate']['unverified']}/"
          f"{rep['hallucination']['after_gate']['total']}; {rep['time']['mean_wall_s_per_turn']:.3f} s per turn")
    print("report:", os.path.join(run_dir, "report.md"))

if __name__ == "__main__":
    main()
