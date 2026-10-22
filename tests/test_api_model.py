"""Tests of the frontier API arm's model client (bench/api_model.py) and of its place in the frozen-set runner
(bench/run_frozen.py --api-model). No network and no key: a fake Anthropic client stands in for the Messages API. The end-to-end
test drives the stub model of the dry run through the adapter and needs the caladrius-mcp binary, like the other engine tests."""
import json, os, shutil, sys, tempfile, types, unittest

AGENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire, optchat  # noqa: E402
from bench import api_model as am, make_exercises as mk, run_bench as rb, run_frozen as rf  # noqa: E402
from bench.stub_model import StubModel  # noqa: E402

HAVE_MCP = os.path.exists(apothicaire.MCP_BIN)
TOOLS = [{"type": "function", "function": {"name": "nca_run", "description": "NCA", "parameters": {"type": "object", "properties": {}}}}]

def response(content, stop="end_turn", usage=None, stop_details=None):
    return types.SimpleNamespace(content=content, stop_reason=stop, stop_details=stop_details,
                                 usage=usage or {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0,
                                                 "cache_read_input_tokens": 900})

class Recorder:
    """messages.create that records its keyword arguments and returns the next scripted response (or raises it)."""
    def __init__(self, *responses): self.responses, self.calls = list(responses), []; self.messages = self
    def create(self, **kw):
        self.calls.append(kw); r = self.responses.pop(0)
        if isinstance(r, Exception): raise r
        return r

class StubThroughAPI:
    """The dry-run stub model behind a fake Messages API: the request is turned back into OpenAI messages for the stub, its
    answer into content blocks. A compaction call (structured output) gets the asked number of lines."""
    def __init__(self, stub): self.stub, self.messages = stub, self
    def create(self, **kw):
        fmt = kw.get("output_config", {}).get("format")
        if fmt:
            n = kw["messages"][-1]["content"][0]["text"].count("\n") + 1
            return response([{"type": "text", "text": json.dumps({"lines": ["résumé"] * n})}])
        msgs = [{"role": "system", "content": kw.get("system", "")}]
        for m in kw["messages"]:
            for b in m["content"]:
                t = am._get(b, "type")
                if t == "tool_result": msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
                elif t == "tool_use": msgs.append({"role": "assistant", "content": "", "tool_calls": [
                    {"id": am._get(b, "id"), "type": "function", "function": {"name": am._get(b, "name"), "arguments": json.dumps(am._get(b, "input"))}}]})
                elif t == "text": msgs.append({"role": m["role"], "content": am._get(b, "text")})
        out = self.stub.chat(msgs, slot=0, tools=kw.get("tools"))
        blocks = [{"type": "text", "text": out["content"]}] if out.get("content") else []
        for tc in out.get("tool_calls") or []:
            blocks.append({"type": "tool_use", "id": "toolu_" + tc["id"], "name": tc["function"]["name"],
                           "input": json.loads(tc["function"]["arguments"])})
        return response(blocks, "tool_use" if out.get("tool_calls") else "end_turn")

class TestMessages(unittest.TestCase):
    def test_system_user_calls_and_results(self):
        msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "a1", "type": "function", "function": {"name": "nca_run", "arguments": '{"dose": 1}'}},
                                                                    {"id": "a2", "type": "function", "function": {"name": "analysis_get", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "a1", "content": "r1"}, {"role": "tool", "tool_call_id": "a2", "content": "r2"}]
        system, out = am.to_messages(msgs)
        self.assertEqual(system, "SYS")
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user"])
        self.assertEqual([b["type"] for b in out[1]["content"]], ["tool_use", "tool_use"])
        self.assertEqual(out[1]["content"][0]["input"], {"dose": 1})
        self.assertEqual([(b["tool_use_id"], b["content"]) for b in out[2]["content"]], [("a1", "r1"), ("a2", "r2")])

    def test_unpaired_calls_and_results_become_text(self):
        # the raw zone can start with a result whose call was summarised away, and a call can lose its result
        msgs = [{"role": "user", "content": "<memory>"}, {"role": "assistant", "content": "ok"},
                {"role": "tool", "tool_call_id": "gone", "content": "old result"}, {"role": "user", "content": "q"},
                {"role": "assistant", "content": "x", "tool_calls": [{"id": "b1", "type": "function", "function": {"name": "nca_run", "arguments": "{}"}}]},
                {"role": "user", "content": "next"}]
        _, out = am.to_messages(msgs)
        self.assertEqual([m["role"] for m in out], ["user", "assistant", "user", "assistant", "user"])
        self.assertEqual(out[2]["content"][0], {"type": "text", "text": "[tool result gone] old result"})
        self.assertEqual(out[3]["content"], [{"type": "text", "text": "x"}, {"type": "text", "text": "call nca_run({})"}])
        self.assertFalse(any(b["type"] in ("tool_use", "tool_result") for m in out for b in m["content"]))

    def test_thinking_blocks_come_back_only_inside_the_current_tool_loop(self):
        call = lambda i: {"role": "assistant", "content": "", "tool_calls": [{"id": i, "type": "function", "function": {"name": "nca_run", "arguments": "{}"}}]}
        blocks = lambda i: [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "tool_use", "id": i, "name": "nca_run", "input": {}}]
        msgs = [{"role": "user", "content": "turn 1"}, call("old"), {"role": "tool", "tool_call_id": "old", "content": "r"},
                {"role": "assistant", "content": "answer 1"}, {"role": "user", "content": "turn 2"}, call("new"),
                {"role": "tool", "tool_call_id": "new", "content": "r"}]
        _, out = am.to_messages(msgs, {"old": blocks("old"), "new": blocks("new")})
        self.assertEqual([b["type"] for b in out[1]["content"]], ["tool_use"])                  # an earlier turn: rebuilt
        self.assertEqual([b["type"] for b in out[5]["content"]], ["thinking", "tool_use"])      # this turn's loop: replayed

class TestRequest(unittest.TestCase):
    def llm(self, model="claude-sonnet-5-5", *responses): return am.AnthropicLLM(model, client=Recorder(*responses))

    def test_declared_defaults_and_no_sampling_fields(self):
        s = self.llm().request([{"role": "user", "content": "q"}], TOOLS, 1200)
        self.assertEqual((s["thinking"], s["output_config"], s["max_tokens"]), ({"type": "between_tools"}, {"effort": "high"}, 1200))
        self.assertEqual(s["tool_choice"], {"type": "auto"}); self.assertEqual(s["tools"][0]["name"], "nca_run")
        self.assertEqual(s["cache_control"], {"type": "ephemeral"})
        for k in ("temperature", "top_p", "top_k", "seed"): self.assertNotIn(k, s)
        o = self.llm("claude-opus-5-5").request([{"role": "user", "content": "q"}], None, 1200)
        self.assertEqual((o["thinking"], o["output_config"], o["max_tokens"]), ({"type": "adaptive"}, {"effort": "medium"}, 1200 + am.THINKING_HEADROOM))
        self.assertNotIn("tools", o)

    def test_a_round_without_tools_keeps_them_defined_but_uncallable(self):
        llm = self.llm()
        llm.request([{"role": "user", "content": "q"}], TOOLS, 100)
        hist = [{"role": "user", "content": "q"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c", "type": "function", "function": {"name": "nca_run", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c", "content": "r"}]
        p = llm.request(hist, None, 100)
        self.assertEqual(p["tool_choice"], {"type": "none"}); self.assertEqual(p["tools"][0]["name"], "nca_run")

    def test_compaction_schema_goes_to_structured_outputs_without_array_bounds(self):
        p = self.llm().request([{"role": "user", "content": "x"}], None, 100, optchat._json_lines_schema(3))
        fmt = p["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["schema"]["properties"]["lines"], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(p["output_config"]["effort"], "high")

class TestChat(unittest.TestCase):
    def test_tool_calls_usage_and_cost(self):
        r = response([{"type": "thinking", "thinking": "note", "signature": "s"}, {"type": "text", "text": "Je calcule."},
                      {"type": "tool_use", "id": "toolu_1", "name": "nca_run", "input": {"dose": 100}}], "tool_use",
                     {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 3000})
        llm = am.AnthropicLLM("claude-sonnet-5-5", client=Recorder(r))
        m = llm.chat([{"role": "user", "content": "q"}], tools=TOOLS)
        self.assertEqual(m["content"], "Je calcule.")
        self.assertEqual(m["tool_calls"][0]["id"], "toolu_1"); self.assertEqual(json.loads(m["tool_calls"][0]["function"]["arguments"]), {"dose": 100})
        self.assertEqual((llm.last["prompt_tokens"], llm.last["cache_n"], llm.last["prompt_eval_n"], llm.last["finish_reason"]), (6000, 3000, 3000, "tool_calls"))
        expect = (1000 * 2 + 2000 * 2 * 1.25 + 3000 * 0.2 + 100 * 10) / 1e6
        self.assertAlmostEqual(llm.usage["cost_usd"], expect); self.assertAlmostEqual(llm.last["cost_usd"], expect)
        self.assertEqual(len(llm.replay["toolu_1"]), 3)

    def test_errors_and_refusals_are_failed_calls(self):
        class HTTPErr(Exception): status_code = 400
        llm = am.AnthropicLLM("claude-sonnet-5-5", client=Recorder(HTTPErr("prompt too long"), ConnectionError("down"),
                                                                     response([], "refusal", stop_details={"category": "bio", "explanation": "x"})))
        for want in ("HTTP 400", "transport", "refusal: bio"):
            with self.assertRaises(optchat.LLMError) as e: llm.chat([{"role": "user", "content": "q"}])
            self.assertTrue(str(e.exception).startswith(want), str(e.exception))
        self.assertEqual(llm.refusals, [{"category": "bio", "explanation": "x"}])

    def test_the_key_comes_from_the_environment_only(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(SystemExit): am.AnthropicLLM("claude-sonnet-5-5")
        finally:
            if old is not None: os.environ["ANTHROPIC_API_KEY"] = old

class TestRunner(unittest.TestCase):
    def test_configuration_names(self):
        self.assertEqual(rf.config_name("v1", "claude-sonnet-5-5"), "v1+claude-sonnet-5-5")
        self.assertEqual(rf.config_name("v1"), "v1")
        self.assertEqual(rf.gate_of("v1+claude-sonnet-5-5"), "v1"); self.assertEqual(rf.gate_of("nolm"), "nolm")

    def test_not_with_the_stub_or_the_decider_arm(self):
        with self.assertRaises(SystemExit): rf.run("dev", "v1", [1], stub=True, api_model="claude-sonnet-5-5", api_client=Recorder())
        with self.assertRaises(SystemExit): rf.run("dev", "nolm", [1], api_model="claude-sonnet-5-5", api_client=Recorder())

@unittest.skipUnless(HAVE_MCP, "caladrius-mcp not built")
class TestThroughTheAgent(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_adapter_is_transparent_to_the_agent_gate_and_rubric(self):
        """The stub model straight and the stub model behind the fake Messages API give the same outcomes and answers."""
        ex = mk.list_exercises()[0]; meta, csv_text = mk.load(ex)
        cfg = dict(optchat.CFG, raw_max=1000, raw_max_chars=10 ** 9)
        outs = []
        for name in ("direct", "api"):
            stub = StubModel("v1", 1); stub.begin(meta, csv_text)
            llm = stub if name == "direct" else am.AnthropicLLM("claude-sonnet-5-5", client=StubThroughAPI(stub))
            d = os.path.join(self.tmp, name); os.makedirs(d)
            rec = rb.run_exercise(ex, d, cfg_base=cfg, llm=llm, on_turn=stub.on_turn, gate_version="v1")
            outs.append(rec)
        self.assertEqual([t["outcome"] for t in outs[0]["turns"]], [t["outcome"] for t in outs[1]["turns"]])
        self.assertEqual([t["answer"] for t in outs[0]["turns"]], [t["answer"] for t in outs[1]["turns"]])
        self.assertEqual([t["outcome"] for t in outs[1]["turns"]], ["CORRECT"] * 8)

    def test_a_dev_run_is_stored_as_its_configuration_with_its_cost(self):
        calls = []
        class Client:
            messages = None
            def __init__(self): self.messages = self
            def create(self, **kw):
                calls.append(kw); return response([{"type": "text", "text": "Je ne sais pas."}])
        ids = [os.path.basename(mk.list_exercises()[0])]
        base = rf.run("dev", "v1", [1, 2], ids=ids, base=self.tmp, out=lambda *a: None, api_model="claude-sonnet-5-5", api_client=Client())
        for s in (1, 2):
            rd = rf.run_dir(base, "v1+claude-sonnet-5-5", s)
            with open(os.path.join(rd, "run.json"), encoding="utf-8") as f: info = json.load(f)
            with open(os.path.join(rd, "api_usage.json"), encoding="utf-8") as f: use = json.load(f)
            self.assertEqual((info["gate"], info["config"], info["api"]["model"], info["api"]["fallback_model"]), ("v1", "v1+claude-sonnet-5-5", "claude-sonnet-5-5", None))
            self.assertTrue(info["model"].startswith("claude-sonnet-5-5 on the Anthropic Messages API"))
            self.assertGreater(use["calls"], 0); self.assertGreater(use["cost_usd"], 0)
        res = rf.analyse("dev", "v1+claude-sonnet-5-5", "none", base)
        self.assertIn("v1+claude-sonnet-5-5", res["configurations"])
        # a second base read next to it: the configuration keeps its folder, nothing is written there
        other = os.path.join(self.tmp, "other"); shutil.copytree(os.path.join(base, "v1+claude-sonnet-5-5"), os.path.join(other, "v1"))
        res = rf.analyse("dev", "v1", "v1+claude-sonnet-5-5", base, extra=[(other, ["v1"])])
        self.assertIn("paired", res); self.assertEqual(sorted(res["sources"]), ["v1"])
        self.assertFalse(os.path.exists(os.path.join(other, "ANALYSIS.md")))
        with self.assertRaises(SystemExit): rf.analyse("dev", "v1", "v2", base, extra=[(other, ["v2"])])

if __name__ == "__main__":
    unittest.main()
