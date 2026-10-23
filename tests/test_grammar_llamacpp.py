"""The grammar of gate v3 against llama.cpp b11700 itself (bench/grammar_llamacpp.py): llama.dll of the upstream release through ctypes,
the vocabulary of the 27B opened vocab-only, the CPU. No llama-server, no GPU, no weights. Skipped where llama.dll or the GGUF is not on
the machine (CI): the PC has both.

gate_v3.Machine and tests/gbnf_reader.py are two readers written for this repository; these tests ask the library the server runs.
The verdict of llama.cpp on a text (alive: every token of it is allowed by the grammar sampler; accepted: an end-of-generation token is
allowed after it) must be that of `gate_v3.conformance`, and when both refuse, the token llama.cpp refuses must hold the character
Machine refuses.
"""
import os, random, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, HERE)
import gate_v3                                     # noqa: E402
from bench import grammar_llamacpp as gl, grammar_offline as go   # noqa: E402
import test_gate_v3 as t3                          # noqa: E402


class TestHelpers(unittest.TestCase):
    """The parts that need no library."""

    TEXT = "Cmax = {{call_2.cmax}} puis Tmax = {{call_2.tmax}}."

    def test_a_mutation_is_one_edit_of_its_family(self):
        rng = random.Random(1)
        for kind in gl.MUTATIONS:
            m = gl.mutate(self.TEXT, kind, rng)
            self.assertIsNotNone(m, kind); self.assertNotEqual(m, self.TEXT)
        self.assertIn(" 12", gl.mutate(self.TEXT, "digits", random.Random(2)))
        u = gl.mutate(self.TEXT, "unit", random.Random(3)); self.assertTrue("}} mg" in u or "}} h" in u or "}} ng/mL" in u or "}} %" in u, u)
        self.assertTrue(gl.mutate(self.TEXT, "cut reference", random.Random(4)).count("}}") < self.TEXT.count("}}"))
        self.assertIn("_x}}", gl.mutate(self.TEXT, "wrong path", random.Random(5)))

    def test_the_families_that_need_a_reference_have_no_place_in_a_text_without_one(self):
        rng = random.Random(1)
        for kind in ("unit", "sign", "wrong path", "cut reference", "digits"): self.assertIsNone(gl.mutate("Bonjour.", kind, rng), kind)
        self.assertIsNotNone(gl.mutate("Bonjour tout le monde.", "other letters", rng))

    def test_mutations_are_reproducible(self):
        a = [gl.mutate(self.TEXT, k, random.Random(7)) for k in gl.MUTATIONS]
        self.assertEqual(a, [gl.mutate(self.TEXT, k, random.Random(7)) for k in gl.MUTATIONS])

    def test_byte_offsets_count_utf8_bytes(self):
        self.assertEqual(gl.byte_offset("aé⅕\U0001f600b", 4), 1 + 2 + 3 + 4)
        self.assertEqual(gl.byte_offset("abc", 0), 0)

    def test_the_struct_sizes_are_those_of_llama_h_on_x64(self):
        import ctypes
        self.assertEqual((ctypes.sizeof(gl._ModelParams), ctypes.sizeof(gl._TokenData), ctypes.sizeof(gl._TokenDataArray)), (80, 12, 32))
        self.assertEqual(gl.VOCAB_ONLY, 72)


@unittest.skipUnless(gl.available(), "llama.dll (b11700) or a GGUF to take the vocabulary from is not on this machine")
class TestAgainstLlamaCpp(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.ll = gl.LlamaCpp()

    @classmethod
    def tearDownClass(cls): cls.ll.close()

    def pristine(self, gr):
        s = self.ll.grammar(gr.gbnf)
        self.assertIsNotNone(s, self.ll.messages)
        self.addCleanup(self.ll.free, s)
        return s

    def agree(self, gr, texts, what=""):
        """Both readers on every text; returns the records. Fails on the first disagreement."""
        s, out = self.pristine(gr), []
        for t in texts:
            r = gl.compare(self.ll, s, gr, t)
            self.assertIsNotNone(r, f"the tokenizer does not round-trip {t!r}")
            self.assertTrue(r["agree"], f"{what} {t!r}: Machine alive={r['alive']} accepted={r['accepted']}, llama.cpp alive={r['llama_alive']} accepted={r['llama_accepted']}, place {r['same_place']}")
            out.append(r)
        return out

    # ---------------------------------------------------------------- the harness itself
    def test_the_vocabulary_is_the_27b(self):
        self.assertGreater(self.ll.n_vocab, 100_000)
        self.assertTrue(self.ll.lib.llama_vocab_is_eog(self.ll.vocab, self.ll.eot))
        self.assertEqual(b"".join(self.ll.piece(t) for t in self.ll.tokenize("Cmax = 12,5 µg/mL é")), "Cmax = 12,5 µg/mL é".encode("utf-8"))

    def test_a_tiny_grammar_behaves_as_llama_cpp_documents(self):
        s = self.ll.grammar('root ::= "a" [b-c]*\n'); self.assertIsNotNone(s); self.addCleanup(self.ll.free, s)
        for text, alive, accepted in (("a", True, True), ("abc", True, True), ("acbcb", True, True), ("", True, False), ("abd", False, False), ("b", False, False), ("ab ", False, False)):
            with self.subTest(text):
                v = self.ll.walk(s, text); self.assertTrue(v["faithful"])
                self.assertEqual((v["alive"], v["accepted"]), (alive, accepted))

    def test_a_text_that_is_not_a_grammar_is_not_parsed(self):
        for bad, why in (("root ::= [\n", "unexpected end of input"), ("root ::= foo\n", "Undefined rule identifier"), ("root ::= root \"a\"\n", "left recursion"),
                         ("x ::= \"a\"\n", "root"), ("root ::= \"a\" )\n", "")):
            with self.subTest(bad):
                s = self.ll.grammar(bad)
                if s is not None: self.ll.free(s)
                self.assertIsNone(s)
                self.assertIn(why, " ".join(self.ll.messages))                                   # the parser's message is kept

    # ---------------------------------------------------------------- the grammars of the tables
    def test_the_sentence_tables(self):
        gr = t3.GR
        good = self.agree(gr, t3.GOOD, "GOOD")
        self.assertTrue(all(r["llama_accepted"] for r in good))
        bad = self.agree(gr, [t for t, _ in t3.TestAcceptance.BAD], "BAD")
        self.assertFalse(any(r["llama_accepted"] for r in bad))
        stricter = self.agree(gr, [t for t, _ in t3.TestAcceptance.STRICTER], "STRICTER")
        self.assertFalse(any(r["llama_accepted"] for r in stricter))
        gaps = self.agree(gr, [t for t, _, _ in t3.TestAcceptance.GAPS], "GAPS")
        self.assertTrue(all(r["llama_accepted"] for r in gaps))

    def test_every_unit_gate_v2_reads_after_a_reference_is_refused_and_so_is_every_one_in_a_parenthesis_but_labels(self):
        gr = t3.GR
        units = t3.unit_strings()
        self.assertGreater(len(units), 100)
        texts = [f"{t3.REF} {u}" for u in units] + [f"{t3.REF}{u}" for u in units] + [f"{t3.REF} ({u})" for u in units] + [f"Cmax ({u}) : {t3.REF}" for u in units]
        rs = self.agree(gr, texts, "unit")
        after = rs[:2 * len(units)]
        self.assertFalse(any(r["llama_accepted"] for r in after))                       # a unit right after a reference: refused by llama.cpp too

    def test_the_other_grammars_of_the_tests(self):
        calls = {k: t3.CALLS[k] for k in ("call_1", "call_2")}
        for gr in (gate_v3.build(calls, [t3.USER], t3.SCHEMAS), gate_v3.build(t3.CALLS, [t3.USER], t3.SCHEMAS, idents=False), gate_v3.build({}, [], None),
                   gate_v3.build({k: t3.CALLS[k] for k in ("call_2", "call_4", "call_5")}, ["compare"], t3.SCHEMAS)):
            self.agree(gr, t3.GOOD[:10] + ("Bonjour.", "dose 12 mg", "analyse 7", "{{call_2.cmax}} mg"), "other")

    # ---------------------------------------------------------------- random texts
    def test_random_walks_the_machine_accepts_are_accepted_by_llama_cpp(self):
        gr, rng, texts = t3.GR, random.Random(20261023), []
        while len(texts) < 600:
            t = t3.walk(gr.machine, rng)
            if t: texts.append(t)
        rs = self.agree(gr, texts, "walk")
        self.assertTrue(all(r["llama_accepted"] for r in rs))
        self.assertTrue(any("{{" in t for t in texts))

    def test_random_fragments_get_the_same_verdict_and_the_same_place(self):
        gr, rng = t3.GR, random.Random(7)
        texts = ["".join(rng.choice(t3.FRAGMENTS) for _ in range(rng.randrange(1, 9))) for _ in range(1500)]
        rs = self.agree(gr, texts, "fragments")
        self.assertGreater(sum(r["llama_accepted"] for r in rs), 30)                       # not vacuous: some pass
        self.assertGreater(sum(r["same_place"] is True for r in rs), 300)                  # and many are refused, at the same place

    def test_random_characters_including_multibyte_ones(self):
        gr, rng = t3.GR, random.Random(11)
        alphabet = t3.CHARS + list("⅕٣１中\U0001f600½²→µΔ")
        texts = ["".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 14))) for _ in range(1500)]
        self.agree(gr, texts, "chars")

    # ---------------------------------------------------------------- the stored runs
    def test_the_first_turns_of_the_stored_runs(self):
        turns = go.load_turns()
        res = gl.run(self.ll, turns, limit=40, timing=False)
        self.assertEqual((res["turns"], res["grammars"], res["parse_failures"], res["disagreements"], res["untokenizable"]), (res["turns"], res["turns"], [], [], 0))
        self.assertGreater(res["turns"], 10)
        t = gl.tally(res)
        self.assertEqual(t["all"]["agree"], t["all"]["texts"])
        self.assertEqual(t["finals"]["accepted"], t["finals"]["texts"] - t["finals"]["refused_places"])
        self.assertEqual(t["drafts"]["alive"], 0)
        for kind in ("unit", "wrong path", "other digits"): self.assertEqual(t["mutated"][kind]["accepted"], 0, kind)

    def test_the_report_has_the_numbers_it_claims(self):
        res = gl.run(self.ll, go.load_turns(), limit=12, timing=True)
        md = gl.markdown(res, "bench/runs/decision/v2")
        self.assertIn("Disagreements: 0.", md); self.assertIn("Expected cost of the regeneration", md); self.assertIn("inside a reference", md)
        self.assertIn(res["dll"]["llama.dll"][:16], md)
        inside = next(r for r in res["timing"] if r["state"] == "inside a reference")
        prose = next(r for r in res["timing"] if r["state"] == "start of an answer")
        self.assertLess(inside["left"], 100); self.assertGreater(prose["left"], 10_000)       # in a reference only a few tokens fit, in prose most do


if __name__ == "__main__":
    unittest.main()
