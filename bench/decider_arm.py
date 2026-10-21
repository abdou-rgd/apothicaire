"""The decider-only arm of the frozen set: no language model on the answer path (bench/NO_LM_ARM.md).

A decision model answers the 20 closed questions of decision/make_dataset.py on each turn, the deterministic harness of
decision/harness.py calls Caladrius and renders the engine's values from fixed French templates. No 27B call, no OptChat summary,
no generated number. The turns are the frozen script of bench/run_frozen.py (the same wordings, the same wording seed, the same
expectations), the records are the ones decision/run_harness.py writes, then scored by the rubric of FROZEN_SET.md §6.2 and given
their outcome class (§6.1), so `run_frozen.py analyse` reads them next to the gate v1 and v2 runs under the configuration name
`nolm`.

The harness runs with its three switches on (`engine_units`: the dose unit goes to Caladrius as the agent's client sends it, so CL and
V are in L/time and L like the frozen gold; `free_layout`: the table of the first message may sit anywhere in it;
`extrapolation_verdict`: the extrapolated percentage is followed by the engine's verdict on it, from its quality flag).

  python bench/run_frozen.py run --tier demo --gate nolm --seeds 1,2,3 --wordings PATH --wording-seed N \\
      --decider decider_unsloth:decide --decider-model decision/models/qwen35-0.8b-d01-v2/adapters     on the PC (GPU)
  python bench/run_frozen.py run --tier dev --gate nolm --seeds 1 --stub --out DIR                     dry run, no model (cloud)

`--stub` replaces the decision model with `StubDecider`, which answers each turn's gold decisions from the script (the turn kind,
the route, the parameters the scripted wording asks). Its run is the ceiling of the harness on these exercises: what the arm scores
when every decision is right. It says nothing about a decision model and is never confirmatory.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
DECISION = os.path.join(AGENT, "decision")
for p in (AGENT, DECISION):
    if p not in sys.path: sys.path.insert(0, p)
import make_dataset as md  # noqa: E402
import run_harness  # noqa: E402
from bench import make_exercises as mk, run_bench as rb, scripts  # noqa: E402

ARM = "nolm"
HARNESS_KW = {"engine_units": True, "free_layout": True, "extrapolation_verdict": True}

class StubDecider:
    """decide(state, questions) answering the gold decisions of the current turn (set by on_turn), as make_dataset.build_row labels a
    scripted turn: the analysis of the kind, the exercise's route, linear on the NCA turn and lin-up/log-down on the compare turn, the
    parameters of make_dataset.scripted_params, a dose with its unit, `is_not_available` on the not-available turn, the pair of the
    two analyses (the linear one first, the reference) once both exist."""
    name = "stub-gold-decisions"

    def __init__(self):
        self.meta = self.turn = None
        self.last_info = None

    def begin(self, meta):
        self.meta = meta

    def on_turn(self, k, turn):
        self.turn = turn

    def __call__(self, state, questions):
        kind, meta = self.turn["kind"], self.meta
        route_kind = scripts.kind_of(meta)
        what = self.turn["expect"].get("not_calculated_parameter")
        params = md.scripted_params(kind, route_kind, what)
        auc = "linear" if kind == "import_nca" else md.AUC_METHOD_OF.get(kind, "not_applicable")
        pairs = questions["compare_pair"]["criteria"]
        ids = sorted(a["id"] for a in state["analyses"])
        pair = "not_applicable"
        if kind == "compare": pair = f"{ids[0]}+{ids[1]}" if len(ids) >= 2 and f"{ids[0]}+{ids[1]}" in pairs else "none_available"
        out = {"analysis": md.ANALYSIS_OF[kind], "route": route_kind, "auc_method": auc,
               **{f"asked_{p}": "true" if p in params else "false" for p in md.PARAMETERS},
               "dose_has_unit": "true", "is_not_available": "true" if kind == "not_available" else "false", "compare_pair": pair}
        return {q: out[q] for q in questions}

def decision_check(turn, meta, st):
    """The decisions of one turn against the gold decisions of its kind (StubDecider on the same analyses and questions): per ask, the
    questions answered otherwise. The first ask of a compare turn, made before the re-run, has no pair to find (its `compare_pair` is
    unused by the harness) and is not counted. Attributes a failed turn to the decision model or to the deterministic part."""
    stub = StubDecider(); stub.begin(meta); stub.on_turn(0, st)
    asks = turn.get("decisions") or []
    out = {"asks": 0, "asks_right": 0, "wrong": []}
    for j, d in enumerate(asks):
        if st["kind"] == "compare" and j == 0 and len(asks) > 1: continue
        ids = d.get("analyses_in_state") or []
        qs = md.questions_for(sorted(ids))
        gold = stub({"analyses": [{"id": i} for i in ids]}, qs)
        bad = [{"question": q, "model": d["answers"].get(q), "gold": g} for q, g in gold.items() if d["answers"].get(q) != g]
        out["asks"] += 1; out["asks_right"] += not bad
        out["wrong"] += [{"ask": j + 1, **b} for b in bad]
    return out

def load_decider(spec, model=None):
    """The decision model: `module:function` as decision/run_harness.py loads it (`model`: the folder for decider_unsloth, $D01_MODEL)."""
    if model: os.environ["D01_MODEL"] = os.path.abspath(model)
    return run_harness.load_decider(spec)

def run_one(ex_dir, out, seed, script, decide, stub=None):
    """One exercise on one seed through the harness; the record of decision/run_harness.py with the rubric and the outcome of each turn
    (run_bench.attach_rubric), the configuration name and the seed. A decision model has no sampler: the seed only labels the run (its
    repeats show whether the forward passes are deterministic on the machine)."""
    meta, csv_text = mk.load(ex_dir)
    if stub is not None: stub.begin(meta)
    try:
        rec = run_harness.run_exercise(ex_dir, out, decide, script=script, harness_kw=HARNESS_KW,
                                       on_turn=stub.on_turn if stub is not None else None)
    except Exception as e:                  # the engine did not start: 8 ERROR turns, the exercise stays in every denominator (§6.1)
        rec = rb.planned_error_record(meta, script, f"{type(e).__name__}: {e}")
    for k, (t, st) in enumerate(zip(rec["turns"], script)):
        t.setdefault("max_tool_rounds", 8)
        rb.attach_rubric(t, meta, st, csv_text, rec["turns"][:k])
        if "decisions" in t: t["decision_check"] = decision_check(t, meta, st)
    rec.update(gate=ARM, seed=seed)
    with open(os.path.join(out, meta["id"] + ".json"), "w", encoding="utf-8") as f: json.dump(rec, f, ensure_ascii=False, indent=1)
    return rec
