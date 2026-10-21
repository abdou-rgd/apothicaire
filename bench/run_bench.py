#!/usr/bin/env python
"""Runs the Apothicaire benchmark: every exercise through the agent (gate in the loop), then the report.

  python bench/run_bench.py [--date YYYY-MM-DD] [--first N] [--ids ex01_iv_bolus,...] [--resume] [--report-only] [--rescore] [--tool-arg-audit]

For each exercise of bench/exercises/ (sorted by id): a fresh memory folder bench/runs/<date>/<id>-data/
(git-ignored), the 8-turn script of bench/scripts.py, one record per turn; the exercise's records are written
to bench/runs/<date>/<id>.json (synthetic data, versioned). report.json and report.md are built from them.

Per turn: numbers_total / numbers_unverified (the gate) before the one regeneration and in the answer shown,
badge shown or not, tool calls (valid / invalid / failed, see classify_call), the expected numbers found
(score.score_turn), wall time, prompt tokens (first call of the turn), the taxonomy class of every unverified
number (score.classify). Metric: hallucination rate = numbers_unverified / numbers_total, with both numbers.
"""
import argparse, datetime, json, math, os, random, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire, gate, optchat  # noqa: E402
from bench import make_exercises as mk, scripts, score  # noqa: E402

RUNS = os.path.join(HERE, "runs")
BADGE_MARK = "\n\n⚠ "

# ---------------------------------------------------------------- tool calls
def classify_call(name, ok, text, known_tools):
    """valid: the server accepted the call and the analysis ran;
    invalid: the call itself is wrong (unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis,
             any other rejection by the server);
    failed: the call was accepted but the analysis reports an error for every subject (data problem)."""
    if name not in known_tools: return "invalid"
    if not ok: return "invalid"
    if name == "nca_run":
        try:
            subj = json.loads(text)["result"]["subjects"]
            if subj and all("ok" not in s.get("outcome", {}) for s in subj): return "failed"
        except Exception: pass
    return "valid"

def elide(args, csv_text):
    a = dict(args)
    if isinstance(a.get("csv"), str):
        same = [x.strip() for x in a["csv"].strip().splitlines()] == [x.strip() for x in csv_text.strip().splitlines()]
        a["csv"] = f"<{len(a['csv'])} chars, {'identical to' if same else 'DIFFERENT from'} the exercise CSV>"
    return a

def tool_records(calls, meta, csv_text, known_tools):
    out = []
    for c in calls:
        r = {"name": c["name"], "args": elide(c["args"], csv_text), "ok": c["ok"], "shown": c["shown"][:6000],
             "status": classify_call(c["name"], c["ok"], c["text"], known_tools)}
        if not c["ok"]: r["error"] = c["text"][:240]
        if c["name"] == "data_import":
            r["csv_identical"] = r["args"].get("csv", "").startswith("<") and "identical to" in r["args"]["csv"]
        if c["name"] == "nca_run":
            a = c["args"]
            r["dose_ok"] = a.get("dose") == meta["dose"]["amount"] or (a.get("dose") is not None and float(a["dose"]) == float(meta["dose"]["amount"]))
            r["route_ok"] = a.get("route") == meta["route"]
        out.append(r)
    return out

# ---------------------------------------------------------------- the compare turn
def resolve_turn(meta, st, prior_turns, this_calls):
    """(script turn to score against, compare usage). Only the compare turn changes: when the model called `analysis_compare` on the
    linear and the lin-up/log-down analyses, the engine's difference and percentage are expected and allowed (scripts.resolve_compare);
    otherwise the static strict rule applies. `prior_turns`: the records of the earlier turns (their tool calls say which analysis is
    which method); `this_calls`: the tool records of this turn."""
    if st["kind"] != "compare": return st, None
    usage = score.compare_usage([c for t in prior_turns for c in t.get("tool_calls", [])], this_calls,
                                truth=lambda ref: scripts.compare_truth(meta, ref))
    return scripts.resolve_compare(st, meta, usage)[0], usage

def resolved_script(meta, script, turns):
    """The script with the compare turn's rule resolved from what the stored turns did."""
    return [resolve_turn(meta, st, turns[:k], turns[k].get("tool_calls", []))[0] if k < len(turns) else st for k, st in enumerate(script)]

# ---------------------------------------------------------------- oracle
def attach_oracle(rec, meta, script):
    """Adds the oracle verdict to every turn (`oracle`, see score.oracle_exercise) and the tool-call argument audit to the
    record (`tool_arg_audit`). Pure function of the stored answers and tool calls; the gate counts are not touched.
    The compare turn is judged against its resolved rule (resolve_turn)."""
    script = resolved_script(meta, script, rec["turns"])
    for t, o in zip(rec["turns"], score.oracle_exercise(meta, script, rec["turns"], BADGE_MARK)):
        if o is None: t.pop("oracle", None)
        else: t["oracle"] = o
    rec["tool_arg_audit"] = score.tool_arg_audit(meta, rec["turns"])

# ---------------------------------------------------------------- rubric and outcome (FROZEN_SET.md §6, T-066, T-071)
def attach_rubric(rec, meta, st, csv_text, prior_turns):
    """Adds the rubric verdict (`rubric`, score.rubric_turn on the answer shown) and the outcome class (`outcome`, §6.1) to a
    turn record. The compare turn is judged with what the model did with analysis_compare (its reference analysis)."""
    if "error" in rec:
        rec["outcome"] = "ERROR"; rec.pop("rubric", None); return rec
    _, usage = resolve_turn(meta, st, prior_turns, rec.get("tool_calls", []))
    shown = [c.get("shown", "") for c in rec.get("tool_calls", [])]
    rec["rubric"] = score.rubric_turn(rec.get("answer") or "", st, meta, shown, usage, BADGE_MARK, scripts.csv_numbers(csv_text))
    rec["outcome"] = score.outcome_of(rec, rec["rubric"])
    return rec

def planned_error_record(meta, script, error):
    """The record of an exercise that could not run at all (the agent or the engine failed to start): every planned turn is
    an ERROR, so the exercise stays in every denominator (§6.1)."""
    turns = [{"exercise": meta["id"], "turn": k + 1, "id": t["id"], "kind": t["kind"], "question": t["question"],
              "error": error, "wall_s": 0.0, "outcome": "ERROR"} for k, t in enumerate(script)]
    return {"id": meta["id"], "family": meta["family"], "model": meta["model"], "units": meta["units"], "dose": meta["dose"],
            "blq": bool(meta.get("blq")), "wall_s": 0.0, "taxonomy_chance_baseline": {}, "turns": turns}

# ---------------------------------------------------------------- one exercise
def run_exercise(ex_dir, run_dir, cfg_base=None, verbose=False, llm=None):
    """Runs the 8 turns of one exercise; returns the record (also written to <run_dir>/<id>.json)."""
    meta, csv_text = mk.load(ex_dir)
    script = scripts.build_script(meta, csv_text)
    data = os.path.join(run_dir, meta["id"] + "-data")
    if os.path.exists(data): shutil.rmtree(data)
    cfg = dict(cfg_base or optchat.CFG, data_dir=data)
    ag = apothicaire.Apothicaire(cfg=cfg)
    if llm is not None: ag.llm = llm; ag.compactor.llm = llm          # tests: a scripted model
    turns, t_ex = [], time.time()
    try:
        for k, t in enumerate(script):
            n_log, n_msgs = len(ag.tool_log), len(ag.store.log)
            rec = {"exercise": meta["id"], "turn": k + 1, "id": t["id"], "kind": t["kind"], "question": t["question"]}
            t0 = time.time()
            try:
                ans, st = ag.turn(t["question"], verbose=verbose)
            except Exception as e:                                   # a model / server failure: recorded, the exercise continues
                rec.update(error=f"{type(e).__name__}: {e}", wall_s=round(time.time() - t0, 1), outcome="ERROR"); turns.append(rec)
                try: ag.wait_bg()
                except Exception: pass
                continue
            wall = time.time() - t0
            g = st.get("gate") or {}
            before, after = g.get("before", {}), g.get("after", {})
            answer = ans.split(BADGE_MARK)[0] if BADGE_MARK in ans else ans
            tool_texts, users = apothicaire.gate_context(ag.store.log, ag.mcp.tools)
            allowed = gate.allowed_numbers(tool_texts, users)
            f_before = g.get("first_findings") if g.get("regenerated") else g.get("findings", [])
            f_after = g.get("findings", [])
            cls = lambda fs, text: [{"text": f["text"], "value": f["value"], "significant_digits": f.get("significant_digits"),
                                     "position": f.get("position"), "nearest": f.get("nearest_allowed"),
                                     "class": score.classify(f, allowed, t["kind"], text)} for f in (fs or [])]
            msgs = ag.store.log[n_msgs:]
            mem_calls = sum(1 for m in msgs if m["role"] == "tool_call" for c in optchat._calls_of(m) if c["name"] in ("zoom", "read_message"))
            tool_recs = tool_records(ag.tool_log[n_log:], meta, csv_text, set(ag.mcp.tools))
            st_resolved, usage = resolve_turn(meta, t, turns, tool_recs)
            sc = score.score_turn(answer, st_resolved["expect"], after.get("numbers_unverified", 0), [c["shown"] for c in ag.tool_log[n_log:]])
            rec.update(tools_withdrawn=bool(ag._withdraw_tools or g.get("tool_call_text")), max_tool_rounds=cfg["max_tool_rounds"])
            rec.update(
                answer=ans, wall_s=round(wall, 1), prompt_tokens=st["prompt_tokens"], rounds=st["rounds"],
                numbers_total_before=before.get("numbers_total", 0), numbers_unverified_before=before.get("numbers_unverified", 0),
                numbers_total_after=after.get("numbers_total", 0), numbers_unverified_after=after.get("numbers_unverified", 0),
                regenerated=bool(g.get("regenerated")), kept=g.get("kept"), badge=bool(f_after),
                findings_before=cls(f_before, g.get("first_answer") if g.get("regenerated") else answer), findings_after=cls(f_after, answer),
                first_answer=g.get("first_answer") if g.get("regenerated") else None,
                tool_calls=tool_recs, memory_calls=mem_calls, score=sc)
            if usage is not None: rec["compare_tool"] = usage
            attach_rubric(rec, meta, t, csv_text, turns)
            turns.append(rec)
            ag.wait_bg()                                             # compaction does not leak into the next turn's time
        tool_texts, users = apothicaire.gate_context(ag.store.log, ag.mcp.tools)
        allowed = gate.allowed_numbers(tool_texts, users)
        baseline = {str(d): score.chance_baseline(allowed, n=50, seed=meta["index"], digits=d) for d in (3, 4)}
    finally:
        ag.close()
    record = {"id": meta["id"], "family": meta["family"], "model": meta["model"], "units": meta["units"],
              "dose": meta["dose"], "blq": bool(meta.get("blq")), "wall_s": round(time.time() - t_ex, 1),
              "taxonomy_chance_baseline": baseline, "turns": turns}
    attach_oracle(record, meta, script)
    with open(os.path.join(run_dir, meta["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    return record

# ---------------------------------------------------------------- report
def _sum(turns, key): return sum(t.get(key, 0) or 0 for t in turns)
def _rate(u, n): return (u / n) if n else None

def cluster_interval(records, num, den, n_boot=2000, seed=0):
    """95 % percentile interval of sum(num)/sum(den) with the exercises resampled (a cluster bootstrap: the numbers
    of one conversation are not independent)."""
    per = [(sum(t.get(num, 0) or 0 for t in r["turns"]), sum(t.get(den, 0) or 0 for t in r["turns"])) for r in records]
    return _cluster_ci(per, n_boot, seed)

def _cluster_ci(per, n_boot=2000, seed=0):
    """Percentile interval of sum(a)/sum(b) over resampled (a, b) pairs, one pair per exercise."""
    if len(per) < 2: return None
    rng, vals = random.Random(seed), []
    for _ in range(n_boot):
        s = [per[rng.randrange(len(per))] for _ in per]
        d = sum(x[1] for x in s)
        if d: vals.append(sum(x[0] for x in s) / d)
    vals.sort()
    return [vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]] if vals else None

def build_report(records, meta=None):
    turns = [t for r in records for t in r["turns"]]
    ok_turns = [t for t in turns if "error" not in t]
    out = {"meta": meta or {}, "exercises": len(records), "turns": len(turns), "turns_failed": len(turns) - len(ok_turns)}
    ub, nb = _sum(ok_turns, "numbers_unverified_before"), _sum(ok_turns, "numbers_total_before")
    ua, na = _sum(ok_turns, "numbers_unverified_after"), _sum(ok_turns, "numbers_total_after")
    out["hallucination"] = {
        "before_gate": {"unverified": ub, "total": nb, "rate": _rate(ub, nb), "ci95_cluster_bootstrap": cluster_interval(records, "numbers_unverified_before", "numbers_total_before")},
        "after_gate": {"unverified": ua, "total": na, "rate": _rate(ua, na), "ci95_cluster_bootstrap": cluster_interval(records, "numbers_unverified_after", "numbers_total_after")},
        "turns_with_unverified_before": sum(1 for t in ok_turns if t["numbers_unverified_before"]),
        "turns_with_unverified_after": sum(1 for t in ok_turns if t["numbers_unverified_after"]),
        "turns_regenerated": sum(1 for t in ok_turns if t["regenerated"]),
        "regeneration_kept": sum(1 for t in ok_turns if t["regenerated"] and t["kept"] == "regenerated"),
        "turns_with_badge": sum(1 for t in ok_turns if t["badge"]),
    }
    tax = {"before_gate": {c: 0 for c in score.CLASSES}, "after_gate": {c: 0 for c in score.CLASSES}}
    for t in ok_turns:
        for f in t["findings_before"]: tax["before_gate"][f["class"]] += 1
        for f in t["findings_after"]: tax["after_gate"][f["class"]] += 1
    out["taxonomy"] = tax
    base = {d: {c: 0 for c in score.CLASSES} for d in ("3", "4")}
    for r in records:
        for d, cnt in (r.get("taxonomy_chance_baseline") or {}).items():
            for c, v in cnt.items(): base[d][c] += v
    out["taxonomy_chance_baseline"] = base
    bykind = {}
    for t in turns:                                                  # every planned turn is in the denominator (T-071)
        b = bykind.setdefault(t["kind"], {"turns": 0, "correct": 0, "found": 0, "must": 0, "unverified_before": 0, "total_before": 0,
                                          "unverified_after": 0, "total_after": 0})
        b["turns"] += 1
        if "error" in t: continue
        b["correct"] += t["score"]["correct"]; b["found"] += len(t["score"]["found"]); b["must"] += t["score"]["n_must"]
        b["unverified_before"] += t["numbers_unverified_before"]; b["total_before"] += t["numbers_total_before"]
        b["unverified_after"] += t["numbers_unverified_after"]; b["total_after"] += t["numbers_total_after"]
    for b in bykind.values(): b["correct_rate"] = _rate(b["correct"], b["turns"]); b["found_rate"] = _rate(b["found"], b["must"])
    out["by_question_type"] = {k: bykind[k] for k in scripts.KINDS if k in bykind}
    out["correctness"] = {"correct_turns": sum(t["score"]["correct"] for t in ok_turns), "turns": len(turns), "turns_error": len(turns) - len(ok_turns),
                          "expected_numbers_found": sum(len(t["score"]["found"]) for t in ok_turns),
                          "expected_numbers": sum(t["score"]["n_must"] for t in ok_turns),
                          "forbidden_values_present": sum(len(t["score"]["forbidden"]) for t in ok_turns)}
    calls = [c for t in ok_turns for c in t["tool_calls"]]
    cnt = {s: sum(1 for c in calls if c["status"] == s) for s in ("valid", "invalid", "failed")}
    nca = [c for c in calls if c["name"] == "nca_run"]
    out["tool_calls"] = {**cnt, "total": len(calls), "validity_rate": _rate(cnt["valid"], len(calls)),
                         "nca_run_calls": len(nca), "nca_run_right_dose": sum(1 for c in nca if c.get("dose_ok")),
                         "nca_run_right_route": sum(1 for c in nca if c.get("route_ok")),
                         "memory_calls": _sum(ok_turns, "memory_calls"),
                         "by_tool": {n: sum(1 for c in calls if c["name"] == n) for n in sorted({c["name"] for c in calls})}}
    walls = [t["wall_s"] for t in ok_turns]
    out["time"] = {"mean_wall_s_per_turn": sum(walls) / len(walls) if walls else None,
                   "mean_prompt_tokens_first_call": (sum(t["prompt_tokens"] for t in ok_turns) / len(ok_turns)) if ok_turns else None,
                   "total_wall_s": sum(r["wall_s"] for r in records)}
    out["outcomes"] = outcome_section(records)
    out["compare_tool"] = compare_section(records)
    out["oracle"] = oracle_section(records)
    out["tool_arg_audit"] = audit_section(records)
    out["per_exercise"] = []
    for r in records:
        ts = [t for t in r["turns"] if "error" not in t]
        out["per_exercise"].append({
            "id": r["id"], "family": r["family"], "dose": f"{r['dose']['amount']} {r['dose']['unit']}", "units": f"{r['units']['time']}, {r['units']['conc']}",
            "turns": len(r["turns"]), "turns_failed": len(r["turns"]) - len(ts),
            "outcome_correct": sum(1 for t in r["turns"] if t.get("outcome") == "CORRECT"),
            "unverified_before": _sum(ts, "numbers_unverified_before"), "total_before": _sum(ts, "numbers_total_before"),
            "unverified_after": _sum(ts, "numbers_unverified_after"), "total_after": _sum(ts, "numbers_total_after"),
            "correct_turns": sum(t["score"]["correct"] for t in ts), "badge_turns": sum(1 for t in ts if t["badge"]),
            "calls_valid": sum(1 for t in ts for c in t["tool_calls"] if c["status"] == "valid"),
            "calls_total": sum(len(t["tool_calls"]) for t in ts),
            "mean_wall_s": (sum(t["wall_s"] for t in ts) / len(ts)) if ts else None})
    return out

def outcome_section(records):
    """Outcome classes of FROZEN_SET.md §6.1 over every planned turn (score.outcome_of; ERROR for a turn that raised), in total
    and by question type, with the rubric's correct turns and the exercises whose 8 turns are all CORRECT. None when the records
    carry no outcome (runs older than 2026-10-21 that were not rescored)."""
    turns = [t for r in records for t in r["turns"]]
    if not turns or not all("outcome" in t or "error" in t for t in turns): return None
    oc = lambda t: t.get("outcome") or "ERROR"
    total = {c: sum(1 for t in turns if oc(t) == c) for c in score.OUTCOMES}
    byk = {}
    for t in turns:
        b = byk.setdefault(t["kind"], {c: 0 for c in score.OUTCOMES}); b[oc(t)] += 1
    passed = [r["id"] for r in records if r["turns"] and all(oc(t) == "CORRECT" for t in r["turns"])]
    return {"turns": len(turns), "classes": total, "by_question_type": {k: byk[k] for k in scripts.KINDS if k in byk},
            "rubric": score.RUBRIC_VERSION, "exercises": len(records), "exercises_all_correct": len(passed),
            "exercises_failed": sorted(r["id"] for r in records if r["id"] not in passed)}

def render_outcomes_md(o):
    if not o: return []
    L = [f"## Outcomes (FROZEN_SET.md §6.1, rubric {o['rubric']}): {o['classes']['CORRECT']} / {o['turns']} turns CORRECT; "
         f"exercises with all turns CORRECT {o['exercises_all_correct']} / {o['exercises']}", "",
         "Every planned turn is in the denominator: a turn that raised is ERROR, over the wall-clock cap TIMEOUT, ended by the tool-round "
         "cap or the repeated-call guard LOOP, without any expected value and saying it cannot answer ABSTAINED; otherwise the rubric of "
         "§6.2 (`score.rubric_turn`) says CORRECT or WRONG.", "",
         "| question type | " + " | ".join(score.OUTCOMES) + " |", "|---|" + "---|" * len(score.OUTCOMES)]
    for k, b in o["by_question_type"].items(): L.append(f"| {k} | " + " | ".join(str(b[c]) for c in score.OUTCOMES) + " |")
    L += ["| **total** | " + " | ".join(str(o["classes"][c]) for c in score.OUTCOMES) + " |", ""]
    return L

def compare_section(records):
    """What the model did on the compare turn with `analysis_compare`: turns that called it, calls (valid / invalid), turns where the call
    was usable (linear vs lin-up/log-down, the auclast row with its difference and percentage, equal to the ground-truth arithmetic;
    then the engine's numbers are the expected answer), turns where the row disagreed with the ground truth."""
    rows = [(r["id"], t) for r in records for t in r["turns"] if "error" not in t and t["kind"] == "compare"]
    cu = [(ex, t.get("compare_tool") or {"calls": 0, "valid": 0, "usable": False}) for ex, t in rows]
    return {"turns": len(rows), "turns_with_call": sum(1 for _, u in cu if u["calls"]), "calls": sum(u["calls"] for _, u in cu),
            "valid_calls": sum(u["valid"] for _, u in cu), "turns_usable": sum(1 for _, u in cu if u["usable"]),
            "turns_row_disagrees_with_truth": [ex for ex, u in cu if u.get("mismatch")],
            "turns_without_call": [ex for ex, u in cu if not u["calls"]],
            "analysis_compare_calls_all_turns": sum(1 for r in records for t in r["turns"] if "error" not in t for c in t["tool_calls"] if c["name"] == "analysis_compare")}

# ---------------------------------------------------------------- oracle section of the report
def oracle_section(records):
    """Oracle correctness (bench/score.py: oracle_turn), separate from the gate counts and from the scorer's `correct`.
    Denominators: the turns whose expectation contains numbers (not_available has none) and the expected numbers (items)."""
    rows = [(r["id"], t) for r in records for t in r["turns"] if "error" not in t and t.get("oracle")]
    zero = lambda: {c: 0 for c in score.ORACLE_CLASSES}
    byk, classes, mism = {}, zero(), []
    dis = {"items_oracle_wrong_scorer_found": [], "items_oracle_ok_scorer_missing": [],
           "turns_oracle_wrong_scorer_correct": [], "turns_oracle_ok_scorer_incorrect": []}
    for ex, t in rows:
        o, b = t["oracle"], byk.setdefault(t["kind"], {"turns": 0, "correct": 0, "items": 0, "ok": 0, "classes": zero()})
        b["turns"] += 1; b["correct"] += o["correct"]; b["items"] += o["n_items"]; b["ok"] += o["n_ok"]
        for it in o["items"]:
            if it["ok"]:
                if it["label"] in t["score"]["missing"]: dis["items_oracle_ok_scorer_missing"].append(f"{ex} t{t['turn']} {it['label']}")
                continue
            classes[it["class"]] += 1; b["classes"][it["class"]] += 1
            mism.append({"exercise": ex, "turn": t["turn"], "kind": t["kind"], "label": it["label"], "class": it["class"],
                         "detail": it["detail"], "claimed": it["claimed"]})
            if it["label"] in t["score"]["found"]: dis["items_oracle_wrong_scorer_found"].append(f"{ex} t{t['turn']} {it['label']} ({it['class']})")
        if o["correct"] and not t["score"]["correct"]: dis["turns_oracle_ok_scorer_incorrect"].append(f"{ex} t{t['turn']} {t['kind']}")
        if not o["correct"] and t["score"]["correct"]: dis["turns_oracle_wrong_scorer_correct"].append(f"{ex} t{t['turn']} {t['kind']}")
    for b in byk.values(): b["correct_rate"] = _rate(b["correct"], b["turns"]); b["ok_rate"] = _rate(b["ok"], b["items"])
    n_t, n_ok_t = len(rows), sum(t["oracle"]["correct"] for _, t in rows)
    n_i, n_ok_i = sum(t["oracle"]["n_items"] for _, t in rows), sum(t["oracle"]["n_ok"] for _, t in rows)
    per_t, per_i = {}, {}
    for ex, t in rows:
        a = per_t.setdefault(ex, [0, 0]); a[0] += not t["oracle"]["correct"]; a[1] += 1
        a = per_i.setdefault(ex, [0, 0]); a[0] += t["oracle"]["n_items"] - t["oracle"]["n_ok"]; a[1] += t["oracle"]["n_items"]
    ci = lambda per: _cluster_ci(list(per.values()))
    wrong_t, wrong_i = n_t - n_ok_t, n_i - n_ok_i
    inv = lambda c: None if c is None else [1 - c[1], 1 - c[0]]
    return {"turns": n_t, "correct_turns": n_ok_t, "correct_turns_rate": _rate(n_ok_t, n_t),
            "correct_turns_ci95_cluster_bootstrap": inv(ci(per_t)) if wrong_t else None,
            "numbers": n_i, "numbers_ok": n_ok_i, "numbers_ok_rate": _rate(n_ok_i, n_i),
            "numbers_ok_ci95_cluster_bootstrap": inv(ci(per_i)) if wrong_i else None,
            "classes": classes, "by_question_type": {k: byk[k] for k in scripts.KINDS if k in byk},
            "not_covered": [k for k in scripts.KINDS if k not in byk], "mismatches": mism, "disagreements_with_scorer": dis}

def audit_section(records):
    """Aggregate of the per-exercise `tool_arg_audit` (score.tool_arg_audit): tool calls whose arguments differ from the intent."""
    per, by_field = {}, {}
    for r in records:
        a = r.get("tool_arg_audit")
        if not a: continue
        per[r["id"]] = a
        for d in a["deviations"]:
            k = f"{d['tool']}: {d['field']} = {json.dumps(d['got'], ensure_ascii=False)} (intended {json.dumps(d['intended'], ensure_ascii=False)})"
            by_field[k] = by_field.get(k, 0) + 1
    return {"calls": sum(a["calls"] for a in per.values()), "deviating_calls": sum(a["deviating_calls"] for a in per.values()),
            "exercises_with_deviation": sorted(i for i, a in per.items() if a["deviations"]), "by_deviation": by_field, "per_exercise": per}

def render_oracle_md(o):
    c, L = o, []
    if not o["turns"]: return ["## Oracle check: no stored oracle verdicts (run `run_bench.py --rescore`)", ""]
    fmt = lambda ci: "" if not ci else f" (95 % CI, exercises resampled: {100 * ci[0]:.1f}-{100 * ci[1]:.1f} %)"
    L += [f"## Oracle check: {c['correct_turns']} / {c['turns']} turns = {_pct(c['correct_turns_rate'])}{fmt(c['correct_turns_ci95_cluster_bootstrap'])}; "
          f"{c['numbers_ok']} / {c['numbers']} expected numbers = {_pct(c['numbers_ok_rate'])}{fmt(c['numbers_ok_ci95_cluster_bootstrap'])}", "",
          "Second judgement, independent of the gate (`bench/score.py`, `oracle_turn`): the number written after the label of the parameter "
          "the question asks for must be Caladrius's value of THAT parameter, of the right AUC method, with the unit Caladrius reports. "
          "The gate counts above are untouched; the denominators here are the turns that expect numbers and the numbers they expect "
          f"(not covered: {', '.join(c['not_covered']) or 'none'}, no value to check).", "",
          "| question type | turns | oracle-correct | expected numbers ok | " + " | ".join(score.ORACLE_CLASSES) + " |",
          "|---|---|---|---|" + "---|" * len(score.ORACLE_CLASSES)]
    for k, v in c["by_question_type"].items():
        L.append(f"| {k} | {v['turns']} | {v['correct']} ({_pct(v['correct_rate'])}) | {v['ok']} / {v['items']} | " +
                 " | ".join(str(v["classes"][x]) for x in score.ORACLE_CLASSES) + " |")
    L.append("| **total** | %d | %d (%s) | %d / %d | %s |" % (c["turns"], c["correct_turns"], _pct(c["correct_turns_rate"]), c["numbers_ok"], c["numbers"],
                                                          " | ".join(str(c["classes"][x]) for x in score.ORACLE_CLASSES)))
    d = c["disagreements_with_scorer"]
    L += ["", f"Against the scorer's expected-number check (the global search of the numbers, above): items the scorer found but the oracle rejects "
          f"{len(d['items_oracle_wrong_scorer_found'])}" + (f" ({'; '.join(d['items_oracle_wrong_scorer_found'])})" if d["items_oracle_wrong_scorer_found"] else "") +
          f"; items the scorer missed but the oracle accepts {len(d['items_oracle_ok_scorer_missing'])}" +
          (f" ({'; '.join(d['items_oracle_ok_scorer_missing'])})" if d["items_oracle_ok_scorer_missing"] else "") +
          f"; turns oracle-wrong but scorer-correct {len(d['turns_oracle_wrong_scorer_correct'])}" +
          (f" ({'; '.join(d['turns_oracle_wrong_scorer_correct'])})" if d["turns_oracle_wrong_scorer_correct"] else "") +
          f"; turns oracle-correct but scorer-incorrect {len(d['turns_oracle_ok_scorer_incorrect'])}" +
          (f" ({'; '.join(d['turns_oracle_ok_scorer_incorrect'])})" if d["turns_oracle_ok_scorer_incorrect"] else "") + ".", ""]
    if c["mismatches"]:
        L += ["Every expected number the oracle rejects:", "", "| exercise | turn | expected | class | detail | numbers written after the label |", "|---|---|---|---|---|---|"]
        for m in c["mismatches"]:
            L.append(f"| {m['exercise']} | {m['turn']} {m['kind']} | {m['label']} | {m['class']} | {m['detail'] or ''} | {', '.join(m['claimed']) or '(none)'} |")
        L.append("")
    return L

def render_audit_md(a):
    if not a["calls"]: return []
    L = [f"## Tool-call argument audit: {a['deviating_calls']} of {a['calls']} `nca_run` / `data_import` calls differ from the exercise's intent "
         f"(dose, route, the AUC method and the units as options; the CSV and the column units)", ""]
    if a["by_deviation"]:
        L += ["| deviation | calls |", "|---|---|"] + [f"| {k} | {n} |" for k, n in sorted(a["by_deviation"].items(), key=lambda kv: (-kv[1], kv[0]))]
        L += ["", "In exercises: " + ", ".join(a["exercises_with_deviation"]) + ". A deviation is listed here whatever its effect; the oracle check calls it `wrong_option` only when "
              "the answer's value is wrong (`run_bench.py --tool-arg-audit` prints every call).", ""]
    else: L += ["No deviation.", ""]
    return L

def _pct(x): return "n/a" if x is None else f"{100 * x:.1f} %"
def _ci(c, u=None, n=None):
    if u == 0 and n: return f" (none observed: upper 95 % bound by the rule of three 3/{n} = {300 / n:.2f} %)"
    return "" if not c else f" (95 % CI, exercises resampled: {100 * c[0]:.1f}-{100 * c[1]:.1f} %)"

def render_md(rep):
    h, c, t, tm = rep["hallucination"], rep["correctness"], rep["tool_calls"], rep["time"]
    L = ["# Apothicaire benchmark report", ""]
    m = rep.get("meta") or {}
    if m: L += [", ".join(f"{k}: {v}" for k, v in m.items()), ""]
    b, a = h["before_gate"], h["after_gate"]
    L += [f"**Hallucination rate = numbers not found in a tool result or user message / numbers checked (deterministic gate `gate.py`).**", "",
          f"- before the gate's regeneration (first drafts): **{b['unverified']} / {b['total']} = {_pct(b['rate'])}**{_ci(b['ci95_cluster_bootstrap'], b['unverified'], b['total'])}",
          f"- in the answers shown (gate in the loop): **{a['unverified']} / {a['total']} = {_pct(a['rate'])}**{_ci(a['ci95_cluster_bootstrap'], a['unverified'], a['total'])}",
          f"- {rep['exercises']} exercises, {rep['turns']} turns ({rep['turns_failed']} failed by an error); turns with an unverified number: "
          f"{h['turns_with_unverified_before']} before, {h['turns_with_unverified_after']} after; regenerated {h['turns_regenerated']} "
          f"(regeneration kept {h['regeneration_kept']}); turns shown with the badge: {h['turns_with_badge']}", "",
          "## Failure taxonomy (unverified numbers)", "", "| class | before the gate | in the answers shown |", "|---|---|---|"]
    for k in score.CLASSES: L.append(f"| {k} | {rep['taxonomy']['before_gate'][k]} | {rep['taxonomy']['after_gate'][k]} |")
    L += ["", "Classes are heuristics (`bench/score.py`); the unverified counts above never depend on them. Chance baseline: how the "
          "same rules classify random numbers of 3 and 4 significant digits drawn over each exercise's range of tool values "
          "(a class whose baseline share is large is weak evidence at that precision):", "",
          "| class | random 3-digit numbers | random 4-digit numbers |", "|---|---|---|"]
    b3, b4 = rep["taxonomy_chance_baseline"]["3"], rep["taxonomy_chance_baseline"]["4"]
    n3, n4 = sum(b3.values()) or 1, sum(b4.values()) or 1
    for k in score.CLASSES: L.append(f"| {k} | {_pct(b3[k] / n3)} | {_pct(b4[k] / n4)} |")
    L += ["",
          f"## Correctness (development scorer `score_turn`): {c['correct_turns']} / {c['turns']} turns fully correct "
          f"({c.get('turns_error', 0)} turns failed by an error count as incorrect); expected numbers found {c['expected_numbers_found']} / {c['expected_numbers']}; "
          f"forbidden (converted or computed) values present in {c['forbidden_values_present']} answers", "",
          "| question type | turns | correct | found / expected numbers | unverified / total before | unverified / total shown |", "|---|---|---|---|---|---|"]
    for k, v in rep["by_question_type"].items():
        L.append(f"| {k} | {v['turns']} | {v['correct']} ({_pct(v['correct_rate'])}) | {v['found']} / {v['must']} | "
                 f"{v['unverified_before']} / {v['total_before']} | {v['unverified_after']} / {v['total_after']} |")
    ct = rep.get("compare_tool")
    if ct and ct["turns"]:
        L += ["", f"## Compare turn and `analysis_compare`: called in {ct['turns_with_call']} of {ct['turns']} compare turns ({ct['calls']} calls, {ct['valid_calls']} valid; "
              f"{ct['analysis_compare_calls_all_turns']} calls in all turns); usable in {ct['turns_usable']} (the two analyses of the exercise, the auclast row with "
              f"difference and percentage, equal to the ground-truth arithmetic: then the engine's difference and percentage are expected and allowed, other computed values stay forbidden); "
              f"row disagreeing with the ground truth: {len(ct['turns_row_disagrees_with_truth'])}; no call: {len(ct['turns_without_call'])}" +
              (f" ({', '.join(ct['turns_without_call'])})" if ct["turns_without_call"] else ""), ""]
    L += [""] + render_outcomes_md(rep.get("outcomes"))
    L += render_oracle_md(rep.get("oracle") or oracle_section([]))
    L += [f"## Tool calls: {t['valid']} valid, {t['invalid']} invalid, {t['failed']} failed of {t['total']} (validity {_pct(t['validity_rate'])})", "",
          f"`nca_run` calls: {t['nca_run_calls']}, with the right dose {t['nca_run_right_dose']}, with the right route {t['nca_run_right_route']}; "
          f"memory calls (zoom / read_message): {t['memory_calls']}; by tool: {t['by_tool']}. "
          "invalid = unknown tool, invalid_parameters, unknown_worksheet / unknown_analysis or any rejection; failed = accepted but the analysis errs for every subject.", "",
          *render_audit_md(rep.get("tool_arg_audit") or audit_section([])),
          f"## Time: mean {tm['mean_wall_s_per_turn']:.1f} s per turn, mean {tm['mean_prompt_tokens_first_call']:.0f} prompt tokens (first call), total {tm['total_wall_s'] / 60:.0f} min" if tm["mean_wall_s_per_turn"] is not None else "## Time: n/a",
          "", "## Per exercise", "",
          "| exercise | dose | units | unverified / total before | unverified / total shown | correct turns | badge turns | calls valid / total | mean s per turn |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in rep["per_exercise"]:
        w = "n/a" if e["mean_wall_s"] is None else f"{e['mean_wall_s']:.1f}"
        L.append(f"| {e['id']} | {e['dose']} | {e['units']} | {e['unverified_before']} / {e['total_before']} | {e['unverified_after']} / {e['total_after']} | "
                 f"{e['correct_turns']} / {e['turns']} | {e['badge_turns']} | {e['calls_valid']} / {e['calls_total']} | {w} |")
    return "\n".join(L) + "\n"

def rescore(run_dir, ids):
    """Recomputes the `score` and the `oracle` verdict of every stored turn from the stored answer, the stored tool calls and
    the current expectation rules (no model, no engine). Used after a fix of a scoring rule; the gate counts and the
    taxonomy are not touched."""
    changed = []
    for i in ids:
        p = os.path.join(run_dir, i + ".json")
        if not os.path.exists(p): continue
        with open(p, encoding="utf-8") as f: rec = json.load(f)
        meta, csv_text = mk.load(os.path.join(mk.OUT, i))
        script = scripts.build_script(meta, csv_text)
        for k, (t, st) in enumerate(zip(rec["turns"], script)):
            if "error" in t: continue
            ans = t["answer"].split(BADGE_MARK)[0]
            st, usage = resolve_turn(meta, st, rec["turns"][:k], t.get("tool_calls", []))
            if usage is not None: t["compare_tool"] = usage
            # the turn's tool results; decision harness runs also have the units session's results (`unit_calls`), a cache reused later
            shown = [c.get("shown", "") for c in t.get("tool_calls", [])] + [c.get("shown", "") for u in rec["turns"][:k + 1] for c in u.get("unit_calls", [])]
            new = score.score_turn(ans, st["expect"], t["numbers_unverified_after"], shown)
            if new != t["score"]: changed.append((i, t["turn"], t["kind"], t["score"]["correct"], new["correct"]))
            t["score"] = new
        for k, (t, st) in enumerate(zip(rec["turns"], script)): attach_rubric(t, meta, st, csv_text, rec["turns"][:k])
        before = [(t.get("oracle") or {}).get("correct") for t in rec["turns"]]
        attach_oracle(rec, meta, script)
        for t, b in zip(rec["turns"], before):
            if (t.get("oracle") or {}).get("correct") != b: changed.append((i, t["turn"], t["kind"], "oracle", b, (t.get("oracle") or {}).get("correct")))
        with open(p, "w", encoding="utf-8") as f: json.dump(rec, f, ensure_ascii=False, indent=1)
    return changed

def rubric_delta(run_dirs):
    """Old scorer against the rubric on stored runs, without touching them (T-066: the before/after delta next to the published
    figures). For each run folder: turns correct by `score_turn` as stored, turns CORRECT by the rubric, outcomes, by question
    type, and every turn on which the two disagree with the rubric's reasons. Returns the Markdown text."""
    L = ["# Stored runs rescored with the frozen-set rubric", "",
         f"Generated by `python bench/run_bench.py --rubric-delta` (rubric {score.RUBRIC_VERSION}, `score.rubric_turn`, FROZEN_SET.md §6.2). "
         "No model and no engine: the stored answers and tool calls of each run, the gold of `bench/exercises/` the runs were scored "
         "with. The stored records and reports are not modified. These are in-sample development runs; the figures on the left are "
         "the ones published, the ones on the right what the frozen-set rubric says of the same answers.", "",
         "| run | turns | correct, development scorer (as published) | CORRECT, rubric | WRONG | ERROR | TIMEOUT | LOOP | ABSTAINED | exercises all CORRECT |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    details = []
    for d in run_dirs:
        ids = [os.path.basename(x) for x in mk.list_exercises()]
        recs = load_records(d, ids)
        if not recs: continue
        cnt, byk, dis, n_old, ex_ok = {c: 0 for c in score.OUTCOMES}, {}, [], 0, 0
        for r in recs:
            meta, csv_text = mk.load(os.path.join(mk.OUT, r["id"]))
            script = scripts.build_script(meta, csv_text)
            all_ok = True
            for k, (t, st) in enumerate(zip(r["turns"], script)):
                t = dict(t); old = bool(t.get("score", {}).get("correct")) and "error" not in t
                attach_rubric(t, meta, st, csv_text, r["turns"][:k])
                cnt[t["outcome"]] += 1; n_old += old; all_ok &= t["outcome"] == "CORRECT"
                b = byk.setdefault(t["kind"], [0, 0, 0]); b[0] += 1; b[1] += old; b[2] += t["outcome"] == "CORRECT"
                if old != (t["outcome"] == "CORRECT"):
                    dis.append(f"| {r['id']} | {t['turn']} {t['kind']} | {'correct' if old else 'incorrect'} | {t['outcome']} | "
                               f"{'; '.join((t.get('rubric') or {}).get('reasons', [])) or '(none)'} |")
            ex_ok += all_ok
        n = sum(cnt.values()); name = os.path.basename(os.path.normpath(d))
        L.append(f"| {name} | {n} | {n_old} | {cnt['CORRECT']} | {cnt['WRONG']} | {cnt['ERROR']} | {cnt['TIMEOUT']} | {cnt['LOOP']} | "
                 f"{cnt['ABSTAINED']} | {ex_ok} / {len(recs)} |")
        details += ["", f"## {name}", "", "| question type | turns | correct, development scorer | CORRECT, rubric |", "|---|---|---|---|"]
        details += [f"| {k} | {v[0]} | {v[1]} | {v[2]} |" for k, v in sorted(byk.items(), key=lambda kv: scripts.KINDS.index(kv[0]))]
        details += ["", f"Turns on which the two disagree: {len(dis)}.", ""]
        if dis: details += ["| exercise | turn | development scorer | rubric | rubric's reasons |", "|---|---|---|---|---|"] + dis
    return "\n".join(L + details) + "\n"

def print_tool_arg_audit(records, out=print):
    """Per exercise, every `nca_run` / `data_import` call whose arguments differ from the script's intent, with counts."""
    n_calls = n_dev = 0
    for r in records:
        a = r.get("tool_arg_audit") or {"calls": 0, "deviating_calls": 0, "deviations": []}
        n_calls += a["calls"]; n_dev += a["deviating_calls"]
        out(f"{r['id']}: {a['deviating_calls']} of {a['calls']} calls deviate")
        for d in a["deviations"]:
            out(f"    turn {d['turn']} {d['tool']} ({d['status']}): {d['field']} = {json.dumps(d['got'], ensure_ascii=False)}, "
                f"intended {json.dumps(d['intended'], ensure_ascii=False)}")
    out(f"total: {n_dev} of {n_calls} calls deviate, in {sum(1 for r in records if (r.get('tool_arg_audit') or {}).get('deviations'))} of {len(records)} exercises")

def load_records(run_dir, ids):
    out = []
    for i in ids:
        p = os.path.join(run_dir, i + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f: out.append(json.load(f))
    return out

def write_report(run_dir, records, meta):
    rep = build_report(records, meta)
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as f: json.dump(rep, f, ensure_ascii=False, indent=1)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f: f.write(render_md(rep))
    return rep

def model_label():
    """Model file, quantisation and llama.cpp build as the running server reports them (GET /props),
    so that the report header never claims a file that was not loaded. Falls back to a generic label
    when the server is not reachable (e.g. --report-only)."""
    url = os.environ.get("OPTCHAT_URL", "http://127.0.0.1:18435").rstrip("/")
    try:
        import httpx
        d = httpx.get(url + "/props", timeout=5).json()
        name = os.path.basename(str(d.get("model_path") or d.get("model_alias") or "?"))
        ftype = str(d.get("model_ftype") or "").split(" - ")[0].strip()
        build = str(d.get("build_info") or "?")
        return f"{name} ({ftype or 'unknown ftype'}) on llama-server {build}"
    except Exception:
        return "unknown model (server not reachable when the report was written)"

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--first", type=int, default=0, help="only the first N exercises (fixed order: sorted ids)")
    ap.add_argument("--ids", default="", help="comma-separated exercise ids")
    ap.add_argument("--resume", action="store_true", help="skip the exercises whose <id>.json exists")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--tool-arg-audit", action="store_true", help="list, per exercise, every tool call whose arguments differ from the script's intent (needs the stored records; run --rescore first on an older run)")
    ap.add_argument("--rescore", action="store_true", help="recompute the scores of the stored turns with the current rules, then the report")
    ap.add_argument("--rubric-delta", default="", metavar="RUN,RUN", help="stored run folders (names under bench/runs/) rescored with the frozen-set "
                    "rubric, without modifying them; writes bench/runs/RUBRIC-RESCORE.md")
    ap.add_argument("--gate", default=os.environ.get("APOTHICAIRE_GATE", "v1"), choices=["v1", "v2"],
                    help="v1: the number gate (gate.py); v2: typed rendering (gate_v2.py, GATE_V2.md). Sets APOTHICAIRE_GATE for the run.")
    a = ap.parse_args(); optchat._utf8_stdout()
    if a.rubric_delta:
        out = os.path.join(RUNS, "RUBRIC-RESCORE.md")
        with open(out, "w", encoding="utf-8", newline="\n") as f: f.write(rubric_delta([os.path.join(RUNS, x) for x in a.rubric_delta.split(",")]))
        print("written", out); return
    os.environ["APOTHICAIRE_GATE"] = a.gate
    MODEL = f"{model_label()}, temperature 0.3, no fixed seed, gate {a.gate}"
    run_dir = os.path.join(RUNS, a.date); os.makedirs(run_dir, exist_ok=True)
    dirs = mk.list_exercises()
    if a.ids: dirs = [d for d in dirs if os.path.basename(d) in a.ids.split(",")]
    if a.first: dirs = dirs[:a.first]
    ids = [os.path.basename(d) for d in dirs]
    if a.rescore:
        for ch in rescore(run_dir, ids): print("rescored", ch)
    if a.tool_arg_audit:
        print_tool_arg_audit(load_records(run_dir, ids)); return
    if not a.report_only and not a.rescore:
        for d in dirs:
            i = os.path.basename(d)
            if a.resume and os.path.exists(os.path.join(run_dir, i + ".json")): print("skip", i); continue
            t0 = time.time(); r = run_exercise(d, run_dir)
            ok = [t for t in r["turns"] if "error" not in t]
            print(f"{i}: {len(ok)}/{len(r['turns'])} turns, unverified {sum(t['numbers_unverified_before'] for t in ok)}/"
                  f"{sum(t['numbers_total_before'] for t in ok)} before, {sum(t['numbers_unverified_after'] for t in ok)}/"
                  f"{sum(t['numbers_total_after'] for t in ok)} shown, {time.time() - t0:.0f} s", flush=True)
            write_report(run_dir, load_records(run_dir, ids), {"date": a.date, "exercises_run": len(ids), "model": MODEL, "gate": a.gate})
    rep = write_report(run_dir, load_records(run_dir, ids), {"date": a.date, "exercises_run": len(ids), "model": MODEL, "gate": a.gate})
    h = rep["hallucination"]
    print(f"hallucination: {h['before_gate']['unverified']}/{h['before_gate']['total']} before, {h['after_gate']['unverified']}/{h['after_gate']['total']} shown")
    print("report:", os.path.join(run_dir, "report.md"))

if __name__ == "__main__":
    main()
