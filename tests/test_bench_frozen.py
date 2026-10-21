"""Tests of the frozen-set generator, wordings, runner and analysis (bench/make_frozen.py, bench/scripts.py wordings,
bench/run_frozen.py, bench/stub_model.py). No language model: the end-to-end test uses the stub model and needs only the
caladrius-mcp binary.

The wording fixtures below are placeholder strings for the code paths, not questions: the wordings of a frozen set are written
by people who do not tune the system, and Claude never writes or reads them (FROZEN_SET.md §5.3)."""
import collections, json, os, shutil, sys, tempfile, unittest

AGENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire  # noqa: E402
from bench import make_exercises as mk, make_frozen as mf, run_bench as rb, run_frozen as rf, scripts as sc, stats  # noqa: E402

def fixture_wordings(n=3):
    """n placeholder wordings per kind, with every required placeholder and the words each kind must say."""
    body = {"import_nca": "FIXTURE-{i} {table} {dose} {route} {blq_note} {param_list} linear",
            "cmax_tmax": "FIXTURE-{i} {cmax_params}", "clearance_volume": "FIXTURE-{i} {cl_name} {vz_name}",
            "half_life": "FIXTURE-{i} accept", "lambda_z_regression": "FIXTURE-{i}", "recall": "FIXTURE-{i}",
            "compare": "FIXTURE-{i} log-down", "not_available": "FIXTURE-{i} {missing_param}"}
    return {"wordings": {k: [{"text": v.replace("{i}", str(i)), "author": "fixture", "lang": "fr"} for i in range(n)]
                         for k, v in body.items()}}

class TestPlan(unittest.TestCase):
    def test_the_demo_plan_is_stratified_and_reproducible(self):
        rows = mf.draw_plan("demo")
        self.assertEqual(rows, mf.draw_plan("demo"))
        self.assertEqual(len(rows), 40)
        fam = collections.Counter(r[0] for r in rows)
        self.assertEqual([fam[f] for f, _ in mf.FAMILIES], mf.TIERS["demo"]["counts"])
        self.assertEqual(sum(r[2] == "ug" for r in rows), 10); self.assertEqual(sum(r[4] == "min" for r in rows), 10)
        self.assertEqual(sum(r[5] for r in rows), 8)
        self.assertTrue(all(r[3] == "ng/mL" for r in rows if r[2] == "ug"))

    def test_the_page_tier_has_no_seed_before_its_case_freeze(self):
        with self.assertRaises(SystemExit): mf.draw_plan("page")

    def test_seeds_never_reuse_the_development_seed(self):
        seeds = {mf.exercise_seed("demo", i, a) for i in range(1, 41) for a in range(mf.MAX_ATTEMPTS)}
        self.assertEqual(len(seeds), 40 * mf.MAX_ATTEMPTS); self.assertNotIn(20261009, seeds)

    def test_the_committed_exercises_follow_the_plan(self):
        with open(os.path.join(mf.tier_dir("demo"), "PLAN.json"), encoding="utf-8") as f: plan = json.load(f)
        dirs = mf.list_exercises("demo")
        self.assertEqual([os.path.basename(d) for d in dirs], [e["id"] for e in plan["exercises"]])
        for d, e, row in zip(dirs, plan["exercises"], mf.draw_plan("demo")):
            meta, _ = mk.load(d)
            self.assertEqual(meta["frozen"]["tag"], "frozen-set-demo"); self.assertEqual(meta["frozen"]["plan_row"], list(row))
            self.assertTrue(meta["ground_truth"]["units_in_nca_run"])
            self.assertEqual((meta["dose"]["unit"], meta["units"]["conc"], meta["units"]["time"], bool(meta.get("blq"))),
                             (row[2], row[3], row[4], row[5]))

class TestWordings(unittest.TestCase):
    def setUp(self):
        d = mf.list_exercises("demo")[0]; self.meta, self.csv = mk.load(d)

    def test_a_complete_file_is_accepted(self):
        self.assertEqual(sc.validate_wordings(fixture_wordings()), [])

    def test_errors(self):
        w = fixture_wordings(); w["wordings"]["recall"] = w["wordings"]["recall"][:2]
        w["wordings"]["cmax_tmax"][0]["text"] = "FIXTURE {table}"
        w["wordings"]["compare"][1]["text"] = "FIXTURE"
        w["wordings"]["import_nca"][2]["text"] = "FIXTURE {dose} linear"
        errs = "\n".join(sc.validate_wordings(w))
        for part in ("recall: 2 wordings", "cmax_tmax[0]: unknown placeholder", "cmax_tmax[0]: missing placeholder",
                     "compare[1]: does not say", "import_nca[2]: missing placeholder"):
            self.assertIn(part, errs)

    def test_application_keeps_the_expectations(self):
        script = sc.build_script(self.meta, self.csv)
        out = sc.apply_wordings(script, self.meta, self.csv, fixture_wordings(), seed=7)
        self.assertEqual([t["expect"] for t in out], [t["expect"] for t in script])
        self.assertEqual(out, sc.apply_wordings(script, self.meta, self.csv, fixture_wordings(), seed=7))
        self.assertIn(self.csv.strip(), out[0]["question"]); self.assertTrue(all(t["question"].startswith("FIXTURE-") for t in out))
        self.assertEqual({t["wording"]["author"] for t in out}, {"fixture"})
        draws = {sc.wording_choice(f"fd{i:02d}", "recall", 3, 7) for i in range(1, 41)}
        self.assertEqual(draws, {0, 1, 2})

class TestRefusals(unittest.TestCase):
    def test_run_bench_refuses_a_frozen_exercise(self):
        with self.assertRaises(SystemExit) as cm: rb.run_exercise(mf.list_exercises("demo")[0], tempfile.gettempdir())
        self.assertIn("frozen-set-demo", str(cm.exception))

    def test_a_frozen_run_needs_its_wordings(self):
        with self.assertRaises(SystemExit): rf.run("demo", "v1", [1], base=tempfile.gettempdir(), out=lambda *a: None)

    def test_a_manifest_mismatch_stops_the_run(self):
        tmp = tempfile.mkdtemp(prefix="apo_manifest_")
        real = mf.tier_dir
        try:
            m = mf.manifest("demo"); rel = next(iter(m["files"])); m["files"][rel] = "0" * 64
            with open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8") as f: json.dump(m, f)
            mf.tier_dir = lambda tier: tmp
            with self.assertRaises(SystemExit) as cm: rf.preflight("demo", None, False)
            self.assertIn(rel, str(cm.exception))
            m["files"][rel] = mf.sha256_file(os.path.join(AGENT, rel))
            with open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8") as f: json.dump(m, f)
            self.assertEqual(mf.verify_manifest("demo"), [])
        finally:
            mf.tier_dir = real; shutil.rmtree(tmp, ignore_errors=True)
        ok, notes = rf.preflight("demo", None, True)
        self.assertFalse(ok); self.assertTrue(any("not confirmatory" in n for n in notes))

def synthetic_record(i, gate, seed, n_correct, unverified=0):
    turns = [{"turn": k + 1, "kind": sc.KINDS[k], "outcome": "CORRECT" if k < n_correct else "WRONG", "wall_s": 1.0,
              "numbers_unverified_after": unverified if k == 0 else 0, "prompt_tokens": 1000, "tool_calls": []} for k in range(8)]
    return {"id": i, "family": "oral_1", "units": {"time": "h", "conc": "mg/L"}, "dose": {"unit": "mg"}, "blq": False,
            "gate": gate, "seed": seed, "turns": turns, "tool_arg_audit": {"calls": 0, "deviating_calls": 0}}

class TestAnalysis(unittest.TestCase):
    def test_strict_rule_pass_k_and_paired_comparison(self):
        # v1: a passes on all seeds, b on 2 of 3, c never, d all. v2: a, b, c pass on all seeds, d fails on seed 3.
        plan = {"v1": {"a": [8, 8, 8], "b": [8, 7, 8], "c": [6, 6, 6], "d": [8, 8, 8]},
                "v2": {"a": [8, 8, 8], "b": [8, 8, 8], "c": [8, 8, 8], "d": [8, 8, 7]}}
        tmp = tempfile.mkdtemp(prefix="apo_analysis_")
        try:
            for g, ex in plan.items():
                for s in (1, 2, 3):
                    rd = rf.run_dir(tmp, g, s); os.makedirs(rd)
                    for i, nc in ex.items():
                        with open(os.path.join(rd, i + ".json"), "w") as f: json.dump(synthetic_record(i, g, s, nc[s - 1], int(i == "c")), f)
            res = rf.analyse("dev", base=tmp)
            v1, v2 = res["configurations"]["v1"], res["configurations"]["v2"]
            self.assertEqual(v1["failed_ids"], ["b", "c"]); self.assertEqual(v2["failed_ids"], ["d"])
            self.assertEqual(v1["failed"]["interval"], stats.clopper_pearson(2, 4))
            self.assertAlmostEqual(v1["pass_k"][1], (3 + 2 + 0 + 3) / 12)
            self.assertAlmostEqual(v1["pass_k"][2], (1 + 1 / 3 + 0 + 1) / 4)
            self.assertAlmostEqual(v1["pass_k"][3], 2 / 4)
            self.assertEqual(v1["mixed_across_seeds"], ["b"]); self.assertEqual(v1["unverified_shown_ids"], ["c"])
            self.assertEqual((v1["turns_correct"], v1["turns"]), (8 * 3 * 3 - 1 + 18, 96))
            p = res["paired"]
            self.assertEqual((p["only_c1_passes"], p["only_c2_passes"], p["both_pass"], p["neither_passes"]), (["d"], ["b", "c"], 1, 0))
            self.assertEqual(p["mcnemar_p"], stats.mcnemar_exact(1, 2))
            self.assertAlmostEqual(p["mean_d"], ((-1 / 24) + (1 / 24) + (6 / 24) + 0) / 4)
            self.assertEqual(res["demo_gate_decision"]["demo_gate"], "v2")          # 3 passed against 2
            self.assertFalse(res["confirmatory"])
            with open(os.path.join(tmp, "ANALYSIS.md"), encoding="utf-8") as f: md = f.read()
            self.assertIn("Demo-gate decision (§8): **v2**", md); self.assertIn("pass^3 (strict rule of §6.3)", md)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_missing_exercise_fails_it(self):
        tmp = tempfile.mkdtemp(prefix="apo_analysis_")
        try:
            for s in (1, 2):
                rd = rf.run_dir(tmp, "v1", s); os.makedirs(rd)
                for i in ("a", "b") if s == 1 else ("a",):
                    with open(os.path.join(rd, i + ".json"), "w") as f: json.dump(synthetic_record(i, "v1", s, 8), f)
            c = rf.analyse("demo", base=tmp)["configurations"]["v1"]
            self.assertEqual(c["failed_ids"], ["b"]); self.assertEqual(c["per_exercise"]["b"]["missing_seeds"], [2])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestDryRun(unittest.TestCase):
    """The whole pipeline with the stub model: real client, real engine, both gates, rubric, reports, analysis."""
    def test_two_exercises_two_gates_two_seeds(self):
        ids = [os.path.basename(d) for d in mf.list_exercises("demo")[:2]]
        tmp = tempfile.mkdtemp(prefix="apo_dry_")
        try:
            for g in ("v1", "v2"):
                rf.run("demo", g, [1, 2], ids=ids, stub=True, base=tmp, out=lambda *a: None)
            res = rf.analyse("demo", base=tmp)
            for g in ("v1", "v2"):
                c = res["configurations"][g]
                self.assertEqual(c["failed"]["failed"], 0, c["failed_ids"]); self.assertEqual(c["pass_k"][2], 1.0)
                self.assertEqual(c["outcomes"]["CORRECT"], 32); self.assertEqual(c["unverified_shown_ids"], [])
                rec = rf._load(os.path.join(tmp, g, "seed-2", ids[0] + ".json"))
                self.assertEqual((rec["gate"], rec["seed"]), (g, 2))
            self.assertFalse(res["confirmatory"]); self.assertTrue(any("stub" in n for n in res["notes"]))
            self.assertEqual(res["paired"]["mcnemar_p"], 1.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_injected_errors_are_caught(self):
        ids = [os.path.basename(mf.list_exercises("demo")[0])]
        tmp = tempfile.mkdtemp(prefix="apo_dry_")
        try:
            for g in ("v1", "v2"):
                rf.run("demo", g, [1], ids=ids, stub=True, stub_error_rate=1.0, base=tmp, out=lambda *a: None)
            res = rf.analyse("demo", base=tmp)
            v1, v2 = res["configurations"]["v1"], res["configurations"]["v2"]
            self.assertEqual(v1["failed_ids"], ids); self.assertEqual(v2["failed_ids"], ids)
            self.assertEqual(v1["unverified_shown_ids"], ids)                 # v1: the wrong number is shown with its badge
            self.assertGreater(v2["outcomes"]["WRONG"], 0)                    # v2: the wrong parameter renders, the rubric rejects it
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
