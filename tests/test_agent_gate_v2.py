"""Gate v2 (typed rendering) wired into the agent, with a scripted language model and the REAL caladrius-mcp server
(skipped if the binary is not built). No llama.cpp server is needed: `ag.llm.chat` is replaced.

Checked: the tool results shown to the model carry a "ref", the refs are persisted (refs.jsonl) and survive a restart,
a clean answer made of references is rendered with the values and units of the structuredContent (the memory keeps
the references), a typed number or a wrong reference triggers the one regeneration with the v2 reminder at the END
of the messages, a still-wrong answer shows markers and a badge, the v1 default is untouched, and the bench runner
builds a record from a v2 run.
"""
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import apothicaire, optchat, gate_v2  # noqa: E402
import test_digest as td              # noqa: E402
from test_agent_gate import FakeLLM, tool_call, say, IMPORT_ARGS, NCA_ARGS, USER  # noqa: E402

BLQ = td.GOLDENS["edge_blq_6_subjects"]

def shown_params(ag, name="nca_run"):
    digest = json.loads(next(c for c in reversed(ag.tool_log) if c["name"] == name)["shown"])
    return digest

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestAgentGateV2(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_v2_"); self.ag = None

    def tearDown(self):
        if self.ag: self.ag.close()
        shutil.rmtree(self.dir, ignore_errors=True)
        apothicaire.install_prompt(apothicaire.SYSTEM_ADDITION)          # leave the module as the other tests expect it

    def agent(self, version="v2", import_args=IMPORT_ARGS, nca_args=NCA_ARGS, data_dir=None):
        cfg = dict(optchat.CFG, data_dir=data_dir or self.dir)
        ag = apothicaire.Apothicaire(cfg=cfg, gate_version=version)
        script = [tool_call("data_import", import_args, "c1"), tool_call("nca_run", {"worksheet": 1, **nca_args}, "c2")]
        ag.llm = FakeLLM(script); ag.compactor.llm = ag.llm
        self.ag = ag
        return ag

    def test_clean_answer_is_rendered_and_the_memory_keeps_the_references(self):
        ag = self.agent()
        ag.llm.script += [say("Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}} ; demi-vie {{call_2.half.life}}.")]
        ans, st = ag.turn(USER, verbose=False)
        d = shown_params(ag)
        self.assertEqual(d["ref"], "call_2"); self.assertEqual(list(d)[0], "ref")
        self.assertEqual(json.loads(ag.tool_log[0]["shown"])["ref"], "call_1")
        self.assertEqual([c["ref"] for c in ag.tool_log], ["call_1", "call_2"])
        p = d["subjects"][0]["parameters"]
        fr = lambda s: s.replace(".", ",")                                    # the chat language is French: decimal comma
        self.assertEqual(ans, f"Cmax = {fr(p['cmax'])} [Cmax] à Tmax = {fr(p['tmax'])} [Tmax] ; demi-vie {fr(p['half.life'])} [half-life].")
        self.assertNotIn("{{", ans); self.assertNotIn("⚠", ans)
        self.assertEqual(ag.store.log[-1]["content"], "Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}} ; demi-vie {{call_2.half.life}}.")
        g = st["gate"]
        self.assertEqual(g["version"], "v2"); self.assertFalse(g["regenerated"])
        self.assertEqual((g["before"]["references_total"], g["before"]["references_unresolved"], g["before"]["numbers_unverified"]), (3, 0, 0))
        self.assertEqual(g["rendered"], ans); self.assertEqual(len(ag.llm.calls), 3)
        with open(os.path.join(self.dir, "refs.jsonl"), encoding="utf-8") as f: recs = [json.loads(l) for l in f]
        self.assertEqual([r["ref"] for r in recs], ["call_1", "call_2"])
        self.assertEqual(recs[1]["structured"]["result"]["subjects"][0]["subject"], "1")
        self.assertEqual(recs[1]["units"]["parameters"]["cmax"], p["cmax"].partition(" ")[2])
        json.dumps(st)

    def test_a_typed_tool_number_is_regenerated_with_the_reminder_at_the_end(self):
        ag = self.agent()
        def typed(messages):                                                  # half.life: a tool number that is not in the user's CSV
            v = shown_params(ag)["subjects"][0]["parameters"]["half.life"]
            return say(f"Demi-vie = {v.replace('.', ',')}.")
        ag.llm.script += [typed, say("Cmax = {{call_2.cmax}}.")]
        ans, st = ag.turn(USER, verbose=False)
        calls = ag.llm.calls
        self.assertEqual(len(calls), 4)
        third, fourth = calls[2]["messages"], calls[3]["messages"]
        self.assertEqual(fourth[:len(third)], third); self.assertEqual([m["role"] for m in fourth[len(third):]], ["assistant", "user"])
        rem = fourth[-1]["content"]
        self.assertTrue(rem.startswith("[system reminder] Your last answer was rejected by the renderer"))
        self.assertIn("not in the user's message", rem); self.assertIn("Available references: call_2 (nca_run, analysis 2, subject 1)", rem)
        self.assertIsNone(calls[3]["tools"])
        p = shown_params(ag)["subjects"][0]["parameters"]["cmax"]
        self.assertEqual(ans, f"Cmax = {p.replace('.', ',')} [Cmax].")
        g = st["gate"]
        self.assertTrue(g["regenerated"]); self.assertEqual(g["kept"], "regenerated")
        self.assertEqual((g["before"]["numbers_unverified"], g["after"]["numbers_unverified"]), (1, 0))
        self.assertEqual(g["first_findings"][0]["kind"], "bare_number"); self.assertEqual(ag.store.log[-1]["content"], "Cmax = {{call_2.cmax}}.")
        self.assertFalse(any("system reminder" in m["content"] for m in ag.store.log))

    def test_a_wrong_reference_gets_a_hint_and_a_badge_when_it_stays_wrong(self):
        ag = self.agent()
        ag.llm.script += [say("Cmax = {{call_2.cmaxx}}, AUC {{call_2.auclast}} h*mg/L."), say("Cmax = {{call_2.cmaxx}}, AUC {{call_2.auclast}}.")]
        ans, st = ag.turn(USER, verbose=False)
        rem = ag.llm.calls[3]["messages"][-1]["content"]
        self.assertIn("no parameter 'cmaxx' in this analysis (closest: cmax", rem); self.assertIn("unit next to a reference", rem)
        p = shown_params(ag)["subjects"][0]["parameters"]
        self.assertEqual(ans, f"Cmax = ⟦no parameter 'cmaxx' in this analysis: {{{{call_2.cmaxx}}}}⟧, AUC {p['auclast'].replace('.', ',')} [AUClast]."
                              "\n\n⚠ 1 problem(s) in the answer (typed rendering): {{call_2.cmaxx}}")
        g = st["gate"]
        self.assertEqual(g["kept"], "regenerated"); self.assertEqual((g["before"]["numbers_unverified"], g["after"]["numbers_unverified"]), (2, 1))
        self.assertNotIn("⚠", ag.store.log[-1]["content"]); self.assertIn("{{call_2.cmaxx}}", ag.store.log[-1]["content"])
        self.assertNotIn(p["cmax"].partition(" ")[0], ans)                     # the value of cmax never appears

    def test_references_survive_a_restart(self):
        ag = self.agent(); ag.llm.script += [say("Cmax = {{call_2.cmax}}.")]
        ag.turn(USER, verbose=False); ag.close(); self.ag = None
        ag2 = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=self.dir), gate_version="v2")
        ag2.llm = FakeLLM([say("Je rappelle : Cmax = {{call_2.cmax}} et Tmax = {{call_2.tmax}}.")]); ag2.compactor.llm = ag2.llm
        self.ag = ag2
        self.assertEqual(sorted(ag2.refs), ["call_1", "call_2"])
        ans, st = ag2.turn("Et la Cmax ?", verbose=False)
        self.assertNotIn("{{", ans); self.assertNotIn("⚠", ans); self.assertIn("mg/L [Cmax]", ans); self.assertIn(" h [Tmax].", ans)
        self.assertEqual(st["gate"]["before"]["references_unresolved"], 0)

    def test_several_subjects_need_a_subject_ref(self):
        imp = BLQ["calls"][0]["arguments"]; nca = {k: v for k, v in BLQ["calls"][1]["arguments"].items() if k != "worksheet"}
        ag = self.agent(import_args=imp, nca_args=nca)
        ag.llm.script += [say("Cmax : {{call_2.cmax}}."), say("Cmax du sujet 3 : {{call_2.subject=3.cmax}}.")]
        ans, st = ag.turn("Voici les données (mg, h, mg/L) :\n" + imp["csv"] + "\nNCA.", verbose=False)
        d = shown_params(ag)
        self.assertEqual([s["ref"] for s in d["subjects"]], [f"call_2.subject={s['subject']}" for s in d["subjects"]])
        p3 = next(s for s in d["subjects"] if s["subject"] == "3")["parameters"]["cmax"]
        self.assertEqual(ans, f"Cmax du sujet 3 : {p3.replace('.', ',')} [Cmax, subject 3].")
        self.assertIn("6 subjects: write subject=LABEL", ag.llm.calls[3]["messages"][-1]["content"])

    def test_v1_is_the_default_and_unchanged(self):
        ag = self.agent(version="v1")
        self.assertEqual(ag.gate_version, "v1"); self.assertEqual(apothicaire.gate_version_of(None), "v1")
        self.assertTrue(optchat.SYSTEM_PROMPT.endswith(apothicaire.SYSTEM_ADDITION)); self.assertNotIn("{{call_3.cmax}}", optchat.SYSTEM_PROMPT)
        ag.llm.script += [say("Cmax = {{call_2.cmax}}.")]
        ans, st = ag.turn(USER, verbose=False)
        self.assertNotIn('"ref"', ag.tool_log[1]["shown"]); self.assertFalse(os.path.exists(os.path.join(self.dir, "refs.jsonl")))
        self.assertEqual(ans, "Cmax = {{call_2.cmax}}.")                        # v1 does not render; no digits, nothing to check
        self.assertEqual(st["gate"]["version"], "v1"); self.assertNotIn("references_total", st["gate"]["before"])

    def test_aliases_render_the_selected_regression_and_the_thresholds(self):
        ag = self.agent()
        invented = say("R² ajusté {{call_2.lambda_z_regression.adj_r_squared}}, seuil {{call_2.options_used.quality_thresholds.max_extrapolated_percent}}.")
        good = say("R² ajusté {{call_2.lambda_z.adj_r_squared}} sur {{call_2.lambda_z.n_points}} points de {{call_2.lambda_z.time_first}} à "
                   "{{call_2.lambda_z.time_last}} ; seuil {{call_2.thresholds.max_extrapolated_percent}}.")
        ag.llm.script += [invented, good]
        ans, st = ag.turn(USER, verbose=False)
        d = shown_params(ag); reg = d["subjects"][0]["lambda_z_regression"]; thr = d["options_used"]["quality_thresholds"]
        fr = lambda x: gate_v2.render_value(x, "", ",")
        self.assertEqual(ans, f"R² ajusté {fr(reg['adj_r_squared'])} [adjusted R² of λz] sur {reg['n_points']} [λz points] points de "
                              f"{fr(reg['time_first'])} h [λz first time] à {fr(reg['time_last'])} h [λz last time] ; "
                              f"seuil {fr(thr['max_extrapolated_percent'])} % [threshold: max AUC%extrap].")
        rem = ag.llm.calls[3]["messages"][-1]["content"]
        self.assertIn("closest: lambda_z.adj_r_squared", rem); self.assertIn("closest: thresholds.max_extrapolated_percent", rem)
        self.assertIn("Aliases: call_2.lambda_z.adj_r_squared, .r_squared, .n_points, .time_first, .time_last (the selected λz regression); "
                      "call_2.thresholds.max_extrapolated_percent (also", rem)
        g = st["gate"]
        self.assertEqual((g["before"]["references_unresolved"], g["after"]["references_unresolved"]), (2, 0)); self.assertEqual(g["kept"], "regenerated")

    def test_conventions_are_rendered_from_the_analysis_or_the_table(self):
        ag = self.agent()
        ag.llm.script += [say("Seuil d'extrapolation 20 %."), say("Seuil {{convention.max_extrapolated_percent}}, R² minimal {{convention.min_adj_r_squared}}, {{convention.min_points}} points.")]
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(ans, "Seuil 20 % [threshold: max AUC%extrap], R² minimal 0,9 [threshold: min adjusted R²], 3 [threshold: min λz points] points.")
        rem = ag.llm.calls[3]["messages"][-1]["content"]
        self.assertIn("20 %: a number typed by hand", rem); self.assertIn("write {{call_2.thresholds.max_extrapolated_percent}}", rem)   # the analysis echoes it
        self.assertEqual((st["gate"]["before"]["numbers_unverified"], st["gate"]["after"]["numbers_unverified"]), (1, 0))
        self.assertEqual(ag.store.log[-1]["content"], "Seuil {{convention.max_extrapolated_percent}}, R² minimal {{convention.min_adj_r_squared}}, {{convention.min_points}} points.")

    def test_the_bench_runner_records_a_v2_run(self):
        from bench import run_bench as rb, make_exercises as mk, scripts as sc
        from test_bench_run import ideal_answer
        ex_dir = mk.list_exercises()[1]; meta, csv = mk.load(ex_dir)
        turns = sc.build_script(meta, csv); imp, nca = mk.tool_arguments(meta, csv)
        keys = {m["label"]: m["key"] for m in turns[0]["expect"]["must"]}
        full = ", ".join(f"{label} = {{{{call_2.{key}}}}}" for label, key in keys.items())        # the 9 labels, all by reference
        typed = say("CL/F = 1234.5 L/h, Vz/F = 99.9 L.")                           # invented digits, typed twice (draft and regeneration)
        items = [tool_call("data_import", imp, "c1"), tool_call("nca_run", {"worksheet": 1, **nca("linear")}, "c2"),
                 say(full), say("Cmax = {{call_2.cmax}}, Tmax = {{call_2.tmax}}."), typed, typed]
        tmp = tempfile.mkdtemp(prefix="apo_v2_run_"); old = os.environ.get("APOTHICAIRE_GATE")
        os.environ["APOTHICAIRE_GATE"] = "v2"
        try:
            cfg = dict(optchat.CFG, raw_max=1000, raw_max_chars=10 ** 9)
            ag_llm = FakeLLM(items + [say("fin")] * 10)
            rec = rb.run_exercise(ex_dir, tmp, cfg_base=cfg, llm=ag_llm)
            t = rec["turns"]
            self.assertTrue(t[0]["score"]["correct"], t[0]["score"]); self.assertEqual(t[0]["numbers_unverified_after"], 0)
            self.assertNotIn("{{", t[0]["answer"]); self.assertFalse(t[0]["badge"])
            self.assertTrue(t[1]["score"]["correct"], t[1]["score"]); self.assertFalse(t[1]["badge"])
            self.assertEqual((t[2]["numbers_unverified_before"], t[2]["numbers_unverified_after"]), (2, 2))
            self.assertTrue(t[2]["regenerated"]); self.assertTrue(t[2]["badge"]); self.assertIn("⟦", t[2]["answer"]); self.assertFalse(t[2]["score"]["correct"])
            self.assertTrue(all("class" in f for f in t[2]["findings_after"]))
            rep = rb.write_report(tmp, [rec], {"date": "test", "gate": "v2"})
            self.assertEqual(rep["hallucination"]["after_gate"]["unverified"], sum(x["numbers_unverified_after"] for x in t))
        finally:
            if old is None: os.environ.pop("APOTHICAIRE_GATE", None)
            else: os.environ["APOTHICAIRE_GATE"] = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
