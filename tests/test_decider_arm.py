"""Tests of the decider-only arm of the frozen set (bench/decider_arm.py, bench/NO_LM_ARM.md) and of the three harness switches it
turns on (decision/harness.py: engine_units, free_layout, extrapolation_verdict). No model: the end-to-end tests use the stub decider
(gold decisions) and need only the caladrius-mcp binary.

The layouts below are placeholder messages for the parser, not frozen-set wordings: those are written by people who do not tune the
system, and Claude never writes or reads them (FROZEN_SET.md §5.3)."""
import json, os, shutil, sys, tempfile, unittest

AGENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (AGENT, os.path.join(AGENT, "decision")):
    if p not in sys.path: sys.path.insert(0, p)
import apothicaire  # noqa: E402
import harness  # noqa: E402
import make_dataset as md  # noqa: E402
from bench import decider_arm, make_exercises as mk, make_frozen as mf, run_frozen as rf, score, scripts as sc  # noqa: E402
from tests.test_bench_frozen import fixture_wordings  # noqa: E402

class TestFreeLayout(unittest.TestCase):
    def test_the_benchmark_layout_is_split_as_before(self):
        """On every development exercise the free-layout split gives the state the decision model was trained on."""
        for d in mk.list_exercises():
            meta, csv = mk.load(d)
            t1 = sc.first_message(meta, csv)
            self.assertEqual(harness.split_message_anywhere(t1), md.split_first_message(t1), meta["id"])

    def test_other_layouts(self):
        meta, csv = mk.load(mk.list_exercises()[0])
        table = csv.strip()
        cases = {  # message -> (intro, request)
            f"{table}\n200 mg en bolus intraveineux.\nFais la NCA linéaire.": ("200 mg en bolus intraveineux.", "Fais la NCA linéaire."),
            f"Fais la NCA linéaire, 200 mg en bolus intraveineux :\n\n{table}\n": ("Fais la NCA linéaire, 200 mg en bolus intraveineux :",) * 2,
            f"Données : {table}\nDose 200 mg, bolus.\nNCA linéaire.": ("Données : Dose 200 mg, bolus.", "NCA linéaire."),
            f"NCA linéaire, 200 mg en bolus. Données : {table} Merci.": ("NCA linéaire, 200 mg en bolus. Données :", "Merci."),
        }
        for text, (intro, request) in cases.items():
            p = harness.split_message_anywhere(text)
            self.assertEqual(p["csv"], table, text); self.assertEqual(p["request"], request, text)
            if text.startswith("Données"): self.assertEqual(p["intro"], "Données :"); self.assertEqual(p["notes"], ["Dose 200 mg, bolus."])
            else: self.assertEqual(p["intro"], intro, text)
        self.assertEqual(harness.split_message_anywhere("Bonjour\nrien\nFais une NCA.")["csv"], "")

class TestDecisionCheck(unittest.TestCase):
    def test_a_wrong_answer_is_attributed_to_the_decision_model(self):
        meta, csv = mk.load(mk.list_exercises()[0])
        st = next(t for t in sc.build_script(meta, csv) if t["kind"] == "clearance_volume")
        stub = decider_arm.StubDecider(); stub.begin(meta); stub.on_turn(2, st)
        qs = md.questions_for([2])
        right = stub({"analyses": [{"id": 2}]}, qs)
        wrong = dict(right, asked_cl="false")
        turn = {"decisions": [{"answers": right, "analyses_in_state": [2]}, {"answers": wrong, "analyses_in_state": [2]}]}
        c = decider_arm.decision_check(turn, meta, st)
        self.assertEqual((c["asks"], c["asks_right"]), (2, 1))
        self.assertEqual(c["wrong"], [{"ask": 2, "question": "asked_cl", "model": "false", "gold": "true"}])

class TestVerdict(unittest.TestCase):
    def digest(self, flags):
        return {"options_used": {"quality_thresholds": {"max_extrapolated_percent": 20.0}}, "subjects": [{"flags": flags}]}

    def test_the_verdict_follows_the_engine_flag(self):
        ok = harness.render_verdict(self.digest([]), {"flags": []})
        high = harness.render_verdict(self.digest([]), {"flags": [{"code": "high_extrapolation", "parameter": "aucpext.obs"}]})
        pred_only = harness.render_verdict(self.digest([]), {"flags": [{"code": "high_extrapolation", "parameter": "aucpext.pred"}]})
        self.assertIn("acceptable", ok); self.assertNotIn("non acceptable", ok); self.assertIn("(20 %)", ok)
        self.assertIn("non acceptable", high); self.assertEqual(pred_only, ok)

    def test_the_dose_warning_is_dropped_only_when_the_analysis_had_the_unit(self):
        w = {"code": "missing_unit", "message": "the dose has no unit; derived units (AUC, clearance, volume) cannot be named"}
        without = {"unit_warnings": [w], "options_used": {}}
        with_unit = {"unit_warnings": [w], "options_used": {"units": {"dose": "mg"}}}
        self.assertEqual(len(harness._warnings(without, {})), 1); self.assertEqual(harness._warnings(with_unit, {}), [])

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestDryRun(unittest.TestCase):
    """The arm end to end with the stub decider: real harness, real engine, rubric, outcomes, analysis."""
    def test_the_harness_ceiling_on_development_exercises(self):
        ids = ["ex01_iv_bolus", "ex05_iv_infusion"]
        tmp = tempfile.mkdtemp(prefix="apo_nolm_")
        try:
            rf.run("dev", decider_arm.ARM, [1, 2], ids=ids, stub=True, base=tmp, out=lambda *a: None)
            res = rf.analyse("dev", c1=decider_arm.ARM, c2="none", base=tmp)
            c = res["configurations"][decider_arm.ARM]
            self.assertEqual(c["failed"]["failed"], 0, c["failed_ids"]); self.assertEqual(c["outcomes"]["CORRECT"], 32)
            self.assertEqual(c["unverified_shown_ids"], [])
            rec = rf._load(os.path.join(tmp, decider_arm.ARM, "seed-2", "ex05_iv_infusion.json"))
            self.assertEqual((rec["gate"], rec["seed"], rec["decider"]), (decider_arm.ARM, 2, "stub-gold-decisions"))
            cl = rec["turns"][2]["answer"]
            self.assertIn(" L/h", cl); self.assertNotIn("dose unit", cl)            # engine_units: CL and V in litres, like the gold
            self.assertIn("acceptable", rec["turns"][3]["answer"])                   # extrapolation_verdict
            self.assertTrue(all(t["decision_check"]["asks"] == t["decision_check"]["asks_right"] > 0 for t in rec["turns"]))
            self.assertEqual(c["decisions"]["compare"]["decisions_all_right"], 4)
            self.assertFalse(res["confirmatory"]); self.assertIn("stub-gold-decisions", res["models"][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_frozen_exercise_with_placeholder_wordings(self):
        """Wordings put the table inside a line of text (free_layout) and the dose after it; the arm still runs and scores."""
        ids = [os.path.basename(mf.list_exercises("demo")[0])]
        tmp = tempfile.mkdtemp(prefix="apo_nolm_")
        try:
            w = fixture_wordings()
            for i, it in enumerate(w["wordings"]["import_nca"]): it["text"] = f"FIXTURE-{i} : {{table}} {{dose}} {{route}} {{blq_note}} {{param_list}} linear"
            path = os.path.join(tmp, "wordings.json")
            with open(path, "w", encoding="utf-8") as f: json.dump(w, f)
            rf.run("demo", decider_arm.ARM, [1], wordings_path=path, wording_seed=3, ids=ids, stub=True, base=os.path.join(tmp, "runs"),
                   out=lambda *a: None)
            rec = rf._load(os.path.join(tmp, "runs", decider_arm.ARM, "seed-1", ids[0] + ".json"))
            self.assertTrue(rec["turns"][0]["question"].startswith("FIXTURE-"))
            self.assertEqual(len(rec["turns"]), 8); self.assertTrue(all(t["outcome"] in score.OUTCOMES for t in rec["turns"]))
            self.assertEqual(rec["turns"][0]["outcome"], "CORRECT", rec["turns"][0].get("rubric"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
