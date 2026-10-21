"""Tests of the benchmark scripts and runner (bench/scripts.py, bench/run_bench.py).

* the scripts: 8 turns per exercise, the truth answer built from the expectation scores correct on every
  turn of every exercise, and the typical wrong answers (a converted CL, a computed AUC difference) do not;
* classify_call and the report arithmetic on synthetic records;
* an end-to-end run of one exercise with a SCRIPTED model and the real caladrius-mcp (skipped if not built):
  a correct conversation except turn 3, where the first draft converts CL/F by 10^3 and the regeneration
  quotes the tool value.
"""
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import apothicaire, optchat  # noqa: E402
from bench import make_exercises as mk, scripts as sc, score, run_bench as rb  # noqa: E402

NEGATION = "Caladrius n'a pas calculé ce paramètre pour cette voie d'administration."

def ideal_answer(turn, meta):
    """An answer that satisfies the turn's expectation (built only from the expectation and the meta)."""
    e = turn["expect"]
    parts = [f"{m['label']} = {m['value']:.6g}" for m in e.get("must", [])]
    k = turn["kind"]
    if k == "recall":
        parts = [f"dose {meta['dose']['amount']} {'µg' if meta['dose']['unit'] == 'ug' else 'mg'}",
                 "perfusion" if isinstance(meta["route"], dict) else ("bolus intraveineux" if meta["route"] == "iv_bolus" else "voie orale"),
                 "méthode linéaire des trapèzes"]
    if k == "compare": parts.append("Caladrius ne calcule pas la différence, voici les deux valeurs")
    if k == "half_life": parts.append("c'est acceptable")
    if k == "not_available": parts = [NEGATION]
    return ", ".join(parts)

class TestScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = [mk.load(d) for d in mk.list_exercises()]

    def test_eight_turns_in_order_for_every_exercise(self):
        self.assertEqual(len(self.ex), 25)
        types = set()
        for meta, csv in self.ex:
            s = sc.build_script(meta, csv); types.add(sc.kind_of(meta))
            self.assertEqual([t["kind"] for t in s], list(sc.KINDS), meta["id"])
            self.assertTrue(6 <= len(s) <= 8)
            self.assertIn(csv.strip(), s[0]["question"])                    # the data are in the first message
            self.assertIn(str(meta["dose"]["amount"]).replace(".", ","), s[0]["question"])
            self.assertIn("méthode linéaire", s[0]["question"])
            json.dumps(s)                                                    # serialisable
        self.assertEqual(types, {"oral", "iv_bolus", "iv_infusion"})

    def test_the_truth_answer_is_correct_on_every_turn(self):
        for meta, csv in self.ex:
            for t in sc.build_script(meta, csv):
                with self.subTest(ex=meta["id"], turn=t["kind"]):
                    s = score.score_turn(ideal_answer(t, meta), t["expect"], 0)
                    self.assertTrue(s["correct"], s)

    def test_wrong_answers_are_not_correct(self):
        meta, csv = self.ex[1]; s = {t["kind"]: t for t in sc.build_script(meta, csv)}
        cl = sc.truth_value(meta, "cl.obs")
        wrong = ideal_answer(s["clearance_volume"], meta).replace(f"{cl:.6g}", f"{cl * 1000:.6g}")
        r = score.score_turn(wrong, s["clearance_volume"]["expect"], 1)
        self.assertFalse(r["correct"]); self.assertIn("CL/F", r["missing"])
        a_lin, a_ll = sc.truth_value(meta, "auclast"), sc.truth_value(meta, "auclast", "lin_up_log_down")
        diff = abs(a_ll - a_lin)
        ans = f"AUC lineaire {a_lin:.6g}, log-down {a_ll:.6g}, soit une différence de {diff:.5g}"
        r = score.score_turn(ans, s["compare"]["expect"], 1)
        self.assertFalse(r["correct"]); self.assertTrue(r["forbidden"] or r["new_numbers"])
        self.assertFalse(score.score_turn("C0 vaut 0", s["not_available"]["expect"], 0)["correct"])   # no 'not available'
        self.assertFalse(score.score_turn("Dose 450 mg, voie orale, linéaire", s["recall"]["expect"])["correct"])   # wrong dose

    def test_not_available_phrasings(self):
        import re
        yes = ["Caladrius ne retourne pas de valeur pour C0.", "Caladrius ne renvoie pas de paramètre c0.", "C0 n'a pas été calculée.",
               "C0 n'est pas disponible pour cette voie.", "Le paramètre est non calculé.", "Il n'y a pas de C0.", "C0 not calculated for this route.",
               "Impossible de donner C0.", "Le Tlag n'est pas défini pour un bolus."]
        no = ["C0 vaut 12 ng/mL.", "La concentration initiale extrapolée est 12.", "Le Tlag est de 0,5 h."]
        for t in yes: self.assertTrue(re.search(sc.NOT_AVAILABLE, t, re.I), t)
        for t in no: self.assertFalse(re.search(sc.NOT_AVAILABLE, t, re.I), t)

    def test_not_available_asks_for_a_parameter_caladrius_did_not_compute(self):
        for meta, csv in self.ex:
            t = sc.build_script(meta, csv)[7]
            self.assertIn(t["expect"]["not_calculated_parameter"], meta["ground_truth"]["nca"]["linear"]["not_calculated"])
            self.assertNotIn(t["expect"]["not_calculated_parameter"], meta["ground_truth"]["nca"]["linear"]["parameters"])

    def test_forbidden_values_do_not_coincide_with_legitimate_numbers(self):
        for meta, csv in self.ex:
            pool = {sc._round3(p) for p in sc.pool_of(meta, csv)}
            for t in sc.build_script(meta, csv):
                for f in t["expect"].get("must_not", []):
                    if t["kind"] == "compare": continue                       # the pool of this turn also holds both AUC
                    self.assertNotIn(sc._round3(f["value"]), pool, (meta["id"], f["label"]))

class TestRunnerPieces(unittest.TestCase):
    def test_classify_call(self):
        known = {"data_import", "nca_run"}
        ok_nca = json.dumps({"result": {"subjects": [{"outcome": {"ok": {}}}]}})
        err_nca = json.dumps({"result": {"subjects": [{"outcome": {"error": "negative"}}]}})
        self.assertEqual(rb.classify_call("nca_run", True, ok_nca, known), "valid")
        self.assertEqual(rb.classify_call("nca_run", True, err_nca, known), "failed")
        self.assertEqual(rb.classify_call("nca_run", False, "invalid_parameters: x", known), "invalid")
        self.assertEqual(rb.classify_call("nca_run", False, "unknown_worksheet: x", known), "invalid")
        self.assertEqual(rb.classify_call("fit_run", True, "{}", known), "invalid")             # not an exposed tool
        self.assertEqual(rb.classify_call("data_import", True, "{}", known), "valid")

    def synthetic(self):
        def turn(kind, ub, tb, ua, ta, correct, status="valid", wall=10.0):
            return {"kind": kind, "numbers_unverified_before": ub, "numbers_total_before": tb, "numbers_unverified_after": ua,
                    "numbers_total_after": ta, "regenerated": ub > 0, "kept": "regenerated" if ua < ub else "first", "badge": ua > 0,
                    "findings_before": [{"class": "unit_conversion"}] * ub, "findings_after": [{"class": "arithmetic"}] * ua,
                    "tool_calls": [{"name": "nca_run", "status": status, "dose_ok": True, "route_ok": True}], "memory_calls": 1,
                    "wall_s": wall, "prompt_tokens": 3000,
                    "score": {"correct": correct, "found": ["a"] * (2 if correct else 1), "n_must": 2, "forbidden": []}}
        base = {"3": {c: 0 for c in score.CLASSES}, "4": {c: 0 for c in score.CLASSES}}
        mk_rec = lambda i, turns: {"id": f"ex{i}", "family": "oral_1", "model": "pk1.oral_1", "units": {"time": "h", "conc": "ng/mL"},
                                   "dose": {"amount": 100, "unit": "mg"}, "blq": False, "wall_s": 60.0,
                                   "taxonomy_chance_baseline": base, "turns": turns}
        return [mk_rec(1, [turn("import_nca", 4, 20, 0, 18, True), turn("recall", 0, 5, 0, 5, True)]),
                mk_rec(2, [turn("import_nca", 2, 10, 2, 10, False, status="invalid", wall=20.0), {"kind": "recall", "error": "LLMError: timeout", "wall_s": 5}])]

    def test_report_arithmetic(self):
        rep = rb.build_report(self.synthetic(), {"date": "x"})
        h = rep["hallucination"]
        self.assertEqual((h["before_gate"]["unverified"], h["before_gate"]["total"]), (6, 35))
        self.assertEqual((h["after_gate"]["unverified"], h["after_gate"]["total"]), (2, 33))
        self.assertAlmostEqual(h["before_gate"]["rate"], 6 / 35); self.assertAlmostEqual(h["after_gate"]["rate"], 2 / 33)
        self.assertEqual((rep["exercises"], rep["turns"], rep["turns_failed"]), (2, 4, 1))
        self.assertEqual(h["turns_regenerated"], 2); self.assertEqual(h["regeneration_kept"], 1); self.assertEqual(h["turns_with_badge"], 1)
        self.assertEqual(rep["taxonomy"]["before_gate"]["unit_conversion"], 6); self.assertEqual(rep["taxonomy"]["after_gate"]["arithmetic"], 2)
        self.assertEqual(rep["by_question_type"]["import_nca"]["correct"], 1); self.assertEqual(rep["by_question_type"]["import_nca"]["turns"], 2)
        self.assertEqual(rep["tool_calls"]["valid"], 2); self.assertEqual(rep["tool_calls"]["invalid"], 1)
        self.assertAlmostEqual(rep["tool_calls"]["validity_rate"], 2 / 3)
        self.assertAlmostEqual(rep["time"]["mean_wall_s_per_turn"], (10 + 10 + 20) / 3)
        self.assertEqual(rep["per_exercise"][1]["turns_failed"], 1)
        ci = h["before_gate"]["ci95_cluster_bootstrap"]; self.assertTrue(ci and 0 <= ci[0] <= ci[1] <= 1)
        md = rb.render_md(rep)
        for needle in ("6 / 35", "2 / 33", "unit_conversion", "| ex1 |", "Per exercise", "Failure taxonomy"):
            self.assertIn(needle, md)

    def test_an_error_turn_stays_in_the_denominator(self):
        """T-071 / FROZEN_SET.md §6.1: 4 planned turns, one raised: 4 in every correctness denominator, the error counted apart."""
        recs = self.synthetic()
        rep = rb.build_report(recs, {})
        self.assertEqual((rep["correctness"]["turns"], rep["correctness"]["turns_error"], rep["correctness"]["correct_turns"]), (4, 1, 2))
        self.assertEqual((rep["by_question_type"]["recall"]["turns"], rep["by_question_type"]["recall"]["correct"]), (2, 1))
        self.assertEqual(rep["per_exercise"][1]["turns"], 2)
        self.assertIsNone(rep["outcomes"])                             # no outcome stored: section left out
        for r in recs:
            for t in r["turns"]: t.setdefault("outcome", "CORRECT" if t.get("score", {}).get("correct") else "WRONG")
        recs[1]["turns"][1]["outcome"] = "ERROR"
        o = rb.build_report(recs, {})["outcomes"]
        self.assertEqual(o["turns"], 4); self.assertEqual(o["classes"]["ERROR"], 1); self.assertEqual(o["classes"]["CORRECT"], 2)
        self.assertEqual((o["exercises_all_correct"], o["exercises_failed"]), (1, ["ex2"]))
        self.assertIn("| **total** | 2 | 0 | 0 | 0 | 1 | 1 |".replace("| 2 | 0 | 0 | 0 | 1 | 1 |", "| 1 | 0 | 0 | 0 | 1 | 2 |"), rb.render_md(rb.build_report(recs, {})))

    def test_planned_error_record(self):
        meta, csv = mk.load(mk.list_exercises()[0])
        rec = rb.planned_error_record(meta, sc.build_script(meta, csv), "RuntimeError: engine did not start")
        self.assertEqual([t["outcome"] for t in rec["turns"]], ["ERROR"] * 8)
        self.assertEqual(rb.build_report([rec], {})["correctness"]["turns"], 8)

def fr(x): return f"{x:.6g}"

class FakeLLM:
    def __init__(self, script):
        self.script, self.calls, self.last, self.total_slots = list(script), [], {}, 2
    def chat(self, messages, slot, tools=None, max_tokens=512, think=False, **kw):
        self.calls.append(json.loads(json.dumps(messages)))
        if not self.script: raise AssertionError("the scripted model has no more answers")
        item = self.script.pop(0)
        self.last = {"wall_s": 0.1, "prompt_tokens": 1000 + len(self.calls), "completion_tokens": 10, "prompt_eval_n": 10,
                     "cache_n": 990, "prompt_ms": 1, "predicted_ms": 1, "gen_tps": 20.0, "finish_reason": "stop"}
        return item

def tool_call(name, args, cid):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestEndToEnd(unittest.TestCase):
    def test_one_exercise_with_a_scripted_model(self):
        ex_dir = mk.list_exercises()[1]; meta, csv = mk.load(ex_dir)
        script_turns = sc.build_script(meta, csv)
        imp, nca = mk.tool_arguments(meta, csv)
        cl = sc.truth_value(meta, "cl.obs")
        say = lambda t: {"role": "assistant", "content": t}
        items = [tool_call("data_import", imp, "c1"), tool_call("nca_run", {"worksheet": 1, **nca("linear")}, "c2"), say(ideal_answer(script_turns[0], meta)),
                 say(ideal_answer(script_turns[1], meta)),
                 say(f"CL/F = {fr(cl * 1000)} L/h, Vz/F = {fr(sc.truth_value(meta, 'vz.obs'))}"),            # draft with a conversion
                 say(ideal_answer(script_turns[2], meta)),                                                # regeneration
                 say(ideal_answer(script_turns[3], meta)), say(ideal_answer(script_turns[4], meta)), say(ideal_answer(script_turns[5], meta)),
                 tool_call("nca_run", {"worksheet": 1, **nca("lin_up_log_down")}, "c3"), say(ideal_answer(script_turns[6], meta)),
                 say(ideal_answer(script_turns[7], meta))]
        tmp = tempfile.mkdtemp(prefix="apo_run_")
        try:
            cfg = dict(optchat.CFG, raw_max=1000, raw_max_chars=10 ** 9)           # no compaction call in this test
            rec = rb.run_exercise(ex_dir, tmp, cfg_base=cfg, llm=FakeLLM(items))
            self.assertTrue(os.path.exists(os.path.join(tmp, meta["id"] + ".json")))
            t = rec["turns"]
            self.assertEqual([x["kind"] for x in t], list(sc.KINDS)); self.assertFalse([x for x in t if "error" in x])
            self.assertEqual([c["status"] for c in t[0]["tool_calls"]], ["valid", "valid"])
            self.assertTrue(t[0]["tool_calls"][0]["csv_identical"]); self.assertTrue(all(c["dose_ok"] and c["route_ok"] for c in t[0]["tool_calls"][1:]))
            t3 = t[2]
            self.assertGreater(t3["numbers_unverified_before"], 0); self.assertEqual(t3["numbers_unverified_after"], 0)
            self.assertTrue(t3["regenerated"]); self.assertEqual(t3["kept"], "regenerated"); self.assertFalse(t3["badge"])
            self.assertIn("unit_conversion", [f["class"] for f in t3["findings_before"]])
            self.assertTrue(t3["score"]["correct"]); self.assertIn("CL/F = ", t3["first_answer"])
            self.assertTrue(all(x["score"]["correct"] for x in t), [(x["kind"], x["score"]) for x in t if not x["score"]["correct"]])
            self.assertEqual([x["outcome"] for x in t if x["kind"] != "compare"], ["CORRECT"] * 7, [x.get("rubric") for x in t])
            self.assertEqual(t[6]["outcome"], "WRONG")                 # the old ideal compare answer has no difference: the rubric asks for it
            self.assertEqual(sum(x["numbers_unverified_after"] for x in t), 0)
            rep = rb.write_report(tmp, [rec], {"date": "test"})
            self.assertEqual(rep["hallucination"]["after_gate"]["unverified"], 0); self.assertGreater(rep["hallucination"]["before_gate"]["unverified"], 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "report.md")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
