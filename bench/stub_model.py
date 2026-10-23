"""A deterministic stand-in for the language model, for the dry run of the frozen-set pipeline (no GPU, no llama-server).

It plays the part of llama-server's chat endpoint for one exercise at a time: it calls the tools a correct assistant calls
(data_import and nca_run on turn 1; nca_run with lin-up/log-down and analysis_compare on the compare turn), reads the ids and
the gate v2 references from the tool results it is shown, and answers from the gold of meta.json: numbers for gate v1 (the
canonical answers of bench/mutations.py), `{{call_N.param}}` references for gate v2 and for gate v3 (whose grammar, sent with a
regeneration, it only records in `grammars`). The real Apothicaire client, the real caladrius-mcp, the gates, the rubric, the
report and the analysis all run unchanged around it.

With `error_rate` > 0 it errs on purpose, on a seeded draw per (gate, seed, exercise, turn): under gate v1 a value multiplied
by 1.37 (the gate flags it, the regeneration repeats it, the badge is shown); under gate v2 and v3 a reference to the wrong parameter
(the gate renders it, the rubric rejects it). This is only there to give the statistics mixed outcomes across seeds and
gates; nothing measured with the stub says anything about a model.
"""
import json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
from bench import mutations, scripts  # noqa: E402

_WS_RE = re.compile(r'"worksheet":\{"id":(\d+)')
_AN_RE = re.compile(r'"analysis":(\d+)')
_METHOD_RE = re.compile(r'"auc_method":"(\w+)"')
_REF_RE = re.compile(r'^\{"ref":"(call_\d+)"')

def _route_args(meta):
    r = meta["route"]
    if isinstance(r, dict): return {"route": "iv_infusion", "infusion_duration": r["iv_infusion"]["duration"]}
    return {"route": r}

class StubModel:
    def __init__(self, gate_version="v1", seed=0, error_rate=0.0):
        self.gate_version, self.seed, self.error_rate = gate_version, seed, error_rate
        self.last, self.total_slots, self.calls = {}, 2, 0
        self.grammars = []                                           # the grammar of each request that came with one (gate v3)
        self.meta = self.csv = self.turn = None
        self.plan, self.answer_text, self.erred = [], "", False

    # -- driven by the runner
    def begin(self, meta, csv_text):
        self.meta, self.csv = meta, csv_text

    def on_turn(self, k, turn):
        """Called by run_bench.run_exercise before each turn: the actions of this turn, in order."""
        self.turn = turn
        kind = turn["kind"]
        self.plan = (["data_import", "nca_linear"] if kind == "import_nca" else
                     ["nca_lud", "compare"] if kind == "compare" else []) + ["answer"]
        rng = random.Random(f"{self.gate_version}:{self.seed}:{self.meta['id']}:{k}")
        self.erred = self.error_rate > 0 and rng.random() < self.error_rate and kind not in ("recall", "not_available")

    # -- the chat endpoint
    def chat(self, messages, slot=0, tools=None, max_tokens=512, think=False, **kw):
        self.calls += 1
        if kw.get("grammar") is not None: self.grammars.append(kw["grammar"])
        self.last = {"wall_s": 0.0, "prompt_tokens": 1000, "completion_tokens": 10, "prompt_eval_n": 10, "cache_n": 990,
                     "prompt_ms": 0, "predicted_ms": 0, "gen_tps": None, "finish_reason": "stop"}
        if slot == 1 or not self.plan:                               # a compaction call, or a regeneration after the gate
            return {"role": "assistant", "content": self.answer_text or "1: résumé"}
        step = self.plan.pop(0)
        seen = self._read_tools(messages)
        if step == "data_import":
            imp, _ = mutations.mk.tool_arguments(self.meta, self.csv)
            return self._call("data_import", imp)
        if step in ("nca_linear", "nca_lud"):
            args = {"worksheet": seen["worksheet"] or 1, "dose": self.meta["dose"]["amount"], **_route_args(self.meta),
                    "dose_unit": self.meta["dose"]["unit"], "options": {"auc_method": "linear" if step == "nca_linear" else "lin_up_log_down"}}
            return self._call("nca_run", args)
        if step == "compare":
            return self._call("analysis_compare", {"a": seen["analysis"].get("linear", 1), "b": seen["analysis"].get("lin_up_log_down", 2)})
        self.answer_text = self._answer(seen)
        return {"role": "assistant", "content": self.answer_text}

    # -- helpers
    def _call(self, name, args):
        return {"role": "assistant", "content": "", "tool_calls": [{"id": f"stub{self.calls}", "type": "function",
                                                                     "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}

    @staticmethod
    def _read_tools(messages):
        """Worksheet id, analysis id per AUC method and the gate v2 reference of each result, from the tool messages shown."""
        out = {"worksheet": None, "analysis": {}, "ref": {}}
        for m in messages:
            if m.get("role") != "tool": continue
            c = m.get("content") or ""
            ref = _REF_RE.match(c)
            ws = _WS_RE.search(c)
            if ws: out["worksheet"] = int(ws.group(1))
            if '"options_used"' in c:                                 # an NCA digest
                a, meth = _AN_RE.search(c), _METHOD_RE.search(c)
                if a and meth:
                    out["analysis"][meth.group(1)] = int(a.group(1))
                    if ref: out["ref"][meth.group(1)] = ref.group(1)
            elif '"parameters"' in c and '"a":{' in c and ref:       # an analysis_compare digest
                out["ref"]["compare"] = ref.group(1)
        return out

    def _answer(self, seen):
        turn, meta = self.turn, self.meta
        if self.gate_version not in ("v2", "v3") or turn["kind"] in ("recall", "not_available"):
            text = mutations.canonical(turn, meta)
            if self.erred:
                items, _ = scripts.score.rubric_items(turn, meta)
                first = items[0] if turn["kind"] != "compare" else next(i for i in items if i["method"] == "lin_up_log_down")
                v = mutations.num(first["value"])
                text = text.replace(f"= {v}", f"= {mutations.num(first['value'] * 1.37)}", 1)
            return text
        return self._answer_v2(seen)

    def _answer_v2(self, seen):
        turn, meta = self.turn, self.meta
        lin, lud, cmp = seen["ref"].get("linear"), seen["ref"].get("lin_up_log_down"), seen["ref"].get("compare")
        items, alts = scripts.score.rubric_items(turn, meta)
        if turn["kind"] == "compare":
            auc = lin if self.erred else lud                                    # the linear AUC under the log-down label
            rows = [("AUC(0-tlast) lin-up/log-down", f"{{{{{auc}.auclast}}}}"), ("Différence", f"{{{{{cmp}.auclast.difference}}}}"),
                    ("Pourcentage", f"{{{{{cmp}.auclast.percent}}}}")]
        else:
            keys = [i["key"] for i in items]
            if self.erred and len(keys) >= 2: keys = [keys[1]] + keys[1:]          # the second parameter under the first label
            elif self.erred: keys = ["tmax" if keys[0] != "tmax" else "cmax"]
            rows = [(i["label"], f"{{{{{lin}.{k}}}}}") for i, k in zip(items, keys)]
        lines = [f"{label} = {ref}" for label, ref in rows]
        if turn["kind"] == "half_life":
            lines.append("C'est acceptable." if scripts.truth_value(meta, "aucpext.obs") <= scripts.score.VERDICT_THRESHOLD
                         else "Ce n'est pas acceptable.")
        return "\n".join(lines)
