"""Tests of the oracle check of the benchmark (bench/score.py: oracle_turn, oracle_exercise, nca_call_deviations, tool_arg_audit).

The oracle reads the expected-answer rule of a turn and the ground truth of meta.json and verifies that the answer quotes the value
of the RIGHT parameter, from the right AUC method, with the unit Caladrius reports. Here:
* the truth answer, written in three styles (list, table, inline) with several spellings of the units, is oracle-correct on every
  turn of the 25 committed exercises (synthetic data);
* one synthetic answer per class of mismatch: wrong_parameter, wrong_method, wrong_option, missing_unit, wrong_unit, missing_value;
* a regression test built from the STRUCTURE of the three failures of the 2026-10-09 run (ex13 quotes aucall as AUC(0-tlast), ex07
  passes `start: zero` and every AUC / CL / Vz / MRT differs, ex21 says the dose has no unit), with synthetic numbers;
* the tool-argument audit and the report arithmetic.
"""
import copy, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bench import make_exercises as mk, scripts as sc, score, run_bench as rb  # noqa: E402

LABEL = {"cmax": "Cmax", "tmax": "Tmax", "c0": "C0 (extrapolée)", "auclast": "AUC(0–tlast)", "aucinf.obs": "AUC(0–inf)", "lambda.z": "λz",
         "half.life": "t½", "cl.obs": "CL/F", "vz.obs": "Vz/F", "mrt.obs": "MRT", "mrt.iv.obs": "MRT", "aucpext.obs": "Part extrapolée de l'AUC",
         "lambda.z.n.points": "Nombre de points", "adj.r.squared": "R² ajusté", "dose": "Dose"}

def exercise(prefix):
    d = next(x for x in mk.list_exercises() if os.path.basename(x).startswith(prefix))
    meta, csv = mk.load(d)
    return meta, {t["kind"]: t for t in sc.build_script(meta, csv)}

def shown_unit(item, spelling):
    u = {"ug": "µg"}.get(item.get("unit"), item.get("unit") or "")
    return u.replace("*", spelling)

def fmt(v, comma): return (f"{v:.6g}").replace(".", ",") if comma else f"{v:.6g}"

def truth_answer(turn, style="list", comma=True, spelling="·", values=None, units=None):
    """The answer that quotes every expected number of the turn with its unit. `values` / `units` override per label."""
    items = turn["expect"]["must"]
    if turn["kind"] == "compare":
        out = []
        for it in items:
            m = "linéaire" if it["method"] == "linear" else "linear-up/log-down"
            v = (values or {}).get(it["label"], it["value"]); u = (units or {}).get(it["label"], shown_unit(it, spelling))
            out += [f"Avec la méthode {m} :", f"- **AUC(0–tlast)** = {fmt(v, comma)} {u}"]
        return "\n".join(out + ["Caladrius ne renvoie pas la différence."])
    rows = []
    for it in items:
        v = (values or {}).get(it["label"], it["value"]); u = (units or {}).get(it["label"], shown_unit(it, spelling))
        lab = LABEL[it["key"]]
        rows.append({"list": f"- **{lab}** : {fmt(v, comma)} {u}".rstrip(), "table": f"| {lab} | {fmt(v, comma)} | {u} |",
                     "inline": f"{lab} = {fmt(v, comma)} {u}".rstrip() + " ;"}[style])
    return "\n".join(rows)

def verdict(turn, meta, answer, deviations=None):
    return score.oracle_turn(answer, turn["expect"], meta, deviations or {})

def classes(res): return {i["label"]: i["class"] for i in res["items"] if not i["ok"]}

class TestTruthAnswers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = [mk.load(d) for d in mk.list_exercises()]

    def test_the_truth_answer_is_oracle_correct_on_every_turn_in_every_style(self):
        for meta, csv in self.ex:
            for t in sc.build_script(meta, csv):
                if not t["expect"].get("must"): continue
                for style, comma, spelling in (("list", True, "·"), ("table", False, "*"), ("inline", True, ".")):
                    with self.subTest(ex=meta["id"], turn=t["kind"], style=style):
                        res = verdict(t, meta, truth_answer(t, style, comma, spelling))
                        self.assertTrue(res["correct"], [i for i in res["items"] if not i["ok"]])

    def test_no_expectation_no_verdict(self):
        meta, turns = exercise("ex13")
        self.assertIsNone(score.oracle_turn("Caladrius ne renvoie pas C0.", turns["not_available"]["expect"], meta))

    def test_the_exponent_form_of_lambda_z_unit_is_accepted(self):
        meta, turns = exercise("ex13"); t = turns["import_nca"]
        for u in ("1/h", "h⁻¹", "h^-1", "h-1"):
            self.assertTrue(verdict(t, meta, truth_answer(t, units={"lambda_z": u}))["correct"], u)

    def test_sample_of_the_stored_run_style(self):
        """A table row with the observed and the predicted value and the unit in the next cell."""
        meta, turns = exercise("ex13"); t = turns["import_nca"]; v = {i["key"]: i["value"] for i in t["expect"]["must"]}
        pred = meta["ground_truth"]["nca"]["linear"]["parameters"]["aucinf.pred"]["value"]
        ans = truth_answer(t, "table", comma=False).replace(f"| AUC(0–inf) | {v['aucinf.obs']:.6g} |", f"| AUC(0–inf) | {v['aucinf.obs']:.6g} (obs) / {pred:.6g} (préd) |")
        self.assertIn("(préd)", ans); self.assertTrue(verdict(t, meta, ans)["correct"])

class TestClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta, cls.turns = exercise("ex13")                          # oral, BLQ: aucall differs from auclast
        cls.p = {m: cls.meta["ground_truth"]["nca"][m]["parameters"] for m in score.METHODS}

    def test_wrong_parameter_the_value_of_another_parameter_of_the_same_analysis(self):
        t = self.turns["import_nca"]; aucall = self.p["linear"]["aucall"]["value"]
        self.assertNotAlmostEqual(aucall, self.p["linear"]["auclast"]["value"], places=1)
        res = verdict(t, self.meta, truth_answer(t, values={"AUC(0-tlast)": aucall}))
        self.assertEqual(classes(res), {"AUC(0-tlast)": "wrong_parameter"}); self.assertFalse(res["correct"])
        self.assertEqual([i["detail"] for i in res["items"] if i["class"]], ["aucall"])
        self.assertEqual((res["n_items"], res["n_ok"]), (9, 8))
        # another parameter, in another position: t1/2 given as the terminal half-life of the MRT row
        res = verdict(t, self.meta, truth_answer(t, values={"MRT": self.p["linear"]["mrt.last"]["value"]}))
        self.assertEqual(classes(res), {"MRT": "wrong_parameter"})

    def test_wrong_method_the_value_of_the_other_auc_method(self):
        t = self.turns["import_nca"]; lud = self.p["lin_up_log_down"]["auclast"]["value"]
        res = verdict(t, self.meta, truth_answer(t, values={"AUC(0-tlast)": lud}))
        self.assertEqual(classes(res), {"AUC(0-tlast)": "wrong_method"}); self.assertIn("lin_up_log_down", res["items"][2]["detail"])
        c = self.turns["compare"]; lin = self.p["linear"]["auclast"]["value"]
        res = verdict(c, self.meta, truth_answer(c, values={"AUC(0-tlast) linear": lud, "AUC(0-tlast) lin-up/log-down": lin}))
        self.assertEqual(classes(res), {"AUC(0-tlast) linear": "wrong_method", "AUC(0-tlast) lin-up/log-down": "wrong_method"})

    def test_wrong_option_only_when_the_value_is_wrong(self):
        t = self.turns["import_nca"]; dev = {"linear": [{"field": "options.start", "got": "zero", "intended": None}]}
        v = {i["label"]: i["value"] * 1.07 for i in t["expect"]["must"] if i["key"] in ("auclast", "aucinf.obs", "cl.obs")}
        res = verdict(t, self.meta, truth_answer(t, values=v), dev)
        self.assertEqual(classes(res), {k: "wrong_option" for k in v}); self.assertIn("options.start=zero", res["items"][2]["detail"])
        self.assertEqual(classes(verdict(t, self.meta, truth_answer(t, values=v))), {k: "missing_value" for k in v})     # no deviation logged
        self.assertTrue(verdict(t, self.meta, truth_answer(t), dev)["correct"])                                          # deviation, right values
        # the deviation of the OTHER method does not explain a wrong linear value
        self.assertEqual(set(classes(verdict(t, self.meta, truth_answer(t, values=v), {"lin_up_log_down": dev["linear"]})).values()), {"missing_value"})

    def test_missing_unit(self):
        t = self.turns["clearance_volume"]
        res = verdict(t, self.meta, truth_answer(t, units={"CL/F": "", "Vz/F": ""}))
        self.assertEqual(classes(res), {"CL/F": "missing_unit", "Vz/F": "missing_unit"})
        # the unit written after the NEXT label is not the unit of this value
        t = self.turns["cmax_tmax"]; cm, tm = [i["value"] for i in t["expect"]["must"]]
        res = verdict(t, self.meta, f"Tmax = {tm:.6g} ; Cmax = {cm:.6g} ng/mL")
        self.assertEqual(classes(res), {"Tmax": "missing_unit"})
        # a unit-less quantity (points, R2) needs no unit
        self.assertTrue(verdict(self.turns["lambda_z_regression"], self.meta, truth_answer(self.turns["lambda_z_regression"]))["correct"])

    def test_wrong_unit(self):
        t = self.turns["clearance_volume"]
        res = verdict(t, self.meta, truth_answer(t, units={"CL/F": "mL/h"}))
        self.assertEqual(classes(res), {"CL/F": "wrong_unit"}); self.assertEqual(res["items"][0]["detail"], "ml/h")
        res = verdict(t, self.meta, truth_answer(t, units={"Vz/F": "µg/(ng/mL)"}))               # the unconverted label: not as Caladrius reports
        self.assertEqual(classes(res), {"Vz/F": "wrong_unit"})
        t = self.turns["cmax_tmax"]
        self.assertEqual(classes(verdict(t, self.meta, truth_answer(t, units={"Cmax": "mg/L"}))), {"Cmax": "wrong_unit"})
        r = self.turns["recall"]                                                                  # dose 50 mg written in µg
        self.assertEqual(classes(verdict(r, self.meta, "Dose : 50 µg, voie orale, trapèzes linéaires")), {"dose": "wrong_unit"})
        self.assertTrue(verdict(r, self.meta, "Dose : 50 mg, voie orale, trapèzes linéaires")["correct"])

    def test_missing_value(self):
        t = self.turns["half_life"]
        res = verdict(t, self.meta, "Demi-vie : voir Caladrius. AUC extrapolée : non disponible")
        self.assertEqual(classes(res), {"t1/2": "missing_value", "AUC % extrapolated": "missing_value"})
        res = verdict(t, self.meta, truth_answer(t, values={"t1/2": 77.7}))                        # a value that is no parameter of the analysis
        self.assertEqual(classes(res), {"t1/2": "missing_value"})

    def test_the_value_must_follow_the_label_not_just_be_somewhere_in_the_answer(self):
        t = self.turns["cmax_tmax"]; cm, tm = [i["value"] for i in t["expect"]["must"]]
        res = verdict(t, self.meta, f"Cmax = 99,9 ng/mL ; Tmax = {tm:.6g} h. (La vraie valeur {cm:.6g} ng/mL est ailleurs.)")
        self.assertFalse(res["correct"]); self.assertIn("Cmax", classes(res))
        # ... where the scorer, which searches the whole answer, is satisfied
        self.assertTrue(score.score_turn(f"Cmax = 99,9 ng/mL ; Tmax = {tm:.6g} h. ({cm:.6g} ng/mL)", t["expect"])["correct"])

    def test_a_number_after_a_reference_to_an_analysis_is_not_a_claim(self):
        t = self.turns["lambda_z_regression"]; n, r2 = [i["value"] for i in t["expect"]["must"]]
        wrong = n + 1
        res = verdict(t, self.meta, f"Nombre de points : {wrong:g} (analyse {n:g})\nR² ajusté : {r2:.6g}")
        self.assertEqual(classes(res), {"lambda_z points": "missing_value"})
        self.assertTrue(verdict(t, self.meta, f"La régression utilise {n:g} points. R² ajusté : {r2:.6g}")["correct"])      # "3 points"

class TestRegressionOfTheRunOfTheTenthOfOctober(unittest.TestCase):
    """The structure of the three failures that the gate cannot see, with synthetic numbers (the truth of the committed
    synthetic exercises, scaled by a made-up factor where the run's numbers differed)."""
    def conversation(self, prefix, answers, calls):
        meta, turns = exercise(prefix); script = sc.build_script(meta, mk.load(next(x for x in mk.list_exercises() if os.path.basename(x).startswith(prefix)))[1])
        recs = []
        for k, st in enumerate(script):
            ans = answers.get(st["kind"]) or (truth_answer(st) if st["expect"].get("must") else "Caladrius n'a pas calculé ce paramètre.")
            recs.append({"turn": k + 1, "kind": st["kind"], "answer": ans, "tool_calls": calls.get(k + 1, [])})
        return meta, script, recs

    def nca(self, meta, method, **extra):
        a = copy.deepcopy(meta["ground_truth"]["nca"][method]["nca_run_arguments"]); a["worksheet"] = 1; a["options"].update(extra)
        return {"name": "nca_run", "args": a, "status": "valid"}

    def test_ex13_structure_aucall_quoted_as_auclast(self):
        meta, turns = exercise("ex13"); p = {m: meta["ground_truth"]["nca"][m]["parameters"]["aucall"]["value"] for m in score.METHODS}
        answers = {"import_nca": truth_answer(turns["import_nca"], "table", False, values={"AUC(0-tlast)": p["linear"]}),
                   "compare": truth_answer(turns["compare"], values={"AUC(0-tlast) linear": p["linear"], "AUC(0-tlast) lin-up/log-down": p["lin_up_log_down"]})}
        meta, script, recs = self.conversation("ex13", answers, {1: [self.nca(meta, "linear")], 7: [self.nca(meta, "lin_up_log_down")]})
        res = score.oracle_exercise(meta, script, recs)
        self.assertEqual([r["correct"] if r else None for r in res], [False, True, True, True, True, True, False, None])
        self.assertEqual(sorted(i["class"] for r in res if r for i in r["items"] if i["class"]), ["wrong_parameter"] * 3)
        # the gate cannot see it: aucall is in the tool results, so it is no unverified number; the scorer sees a missing value
        self.assertEqual(score.tool_arg_audit(meta, recs)["deviating_calls"], 0)

    def test_ex07_structure_start_zero_alone_four_turns_wrong(self):
        meta, turns = exercise("ex07")
        scale = {"AUC(0-tlast)": 0.904, "AUC(0-inf)": 0.907, "CL": 1.103, "Vz": 1.103, "MRT": 1.103}          # made-up factors
        v1 = {i["label"]: i["value"] * scale[i["label"]] for i in turns["import_nca"]["expect"]["must"] if i["label"] in scale}
        v3 = {k: v1[k] for k in ("CL", "Vz")}
        v4 = {"AUC % extrapolated": [i["value"] for i in turns["half_life"]["expect"]["must"] if i["key"] == "aucpext.obs"][0] * 1.1}
        v7 = {i["label"]: i["value"] * 0.9 for i in turns["compare"]["expect"]["must"]}
        answers = {"import_nca": truth_answer(turns["import_nca"], "table", values=v1), "clearance_volume": truth_answer(turns["clearance_volume"], values=v3),
                   "half_life": truth_answer(turns["half_life"], values=v4), "compare": truth_answer(turns["compare"], values=v7)}
        meta, script, recs = self.conversation("ex07", answers, {})
        recs[0]["tool_calls"] = [self.nca(meta, "linear", start="zero")]; recs[6]["tool_calls"] = [self.nca(meta, "lin_up_log_down", start="zero")]
        res = score.oracle_exercise(meta, script, recs)
        self.assertEqual([r["correct"] if r else None for r in res], [False, True, False, False, True, True, False, None])
        self.assertEqual({i["class"] for r in res if r for i in r["items"] if i["class"]}, {"wrong_option"})
        self.assertEqual(sum(1 for r in res if r for i in r["items"] if i["class"]), 5 + 2 + 1 + 2)
        audit = score.tool_arg_audit(meta, recs)
        self.assertEqual((audit["calls"], audit["deviating_calls"]), (2, 2))
        self.assertEqual({(d["turn"], d["field"], d["got"]) for d in audit["deviations"]}, {(1, "options.start", "zero"), (7, "options.start", "zero")})
        # the same wrong numbers with a clean call log would be unexplained
        clean = [dict(r, tool_calls=[]) for r in recs]
        self.assertEqual({i["class"] for r in score.oracle_exercise(meta, script, clean) if r for i in r["items"] if i["class"]}, {"missing_value"})

    def test_ex21_structure_the_dose_had_no_unit(self):
        meta, turns = exercise("ex21")
        self.assertEqual(meta["dose"]["unit"], "ug")
        answers = {"recall": "- **Dose** : 5000 (sans unité, comme indiqué dans votre premier message)\n- **Voie** : extravasculaire (orale)\n- **Méthode d'AUC** : linéaire"}
        meta, script, recs = self.conversation("ex21", answers, {1: [self.nca(meta, "linear")], 7: [self.nca(meta, "lin_up_log_down")]})
        answers["recall"] = answers["recall"].replace("5000", f"{meta['dose']['amount']}")
        recs[5]["answer"] = answers["recall"]
        res = score.oracle_exercise(meta, script, recs)
        self.assertEqual([r["correct"] if r else None for r in res], [True, True, True, True, True, False, True, None])
        self.assertEqual([i["class"] for i in res[5]["items"]], ["missing_unit"])
        recs[5]["answer"] = f"- **Dose** : {meta['dose']['amount']} µg"
        self.assertTrue(score.oracle_exercise(meta, script, recs)[5]["correct"])

class TestToolArgumentAudit(unittest.TestCase):
    def setUp(self):
        self.meta, _ = exercise("ex07")
        self.ok = copy.deepcopy(self.meta["ground_truth"]["nca"]["linear"]["nca_run_arguments"]); self.ok["worksheet"] = 1

    def test_the_intended_call_has_no_deviation(self):
        self.assertEqual(score.nca_call_deviations(self.meta, self.ok), [])
        lud = copy.deepcopy(self.meta["ground_truth"]["nca"]["lin_up_log_down"]["nca_run_arguments"])
        self.assertEqual(score.nca_call_deviations(self.meta, lud), [])

    def test_each_kind_of_deviation(self):
        d = lambda **kw: score.nca_call_deviations(self.meta, {**self.ok, **kw})
        o = self.ok["options"]; self.assertEqual(set(o), {"auc_method", "units"})                              # the units since T-059
        self.assertEqual(d(options={**o, "start": "zero"}), [{"field": "options.start", "got": "zero", "intended": None}])
        self.assertEqual([x["field"] for x in d(options={**o, "lambda_z": {"min_points": 4}})], ["options.lambda_z"])
        self.assertEqual([x["field"] for x in d(options={**o, "start": None})], [])                            # null = absent
        self.assertEqual([x["field"] for x in d(options={"auc_method": "linear"})], ["options.units"])        # no dose unit given
        self.assertEqual([x["field"] for x in d(options={})], ["options.auc_method"])
        self.assertEqual([x["field"] for x in d(options={"auc_method": "linear-up/log-down"})], ["options.auc_method"])
        self.assertEqual([x["field"] for x in d(dose=1)], ["dose"]); self.assertEqual([x["field"] for x in d(dose=float(self.ok["dose"]))], [])
        self.assertEqual([x["field"] for x in d(route="extravascular")], ["route"])
        self.assertEqual([x["field"] for x in d(subjects=["1"])], ["subjects"])

    def test_data_import_deviations(self):
        cols = [{"name": "time", "unit": "h"}, {"name": "conc", "unit": "ng/mL"}]
        want = [c["unit"] for c in self.meta["ground_truth"]["data_import_columns"]]
        cols = [{"name": "time (h)", "unit": want[0]}, {"name": "conc (x)", "unit": want[1], "role": "concentration"}]
        self.assertEqual(score.import_call_deviations(self.meta, {"csv": "<10 chars, identical to the exercise CSV>", "columns": cols}), [])
        bad = score.import_call_deviations(self.meta, {"csv": "<10 chars, DIFFERENT from the exercise CSV>", "columns": [dict(cols[0], unit="min"), cols[1]]})
        self.assertEqual([x["field"] for x in bad], ["csv", "columns.unit"])
        self.assertEqual([x["field"] for x in score.import_call_deviations(self.meta, {"columns": [dict(cols[0], role="concentration"), cols[1]]})], ["columns[0].role"])

    def test_audit_counts_calls_and_lists_deviations(self):
        turns = [{"turn": 1, "tool_calls": [{"name": "data_import", "args": {"csv": "<1 chars, identical to the exercise CSV>", "columns": [{"unit": u} for u in
                                                                                                                                        [c["unit"] for c in self.meta["ground_truth"]["data_import_columns"]]]}, "status": "valid"},
                                           {"name": "nca_run", "args": {**self.ok, "options": {**self.ok["options"], "start": "zero"}}, "status": "valid"},
                                           {"name": "analysis_get", "args": {"analysis": 2}, "status": "valid"}]},
                 {"turn": 2, "tool_calls": [{"name": "nca_run", "args": self.ok, "status": "valid"}]}]
        a = score.tool_arg_audit(self.meta, turns)
        self.assertEqual((a["calls"], a["deviating_calls"], len(a["deviations"])), (3, 1, 1))
        self.assertEqual(a["deviations"][0], {"turn": 1, "tool": "nca_run", "status": "valid", "field": "options.start", "got": "zero", "intended": None})
        out = []
        rb.print_tool_arg_audit([{"id": "exX", "tool_arg_audit": a}, {"id": "exY", "tool_arg_audit": {"calls": 2, "deviating_calls": 0, "deviations": []}}], out.append)
        self.assertIn("exX: 1 of 3 calls deviate", out); self.assertIn("exY: 0 of 2 calls deviate", out)
        self.assertTrue(any("options.start" in l for l in out)); self.assertEqual(out[-1], "total: 1 of 5 calls deviate, in 1 of 2 exercises")

class TestOracleReport(unittest.TestCase):
    def rec(self, ex, oracles, scores):
        turns = []
        for k, (o, s) in enumerate(zip(oracles, scores)):
            turns.append({"turn": k + 1, "kind": o["kind"], "answer": "x", "wall_s": 1.0, "prompt_tokens": 100, "numbers_total_before": 1, "numbers_unverified_before": 0,
                          "numbers_total_after": 1, "numbers_unverified_after": 0, "regenerated": False, "kept": None, "badge": False,
                          "findings_before": [], "findings_after": [], "tool_calls": [], "memory_calls": 0, "score": s,
                          "oracle": o["oracle"]})
        return {"id": ex, "family": "f", "dose": {"amount": 1, "unit": "mg"}, "units": {"time": "h", "conc": "ng/mL"}, "wall_s": 1.0, "turns": turns,
                "tool_arg_audit": {"calls": 2, "deviating_calls": 1, "deviations": [{"turn": 1, "tool": "nca_run", "status": "valid", "field": "options.start", "got": "zero", "intended": None}]}}

    def test_report_arithmetic_and_rendering(self):
        item = lambda label, ok, cls=None, detail=None: {"label": label, "key": "k", "method": "linear", "ok": ok, "class": cls, "detail": detail, "labelled": True, "claimed": ["1"]}
        sc_ok = {"correct": True, "found": ["A", "B"], "missing": [], "forbidden": [], "n_must": 2}
        sc_bad = {"correct": False, "found": ["A"], "missing": ["B"], "forbidden": [], "n_must": 2}
        o1 = {"n_items": 2, "n_ok": 2, "correct": True, "items": [item("A", True), item("B", True)]}
        o2 = {"n_items": 2, "n_ok": 1, "correct": False, "items": [item("A", True), item("B", False, "wrong_option", "options.start=zero")]}
        o3 = {"n_items": 2, "n_ok": 1, "correct": False, "items": [item("A", False, "missing_unit"), item("B", True)]}
        recs = [self.rec("ex1", [{"kind": "import_nca", "oracle": o1}, {"kind": "cmax_tmax", "oracle": o2}], [sc_ok, sc_bad]),
                self.rec("ex2", [{"kind": "import_nca", "oracle": o3}, {"kind": "cmax_tmax", "oracle": o1}], [sc_ok, sc_ok])]
        rep = rb.build_report(recs, {"date": "x"}); o = rep["oracle"]
        self.assertEqual((o["turns"], o["correct_turns"], o["numbers"], o["numbers_ok"]), (4, 2, 8, 6))
        self.assertAlmostEqual(o["correct_turns_rate"], 0.5); self.assertAlmostEqual(o["numbers_ok_rate"], 0.75)
        self.assertEqual(o["classes"], {"wrong_parameter": 0, "wrong_method": 0, "wrong_option": 1, "missing_unit": 1, "wrong_unit": 0, "missing_value": 0})
        self.assertEqual(o["by_question_type"]["import_nca"]["correct"], 1); self.assertEqual(o["by_question_type"]["cmax_tmax"]["classes"]["wrong_option"], 1)
        self.assertEqual(o["not_covered"], ["clearance_volume", "half_life", "lambda_z_regression", "recall", "compare", "not_available"])
        self.assertEqual([(m["exercise"], m["turn"], m["class"]) for m in o["mismatches"]], [("ex1", 2, "wrong_option"), ("ex2", 1, "missing_unit")])
        d = o["disagreements_with_scorer"]
        self.assertEqual(d["items_oracle_wrong_scorer_found"], ["ex2 t1 A (missing_unit)"]); self.assertEqual(d["items_oracle_ok_scorer_missing"], [])
        self.assertEqual(d["turns_oracle_wrong_scorer_correct"], ["ex2 t1 import_nca"])
        self.assertEqual((rep["tool_arg_audit"]["calls"], rep["tool_arg_audit"]["deviating_calls"]), (4, 2))
        self.assertEqual(rep["hallucination"]["after_gate"]["unverified"], 0)                # the gate counts do not depend on the oracle
        md = rb.render_md(rep)
        for needle in ("## Oracle check: 2 / 4 turns = 50.0 %", "6 / 8 expected numbers = 75.0 %", "wrong_option", "ex1 | 2 cmax_tmax", "Tool-call argument audit"):
            self.assertIn(needle, md)

    def test_attach_oracle_and_rescore_on_a_copy_of_a_stored_record(self):
        meta, turns = exercise("ex13"); script = sc.build_script(meta, mk.load(next(x for x in mk.list_exercises() if os.path.basename(x).startswith("ex13")))[1])
        recs = [{"turn": k + 1, "kind": st["kind"], "answer": truth_answer(st) if st["expect"].get("must") else "pas disponible", "tool_calls": []}
                for k, st in enumerate(script)]
        rec = {"id": meta["id"], "turns": recs}
        rb.attach_oracle(rec, meta, script)
        self.assertTrue(all("oracle" in t for t in recs[:7])); self.assertNotIn("oracle", recs[7]); self.assertTrue(all(t["oracle"]["correct"] for t in recs[:7]))
        self.assertEqual(rec["tool_arg_audit"]["calls"], 0)

if __name__ == "__main__":
    unittest.main()
