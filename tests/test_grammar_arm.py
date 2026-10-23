"""The reading of the grammar arm (bench/grammar_arm.py, GRAMMAR_ARM.md §4 and §5) and its place in bench/run_frozen.py.

No model and no server. The decision table is tested on synthetic measures, the numbers the pre-registration quotes on the stored
v1 and v2 runs of bench/runs/decision (read only), the analysis end to end on a copy of the stored v2 runs relabelled as v3 in a
temporary folder, and the command on the stub model (the real caladrius-mcp, no language model).
"""
import contextlib, hashlib, io, json, os, shutil, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT)
import apothicaire  # noqa: E402
from bench import grammar_arm as ga, make_exercises as mk, run_frozen as rf  # noqa: E402

DECISION = rf.DEV_BASE
DOC = os.path.join(AGENT, "bench", "GRAMMAR_ARM.md")
GOOD = dict(exercises=25, passed=20, turns=600, turns_correct=590, unverifiable_exercises=1, regenerations=40, median_s=6.0, p95_s=20.0,
            loop=0, abstained=0, free_digits=0)


def sha(path):
    with open(path, "rb") as f: return hashlib.sha256(f.read()).hexdigest()


class TestTheNumbersAreThoseOfThePreRegistration(unittest.TestCase):
    """GRAMMAR_ARM.md wins over the code (its §4): a number changed on one side only fails here."""

    @classmethod
    def setUpClass(cls):
        with open(DOC, encoding="utf-8") as f: cls.doc = f.read()
        cls.s4 = cls.doc.split("## 4. Thresholds")[1].split("## 5. Reading")[0]
        cls.s5 = cls.doc.split("## 5. Reading")[1].split("## 6.")[0]

    def test_section_4_and_the_constants_agree(self):
        for text in ("at most 3 / 25", "at least 576 / 600", "fewer than 562 / 600", "at most 50", "at most 9 s", "more than 13.5 s", "more than 12 of 600"):
            self.assertIn(text, self.s4)
        self.assertEqual((ga.FREE_DIGITS_MAX, ga.UNVERIFIABLE_MAX, ga.CORRECT_MIN, ga.REGENERATIONS_MAX, ga.MEDIAN_MAX_S), (0, 3, 576, 50, 9.0))
        self.assertEqual((ga.KILL_CORRECT_BELOW, ga.KILL_MEDIAN_ABOVE_S, ga.KILL_LOOP_ABSTAINED_ABOVE), (562, 13.5, 12))
        self.assertEqual(ga.KILL_LOOP_ABSTAINED_ABOVE, int(0.02 * ga.TURNS))                       # 2 % of the turns
        self.assertEqual((ga.TURNS, ga.EXERCISES, ga.SEEDS), (600, len(mk.list_exercises()), [1, 2, 3]))

    def test_the_baselines_of_section_4_are_the_stored_runs(self):
        runs = rf.load_runs(DECISION, ["v1", "v2"])
        ids = sorted(runs["v1"][1])
        for g, row in (("v1", ("583 / 600", "3 / 25", "12", "4.5 s")), ("v2", ("562 / 600", "17 / 25", "188", "6.85 s"))):
            c = rf.config_section(runs[g], ids)
            m = ga.measures(c, ga.gate_records(DECISION, g, [1, 2, 3]), g)
            self.assertEqual((f"{m['turns_correct']} / {m['turns']}", f"{m['unverifiable_exercises']} / {m['exercises']}", str(m["regenerations"]), f"{m['median_s']} s"), row)
            for cell in row: self.assertIn(cell, self.s4.split("**Definitions.**")[0], (g, cell))

    def test_the_five_readings_of_section_5_are_the_strings_of_the_code(self):
        for reading in (ga.KILLED, ga.SUCCESS, ga.COUNT_UNCHANGED, ga.NO_DECISION): self.assertIn(f"**{reading}**", self.s5)
        self.assertIn("**no reading**", self.s5); self.assertTrue(ga.NO_READING.startswith("no reading"))

    def test_the_kill_column_has_four_conditions_and_the_success_column_five_thresholds(self):
        rows = [r for r in self.s4.split("\n") if r.startswith("| ") and r.count("|") == 6][1:]       # the table's rows, its header dropped
        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(1 for r in rows if r.split("|")[5].strip()), 4)                          # Kill column
        self.assertEqual(sum(1 for r in rows if r.split("|")[4].strip()), 5)                          # Success column


class TestFreeDigit(unittest.TestCase):
    def test_a_bare_number_and_a_digit_after_a_reference_count_nothing_else_does(self):
        yes = [{"kind": "bare_number", "reason": "a number typed by hand that is not in the user's message"},
               {"kind": "adjacent_to_reference", "reason": "digit after a reference"}]
        no = [{"kind": "adjacent_to_reference", "reason": "unit next to a reference (the client prints it)"},
              {"kind": "adjacent_to_reference", "reason": "arithmetic next to a reference"},
              {"kind": "adjacent_to_reference", "reason": "sign or arithmetic next to a reference"},
              {"kind": "unresolved_reference", "reason": "no parameter 'x' in this analysis"}, {"kind": "untyped_reference"},
              {"kind": "number_word", "reason": "a quantity spelled in words with a unit"}, {"kind": "contradictory_unit"}, {"kind": "malformed_reference"}]
        self.assertTrue(all(ga.is_free_digit(f) for f in yes)); self.assertFalse(any(ga.is_free_digit(f) for f in no))
        self.assertEqual(ga.free_digits([{"findings": yes + no}, {"findings": []}, {}]), 2)
        self.assertEqual(ga.findings_left([{"findings": yes + no}, {"findings": [{"kind": "bare_number"}]}])["bare_number"], 2)


class TestTheDecisionTable(unittest.TestCase):
    """GRAMMAR_ARM.md §5, row by row, and the edges of every threshold."""

    def judge(self, invalid=(), enforcement=(), **change): return ga.judge({**GOOD, **change}, list(enforcement), list(invalid))

    def test_success_needs_the_four_effects_and_at_most_50_regenerations(self):
        j = self.judge(); self.assertEqual((j["reading"], j["valid"], j["kill"], j["missed"], j["four_effects_met"]), (ga.SUCCESS, True, [], [], True))
        edge = self.judge(free_digits=0, unverifiable_exercises=3, turns_correct=576, regenerations=50, median_s=9.0)
        self.assertEqual(edge["reading"], ga.SUCCESS)                                                 # every threshold met exactly at its limit

    def test_the_four_effects_without_the_regeneration_bound_are_not_success_and_not_no_decision(self):
        j = self.judge(regenerations=51)
        self.assertEqual((j["reading"], j["four_effects_met"], j["missed"]), (ga.COUNT_UNCHANGED, True, ["regenerations"]))
        self.assertNotEqual(self.judge(regenerations=188)["reading"], ga.SUCCESS)

    def test_one_effect_missed_without_a_kill_is_no_decision(self):
        for change, missed in ((dict(free_digits=1), "free digits shown"), (dict(unverifiable_exercises=4), "exercises with an unverifiable quantity shown"),
                               (dict(turns_correct=575), "turns CORRECT"), (dict(median_s=9.01), "median time per turn")):
            j = self.judge(**change)
            self.assertEqual((j["reading"], j["kill"], j["missed"]), (ga.NO_DECISION, [], [missed]), change)
            self.assertEqual(self.judge(regenerations=60, **change)["reading"], ga.NO_DECISION)       # also when the count is above 50

    def test_each_kill_condition_alone_kills_and_not_one_step_before(self):
        for change, safe in ((dict(turns_correct=561), dict(turns_correct=562)), (dict(median_s=13.51), dict(median_s=13.5)),
                             (dict(loop=13), dict(loop=12)), (dict(abstained=13), dict(abstained=12)), (dict(loop=7, abstained=6), dict(loop=7, abstained=5))):
            j = self.judge(**change); self.assertEqual((j["reading"], len(j["kill"])), (ga.KILLED, 1), change)
            self.assertNotEqual(self.judge(**safe)["reading"], ga.KILLED, safe)
        j = self.judge(enforcement=["1 regeneration(s) returned a text that breaks the grammar it was sent"])
        self.assertEqual(j["reading"], ga.KILLED); self.assertIn("does not enforce the grammar", j["kill"][0])
        self.assertEqual(len(self.judge(turns_correct=500, median_s=20.0, loop=30, enforcement=["x"])["kill"]), 4)

    def test_an_invalid_run_is_not_read_even_when_a_kill_condition_holds(self):
        j = self.judge(invalid=["300 turns instead of 600"], turns_correct=100, enforcement=["x"])
        self.assertEqual((j["reading"], j["valid"]), (ga.NO_READING, False)); self.assertTrue(j["kill"])
        self.assertEqual(self.judge(invalid=["x"])["reading"], ga.NO_READING)

    def test_a_missing_figure_is_a_miss_not_a_pass(self):
        self.assertEqual(self.judge(free_digits=None)["reading"], ga.NO_DECISION)
        self.assertEqual(self.judge(median_s=None)["reading"], ga.NO_DECISION)


class TestWhatTheStoredRunsSay(unittest.TestCase):
    """The figures GRAMMAR_ARM.md §1 and §4 quote for gate v2, read from the stored gate.jsonl files."""

    @classmethod
    def setUpClass(cls): cls.v2 = ga.gate_records(DECISION, "v2", [1, 2, 3])

    def test_six_hundred_turns_five_free_digits_ninety_three_findings(self):
        self.assertEqual(len(self.v2), 600)
        self.assertEqual(ga.free_digits(self.v2), 5)
        left = ga.findings_left(self.v2)
        self.assertEqual((sum(left.values()), left["bare_number"], left["adjacent_to_reference"]), (93, 5, 55))
        self.assertEqual(sum(1 for r in self.v2 if r["findings"]), 36)
        self.assertEqual(len({r["exercise"] for r in self.v2 if r["findings"]}), 17)
        self.assertEqual(len({r["exercise"] for r in self.v2 for f in r["findings"] if ga.is_free_digit(f)}), 2)       # "bare numbers in 2 exercises"
        self.assertEqual(sum(1 for r in self.v2 for f in r["findings"] if f["kind"] == "adjacent_to_reference" and f["reason"].startswith("digit after")), 0)

    def test_the_seventeen_exercises_with_a_finding_are_those_with_an_unverifiable_quantity(self):
        runs = rf.load_runs(DECISION, ["v2"])
        section = rf.config_section(runs["v2"], sorted(runs["v2"][1]))
        self.assertEqual({r["exercise"] for r in self.v2 if r["findings"]}, set(section["unverified_shown_ids"]))     # §4, "the same set of 17 exercises"

    def test_the_regenerations_of_v2(self):
        f = ga.grammar_facts(self.v2)
        self.assertEqual((f["regenerations"], f["kept"], f["sent"], f["other_versions"]), (188, {"first": 4, "regenerated": 184}, 0, 600))
        self.assertEqual(len(f["not_sent"]), 188)                         # no grammar was ever sent to these: gate v2


class TestTheRunOfGateV3(unittest.TestCase):
    """The reading of a run whose gate.jsonl files are those of the stored v2 runs relabelled as v3, in a temporary folder."""

    @classmethod
    def setUpClass(cls):
        cls.runs = rf.load_runs(DECISION, ["v1", "v2"])
        cls.ids = sorted(cls.runs["v1"][1])
        cls.sections = {g: rf.config_section(cls.runs[g], cls.ids) for g in ("v1", "v2")}
        cls.infos = {g: [rf._load(os.path.join(DECISION, g, f"seed-{s}", "run.json")) for s in (1, 2, 3)] for g in ("v1", "v2")}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="apo_arm_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    @staticmethod
    def grammar_record(r):
        st = r.get("regen_stats") or {}
        g = {"sent": True, "sha256": "0" * 64, "rules": 418, "bytes": 39800, "refs": 10, "numbers": 3, "idents": 2, "dropped": 0, "build_ms": 15.0}
        if "error" not in st:
            g["conformance"] = {"accepted": st.get("finish_reason") != "length", "alive": True, "refused_at": None, "finish_reason": st.get("finish_reason"), "violation": False}
            g["text"] = r.get("rendered") or ""
        return g

    def make_v3(self, mutate=lambda r: None, grammar=True, model=None):
        """The stored v2 runs copied under tmp/v3: turn records as they are, run.json relabelled, gate.jsonl relabelled and, for each
        regeneration, given the grammar record gate v3 writes; `mutate(record)` may change it before it is written."""
        for s in (1, 2, 3):
            src, dst = os.path.join(DECISION, "v2", f"seed-{s}"), os.path.join(self.tmp, "v3", f"seed-{s}")
            os.makedirs(dst)
            info = rf._load(os.path.join(src, "run.json")); info.update(gate="v3", config="v3")
            if model: info["model"] = model
            with open(os.path.join(dst, "run.json"), "w", encoding="utf-8") as f: json.dump(info, f)
            for fn in os.listdir(src):
                p = os.path.join(src, fn)
                if fn.endswith(".json") and fn not in rf.NOT_RECORDS: shutil.copy(p, os.path.join(dst, fn))
                elif fn.endswith("-data") and os.path.isdir(p):
                    os.makedirs(os.path.join(dst, fn))
                    with open(os.path.join(p, "gate.jsonl"), encoding="utf-8") as f, open(os.path.join(dst, fn, "gate.jsonl"), "w", encoding="utf-8", newline="\n") as g:
                        for line in f:
                            r = json.loads(line); r["version"] = "v3"
                            if r.get("regenerated") and grammar: r["grammar"] = self.grammar_record(r)
                            mutate(r)
                            g.write(json.dumps(r, ensure_ascii=False) + "\n")

    def edit_record(self, seed, exercise, change):
        """Change one turn record of the copy in tmp (what a partial or interrupted run would leave)."""
        p = os.path.join(self.tmp, "v3", f"seed-{seed}", exercise + ".json")
        rec = rf._load(p); change(rec)
        with open(p, "w", encoding="utf-8", newline="\n") as f: json.dump(rec, f)

    def read(self):
        """What `analyse` does with the copy in tmp: its records and run.json files are loaded from there, v1 and v2 from the decision."""
        runs = {**self.runs, **rf.load_runs(self.tmp, ["v3"])}
        sections = {**self.sections, "v3": rf.config_section(runs["v3"], self.ids)}
        infos = {**self.infos, "v3": [rf._load(os.path.join(self.tmp, "v3", f"seed-{s}", "run.json")) for s in sorted(runs["v3"])]}
        return ga.read(sections, {"v1": DECISION, "v2": DECISION, "v3": self.tmp}, runs, infos)

    def test_a_run_with_the_figures_of_v2_is_read_as_no_decision(self):
        self.make_v3(); arm = self.read(); j = arm["v3"]["judgement"]
        self.assertEqual((j["valid"], j["kill"], j["reading"]), (True, [], ga.NO_DECISION))
        self.assertEqual(j["missed"], ["free digits shown", "exercises with an unverifiable quantity shown", "turns CORRECT", "regenerations"])
        self.assertEqual({g: arm["configs"][g]["turns_correct"] for g in arm["configs"]}, {"v1": 583, "v2": 562, "v3": 562})
        self.assertEqual({g: arm["configs"][g]["passed"] for g in arm["configs"]}, {"v1": 14, "v2": 6, "v3": 6})                 # strict rule of §6.3
        self.assertEqual((arm["configs"]["v1"]["free_digits"], arm["configs"]["v2"]["free_digits"], arm["configs"]["v3"]["free_digits"]), (None, 5, 5))
        f = arm["v3"]["facts"]
        self.assertEqual((f["regenerations"], f["sent"], f["other_versions"], f["not_sent"], f["violations"], f["server_errors_mentioning_the_grammar"]), (188, 188, 0, [], [], 0))
        self.assertEqual([(e["seed"], e["exercise"], e["turn"]) for e in f["server_errors"]], [(1, "ex15_oral_0", 5)])      # in the stored v2 run: the context was full
        self.assertIn("exceed_context_size_error", f["server_errors"][0]["error"])
        self.assertEqual(f["conformance_recorded"], sum(1 for r in ga.gate_records(DECISION, "v2", [1, 2, 3]) if r.get("regenerated") and "error" not in (r.get("regen_stats") or {})))

    def test_without_a_grammar_on_every_regeneration_the_run_is_invalid(self):
        self.make_v3(grammar=False); j = self.read()["v3"]["judgement"]
        self.assertEqual((j["valid"], j["reading"]), (False, ga.NO_READING))
        self.assertTrue(any("188 regeneration(s) were not sent a grammar" in r for r in j["invalid_reasons"]), j["invalid_reasons"])

    def test_one_regeneration_the_server_did_not_hold_to_the_grammar_kills(self):
        done = []
        def violate(r):
            if r.get("regenerated") and not done and "conformance" in r["grammar"]:
                r["grammar"]["conformance"].update(accepted=False, alive=False, refused_at=3, violation=True); r["grammar"]["text"] = "Abc 12 mg"; done.append(1)
        self.make_v3(violate); arm = self.read(); j = arm["v3"]["judgement"]
        self.assertEqual(j["reading"], ga.KILLED); self.assertIn("does not enforce the grammar", " ".join(j["kill"]))
        v = arm["v3"]["facts"]["violations"]
        self.assertEqual((len(v), v[0]["refused_at"], v[0]["text"]), (1, 3, "Abc 12 mg"))
        md = "\n".join(ga.render(arm)); self.assertIn("refused at character 3: `Abc[ ]12 mg`", md)
        self.assertIn("| the server enforces the grammar | n/a | n/a | NO | | it does not |", md)

    def with_error(self, message):
        """The first regeneration of the run answered by a server error `message` (no text came back, so no conformance either)."""
        done = []
        def err(r):
            if r.get("regenerated") and not done and "conformance" in r["grammar"]:
                r["regen_stats"] = {"error": message}; r["grammar"].pop("conformance"); r["grammar"].pop("text", None); done.append(1)
        self.make_v3(err); return self.read()["v3"]

    def test_a_server_error_that_mentions_the_grammar_kills(self):
        v3 = self.with_error("HTTP 400: Failed to initialize samplers: failed to parse grammar")
        self.assertEqual(v3["judgement"]["reading"], ga.KILLED); self.assertIn("mentions the grammar", " ".join(v3["judgement"]["kill"]))
        self.assertEqual(v3["facts"]["server_errors_mentioning_the_grammar"], 1)

    def test_other_server_errors_do_not_kill_they_are_listed(self):
        v3 = self.with_error("HTTP 503: no slot available")
        self.assertEqual((v3["judgement"]["reading"], v3["judgement"]["valid"], v3["judgement"]["kill"]), (ga.NO_DECISION, True, []))
        self.assertEqual((len(v3["facts"]["server_errors"]), v3["facts"]["server_errors_mentioning_the_grammar"]), (2, 0))     # the stored one, and this one
        self.assertIn("HTTP 503: no slot available", [e["error"] for e in v3["facts"]["server_errors"]])

    def test_a_run_that_does_not_name_the_llama_server_build_is_invalid(self):
        self.make_v3(model="stub model (bench/stub_model.py), no language model"); j = self.read()["v3"]["judgement"]
        self.assertEqual((j["valid"], j["reading"]), (False, ga.NO_READING)); self.assertIn("llama-server " + ga.LLAMA_BUILD, " ".join(j["invalid_reasons"]))

    def invalid(self, *parts):
        """The run in tmp is invalid, not killed and not read, for reasons that contain each of `parts`."""
        j = self.read()["v3"]["judgement"]
        self.assertEqual((j["valid"], j["reading"]), (False, ga.NO_READING))
        for part in parts: self.assertTrue(any(part in r for r in j["invalid_reasons"]), (part, j["invalid_reasons"]))
        return j

    def test_a_run_of_two_seeds_is_invalid(self):
        self.make_v3(); shutil.rmtree(os.path.join(self.tmp, "v3", "seed-3"))
        self.invalid("seeds [1, 2] instead of [1, 2, 3]", "400 turns instead of 600")

    def test_an_exercise_without_a_record_on_a_seed_is_invalid(self):
        self.make_v3(); os.remove(os.path.join(self.tmp, "v3", "seed-2", self.ids[0] + ".json"))
        self.invalid("1 exercise(s) have no record on some seed (" + self.ids[0] + ")")                  # run_frozen counts its turns as missed, not as absent

    def test_a_record_that_stops_before_its_last_turn_is_invalid(self):
        self.make_v3(); self.edit_record(1, self.ids[0], lambda rec: rec["turns"].pop())
        self.invalid("599 turns instead of 600")

    def test_a_gate_record_that_is_not_gate_v3_is_invalid(self):
        done = []
        def old(r):
            if not r.get("regenerated") and not done: r["version"] = "v2"; done.append(1)
        self.make_v3(old); self.invalid("1 gate record(s) are not gate v3")

    def test_a_regeneration_that_was_sent_no_grammar_is_listed_and_the_run_is_invalid(self):
        done = []
        def none(r):
            if r.get("regenerated") and not done and "conformance" in r["grammar"]:
                r["grammar"] = {"sent": False, "error": "grammar of 1200000 bytes, above 1000000"}; done.append(1)
        self.make_v3(none); self.invalid("1 regeneration(s) were not sent a grammar")
        arm = self.read(); f = arm["v3"]["facts"]
        self.assertEqual((f["regenerations"], f["sent"], len(f["not_sent"]), f["not_sent"][0]["error"]), (188, 187, 1, "grammar of 1200000 bytes, above 1000000"))
        self.assertIn("grammar of 1200000 bytes, above 1000000", "\n".join(ga.render(arm)))

    def test_a_text_cut_at_max_tokens_owes_only_a_valid_prefix_it_is_not_a_violation(self):
        done = []
        def cut(r):
            if r.get("regenerated") and not done and "conformance" in r["grammar"]:
                r["grammar"]["conformance"].update(accepted=False, alive=True, refused_at=None, finish_reason="length", violation=False); done.append(1)
        self.make_v3(cut); arm = self.read(); f = arm["v3"]["facts"]; j = arm["v3"]["judgement"]
        self.assertEqual((f["cut_at_max_tokens"], f["violations"], j["valid"], j["kill"], j["reading"]), (1, [], True, [], ga.NO_DECISION))
        self.assertEqual(f["accepted"], f["conformance_recorded"] - 1)

    def test_the_analysis_end_to_end_writes_the_three_configurations_side_by_side_and_leaves_the_decision_alone(self):
        self.make_v3()
        before = {n: sha(os.path.join(DECISION, n)) for n in ("ANALYSIS.md", "analysis.json")}
        res = rf.analyse("dev", "v2", "v3", base=self.tmp, extra=[(DECISION, ["v1", "v2"])])
        self.assertEqual({n: sha(os.path.join(DECISION, n)) for n in before}, before)                  # the decision's analysis is not touched
        self.assertNotIn("demo_gate_decision", res)
        with open(os.path.join(self.tmp, "ANALYSIS.md"), encoding="utf-8") as f: md = f.read()
        self.assertTrue(md.index("## Grammar arm: gate v3 next to v1 and v2") < md.index("## Gate v1"))   # the reading comes first
        self.assertIn("| turns CORRECT | 583 / 600 | 562 / 600 | 562 / 600 | at least 576 / 600 | fewer than 562 / 600 |", md)
        self.assertIn("| regenerations | 12 | 188 | 188 | at most 50 |  |", md)
        self.assertIn("| free digits shown | n/a | 5 | 5 | 0 |  |", md)
        self.assertIn("**Reading (GRAMMAR_ARM.md §5): no decision.** Missed: free digits shown, exercises with an unverifiable quantity shown, "
                      "turns CORRECT, regenerations.", md)
        self.assertIn("| regeneration call, median wall time | 13.13 s (v2: 13.13 s) |", md)                 # the time of the call against v2's
        self.assertIn("exploratory arm: gate v3", md); self.assertNotIn("## Paired comparison", md); self.assertNotIn("Demo-gate decision", md)
        self.assertIn("- v3 against v2 (exact McNemar", md)
        self.assertIn("- v3 against v1 (exact McNemar", md)
        with open(os.path.join(self.tmp, "analysis.json"), encoding="utf-8") as f: js = json.load(f)
        self.assertEqual(js["grammar_arm"]["v3"]["judgement"]["reading"], ga.NO_DECISION)
        self.assertEqual(sorted(js["sources"]), ["v1", "v2"])
        self.assertEqual(set(js["configurations"]), {"v1", "v2", "v3"})


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestTheCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="apo_arm_cmd_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def main(self, *argv):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["run_frozen.py", *argv]), contextlib.redirect_stdout(out): rf.main()
        return out.getvalue()

    def test_the_default_folders(self):
        self.assertEqual(rf.base_dir("dev"), DECISION); self.assertEqual(rf.base_dir("dev", "v1"), DECISION); self.assertEqual(rf.base_dir("dev", "v2"), DECISION)
        self.assertEqual(rf.base_dir("dev", "v3"), os.path.join(AGENT, "bench", "runs", "grammar-dev"))
        self.assertTrue(rf.base_dir("demo").endswith(os.path.join("demo", "runs")))
        self.assertEqual(rf.run_dir(rf.base_dir("dev", "v3"), "v3", 2), os.path.join(AGENT, "bench", "runs", "grammar-dev", "v3", "seed-2"))

    def test_gate_v3_runs_on_the_development_tier_only_and_on_the_27b(self):
        quiet = lambda *a: None
        with self.assertRaises(SystemExit) as cm: rf.run("demo", "v3", [1], stub=True, base=self.tmp, out=quiet)
        self.assertIn("development tier only", str(cm.exception))
        with self.assertRaises(SystemExit) as cm: rf.run("page", "v3", [1], stub=True, base=self.tmp, out=quiet)
        self.assertIn("development tier only", str(cm.exception))
        for kw in ({"api_model": "claude-sonnet-5-5"}, {"api_addendum": "scope"}):
            with self.assertRaises(SystemExit) as cm: rf.run("dev", "v3", [1], base=self.tmp, out=quiet, **kw)
            self.assertIn("not with --api-model or --api-addendum", str(cm.exception))
        self.assertEqual(os.listdir(self.tmp), [])                                                   # nothing was written by a refused run
        with self.assertRaises(SystemExit): self.main("run", "--tier", "demo", "--gate", "v3", "--seeds", "1", "--stub", "--out", self.tmp)

    def test_the_stub_run_of_gate_v3_and_its_analysis_next_to_the_stored_v1_and_v2(self):
        ids = [os.path.basename(d) for d in mk.list_exercises()[:2]]
        before = {n: sha(os.path.join(DECISION, n)) for n in ("ANALYSIS.md", "analysis.json")}
        said = self.main("run", "--tier", "dev", "--gate", "v3", "--seeds", "1", "--ids", ",".join(ids), "--stub", "--out", self.tmp)
        self.assertIn("analyse --tier dev --c1 v2 --c2 v3", said)
        rd = os.path.join(self.tmp, "v3", "seed-1")
        info = rf._load(os.path.join(rd, "run.json"))
        self.assertEqual((info["gate"], info["config"], info["confirmatory"], info["exercises"]), ("v3", "v3", False, ids))
        self.assertTrue(any("gate v3: exploratory arm" in n for n in info["notes"]))
        for i in ids:
            rec = rf._load(os.path.join(rd, i + ".json")); self.assertEqual((rec["gate"], len(rec["turns"])), ("v3", 8))
            with open(os.path.join(rd, i + "-data", "gate.jsonl"), encoding="utf-8") as f: recs = [json.loads(line) for line in f]
            self.assertTrue(recs and all(r["version"] == "v3" for r in recs))
        said = self.main("analyse", "--tier", "dev", "--c1", "v2", "--c2", "v3", "--out", self.tmp)    # no --with: v1 and v2 come from bench/runs/decision
        self.assertIn("grammar arm (GRAMMAR_ARM.md §5): " + ga.NO_READING, said); self.assertIn("written " + os.path.join(self.tmp, "ANALYSIS.md"), said)
        with open(os.path.join(self.tmp, "ANALYSIS.md"), encoding="utf-8") as f: md = f.read()
        self.assertIn("| turns CORRECT | 583 / 600 | 562 / 600 |", md)                               # the stored runs, side by side with the stub's
        self.assertIn("INVALID", md); self.assertIn("stub model", md)
        self.assertEqual({n: sha(os.path.join(DECISION, n)) for n in before}, before)                    # the decision's analysis is not touched


if __name__ == "__main__":
    unittest.main()
