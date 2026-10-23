"""Tests of the offline check of the gate v3 grammar (bench/grammar_offline.py): the stored gate v2 development runs, no model.

Two kinds of tests.

  * the pinned figures: on bench/runs/decision/v2 (skipped when the stored runs are not on disk) the grammar accepts 541 of the 564
    final answers gate v2 passed without a finding, refuses 184 of the 188 first drafts that had findings, and catches 646 of their
    651 findings. A change of gate_v3.py that moves one of these is a change of the arm: the figures are re-pinned here, and in
    bench/GRAMMAR_ARM.md only with a new, dated entry in bench/frozen/LEDGER.md.
  * the script itself, on a small synthetic run written to a temporary folder: how the turns are paired, which references a turn
    sees, which turns are checked, how a refusal is classified and a finding attributed.

And the second reader: on a sample of the stored answers, tests/gbnf_reader.py (an Earley recogniser that shares no code with
gate_v3) reads the printed GBNF text and agrees with the stack engine prefix by prefix, so that "accepted" above is a property of
the text the server would receive. (On all 752 stored answers, 227,317 characters, the two agree: run once, not repeated here.)
"""
import contextlib, io, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, HERE)
import gate_v2, gate_v3                           # noqa: E402
import gbnf_reader                                # noqa: E402
import test_gate_v2 as t2                         # noqa: E402
from bench import grammar_offline as go           # noqa: E402

_CACHE = {}

def stored():
    """(turns, {"identifiers": result, "strict": result}) of the stored runs, computed once (about 35 s)."""
    if not glob_runs(): raise unittest.SkipTest("bench/runs/decision/v2 is not on disk")
    if not _CACHE:
        turns = go.load_turns()
        _CACHE["turns"] = turns
        _CACHE["results"] = {"identifiers": go.check(turns, idents=True), "strict": go.check(turns, idents=False)}
    return _CACHE["turns"], _CACHE["results"]

def glob_runs():
    return os.path.isdir(go.RUNS) and any(n.startswith("seed-") for n in os.listdir(go.RUNS))


# ================================================================ the figures
class TestStoredRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.turns, cls.results = stored()
        cls.arm, cls.strict = go.tally(cls.results["identifiers"]), go.tally(cls.results["strict"])

    def test_the_runs_are_three_seeds_of_twenty_five_exercises_of_eight_turns(self):
        self.assertEqual(len(self.turns), 600)
        self.assertEqual(sorted({t["seed"] for t in self.turns}), [1, 2, 3])
        self.assertEqual(len({t["exercise"] for t in self.turns}), 25)
        self.assertEqual(sorted({t["turn"] for t in self.turns}), list(range(1, 9)))
        self.assertEqual(self.arm["turns"], 600); self.assertEqual(self.arm["seeds"], [1, 2, 3])

    def test_the_replay_gives_gate_v2_the_counts_it_stored(self):
        """The grammar of a turn is built from the references and user messages `load_turns` rebuilds; gate v2, given the same, counts
        what it counted when the run was made. A wrong visibility (a later reference, a missing message) would move these counts."""
        bad = []
        for t in self.turns:
            g = t["gate"]
            draft = g["first_answer"] if g.get("regenerated") else t["final"]
            res = gate_v2.check(draft, t["calls"], t["users"], decimal_mark=",")
            got = {k: res[k] for k in ("numbers_total", "numbers_unverified", "numbers_exempt", "references_total", "references_unresolved")}
            if got != g["before"]: bad.append((t["seed"], t["exercise"], t["turn"], got, g["before"]))
        self.assertEqual(bad, [])

    def test_the_memory_of_an_exercise_only_grows(self):
        for t in self.turns:
            for r, rec in t["calls"].items(): self.assertEqual(rec["ref"], r)
        first = [t for t in self.turns if t["turn"] == 1]
        later = [t for t in self.turns if t["turn"] == 8]
        self.assertLess(sum(len(t["calls"]) for t in first), sum(len(t["calls"]) for t in later))      # the memory grows along an exercise
        for ex in {t["exercise"] for t in self.turns}:
            seq = [t for t in self.turns if t["exercise"] == ex and t["seed"] == 1]
            for a, b in zip(seq, seq[1:]):
                self.assertTrue(set(a["calls"]) <= set(b["calls"]))                                      # never fewer than the turn before
                self.assertEqual(b["users"][:len(a["users"])], a["users"])

    def test_clean_finals_the_arm(self):
        m = self.arm
        self.assertEqual((m["clean"], m["accepted"]), (564, 541))
        self.assertEqual(m["causes"], {"number": 17, "numeric character": 3, "unit-like word": 2, "label": 1})
        self.assertEqual(sum(m["causes"].values()), m["clean"] - m["accepted"])

    def test_clean_finals_strict(self):
        m = self.strict
        self.assertEqual((m["clean"], m["accepted"]), (564, 469))
        self.assertEqual(m["causes"], {"identifier": 74, "number": 16, "numeric character": 3, "unit-like word": 1, "label": 1})
        self.assertEqual(sum(m["causes"].values()), m["clean"] - m["accepted"])

    def test_the_strict_grammar_accepts_nothing_the_arm_refuses(self):
        arm = {(c["seed"], c["exercise"], c["turn"]): c["accepted"] for c in self.results["identifiers"]["clean"]}
        for c in self.results["strict"]["clean"]:
            if c["accepted"]: self.assertTrue(arm[(c["seed"], c["exercise"], c["turn"])])

    def test_the_refusals_are_by_design_not_by_accident(self):
        """Every refusal of a final the arm refuses is of a kind the docstring of gate_v3 lists as stricter than gate v2."""
        for c in self.results["identifiers"]["clean"]:
            if not c["accepted"]: self.assertIn(c["cause"], {"number", "numeric character", "unit-like word", "label"}, c)

    def test_first_drafts_the_arm(self):
        m = self.arm
        self.assertEqual((m["drafts"], m["refused"]), (188, 184))
        self.assertEqual((m["findings"], m["caught"], m["inside"]), (651, 646, 636))
        self.assertEqual({k: (v["findings"], v["caught"]) for k, v in m["by_class"].items()},
                         {"unit": (349, 349), "unresolved": (207, 207), "untyped": (17, 17), "digit": (11, 11), "arithmetic": (9, 9), "bare": (53, 53), "spelled": (5, 0)})
        self.assertEqual({k: (v["findings"], v["caught"]) for k, v in m["by_family"].items()},
                         {"unit after a reference": (349, 349), "reference that cannot be printed": (224, 224), "other text next to a reference": (20, 20),
                          "bare number": (53, 53), "spelled-out number": (5, 0)})

    def test_first_drafts_strict(self):
        m = self.strict
        self.assertEqual((m["drafts"], m["refused"], m["findings"], m["caught"]), (188, 184, 651, 647))

    def test_the_drafts_the_grammar_accepts_have_only_spelled_out_numbers(self):
        """Four drafts, each with "un d" (un délai): gate v2 reads "un" + "d" (day) as a quantity spelled in words, a false positive."""
        accepted = [d for d in self.results["identifiers"]["drafts"] if not d["refused"]]
        self.assertEqual(len(accepted), 4)
        for d in accepted:
            self.assertEqual({f["cls"] for f in d["findings"]}, {"spelled"})
            self.assertEqual([f["text"] for f in d["findings"]], ["un d"])

    def test_every_refused_draft_is_refused_at_a_finding(self):
        """No draft is refused only for something gate v2 did not find: each of the 184 has a finding the refusal touches."""
        for d in self.results["identifiers"]["drafts"]:
            if d["refused"]: self.assertTrue(any(f["caught"] for f in d["findings"]), d)

    def test_every_finding_of_the_covered_kinds_is_caught(self):
        for d in self.results["identifiers"]["drafts"]:
            for f in d["findings"]:
                if f["cls"] != "spelled": self.assertTrue(f["caught"], (d["seed"], d["exercise"], d["turn"], f))

    def test_a_regenerated_final_is_refused_more_often_than_a_first_one(self):
        """The 152 regenerated finals gate v2 passed were written under pressure: 18 of them use a bare small integer; of 412 others, 5."""
        clean = self.results["identifiers"]["clean"]
        again = [c for c in clean if c["regenerated"]]; first = [c for c in clean if not c["regenerated"]]
        self.assertEqual((len(again), sum(c["accepted"] for c in again)), (152, 134))
        self.assertEqual((len(first), sum(c["accepted"] for c in first)), (412, 407))

    def test_grammar_sizes(self):
        self.assertEqual(self.arm["rules"], (316, 418, 1044))
        self.assertEqual(self.arm["bytes"], (33973, 39799, 75969))

    def test_the_report_and_the_json_hold_the_same_figures(self):
        md = go.markdown(go.RUNS, self.results)
        for needle in ("| with identifiers (the arm) | 564 | 541 (95.9 %) | 23 |", "| strict | 564 | 469 (83.2 %) | 95 |",
                       "| with identifiers (the arm) | 188 | 184 | 4 | 651 | 646 | 636 |", "| **total** | 651 | 646 | 636 |"):
            self.assertIn(needle, md)
        self.assertEqual(md.count("\n- seed "), 23 + 4)                              # the 23 refusals and the 4 accepted drafts
        self.assertEqual(json.loads(json.dumps(self.results, ensure_ascii=False)), self.results)


class TestSecondReader(unittest.TestCase):
    """The printed GBNF text, read by an independent Earley recogniser, against the stack engine: same prefixes alive, same acceptance."""

    def test_a_sample_of_the_stored_answers(self):
        turns, _ = stored()
        n = 0
        for i, t in enumerate(turns):
            if i % 6: continue
            g = t["gate"]
            texts = ([t["final"]] if not g.get("findings") else []) + ([g["first_answer"]] if g.get("regenerated") else [])
            if not texts: continue
            gr = gate_v3.build(t["calls"], t["users"], None)
            reader, m = gbnf_reader.Reader(gr.gbnf), gr.machine
            for text in texts:
                st = m.start
                want = [(True, m.accepting(st))]
                for ch in text:
                    st = m.step(st, ch); want.append((bool(st), bool(st) and m.accepting(st)))
                with self.subTest(seed=t["seed"], exercise=t["exercise"], turn=t["turn"]): self.assertEqual(reader.run(text), want)
                n += 1
        self.assertGreater(n, 80)


# ================================================================ the script, on a small synthetic run
USER1 = t2.USER
USER2 = "Et la demi-vie ?"
USER3 = "Et la clairance ?"

def jl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def make_run(root):
    """seed-1/ex01_demo-data with three turns: a clean first answer; a regenerated one (draft with a bare number, final clean); one that
    shows a finding (not checked). A second call is made in turn 3 only."""
    d = os.path.join(root, "seed-1", "ex01_demo-data"); os.makedirs(d)
    calls = t2.CALLS
    draft = "La demi-vie est de 6,54 h."
    seen = {"call_1": calls["call_1"], "call_2": calls["call_2"]}
    f2 = gate_v2.check(draft, seen, [USER1, USER2], t2.SCHEMAS, decimal_mark=",")["findings"]
    jl(os.path.join(d, "log.jsonl"), [
        {"i": 0, "role": "user", "content": USER1},
        {"i": 1, "role": "tool_call", "content": "", "calls": []},
        {"i": 2, "role": "tool_result", "name": "data_import", "content": '{"ref":"call_1","delimiter":","}'},
        {"i": 3, "role": "tool_call", "content": "", "calls": []},
        {"i": 4, "role": "tool_result", "name": "nca_run", "content": '{"ref":"call_2","analysis":7}'},
        {"i": 5, "role": "assistant", "content": "Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}}."},
        {"i": 6, "role": "user", "content": USER2},
        {"i": 7, "role": "assistant", "content": "La demi-vie est {{call_2.half.life}}."},
        {"i": 8, "role": "user", "content": USER3},
        {"i": 9, "role": "tool_call", "content": "", "calls": []},
        {"i": 10, "role": "tool_result", "name": "analysis_compare", "content": "TOOL ERROR: a and b are the same analysis"},
        {"i": 11, "role": "tool_result", "name": "nca_run", "content": '{"ref":"call_3","analysis":9}'},
        {"i": 12, "role": "assistant", "content": "La clairance est 0,81 L/h."}])
    jl(os.path.join(d, "refs.jsonl"), [calls["call_1"], calls["call_2"], calls["call_3"]])
    jl(os.path.join(d, "gate.jsonl"), [
        {"turn": 1, "regenerated": False, "kept": "first", "findings": []},
        {"turn": 2, "regenerated": True, "kept": "regenerated", "findings": [], "first_answer": draft, "first_findings": f2},
        {"turn": 3, "regenerated": False, "kept": "first", "findings": [{"kind": "bare_number"}]}])
    return d


class TestScriptOnASyntheticRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="apo_goff_"); make_run(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_turns_are_paired_with_their_last_assistant_message(self):
        log = [{"role": "user"}, {"role": "tool_call"}, {"role": "tool_result"}, {"role": "assistant"}, {"role": "assistant"}, {"role": "user"}, {"role": "assistant"}]
        self.assertEqual(go.turns_of(log), [(0, 4), (5, 6)])

    def test_load_turns_rebuilds_what_each_turn_could_cite_and_the_messages_it_had(self):
        ts = go.load_turns(self.root)
        self.assertEqual([(t["seed"], t["exercise"], t["turn"]) for t in ts], [(1, "ex01_demo", 1), (1, "ex01_demo", 2), (1, "ex01_demo", 3)])
        self.assertEqual([sorted(t["calls"]) for t in ts], [["call_1", "call_2"], ["call_1", "call_2"], ["call_1", "call_2", "call_3"]])
        self.assertEqual([t["users"] for t in ts], [[USER1], [USER1, USER2], [USER1, USER2, USER3]])
        self.assertEqual(ts[0]["final"], "Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}}.")
        self.assertEqual(ts[2]["gate"]["findings"], [{"kind": "bare_number"}])

    def test_a_tool_error_is_no_reference(self):
        self.assertNotIn("call_4", go.load_turns(self.root)[2]["calls"])

    def test_missing_or_unusable_runs_fail_loudly(self):
        with self.assertRaises(FileNotFoundError): go.load_turns(os.path.join(self.root, "nothing"))
        os.remove(os.path.join(self.root, "seed-1", "ex01_demo-data", "refs.jsonl"))
        with self.assertRaises(FileNotFoundError): go.load_turns(self.root)

    def test_a_log_and_a_gate_file_that_disagree_fail_loudly(self):
        p = os.path.join(self.root, "seed-1", "ex01_demo-data", "gate.jsonl")
        with open(p, encoding="utf-8") as f: rows = [json.loads(l) for l in f]
        jl(p, rows[:2])
        with self.assertRaises(ValueError): go.load_turns(self.root)

    def test_check_looks_at_clean_finals_and_at_drafts_and_at_nothing_else(self):
        res = go.check(go.load_turns(self.root))
        self.assertEqual([(c["turn"], c["accepted"], c["regenerated"], c["cause"]) for c in res["clean"]], [(1, True, False, None), (2, True, True, None)])
        self.assertEqual([(d["turn"], d["refused"]) for d in res["drafts"]], [(2, True)])
        (d,) = res["drafts"]
        self.assertEqual([(f["cls"], f["caught"], f["inside"]) for f in d["findings"]], [("bare", True, True)])
        self.assertIn("6,[5]4", d["at"])                                                      # 6 and 6,9 are the user's, 6,5 is not
        t = go.tally(res)
        self.assertEqual((t["clean"], t["accepted"], t["drafts"], t["refused"], t["findings"], t["caught"]), (2, 2, 1, 1, 1, 1))

    def test_a_clean_final_the_grammar_refuses_is_counted_and_explained(self):
        p = os.path.join(self.root, "seed-1", "ex01_demo-data", "log.jsonl")
        with open(p, encoding="utf-8") as f: rows = [json.loads(l) for l in f]
        rows[5]["content"] = "3 points ont servi, Cmax = {{call_2.cmax}}."
        jl(p, rows)
        res = go.check(go.load_turns(self.root))
        first = res["clean"][0]
        self.assertFalse(first["accepted"]); self.assertEqual(first["cause"], "number"); self.assertTrue(first["at"].startswith("[3] points"))
        self.assertEqual(go.tally(res)["causes"], {"number": 1})

    def test_the_command_line_prints_json_and_writes_nothing(self):
        before = sorted(os.listdir(os.path.join(self.root, "seed-1", "ex01_demo-data")))
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = go.main([self.root, "--json", "--no-strict"])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(set(data), {"runs", "identifiers"}); self.assertEqual(len(data["identifiers"]["clean"]), 2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "seed-1", "ex01_demo-data"))), before)
        self.assertEqual(sorted(os.listdir(self.root)), ["seed-1"])

    def test_the_command_line_prints_the_report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): go.main([self.root])
        md = out.getvalue()
        self.assertIn("# Gate v3 grammar, offline", md); self.assertIn("| strict |", md); self.assertIn("(a) Final answers", md); self.assertIn("(b) First drafts", md)


# ================================================================ classification and attribution
class TestRefusalCauses(unittest.TestCase):
    GR = gate_v3.build(t2.CALLS, [t2.USER], t2.SCHEMAS)
    STRICT = gate_v3.build(t2.CALLS, [t2.USER], t2.SCHEMAS, idents=False)

    def cause(self, text, gr=None):
        spans = (gr or self.GR).scan(text)
        self.assertTrue(spans, f"the grammar accepts {text!r}")
        return go.refusal_cause(text, spans[0])

    def test_a_number_the_user_did_not_type(self):
        self.assertEqual(self.cause("Les 3 points ont servi."), "number")
        self.assertEqual(self.cause("Cmax = {{call_2.cmax}} sur 4 points."), "number")
        self.assertEqual(self.cause("Message (#1), vous avez indiqué"), "number")               # refused at the ")" that follows the 1
        self.assertEqual(self.cause("Du 12,5 au 13."), "number")

    def test_an_analysis_number_is_an_identifier_for_the_strict_grammar_only(self):
        self.assertTrue(self.GR.accepts("Dans l'analyse 7, Cmax = {{call_2.cmax}}."))
        self.assertEqual(self.cause("Dans l'analyse 7, Cmax = {{call_2.cmax}}.", self.STRICT), "identifier")
        self.assertEqual(self.cause("Le sujet 1 a Cmax = {{call_2.cmax}}.", self.STRICT), "identifier")

    def test_a_label_that_starts_with_a_digit_is_written_after_a_parenthesis_only(self):
        self.assertTrue(self.GR.accepts("λz (1/h)."))
        self.assertEqual(self.cause("h pour MRT, 1/h pour λz."), "label")

    def test_a_superscript_or_fraction_character(self):
        self.assertEqual(self.cause("A² = {{call_2.cmax}}"), "numeric character")
        self.assertTrue(self.GR.accepts("R² = {{call_2.r.squared}}"))                         # a closed label

    def test_a_word_that_begins_like_a_unit_after_a_reference(self):
        self.assertEqual(self.cause("Cmax {{call_2.cmax}} (les valeurs)."), "unit-like word")
        self.assertEqual(self.cause("Cmax {{call_2.cmax}} (MRT)."), "unit-like word")

    def test_a_text_that_stops_in_the_middle_of_a_reference(self):
        self.assertEqual(self.cause("Cmax = {{call_2"), "unfinished")
        self.assertEqual(self.cause("Cmax = {{call_2.cm"), "unfinished")
        self.assertEqual(self.cause(""), "unfinished")

    def test_a_text_that_stops_after_a_number_is_a_number_not_an_unfinished_text(self):
        self.assertEqual(self.cause("Le sujet 1.", self.STRICT), "identifier")                 # "1." is the start of a decimal that never comes

    def test_anything_else(self):
        self.assertEqual(self.cause("Une accolade { dans le texte."), "other")

    def test_every_cause_has_a_description(self):
        for text, gr in (("3 points", None), ("A²", None), ("{{call_2.cmax}} (les", None), ("1/h", None), ("{", None), ("", None), ("sujet 1", self.STRICT)):
            self.assertIn(self.cause(text, gr), go.CAUSES)


class TestAttribution(unittest.TestCase):
    def test_a_refusal_touches_a_finding_it_overlaps_or_borders(self):
        spans = [(10, 11, [])]
        self.assertTrue(go.touches(spans, 5, 15)); self.assertTrue(go.touches(spans, 11, 20)); self.assertTrue(go.touches(spans, 3, 10))       # overlap, and one character either side
        self.assertFalse(go.touches(spans, 12, 20)); self.assertFalse(go.touches(spans, 0, 9))                                               # two characters away
        self.assertFalse(go.touches(spans, 11, 20, slack=0)); self.assertFalse(go.touches(spans, 3, 10, slack=0)); self.assertTrue(go.touches(spans, 5, 15, slack=0))

    def test_a_text_that_stops_where_it_cannot_is_an_empty_span_at_the_end(self):
        spans = [(30, 30, [])]
        self.assertTrue(go.touches(spans, 20, 30)); self.assertTrue(go.touches(spans, 30, 31))
        self.assertFalse(go.touches(spans, 20, 29)); self.assertFalse(go.touches(spans, 31, 40))

    def test_no_span_no_finding_caught(self):
        self.assertFalse(go.touches([], 0, 100))

    def test_gate_v2_findings_are_put_in_their_class(self):
        def f(kind, reason=""): return {"kind": kind, "reason": reason}
        self.assertEqual(go.finding_class(f("adjacent_to_reference", "unit next to a reference (the client prints it)")), "unit")
        self.assertEqual(go.finding_class(f("adjacent_to_reference", "digit after a reference")), "digit")
        self.assertEqual(go.finding_class(f("adjacent_to_reference", "arithmetic next to a reference")), "arithmetic")
        self.assertEqual(go.finding_class(f("adjacent_to_reference", "sign or arithmetic next to a reference")), "arithmetic")
        self.assertEqual(go.finding_class(f("adjacent_to_reference", "a sign written in words next to a reference (the client prints the sign)")), "arithmetic")
        for kind, want in (("unresolved_reference", "unresolved"), ("untyped_reference", "untyped"), ("malformed_reference", "malformed"), ("bare_number", "bare"),
                           ("number_word", "spelled"), ("contradictory_unit", "contradictory")):
            self.assertEqual(go.finding_class(f(kind)), want)
        with self.assertRaises(KeyError): go.finding_class(f("a_kind_gate_v2_does_not_have"))                  # a new kind must be put in the table

    def test_every_class_has_a_family_and_a_description(self):
        self.assertEqual({k for k, _ in go.FINDINGS}, set(go.FAMILIES))

    def test_the_excerpt_marks_the_refused_character_and_stays_on_one_line(self):
        self.assertEqual(go.excerpt("abc\ndef 3 points", 8), "abc\\ndef [3] points")
        self.assertEqual(go.excerpt("abc", 3), "abc[end]")
        self.assertNotIn("`", go.excerpt("a `b` c", 3))
        self.assertEqual(len(go.excerpt("x" * 500, 250)), 24 + 3 + 16)


if __name__ == "__main__":
    unittest.main()
