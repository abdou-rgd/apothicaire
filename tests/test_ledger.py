"""Tests of the evaluation ledger (decision/LEDGER.md): every figure the ledger quotes is either recomputed here from files of the
repository or tied to the sentence of a report that states it.

The ledger ends with a register between the markers `<!-- register:begin -->` and `<!-- register:end -->`, one `key = value` per line.
Each group of keys below (prefix `bench.`, `runs.`, `rows.`, ...) is recomputed from the stored files; a group whose files are not on
disk (decision/data/ is git-ignored, the stale v1 `heldout.jsonl` may be gone) is skipped with a message, never failed. Keys that no
file can recompute are in QUOTED, with the report and the sentence they come from; the test checks that the sentence is still in the
report. A key of the register that is in neither place fails, and so does a fraction `a/b` of the ledger's prose that the register
does not hold. No engine, no model, no GPU.

  python -m unittest tests.test_ledger
  python tests/test_ledger.py --print-register     # the recomputed keys, in the register's format
"""
import collections, glob, json, math, os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, os.path.join(AGENT, "decision"))
from bench import scripts  # noqa: E402
import make_dataset as md  # noqa: E402
import zero_shot_d1 as z  # noqa: E402

LEDGER = os.path.join(AGENT, "decision", "LEDGER.md")
BEGIN, END = "<!-- register:begin -->", "<!-- register:end -->"
BYKIND_BEGIN, BYKIND_END = "<!-- bykind:begin -->", "<!-- bykind:end -->"
EXERCISES = os.path.join(AGENT, "bench", "exercises")
DATA = os.path.join(AGENT, "decision", "data")
RUNS_D = os.path.join(AGENT, "decision", "runs")
RUN_A1 = os.path.join(AGENT, "bench", "runs", "2026-10-09")
RUN_A2 = os.path.join(AGENT, "bench", "runs", "2026-10-09b")
RUN_B4 = os.path.join(RUNS_D, "2026-10-09-harness-gold")
RUN_B4B = os.path.join(RUNS_D, "2026-10-09-harness-gold-asked")
RUN_BTR = os.path.join(RUNS_D, "2026-10-09-harness-qwen35-0.8b")
RUN_B10 = os.path.join(RUNS_D, "2026-10-10-harness-gold-asked")
STEP2 = os.path.join(RUNS_D, "2026-10-09")
STEP3 = os.path.join(RUNS_D, "2026-10-09-train-qwen35-0.8b")
KINDS = scripts.KINDS


def need(path, what=None):
    if not os.path.exists(path): raise unittest.SkipTest("%s not on disk (%s)" % (what or "file", os.path.relpath(path, AGENT)))
    return path

def jload(path):
    with open(need(path), encoding="utf-8") as f: return json.load(f)

def run_exercises(folder):
    files = sorted(glob.glob(os.path.join(need(folder, "run folder"), "ex*.json")))
    if len(files) != 25: raise unittest.SkipTest("run folder %s has %d exercise files" % (os.path.relpath(folder, AGENT), len(files)))
    return [jload(f) for f in files]

def fr(a, b): return "%d/%d" % (a, b)
def pct(a, b): return "%.1f" % (100.0 * a / b)


# ---------------------------------------------------------------- the benchmark script
def benchmark_scripts():
    out = []
    for d in sorted(os.listdir(EXERCISES)):
        p = os.path.join(EXERCISES, d)
        if not os.path.isdir(p): continue
        meta = jload(os.path.join(p, "meta.json"))
        with open(os.path.join(p, "data.csv"), encoding="utf-8") as f: csv = f.read()
        out.append((meta, scripts.build_script(meta, csv)))
    return out

def group_bench():
    bs = benchmark_scripts()
    turns = [t for _, s in bs for t in s]
    with_must = [t for t in turns if t["expect"].get("must")]
    without = [t for t in turns if not t["expect"].get("must")]
    slots = [len(t["expect"].get("must") or []) for t in turns]
    per_kind = {k: collections.Counter(len(t["expect"].get("must") or []) for t in turns if t["kind"] == k) for k in KINDS}
    n_bolus = sum(scripts.kind_of(m) == "iv_bolus" for m, _ in bs)
    return {
        "bench.exercises": str(len(bs)),
        "bench.turns_per_exercise": str(len(bs[0][1])),
        "bench.turns": str(len(turns)),
        "bench.oracle_turns": str(len(with_must)),
        "bench.not_scored_by_oracle": str(len(without)),
        "bench.not_scored_kind": ",".join(sorted({t["kind"] for t in without})),
        "bench.not_scored_with_words": str(sum(bool(t["expect"].get("words")) and bool(t["expect"].get("no_new_numbers")) for t in without)),
        "bench.exercises_iv_bolus": str(n_bolus),
        "bench.exercises_other": str(len(bs) - n_bolus),
        "bench.slots_t1": str(next(iter(per_kind["import_nca"]))),
        "bench.slots_t2_bolus": str(max(per_kind["cmax_tmax"])),
        "bench.slots_t2_other": str(min(per_kind["cmax_tmax"])),
        "bench.slots_static": str(sum(slots)),
        "bench.slots_compare_resolved_extra": "2",
        "bench.slots_max": str(sum(slots) + 2 * len(bs)),
        "bench.kinds": ",".join(KINDS),
    }


# ---------------------------------------------------------------- stored runs
def run_counts(folder):
    ex = run_exercises(folder)
    c = collections.Counter(); per_kind = collections.Counter(); cmp_items = collections.Counter()
    for d in ex:
        a = d.get("tool_arg_audit") or {}
        c["audited"] += a.get("calls", 0); c["deviating"] += a.get("deviating_calls", 0)
        for t in d["turns"]:
            c["turns"] += 1
            if "error" in t: c["errors"] += 1; continue
            c["gate_before"] += t["numbers_total_before"]; c["gate_after"] += t["numbers_total_after"]
            c["unv_before"] += t["numbers_unverified_before"]; c["unv_after"] += t["numbers_unverified_after"]
            c["regenerated"] += bool(t["regenerated"])
            sc = t["score"]; c["scorer_ok"] += bool(sc["correct"]); c["scorer_found"] += len(sc["found"]); c["scorer_must"] += sc["n_must"]
            per_kind[t["kind"]] += t["numbers_total_before"]
            tc = t.get("tool_calls") or []
            c["tool_calls"] += len(tc); c["tool_invalid"] += sum(x.get("status") != "valid" for x in tc)
            c["decisions"] += len(t.get("decisions") or [])
            o = t.get("oracle")
            if o:
                c["oracle_turns"] += 1; c["oracle_turns_ok"] += bool(o["correct"]); c["slots"] += o["n_items"]; c["slots_ok"] += o["n_ok"]
                if t["kind"] == "compare": cmp_items[o["n_items"]] += 1
            if t["kind"] == "not_available": c["na_numbers"] += t["numbers_total_after"]
    c["compare_numbers"] = per_kind["compare"]
    return c, per_kind, cmp_items

def group_runs():
    out = {}
    a1, _, a1c = run_counts(RUN_A1)
    out.update({
        "runs.A1.turns": str(a1["turns"]), "runs.A1.gate_first_drafts": str(a1["gate_before"]), "runs.A1.gate_shown": str(a1["gate_after"]),
        "runs.A1.unverified_first_drafts": fr(a1["unv_before"], a1["gate_before"]), "runs.A1.unverified_shown": fr(a1["unv_after"], a1["gate_after"]),
        "runs.A1.regenerated_turns": str(a1["regenerated"]),
        "runs.A1.scorer_turns": fr(a1["scorer_ok"], a1["turns"]), "runs.A1.scorer_slots": fr(a1["scorer_found"], a1["scorer_must"]),
        "runs.A1.compare_numbers_first_drafts": str(a1["compare_numbers"]),
        "runs.A1.other_kinds_numbers_first_drafts": str(a1["gate_before"] - a1["compare_numbers"]),
        "runs.A1.oracle_turns": fr(a1["oracle_turns_ok"], a1["oracle_turns"]), "runs.A1.oracle_slots": fr(a1["slots_ok"], a1["slots"]),
        "runs.A1.compare_turns_with_2_slots": str(a1c[2]),
        "runs.A1.tool_calls_valid": fr(a1["tool_calls"] - a1["tool_invalid"], a1["tool_calls"]),
    })
    a2, _, a2c = run_counts(RUN_A2)
    out.update({
        "runs.A2.turns": str(a2["turns"]), "runs.A2.gate_first_drafts": str(a2["gate_before"]), "runs.A2.gate_shown": str(a2["gate_after"]),
        "runs.A2.unverified_first_drafts": fr(a2["unv_before"], a2["gate_before"]),
        "runs.A2.compare_numbers_first_drafts": str(a2["compare_numbers"]),
        "runs.A2.scorer_turns": fr(a2["scorer_ok"], a2["turns"]), "runs.A2.scorer_slots": fr(a2["scorer_found"], a2["scorer_must"]),
        "runs.A2.oracle_turns": fr(a2["oracle_turns_ok"], a2["oracle_turns"]), "runs.A2.oracle_slots": fr(a2["slots_ok"], a2["slots"]),
        "runs.A2.compare_turns_with_4_slots": str(a2c[4]), "runs.A2.compare_turns_with_2_slots": str(a2c[2]),
        "runs.A2.numbers_in_not_available_turns": str(a2["na_numbers"]),
        "runs.A2.tool_calls_valid": fr(a2["tool_calls"] - a2["tool_invalid"], a2["tool_calls"]),
        "runs.A2.audited_calls": str(a2["audited"]), "runs.A2.deviating_calls": str(a2["deviating"]),
        "runs.A2.slots_against_fixed_max": fr(a2["slots_ok"], 558),
    })
    for tag, folder in (("B4", RUN_B4), ("B4b", RUN_B4B), ("Btr", RUN_BTR), ("B10", RUN_B10)):
        b, _, bc = run_counts(folder)
        out.update({
            "runs.%s.turns" % tag: str(b["turns"]), "runs.%s.gate_numbers" % tag: str(b["gate_after"]),
            "runs.%s.unverified" % tag: fr(b["unv_after"], b["gate_after"]),
            "runs.%s.oracle_turns" % tag: fr(b["oracle_turns_ok"], b["oracle_turns"]), "runs.%s.oracle_slots" % tag: fr(b["slots_ok"], b["slots"]),
            "runs.%s.compare_turns_with_4_slots" % tag: str(bc[4]),
            "runs.%s.scorer_turns" % tag: fr(b["scorer_ok"], b["turns"]), "runs.%s.scorer_slots" % tag: fr(b["scorer_found"], b["scorer_must"]),
            "runs.%s.decide_calls" % tag: str(b["decisions"]),
            "runs.%s.tool_calls_invalid" % tag: fr(b["tool_invalid"], b["tool_calls"]),
            "runs.%s.audited_calls" % tag: str(b["audited"]),
            "runs.%s.numbers_in_not_available_turns" % tag: str(b["na_numbers"]),
        })
    return out

def bykind_table():
    """The markdown table of the gate-checked numbers per turn kind, one row per stored run (first drafts for the 27B)."""
    runs = [("27B, 2026-10-09 (first drafts)", RUN_A1), ("27B, 2026-10-09b", RUN_A2), ("harness, gold, step 4 (`parameter_asked`)", RUN_B4),
            ("harness, gold, step 4b (`asked_<key>`)", RUN_B4B), ("harness, trained 0.8B (step 5)", RUN_BTR), ("harness, gold, 2026-10-10 (after the fixes)", RUN_B10)]
    head = ["run"] + list(KINDS) + ["all"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name, folder in runs:
        c, per_kind, _ = run_counts(folder)
        lines.append("| " + " | ".join([name] + [str(per_kind[k]) for k in KINDS] + [str(sum(per_kind.values()))]) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- rows of the decision datasets
V1_SCRIPTED_KINDS, V1_EXTRA_KINDS, V1_PARAPHRASES = 8, 4, 2     # decision/make_dataset.py at commit bc47025 (dataset v1)

def rows_per_exercise(path):
    c = collections.Counter()
    with open(need(path), encoding="utf-8") as f:
        for line in f:
            if line.strip(): c[json.loads(json.loads(line)["factors"])["exercise"]] += 1
    return c

def group_rows():
    v2 = sum((1 if k in scripts.KINDS else 0) + md.PARAPHRASES[k] for k in md.KINDS)
    out = {
        "rows.v1_per_exercise": str(V1_SCRIPTED_KINDS * (1 + V1_PARAPHRASES) + V1_EXTRA_KINDS * (V1_PARAPHRASES + 1)),
        "rows.v2_per_exercise": str(v2),
        "rows.v2_scripted_kinds": str(len(scripts.KINDS)), "rows.v2_extra_kinds": str(len(md.EXTRA_KINDS)), "rows.v2_kinds": str(len(md.KINDS)),
        "rows.v2_paraphrases_scripted_kinds": str(md.PARAPHRASES["import_nca"]),
        "rows.v2_paraphrases_extra_kinds": str(md.PARAPHRASES["nca_other"]),
        "rows.v2_paraphrases_nca_oneline": str(md.PARAPHRASES["nca_oneline"]),
        "rows.v2_paraphrase_rows": str(sum(md.PARAPHRASES.values())),
        "rows.v2_heldout_wordings_per_exercise": str(len(md.KINDS)),
        "rows.v2_heldout_both_max_per_exercise": str(2 * len(md.KINDS)),
        "rows.v2_wording_pools": str(len(md.KINDS)),
        "rows.v2_wordings_total": str(len(md.WORDING_BY_ID)),
    }
    return out

def group_rows_files():
    out = {}
    for name, key in (("train", "train"), ("heldout_exercises", "heldout_exercises"), ("bench", "bench"), ("heldout_wordings", "heldout_wordings")):
        c = rows_per_exercise(os.path.join(DATA, name + ".jsonl"))
        out["rows.%s_rows" % key] = str(sum(c.values())); out["rows.%s_exercises" % key] = str(len(c))
        out["rows.%s_per_exercise" % key] = "/".join(str(v) for v in sorted(set(c.values())))
    c = rows_per_exercise(os.path.join(DATA, "heldout_both.jsonl"))
    out["rows.heldout_both_rows"] = str(sum(c.values())); out["rows.heldout_both_exercises"] = str(len(c))
    out["rows.heldout_both_per_exercise"] = "/".join(str(v) for v in sorted(set(c.values())))
    scripted = collections.Counter()
    with open(os.path.join(DATA, "bench.jsonl"), encoding="utf-8") as f:
        for line in f:
            fa = json.loads(json.loads(line)["factors"])
            if fa["scripted_wording"]: scripted[fa["kind"]] += 1
    out["rows.bench_scripted_rows"] = str(sum(scripted.values())); out["rows.bench_scripted_kinds"] = ",".join(sorted(scripted))
    return out

def group_rows_v1():
    p = os.path.join(DATA, "heldout.jsonl")
    c = rows_per_exercise(p)
    if sum(c.values()) != 720 or set(c.values()) != {36}:
        raise unittest.SkipTest("decision/data/heldout.jsonl is not the v1 file (720 rows, 36 per exercise)")
    return {"rows.v1_heldout_rows": str(sum(c.values())), "rows.v1_heldout_exercises": str(len(c)), "rows.v1_heldout_per_exercise": "36"}


# ---------------------------------------------------------------- decisions, complete vectors, ECE
def vector_stats(rows):
    n = ok = bad_rows = 0; errs = collections.Counter(); pos = tp = 0
    for r in rows:
        w = 0
        for q, g in r["gold"].items():
            n += 1
            if r["pred"][q]["label"] == g: ok += 1
            else: errs[q] += 1; w += 1
        bad_rows += w > 0
        if r["gold"]["is_not_available"] == "true":
            pos += 1; tp += r["pred"]["is_not_available"]["label"] == "true"
    return {"n": n, "ok": ok, "rows": len(rows), "rows_ok": len(rows) - bad_rows, "errs": errs, "pos": pos, "tp": tp}

def ece4(rows): return "%.4f" % z.calibration(rows)[1]

def group_decisions():
    out = {}
    held = jload(os.path.join(STEP3, "unsloth-qwen35-0.8b-d01-merged-heldout-cuda.json"))["rows"]
    bench = jload(os.path.join(STEP3, "unsloth-qwen35-0.8b-d01-merged-bench-cuda.json"))["rows"]
    h, b = vector_stats(held), vector_stats(bench)
    out.update({
        "decisions.heldout_rows_x_questions": "%d*%d=%d" % (len(held), len(held[0]["gold"]), h["n"]),
        "decisions.ood_requests_x_questions": "%d*%d=%d" % (74, 20, 74 * 20),
        "decisions.harness_calls_x_questions": "%d*%d=%d" % (225, 20, 225 * 20),
        "decisions.bench_rows_x_questions": "%d*%d=%d" % (len(bench), len(bench[0]["gold"]), b["n"]),
        "decisions.heldout_questions_right": fr(h["ok"], h["n"]), "decisions.bench_questions_right": fr(b["ok"], b["n"]),
        "decisions.heldout_complete_vectors": fr(h["rows_ok"], h["rows"]), "decisions.bench_complete_vectors": fr(b["rows_ok"], b["rows"]),
        "decisions.heldout_complete_vectors_pct": pct(h["rows_ok"], h["rows"]), "decisions.bench_complete_vectors_pct": pct(b["rows_ok"], b["rows"]),
        "decisions.heldout_errors_questions": ",".join(sorted(h["errs"])), "decisions.bench_errors_questions": ",".join(sorted(b["errs"])),
        "decisions.heldout_is_not_available_found": fr(h["tp"], h["pos"]), "decisions.bench_is_not_available_found": fr(b["tp"], b["pos"]),
        "decisions.heldout_questions_pct": pct(h["ok"], h["n"]),
    })
    return out

def group_harness_vectors():
    def dec(folder):
        out = {}
        for d in run_exercises(folder):
            for t in d["turns"]:
                for i, x in enumerate(t["decisions"]): out[(d["id"], t["turn"], i)] = (t["kind"], x["answers"])
        return out
    g, m = dec(RUN_B4B), dec(RUN_BTR)
    if set(g) != set(m): raise unittest.SkipTest("the gold run and the trained run do not have the same decide calls")
    cells = collections.Counter(); calls = collections.Counter()
    for k in g:
        diff = [q for q in g[k][1] if g[k][1][q] != m[k][1].get(q)]
        for q in diff: cells[(g[k][0], q)] += 1
        if diff: calls[g[k][0]] += 1
    n_diff = sum(calls.values())
    return {
        "harness.decide_calls": str(len(g)), "harness.decide_calls_extra_compare": str(len(g) - 200),
        "harness.cells_differing": fr(sum(cells.values()), len(g) * 20),
        "harness.calls_differing": fr(n_diff, len(g)),
        "harness.cells_is_not_available": str(cells[("not_available", "is_not_available")]),
        "harness.cells_compare_pair": str(cells[("compare", "compare_pair")]),
        "harness.complete_vectors_answerable": fr(200 - calls["not_available"], 200),
        "harness.complete_vectors_all_calls": fr(len(g) - n_diff, len(g)),
    }

def group_errors_by_kind():
    rows = {}
    with open(need(os.path.join(DATA, "heldout.jsonl")), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line); rows[r["id"]] = json.loads(r["factors"])
    if len(rows) != 720: raise unittest.SkipTest("decision/data/heldout.jsonl is not the v1 file")
    held = jload(os.path.join(STEP3, "unsloth-qwen35-0.8b-d01-merged-heldout-cuda.json"))["rows"]
    bad = [r for r in held if any(r["pred"][q]["label"] != g for q, g in r["gold"].items())]
    if any(r["id"] not in rows for r in bad): raise unittest.SkipTest("row ids of the run are not those of decision/data/heldout.jsonl")
    kinds = collections.Counter(rows[r["id"]]["kind"] for r in bad)
    exs = {rows[r["id"]]["exercise"] for r in bad}
    n_na = sum(rows[r["id"]]["kind"] == "not_available" for r in held)
    return {"errors.heldout_wrong_rows": str(len(bad)), "errors.heldout_wrong_rows_not_available_kind": str(kinds["not_available"]),
            "errors.heldout_wrong_rows_other_kind": str(len(bad) - kinds["not_available"]),
            "errors.heldout_wrong_rows_distinct_exercises": str(len(exs)), "errors.heldout_not_available_rows": str(n_na)}

def group_ece():
    held = jload(os.path.join(STEP3, "unsloth-qwen35-0.8b-d01-merged-heldout-cuda.json"))["rows"]
    bench = jload(os.path.join(STEP3, "unsloth-qwen35-0.8b-d01-merged-bench-cuda.json"))["rows"]
    h = vector_stats(held)
    const1 = h["errs"] and sum(h["errs"].values()) / h["n"]       # ECE of a classifier that is 100 % sure of every answer
    out = {"ece.heldout_trained": ece4(held), "ece.bench_trained": ece4(bench),
           "ece.confidence_one_everywhere": "%s=%.6f" % (fr(sum(h["errs"].values()), h["n"]), const1),
           "ece.confidence_one_everywhere_4dp": "%.4f" % const1,
           "ece.heldout_trained_6dp": "%.6f" % z.calibration(held)[1]}
    for name, f, key in (("600M_heldout", "d1-omni-600M-heldout", "ece.d1_600M_heldout_720"), ("600M_bench", "d1-omni-600M-bench", "ece.d1_600M_bench_900"),
                         ("600M_heldout_s", "d1-omni-600M-heldout-limit120-stride6", "ece.d1_600M_heldout_120"),
                         ("3B_heldout_s", "d1-3B-heldout-limit120-stride6", "ece.d1_3B_heldout_120"),
                         ("600M_bench_s", "d1-omni-600M-bench-limit112-stride8", "ece.d1_600M_bench_112"),
                         ("3B_bench_s", "d1-3B-bench-limit112-stride8", "ece.d1_3B_bench_112")):
        out[key] = "%.3f" % z.calibration(jload(os.path.join(STEP2, f + ".json"))["rows"])[1]
    return out

def group_d1():
    def rows(f): return jload(os.path.join(STEP2, f + ".json"))["rows"]
    def index(r): return int(r["id"].rsplit("_", 1)[1])
    def acc(rs):
        s = vector_stats(rs); return s["ok"], s["n"]
    h3, b3 = rows("d1-3B-heldout-limit120-stride6"), rows("d1-3B-bench-limit112-stride8")
    h6, b6 = rows("d1-omni-600M-heldout-limit120-stride6"), rows("d1-omni-600M-bench-limit112-stride8")
    hf, bf = rows("d1-omni-600M-heldout"), rows("d1-omni-600M-bench")
    out = {
        "d1.heldout_subsample_rows": str(len(h3)), "d1.heldout_stride": "6", "d1.heldout_rule_holds": str([index(r) for r in h3] == list(range(0, 720, 6))),
        "d1.heldout_first_last_ids": "%s..%s" % (h3[0]["id"], h3[-1]["id"]),
        "d1.bench_subsample_rows": str(len(b3)), "d1.bench_stride": "8", "d1.bench_rule_holds": str([index(r) for r in b3] == list(range(0, 8 * 112, 8))),
        "d1.bench_first_last_ids": "%s..%s" % (b3[0]["id"], b3[-1]["id"]),
        "d1.bench_rows_in_file": str(len(bf)), "d1.bench_stride_candidates": str(len(range(0, len(bf), 8))), "d1.bench_row_cut_by_limit": "be_pk_analysis_requests_%06d" % (8 * 112),
        "d1.questions_per_row": str(len(h3[0]["gold"])),
        "d1.same_rows_both_models": str([r["id"] for r in h3] == [r["id"] for r in h6] and [r["id"] for r in b3] == [r["id"] for r in b6]),
        "d1.3B_heldout_subsample_acc": fr(*acc(h3)), "d1.3B_bench_subsample_acc": fr(*acc(b3)),
        "d1.600M_heldout_subsample_acc": fr(*acc(h6)), "d1.600M_heldout_full_acc": fr(*acc(hf)),
        "d1.600M_bench_subsample_acc": fr(*acc(b6)), "d1.600M_bench_full_acc": fr(*acc(bf)),
        "d1.600M_heldout_subsample_pct": pct(*acc(h6)), "d1.600M_heldout_full_pct": pct(*acc(hf)),
        "d1.600M_bench_subsample_pct": pct(*acc(b6)), "d1.600M_bench_full_pct": pct(*acc(bf)),
        "d1.3B_heldout_subsample_pct": pct(*acc(h3)), "d1.3B_bench_subsample_pct": pct(*acc(b3)),
        "d1.heldout_subsample_is_not_available_true": fr(vector_stats(h3)["pos"], len(h3)),
        "d1.bench_subsample_is_not_available_true": fr(vector_stats(b3)["pos"], len(b3)),
        "d1.heldout_full_is_not_available_true": fr(vector_stats(hf)["pos"], len(hf)),
        "d1.bench_full_is_not_available_true": fr(vector_stats(bf)["pos"], len(bf)),
    }
    return out

def group_d1_coverage():
    ex = {}
    with open(need(os.path.join(DATA, "heldout.jsonl")), encoding="utf-8") as f:
        for i, line in enumerate(f):
            r = json.loads(line); ex[i] = (r["id"], json.loads(r["factors"])["exercise"])
    if len(ex) != 720: raise unittest.SkipTest("decision/data/heldout.jsonl is not the v1 file")
    h3 = jload(os.path.join(STEP2, "d1-3B-heldout-limit120-stride6.json"))["rows"]
    if any(ex[int(r["id"].rsplit("_", 1)[1])][0] != r["id"] for r in h3): raise unittest.SkipTest("heldout.jsonl is not the file the 3B was run on")
    c = collections.Counter(ex[int(r["id"].rsplit("_", 1)[1])][1] for r in h3)
    return {"d1.heldout_subsample_exercises": str(len(c)), "d1.heldout_subsample_rows_per_exercise_min": str(min(c.values())),
            "d1.heldout_subsample_rows_per_exercise_max": str(max(c.values())), "d1.heldout_rows_per_exercise_expected": "6"}


# ---------------------------------------------------------------- grouping, illustrations
def group_stats():
    ood = os.path.join(AGENT, "decision", "ood", "requests.jsonl")
    with open(need(ood, "the reviewer's frozen requests"), encoding="utf-8") as f: n = sum(1 for line in f if line.strip())
    return {"stats.ood_requests": str(n),
            "stats.upper_bound_0_of_926": "%.2f" % (300.0 / 926), "stats.upper_bound_0_of_827": "%.2f" % (300.0 / 827),
            "stats.upper_bound_0_of_25_exercises": "%.3f" % (1 - 0.05 ** (1 / 25.0)),
            "stats.wording_families": str(len(md.FAMILIES))}


GROUPS = {"bench": group_bench, "runs": group_runs, "rows": group_rows, "rows_files": group_rows_files, "rows_v1": group_rows_v1,
          "decisions": group_decisions, "harness_vectors": group_harness_vectors, "errors": group_errors_by_kind, "ece": group_ece,
          "d1": group_d1, "d1_coverage": group_d1_coverage, "stats": group_stats}
PREFIXES = ("bench.", "runs.", "rows.", "decisions.", "harness.", "errors.", "ece.", "d1.", "stats.")

# Figures no stored file recomputes: key -> (value, file, sentence the file must still contain)
QUOTED = {
    "quoted.ood_complete_vectors": ("4/74", "decision/README.md", "4/74"),
    "quoted.ood_gold_vectors": ("74/74", "decision/README.md", "74/74 requests all right"),
    "quoted.ood_decisions_right": ("1337/1480", "decision/README.md", "1337/1480"),
    "quoted.ood_ece": ("0.093", "decision/README.md", "ECE 0.093"),
    "quoted.ood_decisions_below_0.9": ("15", "decision/README.md", "the 15 decisions below 0.9"),
    "quoted.ood_decisions_at_or_above_0.9": ("1465", "decision/README.md", "the 1465 above"),
    "quoted.unsloth_calibrate_ece": ("0.00012", "decision/runs/2026-10-09-train-qwen35-0.8b/report.md", "ECE 0.00012"),
    "quoted.unsloth_calibrate_record_accuracy": ("0.9958", "decision/runs/2026-10-09-train-qwen35-0.8b/report.md", "record accuracy (all 20 answers of a row right) 0.9958"),
    "quoted.unsloth_calibrate_rows": ("720", "decision/runs/2026-10-09-train-qwen35-0.8b/report.md", "`calibrate` on 720 held-out rows"),
    "quoted.reviewer_verbatim_heldout_requests": ("720/720", "decision/ood/REVIEW.md", "720 / 720 held-out rows"),
    "quoted.reviewer_distinct_requests": ("83", "decision/ood/REVIEW.md", "83 distinct requests"),
    "quoted.reviewer_ece_counterexample_counts": ("14386/14400", "../notes/review-astra-2026-10-09.md", "1 - 14,386/14,400"),
    "quoted.astra_rounded_bound": ("0.113", "../notes/review-astra-2026-10-09.md", "about 11.3%"),
    "quoted.ood_requests_on_benchmark_exercises": ("58", "decision/ood/REVIEW.md", "74 lines, 58 on the 25 committed"),
    "quoted.ood_requests_on_invented_exercises": ("16", "decision/ood/REVIEW.md", "16 on 12 invented exercises"),
    "quoted.ood_first_requests": ("62", "decision/README.md", "On the 62 first requests"),
    "quoted.ood_follow_ups": ("12", "decision/README.md", "On the 12 follow-up turns"),
    "quoted.ood_wrong_decisions": ("143", "decision/README.md", "143 wrong decisions on 70 of the 74 requests"),
    "quoted.ood_wrong_decisions_at_least_0.9": ("135", "decision/README.md", "135 of the 143 have a probability"),
    "quoted.hallucination_ci_exercises_resampled": ("7.1-9.1", "docs/benchmark.md", "7.1-9.1 %"),
    "quoted.oracle_turns_ci_exercises_resampled": ("89.7-100", "docs/benchmark.md", "89.7-100 %"),
    "quoted.ex07_wrong_option_slots": ("10", "docs/benchmark.md", "`wrong_option`, 10 numbers"),
    "quoted.majority_baseline_heldout": ("84.6", "decision/README.md", "84.6 %"),
    "quoted.v1_train_rows": ("1980", "decision/README.md", "`train.jsonl` 1980 rows / 55 exercises"),
    "quoted.bonsai_heldout_rows": ("100", "decision/README.md", "100 held-out rows (5 per exercise, 20 exercises)"),
    "quoted.ood_requests_complete_vectors_27B_per_row": ("7/74", "decision/README.md", "7/74"),
    "quoted.heldout_100_complete_vectors_0.8B": ("97/100", "decision/README.md", "97/100"),
}


def read_ledger():
    need(LEDGER, "decision/LEDGER.md")
    with open(LEDGER, encoding="utf-8") as f: return f.read()

def register_of(text):
    if BEGIN not in text or END not in text: raise AssertionError("LEDGER.md has no register block")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    reg = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith(("```", "#")): continue
        k, _, v = line.partition(" = ")
        assert k not in reg, "key twice in the register: " + k
        reg[k.strip()] = v.strip()
    return reg

def prose_of(text):
    """The ledger without its register block and without the generated per-kind table (their numbers are checked by key / by rebuild)."""
    a, rest = text.split(BEGIN, 1); rest = rest.split(END, 1)[1]
    text = a + rest
    if BYKIND_BEGIN in text: text = text.split(BYKIND_BEGIN, 1)[0] + text.split(BYKIND_END, 1)[1]
    return text


class TestLedger(unittest.TestCase):
    def check_group(self, name):
        try: got = GROUPS[name]()
        except unittest.SkipTest as e:
            print("test_ledger: group %s skipped: %s" % (name, e), file=sys.stderr); raise
        reg = register_of(read_ledger())
        for k, v in got.items():
            self.assertIn(k, reg, "%s is recomputed but absent from the register of LEDGER.md" % k)
            self.assertEqual(reg[k], v, "%s: LEDGER.md says %r, the files give %r" % (k, reg[k], v))

    def test_bench_turns_and_slots(self): self.check_group("bench")
    def test_stored_runs(self): self.check_group("runs")
    def test_rows_per_exercise_formula(self): self.check_group("rows")
    def test_rows_per_exercise_files(self): self.check_group("rows_files")
    def test_rows_per_exercise_v1_file(self): self.check_group("rows_v1")
    def test_decisions_and_complete_vectors(self): self.check_group("decisions")
    def test_harness_complete_vectors(self): self.check_group("harness_vectors")
    def test_errors_by_turn_kind(self): self.check_group("errors")
    def test_ece(self): self.check_group("ece")
    def test_d1_subsample(self): self.check_group("d1")
    def test_d1_subsample_exercise_coverage(self): self.check_group("d1_coverage")
    def test_grouping_figures(self): self.check_group("stats")

    def test_bykind_table_is_current(self):
        text = read_ledger()
        self.assertIn(BYKIND_BEGIN, text); self.assertIn(BYKIND_END, text)
        block = text.split(BYKIND_BEGIN, 1)[1].split(BYKIND_END, 1)[0].strip()
        self.assertEqual(block, bykind_table(), "the per-kind table of LEDGER.md is not the one the stored runs give")

    def test_every_register_key_is_checked(self):
        reg = register_of(read_ledger())
        for k, v in reg.items():
            if k in QUOTED:
                self.assertEqual(v, QUOTED[k][0], "%s: LEDGER.md and the quoted table of the test disagree" % k)
            else:
                self.assertTrue(k.startswith(PREFIXES), "%s is in the register but neither recomputed nor quoted" % k)
        # a recomputed key may not hide as a quoted one, and every quoted key must be in the register
        for k in QUOTED: self.assertIn(k, reg, "%s is quoted by the test but absent from the register" % k)

    def test_every_recomputed_key_is_in_the_register(self):
        reg = register_of(read_ledger()); missing = []
        for name, fn in GROUPS.items():
            try: got = fn()
            except unittest.SkipTest: continue
            missing += [k for k in got if k not in reg]
        self.assertEqual(missing, [], "keys the test recomputes but LEDGER.md does not register")

    def test_quoted_sentences_are_still_in_their_reports(self):
        for k, (v, path, sentence) in QUOTED.items():
            p = os.path.normpath(os.path.join(AGENT, path))
            if not os.path.exists(p): print("test_ledger: %s skipped, %s not on disk" % (k, path), file=sys.stderr); continue
            with open(p, encoding="utf-8") as f: self.assertIn(sentence, f.read(), "%s: %r is no longer in %s" % (k, sentence, path))

    def test_every_fraction_of_the_prose_is_registered(self):
        reg = register_of(read_ledger()); text = prose_of(read_ledger())
        known = {re.sub(r"[\s,]", "", v) for v in reg.values()}
        known |= {re.sub(r"[\s,]", "", p) for v in reg.values() for p in re.split(r"[=.]", v) if "/" in p}
        unknown = []
        for m in re.finditer(r"(?<![\w./])(\d[\d,]*)\s?/\s?(\d[\d,]*)(?![\w/])", text):
            tok = re.sub(r"[\s,]", "", m.group(0))
            if tok not in known: unknown.append(m.group(0))
        self.assertEqual(sorted(set(unknown)), [], "fractions of the prose that no register value holds")

    def test_register_values_are_arithmetic_consistent(self):
        reg = register_of(read_ledger())
        for k, v in reg.items():
            m = re.fullmatch(r"(\d+)\*(\d+)=(\d+)", v)
            if m: self.assertEqual(int(m.group(1)) * int(m.group(2)), int(m.group(3)), k)


def print_register():
    for name, fn in GROUPS.items():
        try: got = fn()
        except unittest.SkipTest as e:
            print("# group %s skipped: %s" % (name, e)); continue
        for k, v in got.items(): print("%s = %s" % (k, v))
    for k, (v, _, _) in QUOTED.items(): print("%s = %s" % (k, v))
    print(); print(bykind_table())


if __name__ == "__main__":
    if "--print-register" in sys.argv: print_register()
    else: unittest.main()
