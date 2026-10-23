"""Tests of gate v3 (gate_v3.py): the grammar of the regeneration. Spec: the docstring of gate_v3.py, bench/GRAMMAR_ARM.md.

Gate v3 is gate v2 plus a llama.cpp GBNF for the regeneration call. What is tested here, and how:

  * the building blocks against their sources: the prose alphabet against unicodedata and re.IGNORECASE; the unit automaton against
    the two regular expressions it replaces (gate._ATOM_RE, gate_v2._UNIT_WORD), expanded to their finite languages;
  * the vocabulary of a turn against gate_v2.resolve: every reference the grammar offers resolves, every canonical reference
    gate v2 resolves is offered;
  * the printed GBNF against an independent reader (tests/gbnf_reader.py: an Earley parser that shares no code with gate_v3), in
    lockstep with the stack engine (gate_v3.Machine) that re-implements llama.cpp b11700; every rule is productive, so the
    sampler cannot walk into a dead end;
  * tables of sentences (good, bad, stricter than gate v2, not covered by the grammar), mutation families in the style of
    TestRedTeamMutations (tests/test_gate_v2.py) cross-checked against gate v2, and a seeded random-walk fuzz: whatever the
    grammar accepts, gate v2 reads without a finding of the kinds the grammar is meant to prevent, and the text carries no free
    digit (checked by a segmentation that does not use the grammar's modes).

The tool results are the SYNTHETIC payloads of tests/test_gate_v2.py (invented values).
"""
import itertools, os, random, re, sys, unicodedata, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import gate, gate_v2, gate_v3, apothicaire   # noqa: E402
import gbnf_reader                           # noqa: E402
import test_gate_v2 as t2                    # noqa: E402
from gate_v3 import CS                       # noqa: E402

try: from re import _constants as sre_const, _parser as sre_parse      # python >= 3.11
except ImportError: import sre_constants as sre_const, sre_parse        # noqa: E402

CALLS, USER, SCHEMAS = t2.CALLS, t2.USER, t2.SCHEMAS
GR = gate_v3.build(CALLS, [USER], SCHEMAS)
REF = "{{call_2.cmax}}"
COVERED = {"bare_number", "unresolved_reference", "untyped_reference", "malformed_reference", "adjacent_to_reference"}   # what the grammar prevents
MICRO_SIGN, GREEK_MU = "µ", "μ"
NBSP, NNBSP, THIN, FIGURE = " ", " ", " ", " "


def kinds(text, calls=CALLS, users=(USER,)):
    """The kinds of the findings gate v2 has on `text`."""
    return sorted({f["kind"] for f in t2.v2(text, users=users, calls=calls)["findings"]})


def flagged(text, calls=CALLS, users=(USER,)):
    return bool(COVERED & set(kinds(text, calls, users)))


def expand(pattern, flags=0):
    """The finite language of a regular expression made of literals, classes, alternations, groups and `?` (look-aheads and anchors
    are not part of the strings)."""
    def seq(items):
        out = [""]
        for op, av in items: out = [o + x for o in out for x in node(op, av)]
        return out
    def node(op, av):
        if op is sre_const.LITERAL: return [chr(av)]
        if op is sre_const.IN:
            out = []
            for o, a in av:
                if o is sre_const.LITERAL: out.append(chr(a))
                elif o is sre_const.RANGE: out += [chr(c) for c in range(a[0], a[1] + 1)]
                else: raise ValueError(o)
            return out
        if op is sre_const.BRANCH: return [s for alt in av[1] for s in seq(alt)]
        if op is sre_const.SUBPATTERN: return seq(av[3])
        if op in (sre_const.MAX_REPEAT, sre_const.MIN_REPEAT):
            lo, hi, sub = av
            if hi == sre_const.MAXREPEAT: raise ValueError("unbounded repeat")
            parts = seq(sub)
            return [x for n in range(lo, hi + 1) for x in map("".join, itertools.product(parts, repeat=n))]
        if op in (sre_const.ASSERT, sre_const.ASSERT_NOT, sre_const.AT): return [""]
        raise ValueError(op)
    return set(seq(list(sre_parse.parse(pattern, flags))))


def explained(text, gr):
    """True when `text` splits into prose (no digit, no numeric character, no brace) and phrases the grammar offers: a reference,
    a closed label, a typed number, an identifier. A second opinion that does not use the modes of the grammar."""
    by_first = {}
    for p in list(gr.vocab.refs) + list(gate_v3.LABELS) + list(gr.vocab.numbers) + list(gr.vocab.idents): by_first.setdefault(p[0], []).append(p)
    reach = [False] * (len(text) + 1); reach[0] = True
    for i, c in enumerate(text):
        if not reach[i]: continue
        if not (c.isdigit() or c.isnumeric() or c in "{}"): reach[i + 1] = True
        for p in by_first.get(c, ()):
            if text.startswith(p, i): reach[i + len(p)] = True
    return reach[-1]


# ================================================================ building blocks
class TestCharacterSets(unittest.TestCase):
    def test_set_algebra_agrees_with_python_sets(self):
        rng = random.Random(7)
        def rand(): return CS((a, a + rng.randrange(0, 6)) for a in (rng.randrange(0, 60) for _ in range(rng.randrange(0, 8))))
        def py(cs): return {ord(c) for c in cs}
        for _ in range(300):
            a, b = rand(), rand()
            self.assertEqual(py(a | b), py(a) | py(b)); self.assertEqual(py(a & b), py(a) & py(b)); self.assertEqual(py(a - b), py(a) - py(b))
            self.assertEqual(len(a), len(py(a))); self.assertEqual(bool(a), bool(py(a)))
            for cp in range(0, 70): self.assertEqual(cp in a, cp in py(a))
            for x in (a | b, a & b, a - b): self.assertTrue(all(p[1] + 1 < q[0] for p, q in zip(x.r, x.r[1:])), x)   # sorted, disjoint, not adjacent
        with self.assertRaises(ValueError): CS([(5, 4)])
        self.assertEqual(CS.of("ba"), CS([(97, 98)])); self.assertIn("a", CS.of("ab")); self.assertNotIn("c", CS.of("ab"))

    def test_prose_has_no_digit_no_brace_no_control(self):
        for ch in gate_v3.PROSE:
            cat = unicodedata.category(ch)
            self.assertFalse(ch.isdigit() or ch.isnumeric() or ch.isdecimal(), hex(ord(ch)))
            self.assertIsNone(unicodedata.numeric(ch, None), hex(ord(ch)))
            self.assertNotIn(cat, ("Nd", "No", "Nl", "Cs", "Co", "Zl", "Zp"), hex(ord(ch)))
            self.assertTrue(cat != "Cc" or ch in "\t\n", hex(ord(ch)))
            self.assertNotIn(ch, "{}\r")

    def test_prose_excludes_what_ignorecase_folds_onto_a_unit_letter(self):
        # U+0130, U+0131, U+017F, U+039C, U+212A: gate v2's unit words are case-insensitive, so these would be read as letters of a
        # unit word that the grammar does not see
        folded = {c for c in gate_v3.PROSE if re.fullmatch("[A-Za-z" + MICRO_SIGN + GREEK_MU + "]", c, re.I)}
        self.assertEqual(folded, set(gate_v3.ASCII_LETTERS | gate_v3.MICRO))
        for cp in (0x130, 0x131, 0x17f, 0x39c, 0x212a): self.assertNotIn(chr(cp), gate_v3.PROSE)
        self.assertEqual(set(gate_v3.MICRO), {MICRO_SIGN, GREEK_MU})

    def test_prose_keeps_the_text_of_an_answer(self):
        for ch in ("abcXYZ éèêëàâäîïôöùûüÿçœæñß ÉÈÀÇ λΩαβγδΔΣ .,;:!?'\"’‘“”«»()[]|*_~`#<>=+-−–—/\\^÷×·°%‰&@$€£¥ →←↑↓⇒≈≠≤≥∞∑√ "
                   "✓✗❌⚠️💊📈🧪\t\n" + MICRO_SIGN + GREEK_MU):
            self.assertIn(ch, gate_v3.PROSE, hex(ord(ch)))
        for ch in "0123456789²³¹½¼¾①٣Ⅻ１２⁰⁹₀₉⁻₋{}\r\x00\x1b ":
            self.assertNotIn(ch, gate_v3.PROSE, hex(ord(ch)))

    def test_kinds_partition_prose(self):
        union = CS()
        for name, cs in gate_v3.KINDS.items():
            self.assertTrue(cs, name); self.assertFalse(union & cs, name); union = union | cs
        self.assertEqual(union, gate_v3.PROSE)

    def test_blank_kind_is_what_gate_reads_as_a_blank(self):
        self.assertEqual(gate_v3.BLK, CS.of(gate.SPACES + "\t"))
        self.assertEqual(gate_v3.NL, CS.of("\n"))
        self.assertEqual(set(gate.SPACES), {" ", NBSP, NNBSP, THIN, FIGURE})


class TestUnitTables(unittest.TestCase):
    def test_expand(self):
        self.assertEqual(expand("a(b|cd)?e"), {"ae", "abe", "acde"})
        self.assertEqual(expand("[ab]c[x-z]?"), {"ac", "bc", "acx", "acy", "acz", "bcx", "bcy", "bcz"})
        self.assertEqual(expand("ab(?![c])d"), {"abd"})

    def test_atoms_are_the_atoms_of_gate(self):
        self.assertEqual(expand(gate._ATOM_RE.pattern), set(gate_v3.UNIT_ATOMS))

    def test_words_are_the_unit_words_of_gate_v2(self):
        words = {w.lower() for w in expand(gate_v2._UNIT_WORD, re.I)}
        self.assertEqual(words | {"fold"}, {w.lower() for w in gate_v3.UNIT_WORDS})   # "fold": see the comment at UNIT_ATOMS

    def test_look_ahead_is_the_look_ahead_of_both_expressions(self):
        look = "(?![A-Za-z" + MICRO_SIGN + GREEK_MU + "'’])"
        self.assertIn(look, gate._ATOM_RE.pattern); self.assertIn(look, gate_v2._UNIT_AFTER_WORD_RE.pattern)
        self.assertEqual(gate_v3.LOOK, CS.of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" + MICRO_SIGN + GREEK_MU + "'’"))

    def _run(self, s):
        st = gate_v3.UD.root
        for ch in s:
            st = gate_v3.UD.trans[st].get(ch)
            if st is None: return None
        return st

    def test_automaton_recognises_every_item_in_every_case(self):
        ud, allowed = gate_v3.UD, set()
        for item in gate_v3.UNIT_ITEMS: allowed.update(map("".join, itertools.product(*[list(cs) for cs in item])))
        for s in allowed:
            st = self._run(s)
            self.assertTrue(st is not None and ud.complete[st], s)
        pool, alphabet, rng = sorted(allowed), "abcdefghijklmnopqrstuvwxyzHLMUIC " + MICRO_SIGN + GREEK_MU + "%‰°/", random.Random(3)
        for _ in range(20000):                                    # one edit away from an item: complete exactly when it is an item
            s = list(rng.choice(pool)); i = rng.randrange(len(s) + 1)
            op = rng.choice("rid")
            if op == "r" and i < len(s): s[i] = rng.choice(alphabet)
            elif op == "i": s.insert(i, rng.choice(alphabet))
            elif op == "d" and i < len(s): del s[i]
            s = "".join(s); st = self._run(s)
            self.assertEqual(st is not None and ud.complete[st], s in allowed, s)

    def test_automaton_agrees_with_the_regular_expressions(self):
        rng, alphabet = random.Random(11), "abdeghijlmnoprstuxzHLMUICDSJG " + MICRO_SIGN + GREEK_MU + "%‰°"
        for _ in range(30000):
            s = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 6)))
            if s[0] == " ": continue                              # the automaton starts after the blank; the expression skips it itself
            m1, m2 = gate._ATOM_RE.match(s), gate_v2._UNIT_AFTER_WORD_RE.match(s)
            regex = bool(m1 and m1.end() == len(s)) or bool(m2 and m2.end() == len(s))
            st = self._run(s)
            self.assertEqual(st is not None and gate_v3.UD.complete[st], regex, s)

    def test_a_complete_unit_is_a_dead_end_except_for_the_letters_of_common_words(self):
        ud = gate_v3.UD
        for s in ("h", "min", "mg", "l", "g", "j", "mol", "ml", "mL", "IU", "U", "%", "°C", "heures", "secondes", "pour cent"):
            st = self._run(s)
            self.assertTrue(ud.complete[st], s); self.assertNotIn(st, ud.live, s)
        for s in ("d", "s", "D", "S"): self.assertIn(self._run(s), ud.live, s)
        self.assertEqual(gate_v3.UNIT_ALIVE, CS.of("dDsS"))


class TestLabelsAndIdentifiers(unittest.TestCase):
    CONTEXTS = ("{L}", "a {L} b", "La valeur {L} : {R}", "({L})", "{L} = {R}", "{L}, puis", "{L}.", "avec {L}\n- x", "| {L} | {R} |", "{L}: {R}")

    def test_every_label_is_notation_for_gate_v2(self):
        for label in gate_v3.LABELS:
            for tpl in self.CONTEXTS:
                t = tpl.format(L=label, R=REF)
                with self.subTest(t): self.assertEqual(kinds(t), [])

    def test_every_label_can_be_written(self):
        for label in gate_v3.LABELS:
            for tpl in self.CONTEXTS:
                if label[0].isdigit() and tpl != "({L})": continue                  # 1/h, 1/min, 1/λz: only inside parentheses
                t = tpl.format(L=label, R=REF)
                with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1])

    def test_the_names_the_renderer_prints_are_labels(self):
        self.assertEqual(set(gate_v3.renderer_labels()) - set(gate_v3.LABELS), set())
        self.assertEqual(gate_v3.renderer_labels(), ["C0", "R²"])

    def test_only_closed_notation_carries_a_digit(self):
        for t in ("AUC(0-24)", "AUC(0-tlast)2", "R3", "t1/3", "C1", "R²²", "T½2", "k0", "AUC(0-12h)", "t3/2"):
            with self.subTest(t): self.assertFalse(GR.accepts(t))

    def test_identifiers_come_from_the_tool_results(self):
        ids = gate_v3.ident_numbers(CALLS)
        self.assertEqual({k: sorted(v) for k, v in ids.items()}, {"analysis": ["7", "8", "9"], "subject": ["1", "2", "3"], "worksheet": ["4"]})
        for t in ("analyse 7", "Analyse 8 :", "analysis 9", "Analysis 7.", "sujet 3", "Sujet 1", "subject 2", "worksheet 4", "feuille 4", "Feuille 4 (syn)"):
            with self.subTest(t): self.assertTrue(GR.accepts(t)); self.assertEqual(kinds(t), [])
        for t in ("analyse 12", "analyse 70", "sujet 4", "analyse 0", "worksheet 7", "analyse 07", "Analyse 7,5", "sujet 11"):
            with self.subTest(t): self.assertFalse(GR.accepts(t))

    def test_identifiers_can_be_switched_off(self):
        strict = gate_v3.build(CALLS, [USER], SCHEMAS, idents=False)
        self.assertEqual(strict.vocab.idents, []); self.assertGreater(len(GR.vocab.idents), 0)
        for t in ("analyse 7", "sujet 1", "worksheet 4"): self.assertFalse(strict.accepts(t), t)
        self.assertTrue(strict.accepts("l'analyse et le sujet"))

    def test_an_identifier_is_not_a_number_for_what_follows(self):
        for t in ("analyse 7 {{call_2.cmax}}", "analyse 7{{call_2.cmax}}", "analyse 7.{{call_2.cmax}}", "analyse 7 mg", "analyse 7 fois", "analyse 7-fold",
                  "analyse 7 x 2", "analyse 7 + 3", "analyse 7 5", "analyse 75", "sujet 1 × 2", "analyse 7%"):
            with self.subTest(t): self.assertFalse(GR.accepts(t))
        for t in ("analyse 7, sujet 1.", "analyse 7 : {{call_2.cmax}}", "analyse 7 (sujet 1)", "analyse 7 contre analyse 8", "- analyse 7 :\n- analyse 8 :"):
            with self.subTest(t): self.assertTrue(GR.accepts(t)); self.assertEqual(kinds(t), [])


# ================================================================ the vocabulary of a turn
class TestVocabulary(unittest.TestCase):
    def test_every_reference_resolves_in_gate_v2(self):
        self.assertGreater(len(GR.vocab.refs), 100)
        for ref in GR.vocab.refs:
            r = t2.v2(ref)
            self.assertEqual((r["findings"], r["references_total"], r["references_unresolved"], len(r["assertions"])), ([], 1, 0, 1), ref)

    def _candidates(self):
        keys = set(gate_v2.PARAMETERS) | {"dose"} | {f"lambda_z.{f}" for f in gate_v2._LZ_FIELDS} | {f"lambda_z.{f.replace('_', '.')}" for f in gate_v2._LZ_FIELDS}
        for rec in CALLS.values():
            sc = rec.get("structured")
            if isinstance(sc, dict) and sc.get("kind") == "nca": keys |= {f"thresholds.{n}" for n in gate_v2._thresholds(sc)}
        keys |= {f"{p}.{f}" for p in gate_v2.PARAMETERS for f in ("a", "b", "difference", "percent", "ratio")}
        out = {"{{convention." + k + "}}" for k in gate_v2.CONVENTIONS}
        out |= {"{{" + f"{ref}.{prefix}{key}" + "}}" for ref in CALLS for prefix in ("", "subject=1.", "subject=2.", "subject=3.", "subject=9.") for key in keys}
        return out

    def test_every_canonical_reference_gate_v2_resolves_is_offered(self):
        offered, found = set(GR.vocab.refs), 0
        candidates = self._candidates()
        for t in sorted(candidates):
            r = t2.v2(t)
            if not r["findings"] and r["references_total"] == 1:
                found += 1; self.assertIn(t, offered, t)
        self.assertGreater(found, 100)
        self.assertEqual(offered - candidates, set())                          # and the grammar offers nothing outside the candidates

    def test_what_gate_v2_refuses_cannot_be_written(self):
        for body in ("call_9.cmax", "call_2.cmaxx", "call_2.subject=2.cmax", "cmax", "call_2.result.subjects[0].dose", "call_2.name", "call_2.label",
                     "call_2.route", "call_2.spec.kind", "call_4.cmax.unit_a", "call_4.cmax.not_comparable", "convention.nothing",
                     "call_3.cmax", "call_3.subject=4.cmax", "call_1.cmax", "call_1.worksheet.rows", "call_2", "convention.", "call_2.thresholds.nothing",
                     "call_2.lambda_z.n_poins", "call_4.nothing.a", "call_4.c0.a", ""):
            t = "{{" + body + "}}"
            with self.subTest(t):
                self.assertNotIn(t, GR.vocab.refs); self.assertFalse(GR.accepts(t))
                self.assertNotEqual(kinds(t), [])

    ALIASES = ("call2.cmax", "Call_2.cmax", "call-2.cmax", "call 2.cmax", "call_2:cmax", " call_2.cmax ", "call_2.Cmax", "call_2.CMAX", '"call_2".cmax',
               "call_2.cmax ", " call_2.cmax", "call_2.cmax.", "call_2.aucinf.obs.value", "call_4.auclast.relative_percent", "call_4.auclast.pct", "call_4.auclast.diff")

    def test_aliases_gate_v2_reads_are_not_offered(self):
        # v2 reads these spellings; the system prompt teaches one, and the grammar offers that one
        for body in self.ALIASES:
            t = "{{" + body + "}}"
            with self.subTest(t): self.assertEqual(kinds(t), []); self.assertFalse(GR.accepts(t)); self.assertNotIn(t, GR.vocab.refs)

    def test_several_subjects_need_the_subject_form(self):
        self.assertTrue(GR.accepts("{{call_3.subject=2.cmax}} et {{call_3.subject=3.cmax}}"))
        self.assertFalse(GR.accepts("{{call_3.cmax}}")); self.assertNotEqual(kinds("{{call_3.cmax}}"), [])
        self.assertTrue(GR.accepts("{{call_2.cmax}} {{call_2.subject=1.cmax}}"))        # one subject: both forms
        self.assertFalse(GR.accepts("{{call_3.subject=3.tmax}}"))                       # that subject has no Tmax ("no_rise"): gate v2 does not resolve it
        self.assertNotEqual(kinds("{{call_3.subject=3.tmax}}"), [])

    def test_dotted_spellings_of_the_selected_regression(self):
        calls = t2.make_calls(call_6=apothicaire.ref_record("call_6", "nca_run", t2.with_candidates(t2.NCA, t2.CANDS), t2.WS_UNITS))
        gr = gate_v3.build(calls, [], SCHEMAS)
        for body in ("call_6.lambda_z.n_points", "call_6.lambda_z.n.points", "call_6.lambda_z.adj_r_squared", "call_6.lambda_z.adj.r.squared", "call_6.lambda_z.lambda_z"):
            t = "{{" + body + "}}"
            with self.subTest(t): self.assertEqual(kinds(t, calls=calls, users=()), []); self.assertTrue(gr.accepts(t), t)

    def test_typed_numbers_are_the_users_with_both_decimal_marks(self):
        nums = set(GR.vocab.numbers)
        for n in ("100", "0.5", "4.2", "1.5", "12.35", "6", "6.98", "24", "0.9", "0,5", "4,2", "12,35", "6,98", "0,9", "1,5", "0.5,4.2"):
            self.assertIn(n, nums)
        for n in ("5", "12.3", "12", "0.50", "13", "1", "2", "7.5", "98.7654321"):
            self.assertNotIn(n, nums)
        for t in ("dose de 100 mg", "Cmax 12,35 ng/mL", "Cmax 12.35 ng/mL", "t = 0,5 h", "0.5 h puis 1,5 h", "à 24 h", "t1/2 = 6 h"):
            with self.subTest(t): self.assertTrue(GR.accepts(t)); self.assertEqual(kinds(t), [])
        for t in ("dose de 101 mg", "Cmax 12,3 ng/mL", "Cmax 12,350 ng/mL", "t = 0,55 h", "à 25 h", "dose de 1000 mg", "dose de 10 mg", "dose de 100,5 mg", "t1/2 = 7 h"):
            with self.subTest(t): self.assertFalse(GR.accepts(t))

    def test_a_number_the_user_did_not_type_is_not_writable_even_when_small(self):
        for t in ("3 points", "au moins 2 sujets", "1 analyse", "2 fois", "la 2e", "environ 5", "10 %", "les 4 derniers points", "(#1)"):
            with self.subTest(t): self.assertFalse(GR.accepts(t))

    def test_numbers_of_the_user_text_only(self):
        gr = gate_v3.build({}, ["Dose 12,5 mg le 3 mars, puis 1 000 mg ; 2.0e3"], SCHEMAS)
        self.assertGreaterEqual(set(gr.vocab.numbers), {"12,5", "12.5", "3", "1", "000", "2.0e3"})
        self.assertTrue(gr.accepts("dose de 12,5 mg")); self.assertTrue(gr.accepts("dose de 12.5 mg")); self.assertFalse(gr.accepts("dose de 12,50 mg"))
        self.assertFalse(gr.accepts("dose de 125 mg")); self.assertFalse(gr.accepts("dose de 12,5,5 mg")); self.assertTrue(gr.accepts("le 3 mars"))

    def test_no_tool_result_leaves_the_conventions(self):
        gr = gate_v3.build({}, [], None)
        self.assertEqual(len(gr.vocab.refs), len(gate_v2.CONVENTIONS)); self.assertEqual((gr.vocab.numbers, gr.vocab.idents), ([], []))
        self.assertTrue(gr.accepts("Le critère est {{convention.min_adj_r_squared}}.")); self.assertFalse(gr.accepts("{{call_1.cmax}}"))
        self.assertTrue(gr.accepts("Aucun résultat pour le moment, importez des données.")); self.assertFalse(gr.accepts("Cmax 12"))

    def test_a_record_without_a_structured_result_offers_nothing(self):
        calls = {"call_1": {"name": "x", "structured": None}, "call_2": {"name": "y"}, "call_3": {"structured": {"kind": "nca", "result": None}}}
        gr = gate_v3.build(calls, [], None)
        self.assertEqual(len(gr.vocab.refs), len(gate_v2.CONVENTIONS))

    def test_build_is_deterministic_and_small(self):
        a, b = gate_v3.build(CALLS, [USER], SCHEMAS), gate_v3.build(CALLS, [USER], SCHEMAS)
        self.assertEqual(a.gbnf, b.gbnf)
        s = a.stats
        self.assertEqual(set(s), {"rules", "bytes", "refs", "numbers", "idents", "dropped", "build_ms"})
        self.assertLess(s["rules"], 700); self.assertLess(s["bytes"], 120_000); self.assertLess(s["build_ms"], 2000)
        self.assertEqual((s["refs"], s["numbers"], s["idents"]), (len(a.vocab.refs), len(a.vocab.numbers), len(a.vocab.idents)))


# ================================================================ sentences
GOOD = (
    t2.GOLDEN, "Cmax = {{call_2.cmax}}.", "La demi-vie est de {{call_2.half.life}}, soit {{call_2.tmax}} de plus.", "R² = {{call_2.r.squared}}", "t½ = {{call_2.half.life}}",
    "AUC₀₋∞ = {{call_2.aucinf.obs}}", "Cmax : {{call_2.cmax}}\nTmax : {{call_2.tmax}}", "Résultats :\n- Cmax : {{call_2.cmax}}\n- Tmax : {{call_2.tmax}}\n* AUC : {{call_2.auclast}}",
    "| Paramètre | Valeur |\n|---|---|\n| Cmax | {{call_2.cmax}} |\n| Tmax | {{call_2.tmax}} |", "- {{call_2.cmax}}", "* {{call_2.cmax}}", "+ {{call_2.cmax}}", "  - {{call_2.cmax}}",
    "la différence est négative : {{call_4.auclast.difference}}", "soit moins de {{call_2.thresholds.max_extrapolated_percent}}", "{{call_2.cmax}} {{call_2.tmax}}",
    "{{call_2.cmax}}, soit {{call_2.tmax}}.", "{{call_2.cmax}} (observée)", "Tmax = {{call_2.tmax}} (prélèvement à 1,5 h)", "Tmax = {{call_2.tmax}} après une dose de 100 mg",
    "Les concentrations sont en ng/mL ; Cmax = {{call_2.cmax}}", "La dose est 100 mg.", "dose de 100 mg par voie orale", "concentrations de 0,5 et 4,2", "0.5 puis 4.2", "1,5 h",
    "Pour le sujet 2 : {{call_3.subject=2.cmax}}", "Analyse 7 contre analyse 8 : {{call_4.auclast.a}} et {{call_4.auclast.b}}", "Critères : {{convention.min_adj_r_squared}}",
    "Bonjour.", "a", " ", "Je ne peux pas calculer ça : aucune donnée.", "Cmax ({{call_2.cmax}}) et Tmax ({{call_2.tmax}})", "[{{call_2.cmax}}]", "« {{call_2.cmax}} »",
)

class TestAcceptance(unittest.TestCase):
    def test_good_sentences_are_accepted_and_clean_for_gate_v2(self):
        for t in GOOD:
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), []); self.assertTrue(explained(t, GR))

    def test_the_empty_answer(self):
        self.assertFalse(GR.accepts(""))                   # a regeneration must say something
        self.assertTrue(GR.accepts("."))

    BAD = (       # (text, the kind gate v2 gives it)
        ("La Cmax vaut 12,3 ng/mL", "bare_number"), ("Cmax = 98.7654", "bare_number"), ("AUC = 98", "bare_number"), ("t1/2 = 7 h", "bare_number"),
        ("{{call_2.cmax}} mg/L", "adjacent_to_reference"), ("{{call_2.cmax}}mg", "adjacent_to_reference"), ("{{call_2.cmax}} %", "adjacent_to_reference"),
        ("{{call_2.cmax}}h", "adjacent_to_reference"), ("{{call_2.cmax}} fois", "adjacent_to_reference"), ("{{call_2.cmax}} x 10", "adjacent_to_reference"),
        ("{{call_2.cmax}}2", "adjacent_to_reference"), ("{{call_2.cmax}}.5", "adjacent_to_reference"), ("{{call_2.cmax}}e3", "adjacent_to_reference"),
        ("-{{call_2.cmax}}", "adjacent_to_reference"), ("Cmax = - {{call_2.cmax}}", "adjacent_to_reference"), ("2 {{call_2.cmax}}", "adjacent_to_reference"),
        ("{{call_2.cmax}}{{call_2.tmax}}", "adjacent_to_reference"), ("{{call_2.cmax}} (mg)", "adjacent_to_reference"), ("Cmax = {{call_2.cmaxx}}", "unresolved_reference"),
        ("Cmax = {{call_9.cmax}}", "unresolved_reference"), ("Cmax = {{call_2.name}}", "untyped_reference"), ("{{call_2.result.subjects[0].dose}}", "untyped_reference"),
        ("Cmax = {{cmax}}", "any"), ("Cmax = {{call_2.cmax", None),                      # an unterminated reference is plain text for gate v2: it has nothing to find
    )

    def test_bad_sentences_are_refused_and_flagged_by_gate_v2(self):
        for t, kind in self.BAD:
            with self.subTest(t):
                self.assertFalse(GR.accepts(t))
                if kind == "any": self.assertNotEqual(kinds(t), [])
                elif kind: self.assertIn(kind, kinds(t))

    def test_the_first_refused_character_is_reported(self):
        text = "Cmax = " + REF + " mg."
        self.assertEqual(GR.scan(text)[0][:2], (text.index("mg") + 1, text.index("mg") + 2))
        self.assertEqual(GR.scan("Cmax = 13.")[0][0], len("Cmax = 1"))
        cut = GR.scan("Cmax = {{call_2.cm")
        self.assertEqual([(a, b) for a, b, _ in cut], [(18, 18)]); self.assertTrue(cut[0][2])          # a prefix that cannot end
        self.assertEqual(GR.scan("Cmax = " + REF + "."), [])

    # what gate v2 passes and the grammar refuses, on purpose
    STRICTER = (
        ("**Cmax** {{call_2.cmax}}", "emphasis next to a value"), ("Cmax = *{{call_2.cmax}}*.", "emphasis next to a value"), ("- **{{call_2.cmax}}**", "emphasis next to a value"),
        ("_{{call_2.cmax}}_", "emphasis next to a value"), ("`{{call_2.cmax}}`", "emphasis next to a value"), ("{{call_2.cmax}} *(observée)*", "emphasis next to a value"),
        ("{{call_2.cmax}} **au pic**", "emphasis next to a value"), ("1. {{call_2.cmax}}", "no digit but a closed label, a typed number, a reference"),
        ("_{{call_2.cmax}}", "emphasis next to a value"), ("*{{call_2.cmax}}", "emphasis next to a value"), ("**{{call_2.cmax}}", "emphasis next to a value"),
        ("`{{call_2.cmax}}", "emphasis next to a value"), ("~~{{call_2.cmax}}", "emphasis next to a value"), ("Cmax = _{{call_2.cmax}}", "emphasis next to a value"),
        ("texte\n*{{call_2.cmax}}", "emphasis next to a value"),
        ("il y a 5 points", "small integers"), ("les 3 derniers points", "small integers"), ("2 demi-vies", "small integers"), ("1 sujet", "small integers"), ("A²", "a numeral glued to a letter"),
        ("λz en h⁻¹", "superscripts and subscripts are digits"), ("AUC (h²·ng/mL)", "superscripts and subscripts are digits"), ("10⁻³ près", "superscripts and subscripts are digits"),
        ("analyse 12", "an identifier the tool results do not carry"), ("{{call_2.cmax}} (les valeurs)", "a word that starts like a unit after a parenthesis"),
        ("{{call_2.cmax}} minimum", "a word that starts with a complete unit"), ("{{call_2.cmax}} la dose", "a word that starts with a complete unit"),
        ("{{call_2.cmax}} hors norme", "a word that starts with a complete unit"), ("{{call_2.cmax}} gagné", "a word that starts with a complete unit"),
        ("{{call_2.cmax}} Mm", "a word that starts with a complete unit"), ("{{call_2.cmax}}Moyenne", "a word that starts with a complete unit"),
        ("{{call2.cmax}}", "an alias spelling of a reference"), ("{{ call_2.cmax }}", "an alias spelling of a reference"), ("{{call_2.cmax}} (2 ou 4)", "small integers"),
        ("pour 1/h", "a digit-first label outside parentheses"),
    )

    def test_stricter_than_gate_v2(self):
        for t, why in self.STRICTER:
            with self.subTest(t, why=why):
                self.assertFalse(GR.accepts(t))
                self.assertEqual(kinds(t), [])

    # what the grammar does not look at: gate v2 keeps those findings, the benchmark counts them (the docstring of gate_v3.py)
    GAPS = (
        ("Cmax = negative {{call_2.cmax}}", "adjacent_to_reference", "a sign written in words"), ("Cmax = moins {{call_2.cmax}}", "adjacent_to_reference", "a sign written in words"),
        ("La Cmax en mg/L vaut {{call_2.cmax}}.", "contradictory_unit", "a contradictory unit"), ("Cmax (mg/L) : {{call_2.cmax}}", "contradictory_unit", "a contradictory unit"),
        ("| Cmax | {{call_2.cmax}} | mg/L |", "contradictory_unit", "a unit in a table cell"), ("La demi-vie est quinze heures.", "number_word", "numbers spelled out"),
        ("Cmax = douze virgule trois", "number_word", "numbers spelled out"), ("one hour later", "number_word", "numbers spelled out"),
    )

    def test_documented_gaps(self):
        for t, kind, why in self.GAPS:
            with self.subTest(t, why=why):
                self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertIn(kind, kinds(t, users=()))

    def test_the_helper_that_explains_digits_is_not_vacuous(self):
        for t in ("dose 12 mg", "analyse 70", "{{call_2.cmaxx}}", "Cmax 98", "R3", "{ }", "t1/2 5"): self.assertFalse(explained(t, GR), t)
        for t in ("dose 100 mg", "Cmax {{call_2.cmax}}", "R² = 0,5", "Sujet 24", "C0Sujet 24"): self.assertTrue(explained(t, GR), t)     # "Sujet 24": a word and the user's 24


# ================================================================ mutation families (TestRedTeamMutations style)
def unit_strings():
    """Every string gate v2 reads as a unit: the words in every case (re.IGNORECASE), the atoms in theirs, and some compound units."""
    words = [w for w in gate_v3.UNIT_WORDS if w != "fold"]
    out = words + [w.upper() for w in words] + [w.title() for w in words] + list(gate_v3.UNIT_ATOMS)
    out += ["mg/L", "ng/mL", "h*ng/mL", MICRO_SIGN + "g/mL", GREEK_MU + "g/mL", "L/h", "mL/min/kg", "1/h", "(ng/mL)", "°C", "‰", "mg·h/L", "mg.h/L", "g/L", "IU", "pg/mL", "h^-1"]
    return list(dict.fromkeys(out))


class TestMutations(unittest.TestCase):
    """Each family changes a sentence the grammar accepts in one way gate v2 finds, or the red team of 2026-10-19 found, and expects
    the grammar to refuse every mutant; gate v2 is asked too, and whatever it flags the grammar must refuse."""

    TEMPLATES = ("La Cmax vaut {r}{x}.", "Cmax = {r}{x}", "- Cmax : {r}{x}", "| Cmax | {r}{x} |", "Cmax ({r}{x})", "{r}{x}",
                 "Résultats :\n* Cmax : {r}{x}\n* Tmax : {{{{call_2.tmax}}}}", "**Cmax** : {r}{x} ; Tmax = {{{{call_2.tmax}}}}")
    BEFORE = ("La Cmax vaut {x}{r}.", "Cmax = {x}{r}", "- Cmax : {x}{r}", "| Cmax | {x}{r} |", "Cmax ({x}{r})", "Cmax = {{{{call_2.tmax}}}}, {x}{r}")
    SEPARATORS = ("", " ", "\t", NBSP, NNBSP, THIN, FIGURE)

    def refused_and_found(self, texts):
        """Asserts that the grammar refuses each text and that nothing gate v2 flags escapes it; returns how many gate v2 flags."""
        n = 0
        for t in texts:
            with self.subTest(t):
                self.assertFalse(GR.accepts(t))
                n += flagged(t)
        return n

    def test_templates_are_clean(self):
        for tpl in self.TEMPLATES + self.BEFORE:
            t = tpl.format(r=REF, x="")
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])

    def test_a_unit_after_a_reference_is_refused_whatever_the_blank_and_the_case(self):
        units = unit_strings()
        self.assertGreater(len(units), 250)
        texts = [tpl.format(r=REF, x=sep + u) for u in units for sep in self.SEPARATORS for tpl in (self.TEMPLATES[1], self.TEMPLATES[5], self.TEMPLATES[2])]
        n = self.refused_and_found(texts[::7] + [tpl.format(r=REF, x=sep + u) for u in units[:80] for sep in ("", " ") for tpl in self.TEMPLATES])
        self.assertGreater(n, 400)                                                   # and they are real findings of gate v2
        for u in ("mg/L", "ng/mL", "h", "min", "%", "heures", MICRO_SIGN + "g", "fois", "L/h"):
            for sep in ("", " "): self.assertIn("adjacent_to_reference", kinds(self.TEMPLATES[1].format(r=REF, x=sep + u)))

    def test_every_unit_after_a_reference_is_refused(self):
        for u in unit_strings():
            for sep in self.SEPARATORS:
                t = f"Cmax = {REF}{sep}{u}"
                self.assertFalse(GR.accepts(t), t)
                self.assertFalse(GR.accepts(t + "."), t)
                self.assertFalse(GR.accepts(t + " suite"), t)

    def test_what_looks_like_a_unit_but_is_none_is_not_refused(self):
        for u in ("iu", "khz", "km", "m", "mm", "nm", "pm", "u", "°c", "Kg", "KG", "Kmol", "ms", "cm", "kg", "Xh"):     # gate v2 does not read these as units
            for sep in ("", " "):
                t = f"Cmax = {REF}{sep}{u}"
                if flagged(t): continue                                              # (none of them is, but the test follows gate v2)
                self.assertTrue(GR.accepts(t), (t, GR.scan(t)[:1]))

    def test_a_unit_word_cut_short_is_not_a_unit(self):
        for w in ("et", "de", "du", "des", "dans", "sur", "soit", "selon", "sous", "sont", "contre", "ou", "par", "pour", "pour une", "avec", "environ", "observée", "mais",
                  "maximum", "pourtant", "sec", "de plus", "ensuite", "alors", "puis", "u", "bien", "entre", "pendant", "vers", "chez", "sans", "après", "à", "en", "ni"):
            t = f"Cmax = {REF} {w}"
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])

    def test_punctuation_after_a_reference_is_free(self):
        for x in (",", ".", ";", ":", ")", "]", "|", " |", "!", "?", "…", " —", " –", " →", "\n", "\n\n", "\n- Tmax : {{call_2.tmax}}", ", puis", " ;", " (observée)"):
            t = f"Cmax = {REF}{x}"
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])

    SUFFIXES = ("0", "1", "5", "9", "10", ".5", ",5", "e3", "E-3", "e+3", " x 10", " × 10", "×10", "x10", "*10", " * 10", "/2", " / 2", "^2", "÷3", "+5", "-5", " - 5",
                " + 5", " -5", " (x 2)", "{{call_2.tmax}}", " x{{call_2.tmax}}", " × {{call_2.tmax}}", " + {{call_2.tmax}}", " - {{call_2.tmax}}", ")*(", " ) × (", "²", "⁹", "₂",
                " ± 5", " +/- 5", "%", " %", " ‰", "°C", " fois", " times",
                "e-{{call_2.tmax}}", "e+{{call_2.tmax}}", " e-{{call_2.tmax}}", " - (", " + (", " x (", " × (", "-(")

    def test_a_digit_an_operator_a_sign_or_a_second_reference_after_a_reference_is_refused(self):
        n = self.refused_and_found([tpl.format(r=REF, x=x) for x in self.SUFFIXES for tpl in (self.TEMPLATES[1], self.TEMPLATES[5], self.TEMPLATES[0], self.TEMPLATES[3])])
        self.assertGreater(n, 120)

    def test_what_gate_v2_reads_as_fine_after_a_reference_stays_accepted(self):
        for x in ("-fold", " ± 0,5", " ± 6", "-", " –", "/", " /"):
            t = self.TEMPLATES[1].format(r=REF, x=x)
            if x in ("/", " /"): continue                                           # an operator for gate v2 only when a digit, a reference or "(" follows
            with self.subTest(t): self.assertEqual(kinds(t), []); self.assertTrue(GR.accepts(t), GR.scan(t)[:1])

    def test_an_operator_after_a_reference(self):
        self.refused_and_found([f"Cmax = {REF} / 2", f"Cmax = {REF}/{{{{call_2.tmax}}}}", f"Cmax = ({REF} + 1)", f"Cmax = {REF} × {{{{call_2.tmax}}}}", f"({REF}) × 2",
                                f"({REF}) x ({{{{call_2.tmax}}}})", f"{REF}*{REF}", f"{REF}^{REF}"])

    PREFIXES = ("2", "2 ", "2x", "2 x ", "2 × ", "10*", "1/", "3-", "-", "- ", "+", "−", "+ ", "× ", "x ", "(1+", "0.5 ", "1,5", "1 000 ", "- 1 ", "0,", "1.", "12 ", "5 × 10^",
                "10^", "÷", "/", "× 2 × ", "e", "1e", "x2 ", "² ", "₂")

    def test_a_digit_an_operator_or_a_sign_before_a_reference_is_refused(self):
        # "x " and "e" before a reference are letters (a word that ends with x): the neighbours below; the rest is a digit, an operator or a sign
        texts = [tpl.format(r=REF, x=p) for p in self.PREFIXES if p not in ("x ", "e") for tpl in self.BEFORE]
        n = self.refused_and_found(texts)
        self.assertGreater(n, 100)

    def test_a_letter_before_a_reference_is_prose(self):
        for p in ("x ", "e", "ex", "Cmax e ", "le ", "à ", "de "):
            t = self.BEFORE[1].format(r=REF, x=p)
            with self.subTest(t): self.assertEqual(kinds(t), []); self.assertTrue(GR.accepts(t), GR.scan(t)[:1])

    def test_a_sign_through_any_emphasis_is_refused(self):
        for w in ("**", "*", "_", "__", "`", "***", "~~"):
            for sign in ("-", "−", "+"):
                for t in (f"Cmax = {sign}{w}{REF}{w}", f"Cmax = {w}{sign}{REF}{w}", f"Cmax = {sign} {w}{REF}{w}", f"Cmax : {sign}{w}{REF}{w}", f"({sign}{w}{REF}{w})"):
                    with self.subTest(t): self.assertFalse(GR.accepts(t)); self.assertIn("adjacent_to_reference", kinds(t))
            for t in (f"{REF}{w} mg/L", f"{w}{REF}{w} × 10", f"{REF} {w}mg/L{w}"):
                with self.subTest(t): self.assertFalse(GR.accepts(t)); self.assertIn("adjacent_to_reference", kinds(t))
            with self.subTest(w=w): self.assertFalse(GR.accepts(f"Cmax = {w}{REF}{w}")); self.assertEqual(kinds(f"Cmax = {w}{REF}{w}"), [])   # stricter than v2

    def test_a_list_bullet_may_be_a_minus_for_gate_v2(self):
        # gate v2 reads ")" newline "- (" as a subtraction of two parentheses, so a "(" may not follow a bullet
        n = self.refused_and_found([f"(a)\n{b} ({REF})" for b in "-*+"] + [f"texte)\n{b} ({REF}" for b in "-*+"] + [f"(a)\n{b}({REF})" for b in "-+"])
        self.assertGreater(n, 5)
        for t in ("(a)\n- observée", f"(a)\n- Cmax {REF}", f"- {REF}\n- {REF}", f"(a)\n- {REF}"):
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])
        self.assertFalse(GR.accepts("- (observée)"))                                  # stricter than v2: no "(" after a bullet, whatever precedes

    def test_a_label_that_ends_with_a_digit_takes_no_operator_sign_or_reference(self):
        # C0, t1/2: the digit is the last thing gate v2 sees before an operator, a sign or a reference
        tails = ("×{r}", " × {r}", "/{r}", " / {r}", " ^ {r}", " + {r}", " - {r}", " − {r}", "−{r}", "{r}", " {r}", "-{r}", "+{r}")
        n = self.refused_and_found([f"{label}{tail.format(r=REF)}" for label in ("C0", "c0", "t1/2", "T1/2") for tail in tails])
        self.assertGreater(n, 40)
        for t in ("C0 = " + REF, "C0 : " + REF, "(C0) " + REF, "C0, " + REF, "C0 (" + REF + ")", "t1/2 = " + REF + " et C0 = " + REF):
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])

    def test_an_identifier_takes_no_operator_sign_or_emphasis_before_a_reference(self):
        # the 7 of "analyse 7" is a digit before the operator: gate v2 flags the reference that follows
        heads = ("analyse 7", "Sujet 1", "worksheet 4")
        tails = ("*{r}", " *{r}", "_{r}", " _{r}", "~{r}", " ~{r}", "`{r}", " `{r}", "-{r}", "−{r}", " − {r}", " - {r}", " + {r}", "+{r}", "×{r}", " × {r}", "/{r}", " x {r}", "{r}", ".{r}")
        n = self.refused_and_found([h + tail.format(r=REF) for h in heads for tail in tails])
        self.assertGreater(n, 30)
        for t in (f"analyse 7 : {REF}", f"analyse 7, {REF}", f"analyse 7 ({REF})", f"analyse 7 — {REF}", f"analyse 7 – {REF}"):
            with self.subTest(t): self.assertTrue(GR.accepts(t), GR.scan(t)[:1]); self.assertEqual(kinds(t), [])

    def test_an_identifier_is_not_glued_to_a_pk_label(self):
        # "AUC.analyse 7" is one token for gate v2 (auc[\w.]*): the 7 is then no longer an identifier
        self.refused_and_found(["AUC.analyse 7", "AUC_analyse 7", "AUC_sujet 1", "AUC.sujet 1", "AUC.worksheet 4", "AUC0analyse 7", "AUCanalyse 7"])
        for t in ("AUC analyse 7", "Cmax analyse 7", "AUC(0-tlast) analyse 7", "t½ analyse 7", "tlast analyse 7"):
            with self.subTest(t): self.assertTrue(GR.accepts(t)); self.assertEqual(kinds(t), [])

    def test_a_multiplication_sign_at_the_start_of_a_line_follows_the_digit_before_it(self):
        # gate v2 looks through newlines: "100" newline "x {{ref}}" is 100 x {{ref}}
        n = self.refused_and_found([f"dose 100\nx {REF}", f"{{{{call_2.tmax}}}}\nx {REF}", f"(a)\n× {REF}", f"dose 100\n× {REF}", f"(100)\nx {REF}"])
        self.assertGreater(n, 3)
        self.assertTrue(GR.accepts(f"dose 100 mg\nx {REF}")); self.assertEqual(kinds(f"dose 100 mg\nx {REF}"), [])

    def test_a_reference_the_tables_do_not_know_is_refused(self):
        bodies = ("call_9.cmax", "call_2.cmaxx", "call_2.cmax2", "call_2.subject=2.cmax", "cmax", "call_2.result.subjects[0].dose", "call_2.name", "call_2.label",
                  "call_4.cmax.unit_a", "convention.nothing", "call_3.cmax", "call_1.cmax", "call_2.lambda_z.lambda_z.x", "call_2.tmax.unit",
                  "call_4.cmax.difference_unit", "call_2", "call_2.", "call_2.cmax}}{{call_2.tmax")
        for b in bodies:
            for tpl in ("{r}", "Cmax = {r}.", "- {r}", "| Cmax | {r} |"):
                t = tpl.format(r="{{" + b + "}}")
                with self.subTest(t): self.assertFalse(GR.accepts(t)); self.assertNotEqual(kinds(t), [])

    def test_a_reference_cut_in_the_middle_cannot_stop(self):
        for ref in (REF, "{{call_3.subject=2.cmax}}", "{{convention.min_points}}", "{{call_4.auclast.difference}}"):
            for k in range(1, len(ref)):
                with self.subTest(ref[:k]): self.assertFalse(GR.accepts("Cmax = " + ref[:k]))
            self.assertTrue(GR.accepts("Cmax = " + ref), ref)

    def test_a_typed_number_is_copied_exactly(self):
        for n in GR.vocab.numbers:
            if len(n) > 12: continue
            with self.subTest(n):
                self.assertTrue(GR.accepts(f"dose {n} mg"), n)
                for glue in ("0", "5", ".5", ",5", "e3", "x10", " x 10", " × 10", "²", " fois 2"):
                    self.assertFalse(GR.accepts(f"dose {n}{glue} mg"), n + glue)
                self.assertFalse(GR.accepts(f"dose 7{n} mg"), n)
                self.assertFalse(GR.accepts(f"dose {n} 7 mg"), n)

    def test_typed_numbers_cannot_be_assembled_into_one_the_user_did_not_type(self):
        # gate v2 reads "100 x 10^3" and "100e3" as one number (1e5); the user typed 100, 10 and 3 but not that one
        users = ["dose 100 mg, puis 10 et 3 et 500 et 2"]
        gr = gate_v3.build({}, users, None)
        for t in ("dose 100 x 10^3", "dose 100 x 10**3", "dose 100 x 10 ^ 3", "dose 100 × 10^3", "dose 100 * 10^3", "dose 100·10^3", "dose 100 x 10^-3", "dose 100 x 10^(3)",
                  "dose 100 x 10 3", "dose 100e3", "dose 100E3", "dose 100e-3", "dose 100 e 3", "dose 100 e3", "dose 10 3", "dose 100 500", "dose 100  500", "dose 100 500",
                  "dose 100.500", "dose 100,500", "dose 100 + 10", "dose 100 - 3", "dose 100 / 2", "dose 100×10", "dose 10^3", "dose 10 ^ 3"):
            with self.subTest(t): self.assertFalse(gr.accepts(t))
        for t in ("dose 100 mg, puis 10 et 3", "dose 100 mg puis 10 mg et 3 mg", "100, 10, 3", "100; 10; 3", "(100) puis (10)", "100 x : voir", "100 e : voir"):
            with self.subTest(t): self.assertTrue(gr.accepts(t), (t, gr.scan(t)[:1])); self.assertEqual(gate_v2.check(t, {}, users, None)["findings"], [])
        walks = random.Random(4)
        for _ in range(1500):
            t = walk(gr.machine, walks)
            if t: self.assertEqual([f["kind"] for f in gate_v2.check(t, {}, users, None)["findings"] if f["kind"] in COVERED], [], t)

    def test_a_digit_that_is_none_of_the_three_is_refused_wherever_it_stands(self):
        # the sentences of GOOD with each digit run or reference replaced by something the grammar does not offer
        for t in GOOD:
            for m in re.finditer(r"\{\{[^{}]*\}\}|[0-9][0-9.,]*", t):
                for rep in ("37", "1.5e3", "12,3456", "{{call_2.cmax}}9", "{{call_2.cmaxx}}", "{{call_2.cmax"):
                    u = t[:m.start()] + rep + t[m.end():]
                    with self.subTest(u): self.assertFalse(GR.accepts(u))


# ================================================================ soundness: random walks
FRAGMENTS = ["{{call_2.cmax}}", "{{call_2.tmax}}", "{{call_3.subject=2.cmax}}", "{{call_2.lambda_z.adj_r_squared}}", "{{call_4.auclast.difference}}", "{{convention.min_points}}",
             "{{call_2.thresholds.max_extrapolated_percent}}",
             " ", "  ", "\t", "\n", "\n- ", "\n* ", "- ", "* ", "**", "*", "_", "`", "~", "(", ")", ") (", "[", "]", "|", " | ", ": ", ":", " = ", "=", ", ", ",", ".", ". ",
             "-", " - ", "−", "+", " + ", "×", " × ", "x", " x ", "X", "/", " / ", "^", "÷", "·", "e", "E", "e3", "e-3",
             "%", " %", "‰", " h", "h", " min", "min", " mg", "mg", " ng/mL", " " + MICRO_SIGN + "g", MICRO_SIGN, "L", " L/h", "mol", " fois", " times", " fold", "-fold", " pour cent", " pourcent",
             " d", " de", " dépasse", " s", " sur", " seconde", "second", "secondes", " heures", " jours", " ml", " mL", " g/L",
             "100", "0.5", "4.2", "12.35", "6", "24", "0,9", "150", "7", "3", "1", "0", "20", "10", "500", "2", "R²", "r²", "t½", "t1/2", "C0", "c0", "AUC(0-tlast)", "AUC(0–inf)", "1/h", "1/min",
             "analyse 7", "analyse 8", "sujet 1", "Sujet 2", "worksheet 4", "analyse", "sujet", " point", " points", "demi-vie", "un", "une", "deux", "quinze",
             "mais", "Cmax", "AUC", "le ", "la ", "et ", "est ", "à ", GREEK_MU + "g", "é", "è", "É", "💊", "→", "–", "—", "≈", "≥", "≤", "<", ">", "#", "!", "?", ";", "'", "’", "\"", "«", "»"]
CHARS = [chr(c) for c in range(32, 127)] + list("éèàçù" + MICRO_SIGN + GREEK_MU + "°‰×÷·−–—→λ½²")

def walk(machine, rng, maxsteps=14):
    """A random text the machine accepts: fragments (80 %) and single characters, each kept when the machine does not die on it."""
    state, text = machine.start, ""
    for _ in range(maxsteps):
        f = rng.choice(FRAGMENTS) if rng.random() < 0.8 else rng.choice(CHARS)
        st = state
        for ch in f:
            st = machine.step(st, ch)
            if not st: break
        else: state, text = st, text + f
    for tail in ("", ".", " fin.", "\n", " ", "a"):                                 # close the text: some endings
        st = state
        for ch in tail: st = machine.step(st, ch)
        if st and machine.accepting(st): return text + tail
    return None


class TestSoundness(unittest.TestCase):
    def check_walks(self, gr, calls, users, n, seed):
        rng, m = random.Random(seed), gr.machine
        done = 0
        for _ in range(n):
            t = walk(m, rng)
            if t is None: continue
            done += 1
            self.assertTrue(gr.accepts(t), t)
            self.assertTrue(explained(t, gr), t)
            res = gate_v2.check(t, calls, list(users), SCHEMAS, ".")
            bad = [(f["kind"], f["reason"]) for f in res["findings"] if f["kind"] in COVERED]
            self.assertEqual(bad, [], t)
        self.assertGreater(done, n // 3)

    def test_what_the_grammar_accepts_has_no_covered_finding_and_no_free_digit(self):
        self.check_walks(GR, CALLS, [USER], 2500, 20261023)

    def test_the_same_with_one_analysis_only(self):
        calls = {k: CALLS[k] for k in ("call_1", "call_2")}
        self.check_walks(gate_v3.build(calls, [USER], SCHEMAS), calls, [USER], 800, 1)

    def test_the_same_with_a_comparison_and_no_user_numbers(self):
        calls = {k: CALLS[k] for k in ("call_2", "call_4", "call_5")}
        self.check_walks(gate_v3.build(calls, ["compare"], SCHEMAS), calls, ["compare"], 800, 2)

    def test_the_same_without_identifiers(self):
        self.check_walks(gate_v3.build(CALLS, [USER], SCHEMAS, idents=False), CALLS, [USER], 800, 3)

    def test_the_walk_is_not_vacuous(self):
        rng, seen = random.Random(5), set()
        for _ in range(400):
            t = walk(GR.machine, rng)
            if not t: continue
            if "{{" in t: seen.add("ref")
            if any(lab in t for lab in gate_v3.LABELS): seen.add("label")
            if any(n in t for n in GR.vocab.numbers if len(n) > 1): seen.add("number")
            if any(i in t for i in GR.vocab.idents): seen.add("ident")
        self.assertEqual(seen, {"ref", "label", "number", "ident"})


# ================================================================ the printed grammar
class TestGrammarText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = gbnf_reader.Reader(GR.gbnf)

    def test_the_text_is_ascii_one_rule_per_line_and_llama_cpp_names(self):
        self.assertTrue(GR.gbnf.isascii()); self.assertTrue(GR.gbnf.endswith("\n"))
        lines = GR.gbnf.split("\n")[:-1]
        self.assertEqual(len(lines), len(GR.rules))
        for ln, name in zip(lines, GR.rules):
            self.assertTrue(re.fullmatch(r"[a-zA-Z0-9-]+", name), name); self.assertTrue(ln.startswith(name + " ::= "), ln[:40])
        self.assertIn("root", GR.rules)
        self.assertNotIn("#", re.sub(r'"(?:[^"\\]|\\.)*"|\[(?:[^\]\\]|\\.)*\]', "", GR.gbnf))      # a comment marker outside the literals and the classes

    def test_the_reader_parses_every_rule(self):
        self.assertEqual(list(self.reader.rules), list(GR.rules))

    def test_every_rule_is_productive(self):
        self.assertEqual(self.reader.productive(), set(self.reader.rules))

    def test_no_left_recursion(self):
        gate_v3.Machine(GR.rules)                                                   # raises on left recursion, also through nullable rules

    def test_the_reader_and_the_stack_engine_agree_prefix_by_prefix(self):
        texts = ["Cmax = {{call_2.cmax}}.", "Cmax = {{call_2.cmax}} mg", "La dose est 100 mg.", "R² = {{call_2.r.squared}}", "x1", "analyse 7 :", "Cmax = {{call_2.cmax}} h",
                 "Cmax {{call_2.cmax}}x", "- {{call_2.cmax}}\n* {{call_2.tmax}}", "AUC(0-tlast) = {{call_2.auclast}} (1/h)", "t1/2 %", "t1/2 = {{call_2.half.life}}", "pour cent",
                 "{{call_2.cmax}} pour cent", "{{call_2.cmax}} per cent", "{{call_2.cmax}} pourtant", "{{call_2.cmax}} d", "{{call_2.cmax}} de", "Cmax = {{call_2.cmax", "dose 12,3",
                 "dose 0,5 puis 4.2 h", "💊 {{call_2.cmax}} → ok", "{{call_2.cmax}}" + NNBSP + "mg", "sujet 1 et analyse 8", "(1/h)", "AUC₀₋∞ {{call_2.aucinf.obs}}", "{{convention.min_points}}"]
        rng = random.Random(9)
        for _ in range(20):
            t = walk(GR.machine, rng)
            if t: texts.append(t)
        for _ in range(15):                                                         # and mutants of them
            t = list(rng.choice(texts)); i = rng.randrange(len(t) + 1)
            t.insert(i, rng.choice(CHARS + ["{", "}", "1", "²"])); texts.append("".join(t))
        m = GR.machine
        for t in texts:
            got, st = self.reader.run(t), m.start
            want = [(True, m.accepting(st))]
            for ch in t:
                st = m.step(st, ch)
                want.append((bool(st), bool(st) and m.accepting(st)))
            with self.subTest(t): self.assertEqual(got, want)

    def test_escapes_round_trip_through_the_reader(self):
        chars = ['"', "\\", "[", "]", "-", "^", "#", "{", "}", "\n", "\t", NBSP, "é", MICRO_SIGN, "😀", "\x7f", "|", " ", "'", ":", "=", "<", ">", "*", "(", ")"]
        text = gate_v3.rule_line("root", [[("l", "".join(chars))], [("c", CS.of("".join(chars)))]]) + "\n"
        self.assertTrue(text.isascii())
        rules = gbnf_reader.parse(text)
        self.assertEqual([lo for _, [(lo, hi)] in rules["root"][0]], [ord(c) for c in chars])
        self.assertEqual({cp for _, ranges in rules["root"][1] for lo, hi in ranges for cp in range(lo, hi + 1)}, {ord(c) for c in chars})
        rd = gbnf_reader.Reader(text)
        self.assertTrue(rd.accepts("".join(chars))); self.assertTrue(all(rd.accepts(c) for c in chars)); self.assertFalse(rd.accepts("a"))

    def test_the_reader_rejects_what_llama_cpp_rejects(self):
        for bad in ('root ::= "a" b', 'root ::= "\\q"', 'root ::= [^a]', 'root ::= [\\-]', 'x ::= "a"', 'root ::= "a"\nroot ::= "b"', 'root ::= [a'):
            with self.subTest(bad), self.assertRaises((gbnf_reader.GBNFError, IndexError)): gbnf_reader.parse(bad + "\n")

    def test_the_grammar_of_a_busy_chat_stays_within_a_budget(self):
        users = [USER, "Et avec " + ", ".join(f"{i}.{i}" for i in range(1, 60)) + " ?"]
        gr = gate_v3.build(CALLS, users, SCHEMAS)
        self.assertLess(gr.stats["rules"], 1500); self.assertLess(gr.stats["bytes"], 250_000)
        self.assertTrue(gr.accepts("avec 3.3 puis 17.17"))
        gr0 = gate_v3.build({}, [], None)
        self.assertLess(gr0.stats["rules"], gr.stats["rules"])


class TestMachine(unittest.TestCase):
    """The stack engine on small grammars, against what src/llama-grammar.cpp does (accepting means an empty stack exists)."""
    def accepts(self, rules, text, root="root"):
        m = gate_v3.Machine(rules, root)
        st = m.start
        for ch in text:
            st = m.step(st, ch)
            if not st: return False
        return m.accepting(st)

    def test_sequences_alternatives_and_the_empty_alternative(self):
        rules = {"root": [[("l", "a"), ("r", "b")]], "b": [[("l", "b")], [("l", "")]]}
        for t, want in (("a", True), ("ab", True), ("", False), ("b", False), ("abb", False), ("aa", False)): self.assertEqual(self.accepts(rules, t), want, t)
        self.assertTrue(self.accepts({"root": [[("l", "x")], []]}, "")); self.assertTrue(self.accepts({"root": [[("l", "x")], []]}, "x"))

    def test_classes_and_nested_rules(self):
        rules = {"root": [[("c", CS(((97, 99), (120, 122)))), ("r", "tail")]], "tail": [[("c", CS(((48, 57),))), ("r", "tail")], [("l", ".")]]}
        for t, want in (("a.", True), ("c12.", True), ("z9999.", True), ("d.", False), ("a", False), ("a1", False), ("a.1", False), ("xx.", False)): self.assertEqual(self.accepts(rules, t), want, t)

    def test_a_dead_character_empties_the_state_and_a_prefix_is_alive(self):
        m = gate_v3.Machine({"root": [[("l", "abc")]]})
        st = m.step(m.start, "a"); self.assertTrue(st); self.assertFalse(m.accepting(st))
        self.assertEqual(m.step(st, "x"), frozenset()); self.assertEqual(m.allowed(st), CS.of("b"))

    def test_left_recursion_is_refused_directly_and_through_a_nullable_rule(self):
        for rules in ({"root": [[("r", "root"), ("l", "a")], [("l", "a")]]}, {"root": [[("r", "n"), ("r", "root")], [("l", "a")]], "n": [[("l", "")]]},
                      {"root": [[("r", "a")]], "a": [[("r", "b"), ("l", "x")]], "b": [[("r", "root")]]}):
            with self.assertRaises(ValueError): gate_v3.Machine(rules)
        gate_v3.Machine({"root": [[("l", "a"), ("r", "root")], [("l", "a")]]})       # right recursion is fine

    def test_an_undefined_rule_is_refused(self):
        with self.assertRaises(ValueError): gate_v3.Machine({"root": [[("r", "nowhere")]]})

    def test_the_stacks_of_an_ambiguous_grammar_are_all_followed(self):
        rules = {"root": [[("r", "a"), ("l", "z")], [("r", "b"), ("l", "y")]], "a": [[("l", "xx")]], "b": [[("l", "x"), ("r", "c")]], "c": [[("l", "x")]]}
        self.assertTrue(self.accepts(rules, "xxz")); self.assertTrue(self.accepts(rules, "xxy")); self.assertFalse(self.accepts(rules, "xxx"))


class TestSampling(unittest.TestCase):
    """A token is a string the sampler offers; llama.cpp accepts it when the stacks survive every one of its code points."""
    def feed(self, tokens):
        """None when every token survives, else the index of the first token the grammar rejects."""
        m, st = GR.machine, GR.machine.start
        for i, tok in enumerate(tokens):
            for ch in tok:
                st = m.step(st, ch)
                if not st: return i
        return None

    AFTER_A_REFERENCE = ["Cmax = ", "{{", "call", "_", "2", ".", "cmax", "}}"]

    def test_a_unit_token_after_a_reference_is_refused_by_the_token_itself(self):
        for tok in (" mg", " %", " h", " L", " min", " ng", "mg", "%", "h", " heures", " fois", " " + MICRO_SIGN + "g", " ml", " mL", " °C", ".5", "2"):
            with self.subTest(tok): self.assertEqual(self.feed(self.AFTER_A_REFERENCE + [tok]), len(self.AFTER_A_REFERENCE))
        for tok in (" et", ",", ".", " de", " du", " (", " soit", " :", "\n", " |"):
            with self.subTest(tok): self.assertIsNone(self.feed(self.AFTER_A_REFERENCE + [tok]))

    def test_a_reference_may_be_cut_into_tokens_that_carry_digits(self):
        self.assertIsNone(self.feed(["La Cmax vaut ", "{{", "call_", "2", ".", "cm", "ax", "}}", "."]))
        self.assertEqual(self.feed(["La Cmax vaut ", "{{", "call_", "3", ".", "cm"]), 5)         # call_3 has several subjects: ".cm" is not offered

    def test_a_digit_token_is_refused_outside_a_reference_a_label_and_a_typed_number(self):
        for tok in ("1", "12", " 3", " 7.5", "²"):
            with self.subTest(tok): self.assertEqual(self.feed(["La dose est", tok]), 1)
        self.assertIsNone(self.feed(["La dose est", " 100", " mg"]))
        self.assertEqual(self.feed(["La dose est", " 10", "1"]), 2)

    def test_a_token_that_starts_like_a_unit_but_goes_on_is_alive(self):
        # "d" and "s" are the first letters of de, du, dans, sur, sous, soit, sont, selon (UNIT_ALIVE); "m", "p", "u", "n" begin units and words
        for tok in (" de", " d", " dans", " s", " sur", " m", " mais", " p", " pour", " u", " n", " ni", " pourcent"[:5]):
            with self.subTest(tok): self.assertIsNone(self.feed(["Cmax = ", "{{call_2.cmax}}", tok]))
        self.assertEqual(self.feed(["Cmax = ", "{{call_2.cmax}}", " d", "."]), 3)               # the known residual: after a bare " d" only a letter goes on
        self.assertIsNone(self.feed(["Cmax = ", "{{call_2.cmax}}", " d", "e", " plus"]))


if __name__ == "__main__":
    unittest.main()
