"""Tests of the deterministic number gate (gate.py).

The tool results are the digests of the PUBLIC golden payloads (theoph subject 1, edge_blq...), the
answers are synthetic sentences written for the tests. The wrong sentences reproduce the kinds of
hallucination seen in the first demo (run 2 of 2026-10-08): CL/F and Vz/F multiplied by the dose and
by 10^3, differences and percentages computed by the model. The numbers of that private exercise are
not used anywhere.
"""
import json, os, sys, unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gate, apothicaire  # noqa: E402
import test_digest as td   # noqa: E402  (golden loading and the independent unit table)

def fr(x, sig=6, nbsp=False):
    """A French-formatted number: x at `sig` significant digits, decimal comma."""
    s = format(td.round6(x) if sig == 6 else _round(x, sig), "f")
    if "." in s: s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")

def _round(x, sig):
    d = Decimal(repr(x)); return d.quantize(Decimal(1).scaleb(d.adjusted() - sig + 1))

def tool_text(case):
    g = td.GOLDENS[case]
    units = {}
    apothicaire.render_tool_result("data_import", True, json.dumps(g["data_import_result"]), units)
    return apothicaire.render_tool_result("nca_run", True, json.dumps(g["nca_run_result"]), units)

def raw_value(case, pname, subject=0):
    ok = td.GOLDENS[case]["nca_run_result"]["result"]["subjects"][subject]["outcome"]["ok"]
    return next(p["value"]["value"] for p in ok["parameters"] if p["name"] == pname)

THEOPH = "theoph_s1_oral_dose_arg"
USER = ("Voici les données (320 mg par voie orale ; temps en h, concentration en mg/L) :\n"
        + td.GOLDENS[THEOPH]["calls"][0]["arguments"]["csv"] + "\nFais l'analyse non compartimentale.")

class Base(unittest.TestCase):
    def setUp(self):
        self.tool = tool_text(THEOPH)
        self.cmax = raw_value(THEOPH, "cmax"); self.auc = raw_value(THEOPH, "auclast")
        self.cl = raw_value(THEOPH, "cl.obs"); self.vz = raw_value(THEOPH, "vz.obs")
        self.hl = raw_value(THEOPH, "half.life"); self.pext = raw_value(THEOPH, "aucpext.obs")
        self.dose = td.GOLDENS[THEOPH]["calls"][1]["arguments"]["dose"]

    def run_gate(self, answer, extra_tools=(), users=(USER,)):
        return gate.check(answer, [self.tool, *extra_tools], list(users))

class TestQuotedValuesPass(Base):
    def test_every_parameter_quoted_verbatim_passes(self):
        d, _ = td.digest_of(td.GOLDENS[THEOPH])
        parts = []
        for k, v in d["subjects"][0]["parameters"].items():
            if isinstance(v, str):
                val, _, unit = v.partition(" ")
                parts.append(f"{k} = {val.replace('.', ',')} {unit}")           # French decimal comma, unit attached
            else: parts.append(f"{k} = {str(v).replace('.', ',')}")
        r = self.run_gate("Résultats : " + " ; ".join(parts) + ".")
        self.assertEqual(r["findings"], [])
        self.assertEqual(r["numbers_unverified"], 0)
        self.assertGreaterEqual(r["numbers_total"], len(parts) - 5)

    def test_english_decimal_point_and_french_comma_are_the_same(self):
        for text in (f"Cmax {self.cmax} mg/L", f"Cmax {str(self.cmax).replace('.', ',')} mg/L"):
            self.assertEqual(self.run_gate(text)["numbers_unverified"], 0, text)

    def test_rounding_to_the_digits_shown(self):
        x = self.pext
        for sig in (2, 3, 4, 5):
            with self.subTest(sig=sig):
                self.assertEqual(self.run_gate(f"extrapolé : {fr(x, sig)} %")["numbers_unverified"], 0)

    def test_wrong_last_digit_is_caught(self):
        x = _round(self.pext, 3)
        wrong = x + Decimal("0.01")
        r = self.run_gate(f"extrapolé : {str(wrong).replace('.', ',')} %")
        self.assertEqual(r["numbers_unverified"], 1)
        r = self.run_gate(f"extrapolé : {str(x - Decimal('0.01')).replace('.', ',')} %")
        self.assertEqual(r["numbers_unverified"], 1)

    def test_two_significant_digits_floor(self):
        # 6.98 -> '7,0' and '7' % are the value rounded to two digits; '7,1' and '6,9' are not
        self.assertEqual(gate.check("7,0 %", ['{"p": 6.98412}'])["numbers_unverified"], 0)
        self.assertEqual(gate.check("7 %", ['{"p": 6.98412}'])["numbers_unverified"], 0)
        self.assertEqual(gate.check("7,1 %", ['{"p": 6.98412}'])["numbers_unverified"], 1)
        self.assertEqual(gate.check("6,9 %", ['{"p": 6.98412}'])["numbers_unverified"], 1)
        self.assertEqual(gate.check("6,98 %", ['{"p": 6.98412}'])["numbers_unverified"], 0)
        self.assertEqual(gate.check("6,99 %", ['{"p": 6.98412}'])["numbers_unverified"], 1)

    def test_more_digits_than_the_tool_gave_must_equal_it(self):
        self.assertEqual(gate.check("5,50 mg/L", ['{"c": 5.5}'])["numbers_unverified"], 0)
        self.assertEqual(gate.check("5,51 mg/L", ['{"c": 5.5}'])["numbers_unverified"], 1)
        self.assertEqual(gate.check("5,5000001 mg/L", ['{"c": 5.5}'])["numbers_unverified"], 1)

    def test_sign_is_ignored(self):
        self.assertEqual(gate.check("variation de −2,5 mg/L", ['{"d": 2.5}'])["numbers_unverified"], 0)

class TestNumberFormats(unittest.TestCase):
    def ok(self, text, src='{"v": 3127.58}'):
        r = gate.check(text, [src]); self.assertEqual(r["numbers_unverified"], 0, (text, r["findings"])); return r
    def bad(self, text, src='{"v": 3127.58}'):
        r = gate.check(text, [src]); self.assertGreaterEqual(r["numbers_unverified"], 1, text); return r

    def test_thousands_separators(self):
        self.ok("3 127,58 h·mg/L")                  # French: space
        self.ok("3 127,58 h·mg/L")             # no-break space
        self.ok("3 127,58 h·mg/L")             # narrow no-break space
        self.ok("3,127.58 h·mg/L")                  # English
        self.ok("3.127,58 h·mg/L")                  # German/old French
        self.ok("3127,58 h·mg/L"); self.ok("3127.58")

    def test_wrong_with_separators(self):
        self.bad("3 127,59 h·mg/L"); self.bad("3 137,58 h·mg/L"); self.bad("31 275,8")

    def test_ambiguous_group_passes_if_either_reading_matches(self):
        self.ok("1,234 mg/L", '{"v": 1.234}')       # 1.234
        self.ok("1,234 mg/L", '{"v": 1234}')        # 1234
        self.bad("1,234 mg/L", '{"v": 1.5}')

    def test_scientific_notation(self):
        src = '{"k": 0.00271828}'
        self.ok("CL = 2.72e-3", src); self.ok("CL = 2,72e-3", src); self.ok("CL = 2,72E-3", src)
        self.ok("CL = 2,72 × 10^-3", src); self.ok("CL = 2,72 x 10^-3", src); self.ok("CL = 2,72 × 10⁻³", src)
        self.ok("CL = 2.71828e-3", src)
        self.bad("CL = 2,73e-3", src); self.bad("CL = 2,72 × 10^-2", src)
        self.ok("CL = 2.72e-3 L/h", '{"k": 2.71828e-3}')       # source in scientific notation too

    def test_percentages(self):
        self.ok("6,98 %", '{"p": 6.98412}'); self.ok("6,98%", '{"p": 6.98412}'); self.ok("6.98 %", '{"p": "6.98412 %"}')
        self.bad("7,97 %", '{"p": 6.98412}')

    def test_units_attached_are_read(self):
        nums = gate.extract_numbers("Cmax 10,5 mg/L, CL 0,00272 mg/(h·ng/mL), 3 127,58 h·ng/mL, 20 %, 13,8 h, 0,05 1/h")
        self.assertEqual([n.unit for n in nums], ["mg/L", "mg/(h·ng/mL)", "h·ng/mL", "%", "h", "", "/h"])
        self.assertEqual(nums[-1].exempt, "unit_fragment")          # the 1 of 1/h is part of the unit

    def test_words_after_a_number_are_not_units(self):
        nums = gate.extract_numbers("8 points, 3 sujets, 15 minutes et 2 doses, 4 d'entre eux")
        self.assertEqual([n.unit for n in nums], [""] * 5)

    def test_identifiers_are_not_numbers(self):
        r = gate.check("worksheet ex1, noeud n42, aucpext.obs, R2, Q4, pk1.iv_bolus, version 0.2.0", [])
        self.assertEqual(r["numbers_unverified"], 0)

    def test_csv_row_glued_by_commas_is_checked_as_its_parts(self):
        self.ok("12,205.3", '{"t": 12, "c": 205.3}')
        self.bad("12,205.4", '{"t": 12, "c": 205.3}')
        self.ok("10 250", '{"a": 10, "b": 250}')

    def test_positions_are_offsets_of_the_number(self):
        ans = "Cmax = 10,5 mg/L puis 99,9 mg/L"
        r = gate.check(ans, ['{"c": 10.5}'])
        f = r["findings"][0]
        self.assertEqual(ans[f["position"][0]:f["position"][1]], "99,9")
        self.assertEqual(f["number"], "99,9"); self.assertEqual(f["unit"], "mg/L"); self.assertEqual(f["line"], 1)

class TestUnitConversionsAreViolations(Base):
    """The six hallucinations of run 2 were conversions of CL/F and Vz/F; same shapes on public numbers."""
    def conversions(self):
        d = self.dose
        return {
            "CL x dose": self.cl * d,
            "CL x dose x 1000": self.cl * d * 1000,
            "Vz x dose": self.vz * d,
            "Vz x dose x 1000": self.vz * d * 1000,
            "CL x 1000": self.cl * 1000,
            "Vz / 1000": self.vz / 1000,
        }

    def test_each_conversion_is_caught(self):
        for label, v in self.conversions().items():
            with self.subTest(label):
                ans = f"CL/F = {fr(self.cl)} mg/(h·mg/L), soit {fr(v)} L/h."
                r = self.run_gate(ans)
                self.assertEqual(r["numbers_unverified"], 1, r["findings"])
                f = r["findings"][0]
                self.assertEqual(f["number"], fr(v))
                self.assertEqual(f["unit"], "L/h")
                self.assertIsNotNone(f["nearest_allowed"])

    def test_six_conversions_in_one_answer(self):
        conv = self.conversions()
        ans = ("Dose 319,992 mg. " + "; ".join(f"{fr(v)} unité-{i}" for i, v in enumerate(conv.values())) +
               f". Rappel : CL/F = {fr(self.cl)} dose unit/(h·mg/L).")
        r = self.run_gate(ans)
        self.assertEqual(r["numbers_unverified"], 6, [f["text"] for f in r["findings"]])
        self.assertEqual(sorted(f["number"] for f in r["findings"]), sorted(fr(v) for v in conv.values()))

    def test_power_of_ten_rescaling_gets_a_hint(self):
        f = self.run_gate(f"CL/F = {fr(self.cl * 1000)} L/h")["findings"][0]
        self.assertIn("x 10^3", f["hint"])
        f = self.run_gate(f"CL/F = {fr(self.cl * self.dose * 1000)} L/h")["findings"]
        self.assertEqual(len(f), 1)                                     # dose x 10^3: caught (no hint needed)

    def test_the_right_value_with_the_right_unit_still_passes_next_to_a_conversion(self):
        r = self.run_gate(f"CL/F = {fr(self.cl)} dose unit/(h·mg/L)")
        self.assertEqual(r["findings"], [])

    def test_a_converted_value_matching_nothing_even_when_rounded(self):
        # rounding the converted value to 2 digits does not make it a tool number
        v = self.cl * self.dose
        self.assertEqual(self.run_gate(f"{fr(v, 2)} L/h")["numbers_unverified"], 1)

class TestComputedValuesAreViolations(Base):
    def test_difference_ratio_and_percent_change(self):
        a, b = self.auc, raw_value(THEOPH, "aucinf.obs")
        ans = (f"AUC0-tlast {fr(a)} h·mg/L et AUC0-inf {fr(b)} h·mg/L ; écart {fr(b - a, 5)} h·mg/L, "
               f"soit {fr((b - a) / a * 100, 3)} %, ratio {fr(b / a, 4)}.")
        r = self.run_gate(ans)
        self.assertEqual(r["numbers_unverified"], 3, [f["text"] for f in r["findings"]])

    def test_sum_is_caught(self):
        ans = f"Cmax + Clast = {fr(self.cmax + raw_value(THEOPH, 'clast.obs'), 4)} mg/L"
        self.assertEqual(self.run_gate(ans)["numbers_unverified"], 1)

class TestSources(Base):
    def test_user_numbers_and_csv_are_allowed(self):
        csv_rows = td.GOLDENS[THEOPH]["calls"][0]["arguments"]["csv"].splitlines()[2].split(",")
        t, c = csv_rows[0], csv_rows[1]
        ans = f"Dose de 320 mg ; à {t.replace('.', ',')} h la concentration est de {c.replace('.', ',')} mg/L."
        self.assertEqual(self.run_gate(ans)["numbers_unverified"], 0)

    def test_a_number_only_the_user_gave_needs_the_user_message(self):
        ans = "Il pèse 72,5 kg."
        self.assertEqual(gate.check(ans, [self.tool], [])["numbers_unverified"], 1)
        self.assertEqual(gate.check(ans, [self.tool], ["Le patient pèse 72,5 kg."])["numbers_unverified"], 0)

    def test_user_french_formats(self):
        r = gate.check("poids 72,5 kg et 1 250 mL", [], ["Le patient pèse 72,5 kg ; il a reçu 1 250 mL."])
        self.assertEqual(r["numbers_unverified"], 0)

    def test_previous_tool_results_count_but_assistant_text_does_not(self):
        other = tool_text("indometh_s1_iv_bolus")
        c0 = raw_value("indometh_s1_iv_bolus", "c0")
        ans = f"C0 = {fr(c0)} mg/L"
        self.assertEqual(gate.check(ans, [self.tool, other], [USER])["numbers_unverified"], 0)
        self.assertEqual(gate.check(ans, [self.tool], [USER])["numbers_unverified"], 1)
        # an earlier answer of the assistant is not a source: it is simply not passed
        self.assertEqual(gate.check(ans, [self.tool], [USER, ])["numbers_unverified"], 1)

    def test_non_json_tool_text_is_a_source_too(self):
        self.assertEqual(gate.check("5,5 mg/L", ["TOOL ERROR: expected 5.5 mg/L"])["numbers_unverified"], 0)

    def test_precomputed_allowed_set_gives_the_same_result(self):
        al = gate.allowed_numbers([self.tool], [USER])
        ans = f"Cmax {fr(self.cmax)} mg/L et {fr(self.cl * 1000)} L/h"
        self.assertEqual(gate.check(ans, allowed=al), self.run_gate(ans))

class TestExemptions(unittest.TestCase):
    def ex(self, text):
        r = gate.check(text, []); return r

    def test_small_integers_without_unit(self):
        r = self.ex("8 points, 15 sujets, AUC(0-inf), 20 échantillons, 0 erreur")
        self.assertEqual(r["numbers_unverified"], 0); self.assertEqual(r["numbers_total"], 0)
        self.assertEqual({e["reason"] for e in r["exempt"]}, {"small_integer"})

    def test_21_is_not_exempt(self):
        self.assertEqual(self.ex("21 échantillons")["numbers_unverified"], 1)

    def test_small_integer_with_unit_percent_or_decimal_is_checked(self):
        for t in ("5 mg", "3 h", "10 %", "2,0 h", "1.0", "0,0 mg/L", "5 ng/mL"):
            with self.subTest(t): self.assertEqual(self.ex(t)["numbers_unverified"], 1, t)

    def test_years_dates_steps_list_markers_message_refs_powers_of_ten(self):
        r = self.ex("En 2026, le 2026-10-09, à l'étape 42, voir #1234 et 10^3 ou 10⁻³.\n3. suivant\n45. autre\n- 33) fin")
        self.assertEqual(r["numbers_unverified"], 0, r["findings"])
        self.assertEqual(r["numbers_total"], 0)
        reasons = {e["reason"] for e in r["exempt"]}
        self.assertTrue({"year", "date", "label_number", "power_of_ten", "small_integer"} <= reasons, reasons)

    def test_big_integers_are_checked(self):
        self.assertEqual(self.ex("96 h")["numbers_unverified"], 1)
        self.assertEqual(self.ex("1000")["numbers_unverified"], 1)
        self.assertEqual(self.ex("le nombre 1899")["numbers_unverified"], 1)
        self.assertEqual(self.ex("le nombre 120")["numbers_unverified"], 1)

    def test_label_number_is_limited_to_two_digits(self):
        self.assertEqual(self.ex("étape 150")["numbers_unverified"], 1)

    def test_the_numbers_checked_are_the_denominator(self):
        r = gate.check("Cmax 10,5 mg/L (8 points) en 2026 ; 12,5 mg", ['{"c": 10.5}'])
        self.assertEqual((r["numbers_total"], r["numbers_unverified"], r["numbers_exempt"]), (2, 1, 2))

class TestReportShape(Base):
    def test_finding_fields(self):
        r = self.run_gate(f"CL/F = {fr(self.cl * 1000)} L/h")
        f = r["findings"][0]
        for k in ("number", "text", "value", "position", "line", "unit", "significant_digits", "nearest_allowed",
                  "nearest_source", "hint"):
            self.assertIn(k, f)
        self.assertEqual(f["nearest_source"], "tool result 1")
        json.dumps(r)                                        # serialisable into the transcript JSON

    def test_nearest_allowed_is_the_closest_tool_number(self):
        r = gate.check("Cmax = 10,9 mg/L", ['{"cmax": 10.5, "tmax": 1.12, "x": 3127.58}'])
        self.assertEqual(r["findings"][0]["nearest_allowed"], "10.5")

    def test_nearest_allowed_names_a_number_not_a_csv_row(self):
        r = gate.check("valeur 0,52 mg/L", [], ["time,conc\n0.57,6.57\n1.12,10.5\n"])
        near = r["findings"][0]["nearest_allowed"]
        self.assertNotIn(",", near)
        self.assertIn(near, {"0.57", "6.57", "1.12", "10.5", "0"})

    def test_badge_and_reminder(self):
        r = self.run_gate(f"a {fr(self.cl * 1000)} L/h, b {fr(self.vz * 1000)} L, c {fr(self.cl * 1000)} L/h")
        b = gate.badge(r["findings"])
        self.assertTrue(b.startswith("⚠ 3 number(s) not found in tool results: "), b)
        self.assertEqual(b.count(fr(self.cl * 1000)), 1)      # listed once
        rem = gate.reminder(r["findings"])
        self.assertIn("quote tool values verbatim, never convert", rem)
        self.assertIn(fr(self.vz * 1000), rem)
        self.assertEqual(gate.badge([]), "")

    def test_empty_answer(self):
        r = gate.check("", [self.tool])
        self.assertEqual((r["numbers_total"], r["numbers_unverified"], r["findings"]), (0, 0, []))


if __name__ == "__main__":
    unittest.main()


class TestPerKgUnits(unittest.TestCase):
    """T-102: a value quoted with its per-kg unit is read as one number with that unit; a converted value is not in the sources."""
    SOURCE = json.dumps({"parameters": {"cl.obs": "0.0482 L/h/kg", "vz.obs": "0.581 L/kg"}})

    def test_quoted_per_kg_values_pass(self):
        r = gate.check("CL = 0.0482 L/h/kg et Vz = 0.581 L/kg.", tool_results=[self.SOURCE])
        self.assertEqual(r["numbers_unverified"], 0, r["findings"])
        self.assertEqual([n.unit for n in gate.extract_numbers("0.0482 L/h/kg")], ["L/h/kg"])

    def test_a_converted_value_is_a_finding(self):
        r = gate.check("CL = 0.803 mL/min/kg.", tool_results=[self.SOURCE])        # 0.0482 L/h/kg converted by hand
        self.assertEqual(r["numbers_unverified"], 1)
