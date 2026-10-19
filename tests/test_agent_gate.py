"""The gate wired into the agent, with a scripted language model and the REAL caladrius-mcp server
(skipped if the binary is not built). No llama.cpp server is needed: `ag.llm.chat` is replaced.

Checked: one regeneration with the reminder appended at the END of the messages (system prompt and
earlier messages untouched), the better answer kept, the badge on a still-wrong answer, the memory
holding the answer without the badge or the reminder, the counts and findings in the turn's stats.
"""
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import apothicaire, optchat, gate  # noqa: E402
import test_digest as td           # noqa: E402

CASE = td.GOLDENS["theoph_s1_oral_dose_arg"]
IMPORT_ARGS = CASE["calls"][0]["arguments"]
NCA_ARGS = {k: v for k, v in CASE["calls"][1]["arguments"].items() if k != "worksheet"}
USER = "Voici les données de l'exercice (320 mg par voie orale ; temps en h, mg/L) :\n" + IMPORT_ARGS["csv"] + "\nFais l'analyse NCA."

def tool_call(name, args, cid):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}

def say(text): return {"role": "assistant", "content": text}

class FakeLLM:
    def __init__(self, script):
        self.script, self.calls, self.last, self.total_slots = list(script), [], {}, 2
    def chat(self, messages, slot, tools=None, max_tokens=512, think=False, **kw):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools, "slot": slot})
        item = self.script.pop(0)
        if isinstance(item, Exception): raise item
        n = len(self.calls)
        self.last = {"wall_s": 0.1, "prompt_tokens": 1000 * n, "completion_tokens": 10, "prompt_eval_n": 10,
                          "cache_n": 990, "prompt_ms": 1, "predicted_ms": 1, "gen_tps": 20.0, "finish_reason": "stop"}
        return item(messages) if callable(item) else item

def cl_text(ag):
    """'value unit' of cl.obs as shown to the model in the last NCA digest."""
    digest = json.loads(next(c for c in reversed(ag.tool_log) if c["name"] == "nca_run")["shown"])
    return digest["subjects"][0]["parameters"]["cl.obs"]

def fr(s): return s.replace(".", ",")

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestAgentGate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_test_")
        self.ag = None

    def tearDown(self):
        if self.ag:
            self.ag.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def agent(self):
        """An agent whose model is scripted: two tool rounds (import, NCA); the test appends the answer(s)."""
        cfg = dict(optchat.CFG, data_dir=self.dir)
        ag = apothicaire.Apothicaire(cfg=cfg)
        script = [tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", {"worksheet": 1, **NCA_ARGS}, "c2")]
        ag.llm = FakeLLM(script); ag.compactor.llm = ag.llm
        self.ag = ag
        return ag

    def bad_answer(self, ag):
        # the model converts CL/F: value x 1000 in another unit; a correct number comes first
        def f(messages):
            v = cl_text(ag).split()[0]
            return say(f"CL/F = {fr(v)} dose unit/(h·mg/L), soit {fr(str(float(v) * 1000))} L/h.")
        return f

    def good_answer(self, ag):
        def f(messages): return say(f"CL/F = {fr(cl_text(ag))}.")
        return f

    def test_regeneration_fixes_the_answer(self):
        ag = self.agent()
        ag.llm.script += [self.bad_answer(ag), self.good_answer(ag)]
        ans, st = ag.turn(USER, verbose=False)
        calls = ag.llm.calls
        self.assertEqual(len(calls), 4)
        self.assertEqual(ans, f"CL/F = {fr(cl_text(ag))}.")                   # no badge
        # the reminder is appended at the end of the messages of the 4th call; nothing before it changes
        third, fourth = calls[2]["messages"], calls[3]["messages"]
        self.assertEqual(fourth[0], third[0])                                  # the system prompt
        self.assertEqual(fourth[:len(third)], third)                           # the earlier messages
        self.assertEqual([m["role"] for m in fourth[len(third):]], ["assistant", "user"])
        self.assertIn("quote tool values verbatim, never convert", fourth[-1]["content"])
        self.assertIn(fr(str(float(cl_text(ag).split()[0]) * 1000)), fourth[-1]["content"])
        self.assertIsNone(calls[3]["tools"]); self.assertIsNotNone(calls[2]["tools"])
        self.assertEqual(calls[3]["slot"], 0)
        # the memory holds the corrected answer only
        log = ag.store.log
        self.assertEqual(log[-1]["role"], "assistant"); self.assertEqual(log[-1]["content"], ans)
        self.assertFalse(any("system reminder" in m["content"] for m in log))
        g = st["gate"]
        self.assertTrue(g["regenerated"]); self.assertEqual(g["kept"], "regenerated")
        self.assertEqual(g["before"]["numbers_unverified"], 1); self.assertEqual(g["after"]["numbers_unverified"], 0)
        self.assertGreaterEqual(g["before"]["numbers_total"], 2)
        self.assertEqual(g["findings"], []); self.assertEqual(len(g["first_findings"]), 1)
        self.assertIn("hint", g["first_findings"][0]); self.assertIn("first_answer", g)
        self.assertEqual(st["prompt_tokens"], 1000)                            # stats of the turn are those of its own calls: the regeneration is in st["gate"]["regen_stats"]
        self.assertEqual(st["gate"]["regen_stats"]["prompt_tokens"], 4000)
        json.dumps(st)                                                         # the transcript JSON can hold it
        with open(os.path.join(self.dir, "gate.jsonl"), encoding="utf-8") as f:
            self.assertEqual(len(f.readlines()), 1)

    def test_a_clean_answer_costs_no_regeneration(self):
        ag = self.agent(); ag.llm.script += [self.good_answer(ag)]
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(len(ag.llm.calls), 3)
        self.assertFalse(st["gate"]["regenerated"]); self.assertEqual(st["gate"]["before"]["numbers_unverified"], 0)
        self.assertNotIn("⚠", ans)

    def test_still_wrong_after_regeneration_gets_a_badge(self):
        ag = self.agent(); ag.llm.script += [self.bad_answer(ag), self.bad_answer(ag)]
        ans, st = ag.turn(USER, verbose=False)
        wrong = fr(str(float(cl_text(ag).split()[0]) * 1000))
        self.assertIn("⚠ 1 number(s) not found in tool results: " + wrong, ans)
        self.assertTrue(ans.index("⚠") > ans.index("L/h."))
        self.assertNotIn("⚠", ag.store.log[-1]["content"])                # the badge is shown, not remembered
        g = st["gate"]
        self.assertEqual((g["before"]["numbers_unverified"], g["after"]["numbers_unverified"]), (1, 1))
        self.assertEqual(g["findings"][0]["number"], wrong)
        self.assertEqual(len(ag.llm.calls), 4)                                 # one regeneration, not more

    def test_a_worse_regeneration_is_not_kept(self):
        ag = self.agent()
        def worse(messages):
            v = cl_text(ag).split()[0]
            return say(f"CL/F {fr(str(float(v) * 1000))} L/h, Vz {fr(str(float(v) * 777))} L, {fr(str(float(v) * 999))} L/h")
        ag.llm.script += [self.bad_answer(ag), worse]
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(st["gate"]["kept"], "first"); self.assertTrue(st["gate"]["regenerated"])
        self.assertEqual(st["gate"]["after"]["numbers_unverified"], 1)
        self.assertEqual(st["gate"]["after_regeneration"]["numbers_unverified"], 3)
        self.assertIn("soit", ans)                                              # the first draft

    def test_llm_error_during_regeneration_keeps_the_first_answer(self):
        ag = self.agent(); ag.llm.script += [self.bad_answer(ag), optchat.LLMError("HTTP 500: boom")]
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(st["gate"]["kept"], "first"); self.assertIn("error", st["gate"]["regen_stats"])
        self.assertIn("⚠ 1 number(s)", ans)

    def test_a_number_the_user_gave_is_a_source(self):
        ag = self.agent(); ag.llm.script += [say("Dose : 320 mg ; 15 points.")]
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(st["gate"]["before"]["numbers_unverified"], 0)


class TestGateContext(unittest.TestCase):
    def test_sources_are_user_messages_and_caladrius_results_only(self):
        log = [{"role": "user", "content": "u1"}, {"role": "tool_call", "content": ""},
               {"role": "tool_result", "name": "nca_run", "content": "R1"},
               {"role": "tool_result", "name": "zoom", "content": "Z (a summary with a wrong number)"},
               {"role": "tool_result", "name": "read_message", "content": "M"},
               {"role": "assistant", "content": "A1 (the model's own words)"},
               {"role": "tool_result", "name": "data_import", "content": "R2"}, {"role": "user", "content": "u2"}]
        tools, users = apothicaire.gate_context(log, {"nca_run": 1, "data_import": 1})
        self.assertEqual(tools, ["R1", "R2"]); self.assertEqual(users, ["u1", "u2"])


class TestInputPath(unittest.TestCase):
    """data_import reads a file path only inside the inputs folder (RT-E8)."""
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="apo_inputs_")
        os.makedirs(os.path.join(self.root, "sub"))

    def tearDown(self): shutil.rmtree(self.root, ignore_errors=True)

    def test_inside_is_resolved_outside_is_none(self):
        f = lambda p: apothicaire.input_path(p, self.root)
        real = os.path.realpath(self.root)
        self.assertEqual(f("x.csv"), os.path.join(real, "x.csv"))
        self.assertEqual(f("sub/x.csv"), os.path.join(real, "sub", "x.csv"))
        self.assertEqual(f(os.path.join(self.root, "x.csv")), os.path.join(real, "x.csv"))   # absolute, but inside
        for bad in ("../x.csv", "sub/../../x.csv", os.path.abspath(os.sep + "etc" + os.sep + "passwd"), __file__, "", "  ", ".", None, 3):
            self.assertIsNone(f(bad), bad)

    @unittest.skipIf(os.name == "nt", "symbolic links need privileges on Windows")
    def test_a_symbolic_link_cannot_leave_the_folder(self):
        os.symlink(os.path.dirname(HERE), os.path.join(self.root, "out"))
        self.assertIsNone(apothicaire.input_path("out/README.md", self.root))


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestToolBoundary(unittest.TestCase):
    """Only the EXPOSED tools run, and data_import's file path stays in the inputs folder (RT-E8). Real server, no model."""
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_boundary_")
        self.inputs = os.path.join(self.dir, "inputs"); os.makedirs(self.inputs)
        self.saved_inputs, apothicaire.INPUTS_DIR = apothicaire.INPUTS_DIR, self.inputs
        self.ag = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=self.dir))
        self.calls = []
        real = self.ag.mcp.call_full
        def spy(name, args):
            self.calls.append(name); return real(name, args)
        self.ag.mcp.call_full = spy

    def tearDown(self):
        apothicaire.INPUTS_DIR = self.saved_inputs
        self.ag.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_hidden_tool_is_refused_before_the_engine(self):
        self.ag._tool("data_import", IMPORT_ARGS)
        for name, args in (("data_remove", {"worksheet": 1}), ("project_new", {}), ("analysis_remove", {"analysis": 1}),
                           ("data_set_cell", {"worksheet": 1, "row": 0, "column": "conc", "value": 0}),
                           ("project_load", {"path": "/tmp/x"})):
            with self.subTest(tool=name):
                self.assertIn(name, self.ag.mcp.tools)                           # the server does have it
                out = self.ag._tool(name, args)
                self.assertTrue(out.startswith("TOOL ERROR: tool " + name + " is not available"), out)
                self.assertIn("nca_run", out)
        self.assertEqual(self.calls, ["data_import"])                           # none of them reached the engine
        self.assertEqual(len(self.ag.tool_log), 1)
        self.assertEqual([r["name"] for r in self.ag.refused_log],
                         ["data_remove", "project_new", "analysis_remove", "data_set_cell", "project_load"])
        out = self.ag._tool("export_table", {"table": "worksheet", "worksheet": 1})   # the worksheet is still there
        self.assertNotIn("ERROR", out)

    def test_a_path_outside_the_inputs_folder_is_refused(self):
        outside = os.path.join(self.dir, "x.csv")
        with open(outside, "w", encoding="utf-8") as f: f.write(IMPORT_ARGS["csv"])
        for path in ("../x.csv", outside, os.path.abspath(__file__)):
            with self.subTest(path=path):
                out = self.ag._tool("data_import", {"name": "x", "path": path, "columns": IMPORT_ARGS["columns"]})
                self.assertTrue(out.startswith("TOOL ERROR: data_import reads files only inside the inputs folder"), out)
        self.assertEqual(self.calls, []); self.assertEqual(len(self.ag.refused_log), 3)

    def test_a_path_inside_the_inputs_folder_is_read(self):
        with open(os.path.join(self.inputs, "theoph.csv"), "w", encoding="utf-8") as f: f.write(IMPORT_ARGS["csv"])
        out = self.ag._tool("data_import", {"name": "x", "path": "theoph.csv", "columns": IMPORT_ARGS["columns"]})
        self.assertNotIn("ERROR", out); self.assertEqual(self.calls, ["data_import"])
        self.assertEqual(self.ag.tool_log[-1]["args"]["csv"], IMPORT_ARGS["csv"])
        self.assertNotIn("path", self.ag.tool_log[-1]["args"])


class TestNcaUnits(unittest.TestCase):
    """options.units built from the worksheet and the model's dose_unit (RT-E4), no server."""
    WS = {"time": "h", "conc": "ng/mL", "dose": None}

    def test_built_when_all_three_are_known(self):
        self.assertEqual(apothicaire.nca_units(self.WS, "mg"), {"time": "h", "concentration": "ng/mL", "dose": "mg"})
        self.assertEqual(apothicaire.nca_units({**self.WS, "dose": "ug"}), {"time": "h", "concentration": "ng/mL", "dose": "ug"})
        self.assertEqual(apothicaire.nca_units({**self.WS, "dose": "ug"}, "mg")["dose"], "mg")     # the dose argument's unit wins

    def test_none_when_a_unit_is_missing_or_unknown_to_the_engine(self):
        for ws, du in ((self.WS, None), (self.WS, ""), (self.WS, "mmol"), (self.WS, "mL"), ({**self.WS, "time": "hours"}, "mg"),
                       ({**self.WS, "conc": "nmol/L"}, "mg"), ({**self.WS, "conc": "ng"}, "mg"), ({}, "mg"), (None, "mg")):
            self.assertIsNone(apothicaire.nca_units(ws, du), (ws, du))

    def test_nca_run_function_offers_dose_unit(self):
        tools = td.load("tools_list.json")["tools"]
        f = apothicaire.to_openai(next(t for t in tools if t["name"] == "nca_run"))["function"]["parameters"]["properties"]
        self.assertEqual(f["dose_unit"]["enum"], ["ng", "ug", "mg", "g"])


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestUnitsReachTheEngine(unittest.TestCase):
    """A mg dose on an ng/mL worksheet: CL in L/h and Vz in L, converted by the engine (RT-E4). Real server, no model."""
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_units_")
        self.ag = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=self.dir))
        cols = [{"name": "time", "unit": "h"}, {"name": "conc", "unit": "ng/mL"}]
        self.ag._tool("data_import", {**IMPORT_ARGS, "columns": cols})

    def tearDown(self):
        self.ag.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def run_nca(self, **extra):
        d = json.loads(self.ag._tool("nca_run", {"worksheet": 1, **NCA_ARGS, **extra}))
        p = d["subjects"][0]["parameters"]
        return d, {k: (float(p[k].split()[0]), p[k].split(maxsplit=1)[1]) for k in ("cl.obs", "vz.obs", "cmax")}

    def test_cl_in_l_per_h_and_vz_in_l(self):
        plain_d, plain = self.run_nca()
        self.assertNotIn("units", self.ag.tool_log[-1]["args"].get("options", {}))       # no dose unit: nothing sent
        self.assertTrue(plain_d["dose_unit"].startswith("unknown to Caladrius"))
        self.assertIn("dose unit", plain["cl.obs"][1])
        d, conv = self.run_nca(dose_unit="mg")
        call = self.ag.tool_log[-1]
        self.assertEqual(call["args"]["options"]["units"], {"time": "h", "concentration": "ng/mL", "dose": "mg"})
        self.assertNotIn("dose_unit", call["args"])
        self.assertEqual(conv["cl.obs"][1], "L/h"); self.assertEqual(conv["vz.obs"][1], "L")
        self.assertEqual(conv["cmax"], plain["cmax"][:1] + ("ng/mL",))
        # mg / (ng/mL) = 1e-3 g / (1e-9 g / 1e-3 L) = 1000 L: the engine's conversion, not the client's
        for k in ("cl.obs", "vz.obs"):
            self.assertAlmostEqual(conv[k][0] / plain[k][0], 1000, delta=1000 * 1e-5, msg=k)
        self.assertEqual(d["dose_unit"], "mg"); self.assertEqual(d["options_used"]["units"]["dose"], "mg")

    def test_units_the_model_wrote_are_kept(self):
        mine = {"time": "h", "concentration": "ng/mL", "dose": "ug"}
        self.run_nca(dose_unit="mg", options={**NCA_ARGS.get("options", {}), "units": mine})
        self.assertEqual(self.ag.tool_log[-1]["args"]["options"]["units"], mine)

    def test_an_unknown_dose_unit_leaves_the_run_unitless(self):
        d, plain = self.run_nca(dose_unit="mmol")
        self.assertTrue(self.ag.tool_log[-1]["ok"]); self.assertNotIn("units", self.ag.tool_log[-1]["args"]["options"])
        self.assertIn("dose unit", plain["cl.obs"][1])


class TestLambdaZSelectionShown(unittest.TestCase):
    """The model sees lambda_z_selection with exclude and manual only (RT-E6), no server."""
    def test_schema(self):
        tools = td.load("tools_list.json")["tools"]
        opts = apothicaire.to_openai(next(t for t in tools if t["name"] == "nca_run"))["function"]["parameters"]["properties"]["options"]
        sel = opts["properties"]["lambda_z_selection"]
        self.assertEqual(set(sel["properties"]), {"exclude", "manual"})
        self.assertEqual(sel["properties"]["exclude"]["items"], {"type": "number"})
        self.assertEqual(set(sel["properties"]["manual"]["properties"]), {"times", "range"})
        self.assertNotIn("blq", opts["properties"]); self.assertIn("blq and missing keep the engine's defaults", opts["description"])
        self.assertNotIn("oneOf", json.dumps(sel)); self.assertNotIn("anyOf", json.dumps(sel))


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestLambdaZSelection(unittest.TestCase):
    """"Exclude the last point from λz" from the chat: the scripted model's nca_run carries lambda_z_selection.exclude
    and the engine returns another λz (RT-E6). Real server, no llama.cpp."""
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_lz_")
        self.ag = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=self.dir))

    def tearDown(self):
        self.ag.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def lz(self, call):
        s = json.loads(call["shown"])["subjects"][0]
        return s["parameters"]["lambda.z"], s["lambda_z_regression"]

    def test_excluding_one_point_from_the_chat(self):
        ag = self.ag
        excl = {"worksheet": 1, **NCA_ARGS, "options": {**NCA_ARGS["options"], "lambda_z_selection": {"exclude": [24.37]}}}
        ag.llm = FakeLLM([tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", {"worksheet": 1, **NCA_ARGS}, "c2"),
                          say("Analyse faite."),
                          tool_call("nca_run", excl, "c3"), say("λz recalculée sans le point de 24,37 h.")])
        ag.compactor.llm = FakeLLM([])          # compaction between turns must not take the scripted answers
        ag.turn(USER, verbose=False)
        ag.turn("Exclus le point de 24,37 h de la régression de λz.", verbose=False)
        first, second = ag.tool_log[1], ag.tool_log[2]
        self.assertEqual(second["args"]["options"]["lambda_z_selection"], {"exclude": [24.37]})
        (lz1, reg1), (lz2, reg2) = self.lz(first), self.lz(second)
        self.assertNotEqual(lz1, lz2)
        self.assertLess(reg2["time_last"], 24.37); self.assertEqual(reg1["time_last"], 24.37)
        d = json.loads(second["shown"])
        self.assertEqual(d["options_used"]["lambda_z_selection"], {"exclude": [24.37]})
        self.assertNotIn("lambda_z_selection", json.loads(first["shown"])["options_used"])   # unchanged points: not shown

    def test_manual_points_and_a_readable_error(self):
        ag = self.ag; ag._tool("data_import", IMPORT_ARGS)
        out = json.loads(ag._tool("nca_run", {"worksheet": 1, **NCA_ARGS, "options": {
            "lambda_z_selection": {"manual": {"range": {"start": 5, "end": 13}}}}}))
        self.assertEqual(out["subjects"][0]["lambda_z_regression"]["n_points"], 4)
        out = json.loads(ag._tool("nca_run", {"worksheet": 1, **NCA_ARGS, "options": {"lambda_z_selection": {"exclude": [24]}}}))
        self.assertIn("not a sample time", out["subjects"][0]["outcome"]["error"])          # the model reads why


# The answer of ex12, turn 7, in bench/runs/2026-10-09b: the call the model could not make on its last round.
EX12_ANSWER = ('<tool_call>\n<function=analysis_compare>\n<parameter=a>\n3\n</parameter>\n<parameter=b>\n3\n</parameter>\n'
               '<parameter=parameters>\n["auclast"]\n</parameter>\n</function>\n</tool_call>')
COMPARE_Q = ("Refais l'analyse avec la méthode linear-up/log-down. De combien l'AUC(0-tlast) diffère-t-elle de celle de la "
             "méthode linéaire, en valeur absolue et en pourcentage ?")


class TestToolCallText(unittest.TestCase):
    def test_tool_call_payloads(self):
        for t in (EX12_ANSWER, '{"name": "analysis_compare", "arguments": {"a": 3, "b": 3}}',
                  '```json\n{"name": "nca_run", "arguments": {}}\n```', '[{"name": "nca_run", "parameters": {}}]',
                  "Je compare :\n<tool_call>{\"name\": \"analysis_compare\"}</tool_call>", "[TOOL_CALLS] analysis_compare"):
            self.assertTrue(apothicaire.tool_call_text(t), t)

    def test_prose_is_not_a_tool_call(self):
        for t in ("", "La Cmax est de 10,5 mg/L à 1,12 h.", '{"a": 1}', "[1, 2]", "La fonction analysis_compare donne b moins a.",
                  '{"name": "x"}'):
            self.assertFalse(apothicaire.tool_call_text(t), t)


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestLoopGuards(unittest.TestCase):
    """RT-E1: analysis_compare with a = b refused, an identical call refused within a turn, the tools withdrawn after
    two repeats, and a tool-call text never shown as the answer. Real server, scripted model."""
    LIN = {"worksheet": 1, **NCA_ARGS, "options": {"auc_method": "linear"}}
    LOG = {"worksheet": 1, **NCA_ARGS, "options": {"auc_method": "lin_up_log_down"}}

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="apo_loop_")
        self.ag = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=self.dir))
        self.engine = []
        real = self.ag.mcp.call_full
        def spy(name, args):
            self.engine.append(name); return real(name, args)
        self.ag.mcp.call_full = spy

    def tearDown(self):
        self.ag.close(); shutil.rmtree(self.dir, ignore_errors=True)

    def script(self, *items):
        """The first turn of ex12 (import, linear NCA = analysis 2), then the items of the compare turn."""
        self.ag.llm = FakeLLM([tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", self.LIN, "c2"), say("Fait."),
                               *items])
        self.ag.compactor.llm = FakeLLM([])     # compaction between turns must not take the scripted answers
        self.ag.turn(USER, verbose=False)
        n = len(self.ag.llm.calls)
        ans, st = self.ag.turn(COMPARE_Q, verbose=False)
        return ans, st, self.ag.llm.calls[n:]

    def test_ex12_replayed_ends_without_the_loop(self):
        same = {"a": 3, "b": 3, "parameters": ["auclast"]}
        ans, st, calls = self.script(tool_call("nca_run", self.LOG, "c3"), tool_call("analysis_compare", same, "c4"),
                                     tool_call("analysis_compare", same, "c5"), tool_call("analysis_compare", same, "c6"),
                                     say(EX12_ANSWER))
        self.assertEqual(ans, apothicaire.FAILED_TURN["fr"])
        self.assertNotIn("tool_call", ans)
        self.assertEqual(st["rounds"], 5); self.assertLess(st["rounds"], optchat.CFG["max_tool_rounds"])
        self.assertIsNone(calls[-1]["tools"]); self.assertIsNotNone(calls[-2]["tools"])   # withdrawn after the 2nd repeat
        self.assertEqual(self.engine.count("analysis_compare"), 0)                       # a = b never reached the engine
        reasons = [r["reason"] for r in self.ag.refused_log]
        self.assertEqual(len(reasons), 3)
        self.assertTrue(reasons[0].startswith("a and b are the same analysis (3)"))
        self.assertIn("2 (auc_method linear), 3 (auc_method lin_up_log_down)", reasons[0])
        self.assertTrue(all(r.startswith("this exact analysis_compare call was already made") for r in reasons[1:]))
        self.assertEqual(st["gate"]["tool_call_text"], EX12_ANSWER)
        self.assertEqual(self.ag.store.log[-1]["content"], ans)                          # the memory keeps the message, not the call

    def test_the_model_recovers_after_the_refusal(self):
        def answer(messages):
            self.assertIn("a and b are the same analysis", json.dumps(messages, ensure_ascii=False))
            return say("Voir analysis_compare.")
        ans, st, calls = self.script(tool_call("nca_run", self.LOG, "c3"), tool_call("analysis_compare", {"a": 3, "b": 3}, "c4"),
                                     tool_call("analysis_compare", {"a": 2, "b": 3}, "c5"), answer)
        self.assertEqual(self.engine.count("analysis_compare"), 1)
        self.assertTrue(self.ag.tool_log[-1]["ok"]); self.assertEqual(self.ag.tool_log[-1]["args"], {"a": 2, "b": 3})
        self.assertIsNotNone(calls[-1]["tools"]); self.assertEqual(st["rounds"], 4)

    def test_a_string_pair_is_the_same_pair(self):
        self.ag._tool("data_import", IMPORT_ARGS); self.ag._tool("nca_run", self.LIN)
        out = self.ag._tool("analysis_compare", {"a": "2", "b": 2})
        self.assertTrue(out.startswith("TOOL ERROR: a and b are the same analysis (2)"), out)

    def test_an_identical_call_is_refused_within_a_turn_only(self):
        ag = self.ag
        ag.llm = FakeLLM([tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", self.LIN, "c2"),
                          tool_call("nca_run", self.LIN, "c3"), say("Fait."),
                          tool_call("nca_run", self.LIN, "c4"), say("Refait.")])
        ag.compactor.llm = FakeLLM([])
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(self.engine, ["data_import", "nca_run"])
        self.assertEqual(ag.store.log[-2]["role"], "tool_result")
        self.assertTrue(ag.store.log[-2]["content"].startswith("TOOL ERROR: this exact nca_run call was already made"))
        self.assertIsNotNone(ag.llm.calls[-1]["tools"])                                # one repeat: the tools stay
        ag.turn("Refais la même analyse.", verbose=False)
        self.assertEqual(self.engine, ["data_import", "nca_run", "nca_run"])            # a new turn may repeat it

    def test_a_tool_call_text_from_the_regeneration_is_not_kept(self):
        ag = self.ag
        ag.llm = FakeLLM([tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", self.LIN, "c2"),
                          say("La Cmax vaut 99999 mg/L."), say(EX12_ANSWER)])
        ag.compactor.llm = ag.llm
        ans, st = ag.turn(USER, verbose=False)
        self.assertTrue(ans.startswith("La Cmax vaut 99999 mg/L.")); self.assertNotIn("tool_call", ans)
        self.assertEqual(st["gate"]["kept"], "first")


class TestStaticPrefixUntouched(unittest.TestCase):
    def test_gate_adds_nothing_to_the_system_prompt_or_the_tool_definitions(self):
        self.assertNotIn("gate", optchat.SYSTEM_PROMPT.lower().replace("investigate", ""))
        self.assertNotIn("system reminder", optchat.SYSTEM_PROMPT)
        self.assertNotIn("system reminder", apothicaire.SYSTEM_ADDITION)


if __name__ == "__main__":
    unittest.main()
