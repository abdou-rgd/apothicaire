"""Gate v3 wired into the agent: gate v2 plus a grammar on the regeneration (gate_v3.py, bench/GRAMMAR_ARM.md).

The language model is a stub SERVER: an httpx.MockTransport behind the REAL optchat.LLM, so the request that reaches "llama-server" is
the one optchat builds, byte for byte, plus what apothicaire adds. The caladrius-mcp server is the real one (the tests skip if the
binary is not built). No llama.cpp server is started.

Checked: the exact body of the regeneration request (a `grammar` field, no tools, nothing else changed; it is the grammar gate_v3
builds for that turn), that the first calls carry none, that gate v2 sends none, that the seed and the grammar are sent together, what
is recorded (a hash of the text, its size, whether the text that came back obeys it), and the ways it can go wrong: a text the grammar
refuses, a text cut at the token limit, a server error, a grammar that cannot be built or is too large. The reading of the llama.cpp
b11700 server code behind the request is in bench/GRAMMAR_ARM.md §2.
"""
import hashlib, json, os, shutil, sys, tempfile, unittest

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, HERE)
import apothicaire, optchat, gate_v3        # noqa: E402
from bench import run_bench as rb           # noqa: E402
from bench.stub_model import StubModel       # noqa: E402
from test_agent_gate import tool_call, say, IMPORT_ARGS, NCA_ARGS, USER   # noqa: E402
from test_agent_gate_v2 import shown_params  # noqa: E402
import test_gate_v2 as t2                    # noqa: E402

BASE_KEYS = {"model", "messages", "max_tokens", "temperature", "cache_prompt", "id_slot", "chat_template_kwargs"}


class StubServer:
    """A llama-server stand-in: answers each POST /v1/chat/completions with the next item of `script` (a message, a callable of the
    request body that returns one, or a (message, finish_reason) pair, or an httpx.Response) and records the bodies."""

    def __init__(self, script):
        self.script, self.bodies = list(script), []

    def __call__(self, request):
        assert request.url.path == "/v1/chat/completions", request.url
        body = json.loads(request.content)
        self.bodies.append(body)
        item = self.script.pop(0)
        if callable(item): item = item(body)
        if isinstance(item, httpx.Response): return item
        msg, finish = item if isinstance(item, tuple) else (item, "stop")
        return httpx.Response(200, json={"choices": [{"message": msg, "finish_reason": finish}],
                                         "usage": {"prompt_tokens": 1000 * len(self.bodies), "completion_tokens": 10},
                                         "timings": {"prompt_n": 10, "cache_n": 990, "prompt_ms": 1.0, "predicted_ms": 1.0, "predicted_per_second": 20.0}})


def make_llm(cfg, server):
    """The real optchat.LLM class, its HTTP client wired to the stub server (LLM.__init__ would ask a real one for its slots)."""
    llm = optchat.LLM.__new__(optchat.LLM)
    llm.cfg, llm.last, llm.total_slots = cfg, {}, 2
    llm.http = httpx.Client(base_url="http://llama.invalid", transport=httpx.MockTransport(server))
    return llm


@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
class TestAgentGateV3(unittest.TestCase):
    def setUp(self):
        self.dirs, self.agents, self.ag = [], [], None

    def tearDown(self):
        for ag in self.agents: ag.close()
        for d in self.dirs: shutil.rmtree(d, ignore_errors=True)
        apothicaire.install_prompt(apothicaire.SYSTEM_ADDITION)          # leave the module as the other tests expect it

    def fresh_memory(self):
        self.dir = tempfile.mkdtemp(prefix="apo_v3_"); self.dirs.append(self.dir)
        self.cfg = dict(optchat.CFG, data_dir=self.dir)

    def agent(self, version="v3", answers=(), seed=None):
        """An agent of that gate (its own memory folder) whose model is the real optchat.LLM behind a stub server: two tool rounds
        (import, NCA), then `answers`. The server is `self.server`, the agent `self.ag`, its folder `self.dir`."""
        self.fresh_memory()
        ag = apothicaire.Apothicaire(cfg=self.cfg, gate_version=version); self.agents.append(ag)
        self.server = StubServer([tool_call("data_import", IMPORT_ARGS, "c1"), tool_call("nca_run", {"worksheet": 1, **NCA_ARGS}, "c2"), *answers])
        llm = make_llm(self.cfg, self.server)
        if seed is not None: rb.seed_requests(llm, seed)
        ag.llm = llm; ag.compactor.llm = llm
        self.ag = ag
        return ag

    def typed_half_life(self, body):
        """A draft that types a tool value (gate v2: bare number), written from the digest the model was shown."""
        v = shown_params(self.ag)["subjects"][0]["parameters"]["half.life"]
        return say(f"Demi-vie = {v.replace('.', ',')}.")

    # ---------------------------------------------------------------- the request
    def test_the_regeneration_request_is_the_v2_one_plus_the_grammar(self):
        ag = self.agent(answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")])
        ans, st = ag.turn(USER, verbose=False)
        bodies = self.server.bodies
        self.assertEqual(len(bodies), 4)
        for b in bodies[:3]:                                                         # the tool rounds and the draft: no grammar
            self.assertNotIn("grammar", b); self.assertIn("tools", b); self.assertEqual(b["tool_choice"], "auto")
            self.assertEqual(set(b) - {"tools", "tool_choice"}, BASE_KEYS)
        users = [m["content"] for m in ag.store.log if m["role"] == "user"]
        gr = gate_v3.build(ag.refs, users, ag.schemas)
        regen, third = bodies[3], bodies[2]
        self.assertNotIn("post", vars(ag.llm.http))                                   # the client is as it was once the call is over
        expected = {"model": self.cfg["model"], "messages": third["messages"] + [{"role": "assistant", "content": st["gate"]["first_answer"]},
                                                                                  {"role": "user", "content": regen["messages"][-1]["content"]}],
                    "max_tokens": self.cfg["agent_max_tokens"], "temperature": 0.3, "cache_prompt": True, "id_slot": 0,
                    "chat_template_kwargs": {"enable_thinking": False}, "grammar": gr.gbnf}
        self.assertEqual(regen, expected)                                            # the exact body: no tools, no tool_choice, no response_format
        self.assertTrue(regen["messages"][-1]["content"].startswith("[system reminder] Your last answer was rejected by the renderer"))
        self.assertIn("root ::= ", regen["grammar"]); self.assertTrue(regen["grammar"].isascii())
        g = st["gate"]
        self.assertEqual(g["version"], "v3"); self.assertTrue(g["regenerated"]); self.assertEqual(g["kept"], "regenerated")
        self.assertEqual(g["first_findings"][0]["kind"], "bare_number")
        rec = g["grammar"]
        self.assertTrue(rec["sent"]); self.assertEqual(rec["sha256"], hashlib.sha256(gr.gbnf.encode("utf-8")).hexdigest())
        self.assertEqual({k: rec[k] for k in ("rules", "bytes", "refs", "numbers", "idents")}, {k: gr.stats[k] for k in ("rules", "bytes", "refs", "numbers", "idents")})
        self.assertEqual({k: v for k, v in rec["conformance"].items()}, {"accepted": True, "alive": True, "refused_at": None, "finish_reason": "stop", "violation": False})
        with open(os.path.join(self.dir, "gate.jsonl"), encoding="utf-8") as f: logged = [json.loads(line) for line in f]
        self.assertEqual(logged[-1]["grammar"], rec); self.assertEqual(logged[-1]["version"], "v3")       # the record goes to gate.jsonl
        p = shown_params(ag)["subjects"][0]["parameters"]["cmax"]
        self.assertEqual(ans, f"Cmax = {p.replace('.', ',')} [Cmax].")               # rendered as under gate v2
        self.assertEqual(ag.store.log[-1]["content"], "Cmax = {{call_2.cmax}}.")

    def test_gate_v2_sends_no_grammar_and_records_none(self):
        ag = self.agent(version="v2", answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")])
        ans, st = ag.turn(USER, verbose=False)
        regen = self.server.bodies[3]
        self.assertEqual(set(regen), BASE_KEYS); self.assertNotIn("grammar", regen)
        self.assertNotIn("grammar", st["gate"]); self.assertEqual(st["gate"]["version"], "v2")

    def test_the_v3_requests_are_the_v2_requests_and_one_field(self):
        bodies, answers = {}, {}
        for version in ("v2", "v3"):                                                  # the same chat, the same replies, two gates
            ag = self.agent(version=version, answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")])
            answers[version] = ag.turn(USER, verbose=False)[0]; bodies[version] = self.server.bodies
        self.assertEqual((len(bodies["v2"]), len(bodies["v3"])), (4, 4))
        for k in range(3): self.assertEqual(bodies["v2"][k], bodies["v3"][k])         # the tool rounds and the draft are untouched
        v2, v3 = dict(bodies["v2"][3]), dict(bodies["v3"][3])
        grammar = v3.pop("grammar")
        self.assertEqual(v2, v3); self.assertIn("root ::= ", grammar)
        self.assertEqual(answers["v2"], answers["v3"])                                # same reply, same rendering

    def test_gate_v1_is_unchanged_too(self):
        ag = self.agent(version="v1", answers=[say("CL/F = 12,5 L/h."), say("Voir le résultat de l'analyse.")])
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(len(self.server.bodies), 4); self.assertTrue(st["gate"]["regenerated"])
        self.assertTrue(all("grammar" not in b for b in self.server.bodies)); self.assertEqual(set(self.server.bodies[3]), BASE_KEYS)
        self.assertNotIn("grammar", st["gate"]); self.assertEqual(st["gate"]["version"], "v1")

    def test_no_regeneration_no_grammar(self):
        ag = self.agent(answers=[say("Cmax = {{call_2.cmax}}.")])
        ans, st = ag.turn(USER, verbose=False)
        self.assertEqual(len(self.server.bodies), 3); self.assertFalse(st["gate"]["regenerated"]); self.assertNotIn("grammar", st["gate"])
        self.assertTrue(all("grammar" not in b for b in self.server.bodies))

    def test_the_seed_and_the_grammar_travel_together(self):
        ag = self.agent(answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")], seed=7)
        ag.turn(USER, verbose=False)
        bodies = self.server.bodies
        self.assertTrue(all(b["seed"] == 7 for b in bodies))
        self.assertEqual(set(bodies[3]), BASE_KEYS | {"seed", "grammar"})
        self.assertTrue(all("grammar" not in b for b in bodies[:3]))
        self.assertIn("post", vars(ag.llm.http))                                     # the seeding wrapper is back, not lost

    # ---------------------------------------------------------------- what comes back
    def test_a_text_the_grammar_refuses_is_a_violation_and_gate_v2_still_judges_it(self):
        ag = self.agent(answers=[self.typed_half_life, self.typed_half_life])        # a server that ignored the grammar: the same typed number
        ans, st = ag.turn(USER, verbose=False)
        c = st["gate"]["grammar"]["conformance"]
        self.assertEqual((c["accepted"], c["alive"], c["violation"]), (False, False, True))
        typed = shown_params(ag)["subjects"][0]["parameters"]["half.life"]
        start = len("Demi-vie = ")
        self.assertIn(c["refused_at"], range(start, start + len(typed)))              # inside the typed number: no user number begins like it
        self.assertGreater(st["gate"]["after"]["numbers_unverified"], 0)               # gate v2 judges the new text as it does without a grammar
        self.assertIn("⚠", ans)

    def test_a_text_cut_at_the_token_limit_has_only_to_be_alive(self):
        ag = self.agent(answers=[self.typed_half_life, (say("Cmax = {{call_2.cm"), "length")])
        ans, st = ag.turn(USER, verbose=False)
        c = st["gate"]["grammar"]["conformance"]
        self.assertEqual((c["accepted"], c["alive"], c["violation"], c["finish_reason"]), (False, True, False, "length"))

    def test_a_text_that_stopped_where_the_grammar_cannot_end_is_a_violation(self):
        ag = self.agent(answers=[self.typed_half_life, say("Cmax = {{call_2.cm")])
        ans, st = ag.turn(USER, verbose=False)
        c = st["gate"]["grammar"]["conformance"]
        self.assertEqual((c["accepted"], c["alive"], c["violation"], c["finish_reason"]), (False, True, True, "stop"))

    def test_a_server_error_keeps_the_first_answer_and_is_recorded(self):
        ag = self.agent(answers=[self.typed_half_life, httpx.Response(500, text="failed to parse grammar")])
        ans, st = ag.turn(USER, verbose=False)
        g = st["gate"]
        self.assertTrue(g["regenerated"]); self.assertEqual(g["kept"], "first")
        self.assertIn("HTTP 500", g["regen_stats"]["error"]); self.assertIn("failed to parse grammar", g["regen_stats"]["error"])
        self.assertTrue(g["grammar"]["sent"]); self.assertNotIn("conformance", g["grammar"])
        self.assertIn("grammar", self.server.bodies[3]); self.assertIn("⚠", ans)

    def test_a_grammar_that_cannot_be_built_gives_the_v2_regeneration_and_the_record_says_why(self):
        ag = self.agent(answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")])
        build = gate_v3.build
        gate_v3.build = lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
        try: ans, st = ag.turn(USER, verbose=False)
        finally: gate_v3.build = build
        self.assertEqual(set(self.server.bodies[3]), BASE_KEYS)
        self.assertEqual(st["gate"]["grammar"], {"sent": False, "error": "ValueError: boom"})
        self.assertEqual(st["gate"]["kept"], "regenerated")                          # the regeneration went on as gate v2's

    def test_a_grammar_over_the_limit_is_not_sent(self):
        ag = self.agent(answers=[self.typed_half_life, say("Cmax = {{call_2.cmax}}.")])
        limit = apothicaire.GRAMMAR_MAX_BYTES
        apothicaire.GRAMMAR_MAX_BYTES = 100
        try: ans, st = ag.turn(USER, verbose=False)
        finally: apothicaire.GRAMMAR_MAX_BYTES = limit
        self.assertNotIn("grammar", self.server.bodies[3])
        self.assertFalse(st["gate"]["grammar"]["sent"]); self.assertIn("limit is 100", st["gate"]["grammar"]["error"])

    # ---------------------------------------------------------------- v3 is gate v2 around the regeneration
    def test_v3_is_typed_like_v2(self):
        ag = self.agent(answers=[say("Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}}.")])
        ans, st = ag.turn(USER, verbose=False)
        self.assertTrue(ag.typed); self.assertTrue(optchat.SYSTEM_PROMPT.endswith(apothicaire.SYSTEM_ADDITION_V2))
        self.assertEqual([c["ref"] for c in ag.tool_log], ["call_1", "call_2"]); self.assertNotIn("{{", ans)
        self.assertEqual(st["gate"]["version"], "v3"); self.assertIn("rendered", st["gate"])
        with open(os.path.join(self.dir, "refs.jsonl"), encoding="utf-8") as f: self.assertEqual(len(f.readlines()), 2)
        self.assertEqual(ag.gate_log[-1]["version"], "v3")

    def test_the_environment_variable_picks_v3(self):
        self.assertEqual(apothicaire.gate_version_of("v3"), "v3"); self.assertEqual(apothicaire.gate_version_of(" V3 "), "v3")
        with self.assertRaises(ValueError): apothicaire.gate_version_of("v4")
        old = os.environ.get("APOTHICAIRE_GATE")
        os.environ["APOTHICAIRE_GATE"] = "v3"
        self.fresh_memory()
        try: ag = apothicaire.Apothicaire(cfg=self.cfg); self.agents.append(ag)
        finally:
            if old is None: del os.environ["APOTHICAIRE_GATE"]
            else: os.environ["APOTHICAIRE_GATE"] = old
        self.assertEqual(ag.gate_version, "v3")


class TestChatWithGrammar(unittest.TestCase):
    """The helper on its own, with a recording HTTP client."""

    class Http:
        def __init__(self): self.sent = []
        def post(self, url, json=None, **kw): self.sent.append((url, json, kw)); return None

    class Llm:
        def __init__(self, http, fail=False): self.http, self.fail = http, fail
        def chat(self, messages, slot, tools=None, **kw):
            if self.fail: raise optchat.LLMError("transport: down")
            return self.http.post("/v1/chat/completions", json={"messages": messages, "id_slot": slot})

    def test_the_field_is_added_to_the_one_request_and_the_client_is_left_as_it_was(self):
        http = self.Http(); llm = self.Llm(http)
        apothicaire.chat_with_grammar(llm, "root ::= \"a\"\n", [{"role": "user", "content": "x"}], slot=0)
        self.assertEqual(http.sent[0][1], {"messages": [{"role": "user", "content": "x"}], "id_slot": 0, "grammar": "root ::= \"a\"\n"})
        self.assertNotIn("post", vars(http))
        llm.chat([], slot=0)
        self.assertNotIn("grammar", http.sent[1][1])                                  # the next request has none

    def test_an_existing_wrapper_of_post_is_called_through_and_put_back(self):
        http = self.Http(); llm = self.Llm(http)
        rb.seed_requests(llm, 3); seeded = http.post
        apothicaire.chat_with_grammar(llm, "g", [], slot=1)
        self.assertEqual(http.sent[0][1], {"messages": [], "id_slot": 1, "seed": 3, "grammar": "g"})
        self.assertIs(http.post, seeded)

    def test_the_client_is_put_back_when_the_call_fails(self):
        http = self.Http(); llm = self.Llm(http, fail=True)
        with self.assertRaises(optchat.LLMError): apothicaire.chat_with_grammar(llm, "g", [], slot=0)
        self.assertNotIn("post", vars(http))

    def test_a_model_without_a_client_is_given_the_grammar_as_a_keyword(self):
        stub = StubModel("v3", 1)
        apothicaire.chat_with_grammar(stub, "root ::= \"a\"\n", [], slot=0)
        self.assertEqual(stub.grammars, ["root ::= \"a\"\n"])


class TestConformance(unittest.TestCase):
    GR = gate_v3.build(t2.CALLS, ["Dose 100 mg"], t2.SCHEMAS)          # the references of the synthetic results, one number the user typed

    def test_a_sentence_is_conformant(self):
        c = gate_v3.conformance(self.GR, "La dose est de 100 mg.", "stop")
        self.assertEqual(c, {"accepted": True, "alive": True, "refused_at": None, "finish_reason": "stop", "violation": False})

    def test_a_refused_character_is_a_violation_whatever_the_reason_it_stopped(self):
        for finish in ("stop", "length", None):
            text = "La dose est de 12 mg."
            c = gate_v3.conformance(self.GR, text, finish)                   # the "1" begins the user's 100, the "2" is the first refused
            self.assertEqual((c["alive"], c["accepted"], c["violation"], c["refused_at"]), (False, False, True, text.index("12") + 1), finish)

    def test_a_prefix_is_owed_only_when_the_text_was_cut_or_the_reason_unknown(self):
        for finish, violation in (("length", False), (None, False), ("stop", True)):
            c = gate_v3.conformance(self.GR, "Cmax = {{call_2.cm", finish)
            self.assertEqual((c["alive"], c["accepted"], c["violation"]), (True, False, violation), finish)

    def test_an_empty_text_is_owed_nothing(self):
        c = gate_v3.conformance(self.GR, "", "stop")
        self.assertEqual((c["accepted"], c["alive"], c["violation"]), (False, True, False))


if __name__ == "__main__":
    unittest.main()
