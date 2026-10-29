"""Tests of gate v2 (gate_v2.py): typed rendering. Spec: GATE_V2.md.

The tool results are SYNTHETIC structuredContent payloads in the server's shape (invented values), the user message is
a synthetic CSV; the public goldens (tests/golden) are used only to check that every computed parameter of a real
answer resolves to the text the digest shows and that the outputSchema walk accepts the real shapes.
The class TestAuditBlindSpots replays the kinds of sentences the audit of 2026-10-14 used to show what gate v1 cannot
see (right number on the wrong parameter, changed unit, inverted sign, numbers in words, small integers, years,
2-digit coincidences): each one passes v1 (shown by running gate.check on the same sources) and is rejected by v2,
or cannot be written at all with references.
"""
import copy, glob, json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import gate, gate_v2, apothicaire, optchat  # noqa: E402
import test_digest as td                     # noqa: E402

SCHEMAS = {t["name"]: t["outputSchema"] for t in td.load("tools_list.json")["tools"] if "outputSchema" in t}

# ---------------------------------------------------------------- synthetic payloads
UNITS = {"time": "h", "conc": "ng/mL", "dose": None,
         "derived": {"auc": "h*ng/mL", "aumc": "h^2*ng/mL", "half_life": "h", "lambda_z": "1/h", "mrt": "h"}, "warnings": []}
PARAMS = {"cmax": 12.3456789, "tmax": 1.5, "tlast": 24.0, "auclast": 98.7654321, "aucall": 101.234567, "aucinf.obs": 123.456789,
          "half.life": 6.54321, "cl.obs": 0.81, "aucpext.obs": 22.5, "lambda.z.n.points": 4, "r.squared": 0.998765,
          "c0": "not_applicable_to_route"}
PARAMS_B = dict(PARAMS, auclast=97.0123456, aucall=99.5)              # the same data with lin-up/log-down

def subject(label, dose, params):
    plist = [{"name": n, "value": ({"not_calculated": v} if isinstance(v, str) else {"value": v})} for n, v in params.items()]
    return {"subject": label, "dose": dose, "route": "extravascular", "flag_messages": [], "not_calculated_messages": {},
            "outcome": {"ok": {"flags": [{"code": "high_extrapolation", "parameter": "aucpext.obs", "threshold": 20.0, "value": 22.5}],
                               "lambda_z_candidates": [], "parameters": plist, "profile": [], "removed": []}}}

def nca(aid, subjects, method="linear"):
    return {"id": aid, "kind": "nca", "label": "NCA of syn", "name": None,
            "spec": {"kind": "nca", "worksheet": 4, "dose": 100.0, "route": "extravascular", "subject": None,
                     "options": {"auc_method": method, "quality": {"max_extrapolated_percent": 20.0, "min_adj_r_squared": 0.9}}},
            "status": {"state": "fresh"}, "result": {"kind": "nca", "subjects": subjects}}

NCA = nca(7, [subject("1", 100.0, PARAMS)])
NCA_B = nca(8, [subject("1", 100.0, PARAMS_B)], "lin_up_log_down")
MULTI = nca(9, [subject("1", 100.0, dict(PARAMS, cmax=15.5)), subject("2", 100.0, dict(PARAMS, cmax=9.25)),
                subject("3", 100.0, dict(PARAMS, cmax=11.0, tmax="no_rise"))])
IMPORT = {"delimiter": ",", "notes": [],
          "worksheet": {"id": 4, "name": "syn", "revision": 0, "rows": 9, "subjects": ["1"],
                        "columns": [{"name": "time", "role": "time", "unit": "h", "type": "number", "missing": 0},
                                    {"name": "conc", "role": "concentration", "unit": "ng/mL", "type": "number", "missing": 0}],
                        "unit_warnings": [], "derived_units": UNITS["derived"]}}
def row(p, a, b, d, pct, r, nc=None):
    return {"parameter": p, "a": a, "b": b, "unit_a": None, "unit_b": None, "difference": d, "difference_unit": None,
            "relative_percent": pct, "ratio": r, "not_comparable": nc}
COMPARE = {"a": {"analysis": 7, "kind": "nca", "label": "NCA of syn", "status": "fresh", "subject": "1"},
           "b": {"analysis": 8, "kind": "nca", "label": "NCA of syn", "status": "fresh", "subject": "1"},
           "rows": [row("auclast", 98.7654321, 97.0123456, -1.7530865, -1.775, 0.98225),
                    row("cmax", 12.3456789, 12.3456789, 0.0, 0.0, 1.0),
                    row("c0", None, None, None, None, None, "not calculated on either side")]}
WS_UNITS = {4: UNITS, ("analysis", 7): 4, ("analysis", 8): 4, ("analysis", 9): 4}

def make_calls(**extra):
    calls = {"call_1": apothicaire.ref_record("call_1", "data_import", IMPORT, WS_UNITS),
             "call_2": apothicaire.ref_record("call_2", "nca_run", NCA, WS_UNITS),
             "call_3": apothicaire.ref_record("call_3", "nca_run", MULTI, WS_UNITS),
             "call_4": apothicaire.ref_record("call_4", "analysis_compare", COMPARE, WS_UNITS),
             "call_5": apothicaire.ref_record("call_5", "nca_run", NCA_B, WS_UNITS)}
    calls.update(extra); return calls

CALLS = make_calls()
USER = ("Voici les données (dose 100 mg par voie orale, temps en h, concentrations en ng/mL) :\n"
        "time,conc\n0.5,4.2\n1.5,12.35\n6,6.98\n24,0.9\nFais l'analyse non compartimentale.")

def v2(text, users=(USER,), calls=CALLS, mark="."):
    return gate_v2.check(text, calls, list(users), SCHEMAS, decimal_mark=mark)

def v1(text, users=(USER,)):
    """Gate v1 on the same synthetic sources (the payload texts are what v1 reads)."""
    return gate.check(text, [json.dumps(NCA), json.dumps(NCA_B), json.dumps(MULTI), json.dumps(COMPARE), json.dumps(IMPORT)], list(users))

class Base(unittest.TestCase):
    def ok(self, text, expect=None, **kw):
        r = v2(text, **kw)
        self.assertEqual(r["findings"], [], (text, [f["reason"] for f in r["findings"]]))
        if expect is not None: self.assertEqual(r["rendered"], expect)
        return r
    def bad(self, text, kind=None, reason=None, n=None, **kw):
        r = v2(text, **kw)
        self.assertGreaterEqual(r["numbers_unverified"], 1, text)
        self.assertIn(gate_v2.MARK_OPEN, r["rendered"], text)
        if n is not None: self.assertEqual(r["numbers_unverified"], n, (text, [f["reason"] for f in r["findings"]]))
        if kind: self.assertIn(kind, [f["kind"] for f in r["findings"]], (text, r["findings"]))
        if reason: self.assertTrue(any(reason in f["reason"] for f in r["findings"]), (text, [f["reason"] for f in r["findings"]]))
        return r

# ---------------------------------------------------------------- syntax and rendering
class TestReferenceSyntax(Base):
    def test_parse_ref(self):
        for body in ("call_2.cmax", " call_2.cmax ", "call2.cmax", "call-2.cmax", "call 2.cmax", "Call_2.cmax", '"call_2".cmax', "call_2:cmax"):
            self.assertEqual(gate_v2.parse_ref(body), ("call_2", "cmax"), body)
        self.assertEqual(gate_v2.parse_ref("call_12"), ("call_12", ""))
        self.assertEqual(gate_v2.parse_ref("cmax"), (None, None)); self.assertEqual(gate_v2.parse_ref("ref.cmax"), (None, None))
        self.assertEqual(gate_v2.segments("subject=2.half.life"), ["subject=2", "half", "life"])
        self.assertEqual(gate_v2.segments("result.subjects[0].dose"), ["result", "subjects", 0, "dose"])

    def test_every_spelling_of_a_parameter_reference_renders_the_same(self):
        for t in ("{{call_2.cmax}}", "{{ call_2.cmax }}", "{{call2.cmax}}", "{{call-2.cmax}}", "{{Call_2.CMAX}}", "{{call_2.parameters.cmax}}",
                  "{{call_2.parameters.cmax.value}}", "{{call_2.subject=1.cmax}}", "{{call_2.subject:1.cmax}}", '{{"call_2".cmax}}', "{{call_2.cmax.value}}"):
            with self.subTest(t): self.ok(t, "12.3457 ng/mL [Cmax]")

    def test_dotted_pknca_names(self):
        self.ok("{{call_2.aucinf.obs}}", "123.457 h*ng/mL [AUCinf,obs]"); self.ok("{{call_2.lambda.z.n.points}}", "4 [λz points]")
        self.ok("{{call_2.half.life}}", "6.54321 h [half-life]"); self.ok("{{call_2.r.squared}}", "0.998765 [R² of λz]")
        self.ok("{{call_2.aucpext.obs}}", "22.5 % [AUC%extrap,obs]")
        self.ok("{{call_2.cl.obs}}", "0.81 dose unit/(h*ng/mL) [CL,obs]"); self.ok("{{call_2.tlast}}", "24 h [Tlast]")

    def test_the_name_table_is_closed_and_covers_the_engine(self):
        # every parameter a golden result computes has a printed name; a name the table lacks is not renderable (fail-closed)
        for name, g in td.GOLDENS.items():
            for s in g["nca_run_result"]["result"]["subjects"]:
                for p in (s["outcome"].get("ok") or {}).get("parameters", []):
                    self.assertIn(p["name"], gate_v2.PARAMETERS, (name, p["name"]))
        self.assertEqual(gate_v2.PARAMETERS["aucinf.obs"], "AUCinf,obs"); self.assertEqual(gate_v2.PARAMETERS["cmax.dn"], "Cmax/dose")
        for n in list(gate_v2.PARAMETERS.values()) + [c["name"] for c in gate_v2.CONVENTIONS.values()]:
            self.assertEqual(gate.extract_numbers(f"[{n}]"), [], n)                  # a printed name adds no number to the rendered text
        n = copy.deepcopy(NCA); n["result"]["subjects"][0]["outcome"]["ok"]["parameters"].append({"name": "auc.new", "value": {"value": 1.5}})
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", n, WS_UNITS))
        self.bad("{{call_2.auc.new}}", "unresolved_reference", "not in the renderer's table", calls=calls)

    def test_dose_route_subject(self):
        self.ok("{{call_2.dose}}", "100 [dose]")
        for t in ("{{call_2.route}}", "{{call_2.subject}}"):                       # text fields: never rendered (T-055)
            with self.subTest(t): self.bad(t, "untyped_reference", "a text field")
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", NCA, {4: dict(UNITS, dose="mg")}))
        self.ok("{{call_2.dose}}", "100 mg [dose]", calls=calls)

    def test_several_subjects(self):
        self.ok("{{call_3.subject=2.cmax}}", "9.25 ng/mL [Cmax, subject 2]"); self.ok("{{call_3.subject=1.cmax}}", "15.5 ng/mL [Cmax, subject 1]")
        self.ok("{{call_2.subject=1.cmax}}", "12.3457 ng/mL [Cmax]")                 # one subject: no subject printed
        self.bad("{{call_3.cmax}}", "unresolved_reference", "3 subjects")
        self.bad("{{call_3.subject=9.cmax}}", "unresolved_reference", "no subject '9'")
        self.bad("{{call_3.subject=3.tmax}}", "unresolved_reference", "not calculated")

    def test_compare_fields(self):
        self.ok("{{call_4.auclast.difference}}", "-1.75309 h*ng/mL [AUClast, b−a]"); self.ok("{{call_4.auclast.diff}}", "-1.75309 h*ng/mL [AUClast, b−a]")
        self.ok("{{call_4.auclast.percent}}", "-1.775 % [AUClast, (b−a)/a]"); self.ok("{{call_4.auclast.relative_percent}}", "-1.775 % [AUClast, (b−a)/a]")
        self.ok("{{call_4.auclast.ratio}}", "0.98225 [AUClast, b/a]"); self.ok("{{call_4.auclast.a}}", "98.7654 h*ng/mL [AUClast, a]")
        self.ok("{{call_4.auclast.b}}", "97.0123 h*ng/mL [AUClast, b]")
        self.ok("{{call_4.cmax.difference}}", "0 ng/mL [Cmax, b−a]"); self.ok("{{call_4.cmax.ratio}}", "1 [Cmax, b/a]")
        self.bad("{{call_4.auclast}}", "unresolved_reference", "which field")
        self.bad("{{call_4.c0.difference}}", "unresolved_reference", "not comparable")
        self.bad("{{call_4.tmax.a}}", "unresolved_reference", "not a compared parameter")
        self.bad("{{call_4.auclast.sum}}", "unresolved_reference", "which field")

    def test_import_fields_are_not_quantities(self):
        # the worksheet description (data_import) is the model's and the user's, not a computed quantity: never rendered
        for t in ("{{call_1.rows}}", "{{call_1.worksheet.rows}}", "{{call_1.id}}", "{{call_1.subjects}}", "{{call_1.columns[1].unit}}", "{{call_1.delimiter}}"):
            with self.subTest(t):
                r = self.bad(t, "untyped_reference", "worksheet description"); self.assertEqual((r["references_total"], r["references_untyped"]), (0, 1))

    def test_raw_json_paths_are_never_rendered(self):
        # T-056: the generic JSON path is gone; the same values are cited by their typed names or not at all
        for t in ("{{call_2.spec.options.quality.max_extrapolated_percent}}", "{{call_2.result.subjects[0].dose}}", "{{call_2.id}}",
                  "{{call_2.status.state}}", "{{call_2.result.subjects[0].outcome.ok.flags[0].threshold}}", "{{call_4.a.analysis}}",
                  "{{call_4.rows[0].ratio}}", "{{call_2.outcome.ok.flags[0].value}}", "{{call_2.parameters[0].value.value}}"):
            with self.subTest(t):
                r = self.bad(t, "untyped_reference", "not a quantity the client prints", n=1)
                self.assertEqual((r["references_total"], r["references_untyped"], r["assertions"]), (0, 1, []))
                self.assertIn("{{call_N.cmax}}", r["findings"][0]["hint"])
        self.ok("{{call_2.thresholds.max_extrapolated_percent}} {{call_2.dose}} {{call_4.auclast.ratio}}",
                "20 % [threshold: max AUC%extrap] 100 [dose] 0.98225 [AUClast, b/a]")      # the typed names of the same values

    def test_display_rules(self):
        self.ok("{{call_2.cmax}}", "12.3457 ng/mL [Cmax]")                           # 6 significant digits, never more
        self.ok("{{call_2.tlast}}", "24 h [Tlast]")                                  # no ".0" after an integral value
        self.ok("{{call_2.cmax}}", "12,3457 ng/mL [Cmax]", mark=",")                 # the client's decimal mark
        self.ok("{{call_4.auclast.difference}}", "-1,75309 h*ng/mL [AUClast, b−a]", mark=",")   # the sign is the engine's
        for x in (2128760.0, 1e-05, 0.0, 6.98412345, 24.0, 319.992):
            self.assertEqual(gate_v2.render_value(x), apothicaire._shown(x), x)      # same rule as the digest
        for v in (True, "Cmax = 999 mg/L", [1, 2], None, float("nan")):              # only finite numbers are quantities
            with self.subTest(v), self.assertRaises(TypeError): gate_v2.render_value(v)

    def test_sentences_with_several_references(self):
        r = self.ok("Cmax = {{call_2.cmax}} à Tmax = {{call_2.tmax}} ; AUC(0-tlast) = {{call_2.auclast}} et AUC(0-inf) = {{call_2.aucinf.obs}}.",
                    "Cmax = 12.3457 ng/mL [Cmax] à Tmax = 1.5 h [Tmax] ; AUC(0-tlast) = 98.7654 h*ng/mL [AUClast] et AUC(0-inf) = 123.457 h*ng/mL [AUCinf,obs].")
        self.assertEqual((r["references_total"], r["references_unresolved"], r["numbers_total"], r["numbers_unverified"]), (4, 0, 4, 0))
        self.assertEqual([a["quantity"] for a in r["assertions"]], ["cmax", "tmax", "auclast", "aucinf.obs"])
        self.assertEqual(r["assertions"][0], {"ref": "call_2", "analysis": 7, "subject": None, "quantity": "cmax", "name": "Cmax",
                                              "value": 12.3456789, "unit": "ng/mL", "path": ["result", "subjects", 0, "outcome", "ok", "parameters", 0, "value", "value"]})
        self.assertEqual(r["numbers_exempt"], 2)                                     # the 0 of AUC(0-tlast) and of AUC(0-inf)

# ---------------------------------------------------------------- fail-closed
class TestFailClosed(Base):
    def test_unknown_call(self):
        r = self.bad("Cmax = {{call_9.cmax}}", "unresolved_reference", "not a tool result")
        self.assertEqual(r["rendered"], "Cmax = ⟦not a tool result of this chat: {{call_9.cmax}}⟧".replace("not a tool result of this chat", "call_9 is not a tool result of this chat"))

    def test_unknown_parameter_with_a_hint(self):
        r = self.bad("{{call_2.cmaxx}}", "unresolved_reference", "no parameter 'cmaxx'")
        self.assertIn("closest: cmax", r["findings"][0]["hint"]); self.assertNotIn("12.3457", r["rendered"])

    def test_not_calculated(self):
        self.bad("{{call_2.c0}}", "unresolved_reference", "not calculated (not_applicable_to_route)")

    def test_reference_without_a_path_or_without_a_ref(self):
        self.bad("{{call_2}}", "unresolved_reference", "needs a path"); self.bad("{{cmax}}", "unresolved_reference", "starts with the ref")
        self.bad("{{ref.cmax}}", "unresolved_reference")

    def test_malformed_braces(self):
        for t in ("{call_2.cmax}", "{{call_2.cmax}", "{call_2.cmax}}", "{{{call_2.cmax}}}"):
            with self.subTest(t):
                r = self.bad(t, "malformed_reference"); self.assertNotIn("12.3457", r["rendered"]); self.assertEqual(r["references_total"], 1)

    def test_objects_lists_and_nulls_are_not_values(self):
        for t in ("{{call_2.spec}}", "{{call_2.result.subjects}}", "{{call_2.name}}", "{{call_2.result.subjects[7].dose}}", "{{call_2.spec.nothing}}",
                  "{{call_1.worksheet.columns[0].nope}}", "{{call_2.outcome}}", "{{call_2.flag_messages}}"):
            with self.subTest(t): self.bad(t, "untyped_reference", "not a quantity the client prints")

    def test_schema_forbids_a_field_the_data_happens_to_have(self):
        strict = copy.deepcopy(SCHEMAS)
        strict["nca_run"]["$defs"]["NcaResult"]["properties"]["parameters"]["items"] = {"type": "object", "properties": {"name": {"type": "string"}}, "additionalProperties": False}
        self.assertEqual(gate_v2.check("{{call_2.cmax}}", CALLS, [USER], None)["rendered"], "12.3457 ng/mL [Cmax]")     # without the schema: data only
        r = gate_v2.check("{{call_2.cmax}}", CALLS, [USER], strict)
        self.assertIn("schema has no field 'value'", r["findings"][0]["reason"]); self.assertEqual(r["references_unresolved"], 1)

    def test_schema_type_must_agree_with_the_value(self):
        n = copy.deepcopy(NCA); n["result"]["subjects"][0]["outcome"]["ok"]["parameters"][0]["value"]["value"] = "12.3"
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", n, WS_UNITS))
        self.bad("{{call_2.cmax}}", "unresolved_reference", "declares number, the value is a string", calls=calls)
        self.assertIn("not a number", gate_v2.check("{{call_2.cmax}}", calls, [USER], None)["findings"][0]["reason"])   # without the schema too

    def test_schema_without_properties_constrains_nothing(self):
        self.assertEqual(SCHEMAS["analysis_compare"].get("properties"), None)
        self.ok("{{call_4.auclast.percent}}", "-1.775 % [AUClast, (b−a)/a]")

    def test_every_computed_parameter_of_the_goldens_renders_as_the_digest_shows(self):
        for name, g in td.GOLDENS.items():
            d, units = td.digest_of(g)
            calls = {"call_1": apothicaire.ref_record("call_1", "nca_run", g["nca_run_result"], {g["data_import_result"]["worksheet"]["id"]: units})}
            many = len(d["subjects"]) > 1
            for s in d["subjects"]:
                for pname, shown in s.get("parameters", {}).items():
                    ref = f"{{{{call_1.{'subject=' + str(s['subject']) + '.' if many else ''}{pname}}}}}"
                    r = gate_v2.check(ref, calls, [], SCHEMAS)
                    with self.subTest(case=name, subject=s["subject"], parameter=pname):
                        self.assertEqual(r["findings"], [], ref)
                        value, _, tag = r["rendered"].partition(" [")
                        self.assertEqual(tag, gate_v2.PARAMETERS[pname] + (f", subject {s['subject']}" if many else "") + "]")
                        if isinstance(shown, str): self.assertEqual(value, shown)
                        else: self.assertEqual(float(value), float(shown)); self.assertNotIn(".0", value[-2:])   # 5, not 5.0
                for pname in [p for ps in s.get("not_calculated", {}).values() for p in ps][:3]:
                    ref = f"{{{{call_1.{'subject=' + str(s['subject']) + '.' if many else ''}{pname}}}}}"
                    self.assertEqual(gate_v2.check(ref, calls, [], SCHEMAS)["references_unresolved"], 1, ref)

    def test_a_tool_error_has_nothing_to_cite(self):
        calls = make_calls(call_6={"ref": "call_6", "name": "nca_run", "structured": None, "units": {}})
        self.bad("{{call_6.cmax}}", "unresolved_reference", "no structured result", calls=calls)

# ---------------------------------------------------------------- nothing next to a reference
class TestNothingNextToAReference(Base):
    def test_unit_written_by_the_model_is_rejected(self):
        for t in ("{{call_2.cmax}} ng/mL", "{{call_2.cmax}} mg/L", "{{call_2.cmax}}ng/mL", "{{call_2.aucpext.obs}}%", "{{call_2.aucpext.obs}} %",
                  "{{call_2.half.life}} heures", "{{call_2.half.life}} h", "{{call_2.cmax}} (ng/mL)", "{{call_2.cl.obs}} L/h", "{{call_2.tmax}} hours",
                  "{{call_2.aucpext.obs}} pour cent"):
            with self.subTest(t):
                r = self.bad(t, "adjacent_to_reference", "unit next to a reference", n=1); self.assertNotIn("12.3457", r["rendered"])

    def test_sign_and_arithmetic_are_rejected(self):
        for t in ("-{{call_4.auclast.difference}}", "+{{call_4.auclast.difference}}", "− {{call_4.auclast.difference}}", "{{call_2.cmax}} × 1000",
                  "{{call_2.cmax}} x 2", "{{call_2.cmax}}*2", "{{call_2.cmax}}/{{call_2.tmax}}", "{{call_2.auclast}} - {{call_2.aucinf.obs}}",
                  "{{call_2.cmax}} + 3", "{{call_2.cmax}}^2", "2 × {{call_2.cmax}}", "10^3 × {{call_2.cl.obs}}", "{{call_2.cmax}}e3",
                  "{{call_2.cmax}}{{call_2.tmax}}", "{{call_2.cmax}} - 1", "({{call_2.auclast}}) - ({{call_2.aucall}})"):
            with self.subTest(t): self.bad(t, "adjacent_to_reference")

    def test_digits_glued_to_a_reference_are_rejected(self):
        for t in ("1{{call_2.cmax}}", "{{call_2.cmax}}5", "{{call_2.cmax}}.5", "{{call_2.cmax}},5", "0.{{call_2.cmax}}", "2,{{call_2.cmax}}", "12.{{call_2.cmax}}"):
            with self.subTest(t): self.bad(t, "adjacent_to_reference", "digit")

    def test_label_number_then_punctuation_before_a_reference_is_fine(self):
        # "analyse 2, {{ref}}" is a label followed by punctuation, not a decimal glued to the reference (bench 2026-10-17: 3 false positives)
        for t in ("méthode linéaire (analyse 2, {{call_2.auclast}})", "analyse 2 : {{call_2.auclast}}", "analyse 2 ; {{call_2.auclast}}",
                  "sujet 1, {{call_2.subject=1.cmax}}", "la phase terminale couvre deux demi-vies", "about 2 half-lives"):
            with self.subTest(t):
                r = self.ok(t); self.assertEqual(r["numbers_unverified"], 0, t)

    def test_superscript_labels_are_not_digits(self):
        self.ok("R² {{call_2.r.squared}} ; R² ajusté : {{call_2.r.squared}}", "R² 0.998765 [R² of λz] ; R² ajusté : 0.998765 [R² of λz]")   # ² passed isdigit(): used to crash
        self.bad("{{call_2.cmax}} ²", "number_word", "Unicode numeric")             # a superscript that is no exponent of a label is a number (T-058)

    def test_ordinary_punctuation_and_words_are_fine(self):
        for t in ("Cmax = {{call_2.cmax}}", "Cmax : {{call_2.cmax}}", "({{call_2.cmax}})", "{{call_2.cmax}}, {{call_2.tmax}} et {{call_2.auclast}}.",
                  "{{call_2.cmax}} - c'est élevé", "{{call_2.cmax}} s'il faut", "{{call_2.tmax}} après la dose", "AUC(0-tlast) = {{call_2.auclast}}",
                  "Cmax ≈ {{call_2.cmax}} ; demi-vie {{call_2.half.life}} (8 points)", "{{call_2.cmax}} est la Cmax", "**{{call_2.cmax}}**",
                  "| Cmax | {{call_2.cmax}} |", "{{call_2.cmax}} mais", "{{call_2.half.life}} jusqu'à", "{{call_2.cmax}} d'après Caladrius"):
            with self.subTest(t): self.ok(t)

# ---------------------------------------------------------------- bare numbers: the user's digits only
class TestBareNumbers(Base):
    def test_the_users_numbers_may_be_quoted_exactly(self):
        self.ok("La dose de 100 mg ; à 1,5 h la concentration était de 12,35 ng/mL, à 24 h 0.9 ng/mL.")
        self.ok("dose 100.0 mg")                                                      # the same value
        self.ok("−100 mg")                                                            # sign ignored for the user's numbers, as in v1

    def test_a_tool_number_typed_by_hand_is_rejected_even_when_right(self):
        for t in ("Cmax = 12.3457 ng/mL", "Cmax = 12,3 ng/mL", "AUC = 98.77 h*ng/mL", "Cmax = 12 ng/mL", "r² = 0,998765", "aucpext 22,5 %"):
            with self.subTest(t):
                self.bad(t, "bare_number", n=1); self.assertEqual(v1(t)["numbers_unverified"], 0, t)   # v1 accepts all of them

    def test_no_rounding_match_on_the_users_numbers(self):
        self.ok("6,98 ng/mL"); self.bad("7,0 ng/mL", "bare_number"); self.bad("7 ng/mL", "bare_number")
        self.assertEqual(v1("7,0 ng/mL")["numbers_unverified"], 0)

    def test_years_are_not_exempt(self):
        self.bad("la valeur de 2000", "bare_number"); self.bad("en 2026", "bare_number")
        self.ok("en 2026", users=(USER, "rapport de 2026"))
        self.assertEqual(v1("en 2026")["numbers_unverified"], 0)

    def test_counts_stay_exempt_but_not_after_a_pk_label(self):
        r = self.ok("8 points, 3 sujets, AUC(0-inf), 2 analyses, 0 erreur ; étape 3 ; #17 ; le 2026-10-16 ; 10^3 ; 0,05 1/h".replace("0,05", "0.5"))
        self.assertGreaterEqual(r["numbers_exempt"], 9)
        for t in ("Cmax est de 12", "Cmax = 12", "la clairance : 5", "half-life of 7", "t1/2 ≈ 7", "CL/F vaut 2", "AUC(0-inf) de 15",
                  "une demi-vie d'environ 7", "la Cmax (ng/mL) est 12", "extrapolation : 20", "le ratio est de 1"):
            with self.subTest(t): self.bad(t, "bare_number", n=1)
        self.bad("21 échantillons", "bare_number")
        for t in ("Cmax est de 12", "la clairance : 5", "half-life of 7"): self.assertEqual(v1(t)["numbers_unverified"], 0, t)

    def test_csv_rows_glued_by_commas(self):
        self.ok("la ligne 1,5,12.35 du fichier")

    def test_finding_fields_and_nearest(self):
        f = self.bad("Cmax = 12,36 ng/mL", "bare_number")["findings"][0]
        for k in ("kind", "number", "text", "value", "position", "line", "unit", "significant_digits", "nearest_allowed", "nearest_source", "hint", "reason", "ref"):
            self.assertIn(k, f)
        self.assertEqual((f["number"], f["unit"], f["value"], f["significant_digits"]), ("12,36", "ng/mL", "12.36", 4))
        self.assertEqual(f["nearest_allowed"], "12.35"); self.assertIn("user message", f["nearest_source"])
        self.assertEqual("Cmax = 12,36 ng/mL"[f["position"][0]:f["position"][1]], "12,36 ng/mL")

# ---------------------------------------------------------------- numbers in words
class TestNumberWords(Base):
    def test_quantities_in_words_are_rejected(self):
        for t in ("deux litres", "trois heures", "cinq pour cent", "deux fois plus élevée", "trente-deux", "deux cents", "cent", "mille",
                  "deux virgule cinq", "twenty five", "two hundred", "half the value", "la moitié", "le double", "Cmax vaut douze",
                  "une clairance de dix", "la demi-vie est de six", "about ten hours", "six h", "quatre-vingt-dix", "dix-sept", "twice as high",
                  "two point five", "un tiers", "trois quarts", "sept pour cent"):
            with self.subTest(t): self.bad(t, "number_word", n=1); self.assertEqual(v1(t)["numbers_unverified"], 0, t)

    def test_counts_in_words_and_compound_words_are_fine(self):
        for t in ("les deux analyses", "trois sujets", "deux méthodes", "la demi-vie", "half-life", "the half life", "une analyse", "one subject",
                  "un point", "neuf", "six", "en pour cent", "aucpext en pour cent", "the two AUC methods", "zéro erreur", "quinze points",
                  "le troisième sujet", "sixième", "centre", "millilitre", "pourcentage", "sept points de la régression"):
            with self.subTest(t):
                r = self.ok(t); self.assertEqual(r["numbers_unverified"], 0)

# ---------------------------------------------------------------- the audit's blind spots
class TestAuditBlindSpots(Base):
    """Each case: (what, a sentence gate v1 accepts on these sources, v2's verdict). `v1_passes` None = the sentence only exists in v2."""
    CASES = [
        ("right number on the wrong parameter (aucall quoted as AUC(0-tlast))", "AUC(0-tlast) = 101,235 h*ng/mL", True, "bare_number"),
        ("unit changed (ng/mL written as mg/L)", "Cmax = 12,3457 mg/L", True, "bare_number"),
        ("unit written next to a reference", "{{call_2.cmax}} mg/L", None, "adjacent_to_reference"),
        ("sign inverted (the engine's difference is negative)", "la différence est de 1,75309 h*ng/mL", True, "bare_number"),
        ("sign written next to a reference", "−{{call_4.auclast.difference}}", None, "adjacent_to_reference"),
        ("number spelled in words", "la clairance est d'environ deux litres par heure", True, "number_word"),
        ("decimal spelled in words", "une Cmax de douze virgule trois ng/mL", True, "number_word"),
        ("fraction in words", "la moitié de la Cmax est atteinte", True, "number_word"),
        ("small integer after a label (v1 exempts 0-20)", "Cmax est de 12 (unité non précisée)", True, "bare_number"),
        ("year exemption as a channel", "une AUC de 2000", True, "bare_number"),
        ("2-digit coincidence with a tool number (cl.obs 0.81)", "une baisse de 0,81 %", True, "bare_number"),
        ("2-digit coincidence (the compare ratio 1.00)", "variation de −1,00 %", True, "bare_number"),
        ("rounding chosen by the model", "Cmax ≈ 12 ng/mL", True, "bare_number"),
        ("the engine's difference typed instead of cited", "soit 1,75 h*ng/mL de moins", True, "bare_number"),
        ("wrong subject (subject 1's Cmax given for subject 2)", "Cmax du sujet 2 = 15,5 ng/mL", True, "bare_number"),
        ("wrong analysis (the linear AUC given as lin-up/log-down)", "AUC lin-up/log-down = 98,7654 h*ng/mL", True, "bare_number"),
        ("arithmetic on references", "{{call_2.aucinf.obs}} - {{call_2.auclast}}", None, "adjacent_to_reference"),
        ("a digit glued to a reference", "{{call_2.cmax}}0", None, "adjacent_to_reference"),
    ]

    def test_each_blind_spot_is_rejected_by_v2(self):
        for what, sentence, v1_passes, kind in self.CASES:
            with self.subTest(what):
                r = v2(sentence)
                self.assertGreaterEqual(r["numbers_unverified"], 1, (what, r["findings"]))
                self.assertIn(kind, [f["kind"] for f in r["findings"]], what)
                self.assertIn(gate_v2.MARK_OPEN, r["rendered"], what)
                if v1_passes is not None:
                    self.assertEqual(v1(sentence)["numbers_unverified"], 0, (what, "v1 was expected to accept this sentence"))

    def test_the_rendered_label_is_the_selected_parameter(self):
        # with references the model cannot attach aucall's number to the AUC(0-tlast) label without naming aucall
        self.ok("AUC(0-tlast) = {{call_2.auclast}}", "AUC(0-tlast) = 98.7654 h*ng/mL [AUClast]")
        self.ok("AUC(0-tlast) = {{call_2.aucall}}", "AUC(0-tlast) = 101.235 h*ng/mL [AUCall]")       # a selection error, now visible to the reader
        self.ok("Cmax du sujet 2 = {{call_3.subject=2.cmax}}", "Cmax du sujet 2 = 9.25 ng/mL [Cmax, subject 2]")
        self.ok("AUC lin-up/log-down = {{call_5.auclast}}", "AUC lin-up/log-down = 97.0123 h*ng/mL [AUClast]")
        self.ok("différence {{call_4.auclast.difference}}", "différence -1.75309 h*ng/mL [AUClast, b−a]")   # the sign is the engine's

# ---------------------------------------------------------------- record, badge, reminder
class TestRecordAndMessages(Base):
    def test_counts_and_serialisation(self):
        r = v2("Cmax = {{call_2.cmax}} ; {{call_2.cmaxx}} ; 12,36 ng/mL ; deux litres ; 3 sujets ; dose 100 mg")
        self.assertEqual((r["references_total"], r["references_unresolved"]), (2, 1))
        self.assertEqual((r["numbers_total"], r["numbers_unverified"], r["numbers_exempt"]), (5, 3, 1))
        json.dumps(r)
        self.assertEqual(r["rendered"].count(gate_v2.MARK_OPEN), 3); self.assertIn("12.3457 ng/mL [Cmax]", r["rendered"]); self.assertIn("dose 100 mg", r["rendered"])
        self.assertEqual(gate_v2.check("", CALLS, [USER]), {"rendered": "", "findings": [], "exempt": [], "numbers_total": 0, "numbers_unverified": 0,
                                                            "numbers_exempt": 0, "references_total": 0, "references_unresolved": 0,
                                                            "references_untyped": 0, "assertions": []})
        r = v2("{{call_2.name}} ; {{call_2.cmax}}")                                   # an untyped reference: a marker, outside references_total
        self.assertEqual((r["references_total"], r["references_unresolved"], r["references_untyped"], r["numbers_total"], r["numbers_unverified"]), (1, 0, 1, 2, 1))

    def test_badge_and_reminder(self):
        r = v2("{{call_2.cmaxx}} et 12,36 ng/mL et {{call_2.cmax}} ng/mL et {{call_7.x}}")
        b = gate_v2.badge(r["findings"])
        self.assertTrue(b.startswith("⚠ 4 problem(s)"), b); self.assertIn("{{call_2.cmaxx}}", b); self.assertIn("12,36 ng/mL", b)
        self.assertEqual(gate_v2.badge([]), "")
        rem = gate_v2.reminder(r["findings"], CALLS)
        self.assertTrue(rem.startswith("[system reminder]"))
        self.assertIn("closest: cmax", rem); self.assertIn("computed parameters: aucall, aucinf.obs, auclast", rem)   # listed for the bad ref
        self.assertEqual(rem.count("computed parameters:"), 1)
        self.assertIn("Available references: call_2 (nca_run, analysis 7, subject 1); "
                      "call_3 (nca_run, analysis 9, 3 subjects: call_3.subject=1, call_3.subject=2, call_3.subject=3); "
                      "call_4 (analysis_compare: auclast, cmax; fields .a .b .difference .percent .ratio); call_5 (nca_run, analysis 8, subject 1)", rem)
        self.assertIn("unit next to a reference", rem); self.assertIn("not in the user's message", rem); self.assertIn("call_7 is not a tool result", rem)


# ---------------------------------------------------------------- aliases: the selected λz candidate and the quality thresholds
CANDS = [{"adj_r_squared": 0.98765, "intercept": 2.5, "lambda_z": 0.1234, "n_points": 4, "r_squared": 0.99012, "replaced_points": 0,
          "selected": False, "time_first": 6.0, "time_last": 24.0, "valid": True},
         {"adj_r_squared": 0.99876, "intercept": 2.4, "lambda_z": 0.1111, "n_points": 3, "r_squared": 0.99938, "replaced_points": 0,
          "selected": True, "time_first": 8.0, "time_last": 24.0, "valid": True}]

def with_candidates(payload, cands):
    p = copy.deepcopy(payload)
    for s in p["result"]["subjects"]: s["outcome"]["ok"]["lambda_z_candidates"] = copy.deepcopy(cands)
    return p

class TestAliases(Base):
    """`lambda_z.<field>` = the selected λz regression candidate; `thresholds.<name>` = spec.options.quality (GATE_V2.md)."""
    def setUp(self):
        self.calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", with_candidates(NCA, CANDS), WS_UNITS),
                                call_3=apothicaire.ref_record("call_3", "nca_run", with_candidates(MULTI, CANDS), WS_UNITS))

    def test_the_selected_candidate_by_alias(self):
        for field, out in (("adj_r_squared", "0.99876 [adjusted R² of λz]"), ("r_squared", "0.99938 [R² of λz]"), ("n_points", "3 [λz points]"),
                           ("time_first", "8 [λz first time]"), ("time_last", "24 [λz last time]"), ("lambda_z", "0.1111 [λz]"), ("intercept", "2.4 [λz intercept]")):
            self.ok(f"{{{{call_2.lambda_z.{field}}}}}", out, calls=self.calls)             # the selected one (index 1), never the first
        self.ok("{{call_2.lambda_z.r.squared}} {{call_2.lambda_z.adj.r.squared}} {{ call_2 . lambda_z . n_points }}",
                "0.99938 [R² of λz] 0.99876 [adjusted R² of λz] 3 [λz points]", calls=self.calls)
        self.assertEqual(gate_v2.resolve("call_2", "lambda_z.adj_r_squared", self.calls, SCHEMAS).path,
                         ["result", "subjects", 0, "outcome", "ok", "lambda_z_candidates", 1, "adj_r_squared"])       # the canonical path
        self.assertEqual(v2("{{call_2.lambda_z.adj_r_squared}}", calls=self.calls, mark=",")["rendered"], "0,99876 [adjusted R² of λz]")
        self.ok("{{call_2.r.squared}} {{call_2.lambda.z.n.points}}", "0.998765 [R² of λz] 4 [λz points]", calls=self.calls)   # the PKNCA names resolve as before (synthetic values differ)

    def test_time_fields_carry_the_time_unit_when_the_analysis_has_it(self):
        g = td.GOLDENS["theoph_s1_oral_dose_arg"]; d, units = td.digest_of(g)
        calls = {"call_1": apothicaire.ref_record("call_1", "nca_run", g["nca_run_result"], {g["data_import_result"]["worksheet"]["id"]: units})}
        reg = d["subjects"][0]["lambda_z_regression"]
        for field, unit in (("time_first", " h"), ("time_last", " h"), ("lambda_z", " 1/h"), ("adj_r_squared", ""), ("n_points", "")):
            r = gate_v2.check(f"{{{{call_1.lambda_z.{field}}}}}", calls, [], SCHEMAS)
            self.assertEqual(r["findings"], [], field)
            self.assertTrue(r["rendered"].partition(" [")[0].endswith(unit), (field, r["rendered"]))
            self.assertEqual(float(r["rendered"].split(" ")[0]), float(reg[field]), field)
        for name, v in d["options_used"]["quality_thresholds"].items():
            r = gate_v2.check(f"{{{{call_1.thresholds.{name}}}}}", calls, [], SCHEMAS)
            self.assertEqual(r["findings"], [], name); self.assertEqual(float(r["rendered"].split(" ")[0]), float(v), name)
            self.assertEqual(r["rendered"].partition(" [")[0].endswith(" %"), name.endswith("percent"), r["rendered"])

    def test_every_golden_candidate_renders_as_the_digest_shows(self):
        for name, g in td.GOLDENS.items():
            d, units = td.digest_of(g)
            calls = {"call_1": apothicaire.ref_record("call_1", "nca_run", g["nca_run_result"], {g["data_import_result"]["worksheet"]["id"]: units})}
            many = len(d["subjects"]) > 1
            for s in d["subjects"]:
                pre = f"call_1.{'subject=' + str(s['subject']) + '.' if many else ''}lambda_z."
                if "lambda_z_regression" not in s:                                      # no candidate selected: fail-closed
                    r = gate_v2.check(f"{{{{{pre}adj_r_squared}}}}", calls, [], SCHEMAS)
                    with self.subTest(case=name, subject=s["subject"]):
                        self.assertTrue(any(w in r["findings"][0]["reason"] for w in ("no λz regression candidate is selected", "has no result")), r["findings"][0]["reason"])
                    continue
                for field, shown in s["lambda_z_regression"].items():
                    r = gate_v2.check(f"{{{{{pre}{field}}}}}", calls, [], SCHEMAS)
                    with self.subTest(case=name, subject=s["subject"], field=field):
                        self.assertEqual(r["findings"], [], field); self.assertEqual(float(r["rendered"].split(" ")[0]), float(shown))

    def test_fail_closed_without_one_selected_candidate(self):
        self.bad("{{call_2.lambda_z.adj_r_squared}}", "unresolved_reference", "no λz regression candidate is selected")          # CALLS: no candidates
        two = copy.deepcopy(CANDS); two[0]["selected"] = True
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", with_candidates(NCA, two), WS_UNITS))
        self.bad("{{call_2.lambda_z.adj_r_squared}}", "unresolved_reference", "2 λz candidates are marked selected", calls=calls)
        r = self.bad("{{call_2.lambda_z.foo}}", "unresolved_reference", "no field 'foo' in the selected", calls=self.calls)
        self.assertIn("fields: lambda_z.adj_r_squared", r["findings"][0]["hint"])
        self.bad("{{call_2.lambda_z.selected}}", "unresolved_reference", "no field 'selected'", calls=self.calls)                  # flags are not values
        self.bad("{{call_2.lambda_z}}", "unresolved_reference", "no parameter 'lambda_z'", calls=self.calls)                       # alone: a parameter name

    def test_several_subjects(self):
        self.bad("{{call_3.lambda_z.adj_r_squared}}", reason="3 subjects", calls=self.calls)
        self.ok("{{call_3.subject=2.lambda_z.n_points}}", "3 [λz points, subject 2]", calls=self.calls)
        self.ok("{{call_3.thresholds.max_extrapolated_percent}} {{call_3.subject=2.thresholds.min_adj_r_squared}}",
                "20 % [threshold: max AUC%extrap] 0.9 [threshold: min adjusted R²]", calls=self.calls)

    def test_thresholds(self):
        self.ok("{{call_2.thresholds.max_extrapolated_percent}}", "20 % [threshold: max AUC%extrap]")
        self.ok("{{call_2.thresholds.min_adj_r_squared}}", "0.9 [threshold: min adjusted R²]")
        self.assertEqual(gate_v2.resolve("call_2", "thresholds.min_adj_r_squared", CALLS, SCHEMAS).path, ["spec", "options", "quality", "min_adj_r_squared"])
        self.assertEqual(v2("seuil {{call_2.thresholds.max_extrapolated_percent}}", mark=",")["rendered"], "seuil 20 % [threshold: max AUC%extrap]")
        r = self.bad("{{call_2.thresholds.foo}}", "unresolved_reference", "no quality threshold 'foo'")
        self.assertIn("thresholds: thresholds.max_extrapolated_percent, thresholds.min_adj_r_squared", r["findings"][0]["hint"])
        self.bad("{{call_2.thresholds}}", "unresolved_reference", "say which threshold")
        n = copy.deepcopy(NCA); del n["spec"]["options"]["quality"]
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", n, WS_UNITS))
        self.bad("{{call_2.thresholds.max_extrapolated_percent}}", "unresolved_reference", "carries no quality thresholds", calls=calls)
        self.bad("Le seuil est 20 %", "bare_number")                                       # the domain constant typed by hand stays rejected
        self.bad("{{call_2.thresholds.max_extrapolated_percent}} %", "adjacent_to_reference")   # the client prints the %

    def test_invented_digest_paths_are_rejected_with_the_alias_as_closest_name(self):
        for path, alias in (("lambda_z_regression.adj_r_squared", "lambda_z.adj_r_squared"), ("lambda_z_regression.r.squared", "lambda_z.r_squared"),
                            ("lambda_z_regression.n_points", "lambda_z.n_points"), ("lambda.z_regression.adj_r_squared", "lambda_z.adj_r_squared"),
                            ("subject=1.lambda_z_regression.adj_r_squared", "lambda_z.adj_r_squared"), ("lambda_z_candidates.time_first", "lambda_z.time_first"),
                            ("quality_thresholds.max_extrapolated_percent", "thresholds.max_extrapolated_percent"),
                            ("options_used.quality_thresholds.max_extrapolated_percent", "thresholds.max_extrapolated_percent")):
            raw = path.startswith("lambda_z_candidates")                                    # a JSON key of the result: untyped, same hint
            r = self.bad(f"{{{{call_2.{path}}}}}", "untyped_reference" if raw else "unresolved_reference", "raw JSON path" if raw else "no parameter", calls=self.calls)
            self.assertTrue(r["findings"][0]["hint"].startswith("closest: " + alias), (path, r["findings"][0]["hint"]))
            self.assertIn("closest: " + alias, gate_v2.reminder(r["findings"], self.calls))
        r = self.bad("{{call_2.lambda_z_regression.adj_r_squared}}", calls=CALLS)          # no candidate selected: the alias is still the name to use
        self.assertTrue(r["findings"][0]["hint"].startswith("closest: lambda_z.adj_r_squared"))
        r = self.bad("{{call_2.adj_r_squared}}", "unresolved_reference", "no parameter", calls=self.calls)      # a misspelt PKNCA name: no alias
        self.assertNotIn("lambda_z.", r["findings"][0]["hint"])

    def test_reminder_lists_the_aliases_of_a_citable_analysis(self):
        rem = gate_v2.reminder(v2("{{call_2.cmaxx}}", calls=self.calls)["findings"], self.calls)
        self.assertIn("Aliases: call_3.lambda_z.adj_r_squared, .r_squared, .n_points, .time_first, .time_last (the selected λz regression); "
                      "call_5.thresholds.max_extrapolated_percent (also .min_adj_r_squared) (quality thresholds).", rem)
        self.assertEqual(gate_v2.alias_line({"call_1": CALLS["call_1"], "call_4": CALLS["call_4"]}), "")                      # no analysis: no line
        self.assertTrue(gate_v2.alias_line(CALLS).startswith("Aliases: call_5.thresholds"))                                    # no selected candidate anywhere
        self.assertIn("lambda_z.adj_r_squared", apothicaire.SYSTEM_ADDITION_V2); self.assertIn("thresholds.max_extrapolated_percent", apothicaire.SYSTEM_ADDITION_V2)

    def test_alias_paths_are_checked_against_the_schema_on_their_canonical_path(self):
        strict = copy.deepcopy(SCHEMAS)
        strict["nca_run"]["$defs"]["NcaResult"]["properties"]["lambda_z_candidates"]["items"] = {"type": "object", "properties": {"n_points": {"type": "integer"}}, "additionalProperties": False}
        strict["nca_run"]["$defs"]["AnalysisSpec"]["additionalProperties"] = False
        c = self.calls
        self.assertEqual(gate_v2.check("{{call_2.lambda_z.n_points}}", c, [USER], strict)["rendered"], "3 [λz points]")         # allowed by the strict schema
        r = gate_v2.check("{{call_2.lambda_z.adj_r_squared}}", c, [USER], strict)
        self.assertIn("schema has no field 'adj_r_squared'", r["findings"][0]["reason"])                                      # forbidden although the data has it
        r = gate_v2.check("{{call_2.thresholds.max_extrapolated_percent}}", c, [USER], strict)
        self.assertIn("schema has no field 'options'", r["findings"][0]["reason"])
        self.assertEqual(gate_v2.check("{{call_2.thresholds.max_extrapolated_percent}}", c, [USER], SCHEMAS)["rendered"], "20 % [threshold: max AUC%extrap]")   # the real schema allows it


# ---------------------------------------------------------------- named conventions (closed table, decision of 2026-10-17)
NO_NCA = {"call_1": CALLS["call_1"], "call_4": CALLS["call_4"]}            # no analysis: the table is the only source

class TestConventions(Base):
    def test_the_table_is_closed_and_matches_the_engine(self):
        self.assertEqual(set(gate_v2.CONVENTIONS), {"max_extrapolated_percent", "min_adj_r_squared", "min_span_ratio", "min_points"})
        for name, row in gate_v2.CONVENTIONS.items():
            self.assertEqual(set(row), {"value", "unit", "name", "source"}); self.assertTrue(row["source"].strip(), name); self.assertIn("PKNCA", row["source"])
            for case, g in td.GOLDENS.items():                                                           # the engine's own defaults, as echoed by real results
                self.assertEqual(g["nca_run_result"]["spec"]["options"]["quality"][name], row["value"], (case, name))

    def test_rendering_from_the_table_when_no_analysis_carries_the_threshold(self):
        self.ok("{{convention.max_extrapolated_percent}}", "20 % [convention: max AUC%extrap]", calls=NO_NCA)
        self.ok("{{convention.min_adj_r_squared}} {{convention.min_span_ratio}} {{convention.min_points}}",
                "0.9 [convention: min adjusted R²] 2 [convention: min span ratio] 3 [convention: min λz points]", calls=NO_NCA)
        self.assertEqual(v2("seuil {{convention.max_extrapolated_percent}}, R² {{ convention . min_adj_r_squared }}", calls=NO_NCA, mark=",")["rendered"],
                         "seuil 20 % [convention: max AUC%extrap], R² 0,9 [convention: min adjusted R²]")
        self.assertEqual(gate_v2.resolve_convention("max_extrapolated_percent", NO_NCA).path, ["convention", "max_extrapolated_percent"])
        self.ok("{{convention.min_span_ratio}}", "2 [convention: min span ratio]")                       # CALLS carry no min_span_ratio: table
        r = self.ok("{{convention.max_extrapolated_percent}}", "20 % [convention: max AUC%extrap]", calls=NO_NCA)
        self.assertEqual((r["references_total"], r["numbers_unverified"]), (1, 0))

    def test_an_analysis_that_echoes_the_threshold_wins_over_the_table(self):
        self.assertEqual(gate_v2.resolve_convention("max_extrapolated_percent", CALLS).path, ["spec", "options", "quality", "max_extrapolated_percent"])
        n = copy.deepcopy(NCA); n["spec"]["options"]["quality"]["max_extrapolated_percent"] = 25.0
        only = {"call_1": CALLS["call_1"], "call_2": apothicaire.ref_record("call_2", "nca_run", n, WS_UNITS)}
        self.ok("{{convention.max_extrapolated_percent}}", "25 % [threshold: max AUC%extrap]", calls=only)  # the user's threshold, not the table's
        both = dict(only, call_5=CALLS["call_5"])                                                          # 25 and 20: ambiguous
        r = self.bad("{{convention.max_extrapolated_percent}}", "unresolved_reference", "different values of max_extrapolated_percent", calls=both)
        self.assertIn("{{call_2.thresholds.max_extrapolated_percent}} or {{call_5.thresholds.max_extrapolated_percent}}", r["findings"][0]["hint"])

    def test_unknown_convention(self):
        r = self.bad("{{convention.max_extrapolation}}", "unresolved_reference", "no convention 'max_extrapolation'")
        self.assertTrue(r["findings"][0]["hint"].startswith("closest: convention.max_extrapolated_percent"), r["findings"][0]["hint"])
        self.bad("{{convention}}", "unresolved_reference", "a reference starts with the ref of a tool result")
        self.bad("{{convention.max_extrapolated_percent}} %", "adjacent_to_reference")                     # the client prints the unit
        self.bad("{{convention.max_extrapolated_percent}}%", "adjacent_to_reference")

    def test_a_typed_convention_stays_rejected_and_the_reminder_names_the_reference(self):
        r = self.bad("Le seuil est 20 %.", "bare_number", n=1)
        self.assertEqual(r["findings"][0]["hint"], "the convention max_extrapolated_percent: write {{call_5.thresholds.max_extrapolated_percent}}")   # the last analysis that echoes it
        self.assertIn("20 %: a number typed by hand", gate_v2.reminder(r["findings"], CALLS)); self.assertIn("write {{call_5.thresholds.max_extrapolated_percent}}", gate_v2.reminder(r["findings"], CALLS))
        r = self.bad("Le seuil est 20,0 %.", "bare_number", calls=NO_NCA)
        self.assertEqual(r["findings"][0]["hint"], "the convention max_extrapolated_percent: write {{convention.max_extrapolated_percent}}")
        r = self.bad("R² ajusté minimal 0,9", "bare_number", users=("Dose 100 mg.",), calls=NO_NCA)
        self.assertEqual(r["findings"][0]["hint"], "the convention min_adj_r_squared: write {{convention.min_adj_r_squared}}")
        r = self.bad("Cmax = 20 mg/L", "bare_number")                                                    # same digits, another unit: not the convention
        self.assertIsNone(r["findings"][0]["hint"])
        rem = gate_v2.reminder(v2("{{call_2.cmaxx}}")["findings"], CALLS)
        self.assertIn("Conventions (never type them): {{convention.max_extrapolated_percent}}, {{convention.min_adj_r_squared}}", rem)
        self.assertIn("{{convention.max_extrapolated_percent}}", apothicaire.SYSTEM_ADDITION_V2)

# ---------------------------------------------------------------- red-team probes of 2026-10-19 as mutation tests (T-054 to T-058)
def _leaf_paths(x, path=""):
    """Every JSON path of a payload that ends on a scalar, written the way the model would (`a.b[0].c`)."""
    if isinstance(x, dict):
        for k, v in x.items(): yield from _leaf_paths(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from _leaf_paths(v, f"{path}[{i}]")
    elif path: yield path

GOLDEN = ("Cmax = {{call_2.cmax}}, Tmax = {{call_2.tmax}}, AUC(0-tlast) = {{call_2.auclast}}, AUC(0-inf) = {{call_2.aucinf.obs}}, "
          "demi-vie {{call_2.half.life}}, CL/F {{call_2.cl.obs}}.")

class TestRedTeamMutations(Base):
    """The replayable probes of the red-team triage (project Library, red-team/probes/probes.py), rows RT-A1, RT-A9, RT-A6, RT-A2 and
    RT-A10, each turned into a family of mutations: every one passed gate v2 at a2ae43e with 0 finding."""

    # RT-A1 / T-054: the rendered text names the quantity, so a wrong parameter of the same unit is visible
    def test_a_wrong_parameter_of_the_same_unit_is_named(self):
        r = self.ok("AUC(0-tlast) = {{call_2.aucinf.obs}}", "AUC(0-tlast) = 123.457 h*ng/mL [AUCinf,obs]")
        self.assertEqual(r["assertions"][0]["quantity"], "aucinf.obs")

    def test_swapping_a_referenced_parameter_changes_the_rendered_name(self):
        base = self.ok(GOLDEN)["rendered"]
        computed = [n for n, v in PARAMS.items() if not isinstance(v, str)]
        for old in ("cmax", "tmax", "auclast", "aucinf.obs", "half.life", "cl.obs"):
            for new in computed:
                if new == old: continue
                with self.subTest(old=old, new=new):
                    r = self.ok(GOLDEN.replace(f"{{{{call_2.{old}}}}}", f"{{{{call_2.{new}}}}}"))
                    self.assertNotEqual(r["rendered"], base)
                    self.assertIn(f"[{gate_v2.PARAMETERS[new]}]", r["rendered"]); self.assertEqual(r["rendered"].count(f"[{gate_v2.PARAMETERS[old]}]"), 0)

    # RT-A9 / T-055: a model-written text field never renders as a quantity
    def test_a_model_written_name_is_not_a_quantity(self):
        named = copy.deepcopy(NCA); named["name"] = "Cmax = 999 mg/L"; named["label"] = "AUC 12 h*ng/mL"
        calls = make_calls(call_2=apothicaire.ref_record("call_2", "nca_run", named, WS_UNITS))
        for t in ("Résultat : {{call_2.name}}", "{{call_2.label}}", "{{call_2.spec.kind}}", "{{call_2.subject}}", "{{call_2.route}}"):
            with self.subTest(t):
                r = self.bad(t, "untyped_reference", calls=calls, users=())
                self.assertEqual((r["references_total"], r["references_untyped"], r["assertions"]), (0, 1, []))
                self.assertNotIn("999", r["rendered"].replace(t, "")); self.assertNotIn("Cmax = 999", r["rendered"].split(gate_v2.MARK_OPEN)[0])

    # RT-A6 / T-056: no raw JSON path, no unitless scalar, no non-selected candidate in the number channel
    def test_no_json_path_of_any_result_renders(self):
        for ref, payload in (("call_2", NCA), ("call_3", MULTI), ("call_4", COMPARE), ("call_1", IMPORT), ("call_2", with_candidates(NCA, CANDS))):
            calls = make_calls(**{ref: apothicaire.ref_record(ref, CALLS[ref]["name"], payload, WS_UNITS)})
            for path in _leaf_paths(payload):
                t = f"{{{{{ref}.{path}}}}}"
                with self.subTest(t):
                    r = v2(t, calls=calls)
                    self.assertEqual(r["assertions"], [], t); self.assertGreaterEqual(r["numbers_unverified"], 1, t)

    def test_the_three_raw_path_probes(self):
        g = td.GOLDENS["theoph_s1_oral_dose_arg"]["nca_run_result"]
        calls = make_calls(call_9=apothicaire.ref_record("call_9", "nca_run", g.get("structuredContent", g), {}))
        for t in ("| Cmax (mg/L) | {{call_2.result.subjects[0].outcome.ok.parameters[0].value.value}} |",
                  "λz = {{call_9.outcome.ok.lambda_z_candidates[1].lambda_z}}", "Statut : {{call_9.status.state}}"):
            with self.subTest(t):
                r = self.bad(t, "untyped_reference", calls=calls); self.assertEqual(r["references_total"], 0)
        self.ok("λz = {{call_9.lambda_z.lambda_z}}", calls=calls)                       # the selected candidate, by its typed name

    # RT-A2 / T-057: a contradictory unit anywhere in the clause or the table column
    TEMPLATES = ("La Cmax en {u} vaut {r}.", "Cmax ({u}) : {r}", "{r}, en {u}.", "Cmax [{u}] = {r}", "Les concentrations sont en {u}, Cmax = {r}",
                 "| Cmax ({u}) | {r} |", "| Paramètre | Valeur ({u}) |\n|---|---|\n| Cmax | {r} |", "| Cmax | {r} | {u} |",
                 "| Paramètre | Valeur | Unité |\n|---|---|---|\n| Tmax | 1,5 h |\n| Cmax | {r} | {u} |")

    def test_a_contradictory_unit_anywhere_in_the_clause_is_a_finding(self):
        for u in ("mg/L", "µg/mL", "μg/mL", "ng/L", "g/L", "mg/mL", "pg/mL"):              # concentration, another scale than ng/mL
            for tpl in self.TEMPLATES:
                t = tpl.format(u=u, r="{{call_2.cmax}}")
                with self.subTest(t):
                    r = self.bad(t, "contradictory_unit", n=1); self.assertNotIn("12.3457", r["rendered"])
        for t in ("La clairance est {{call_2.cl.obs}}, en L/h.", "CL/F (mL/min) : {{call_2.cl.obs}}"):   # the engine had no dose unit: no L/h
            with self.subTest(t): self.bad(t, "contradictory_unit")
        for t in ("Tmax (min) : {{call_2.tmax}}", "Tmax en minutes : {{call_2.tmax}}", "AUC(0-tlast) (h*mg/L) = {{call_2.auclast}}"):
            with self.subTest(t): self.bad(t, "contradictory_unit")

    def test_the_same_unit_or_another_dimension_is_not_a_contradiction(self):
        for u in ("ng/mL", "µg/L", "ng / mL", "h", "mg", "%", "min"):                    # same unit, same scale (µg/L), or not a concentration
            for tpl in self.TEMPLATES:
                t = tpl.format(u=u, r="{{call_2.cmax}}")
                with self.subTest(t): self.ok(t)
        for t in ("Cmax = {{call_2.cmax}}", "AUC (h·ng/mL) : {{call_2.auclast}}", "Tmax = {{call_2.tmax}} (prélèvement à 1,5 h)",
                  "Tmax = {{call_2.tmax}} après une dose de 100 mg", "Les concentrations sont en ng/mL ; Cmax = {{call_2.cmax}}",
                  "La demi-vie est de {{call_2.half.life}}. Les concentrations sont en mg/L.", "| Paramètre | min | max |\n|---|---|---|\n"
                  "| Cmax | {{call_3.subject=2.cmax}} | {{call_3.subject=1.cmax}} |", "MRT = {{call_2.half.life}}, au min 3 points"):
            with self.subTest(t): self.ok(t)

    def test_unit_dimensions(self):
        same = (("ng/mL", "µg/L"), ("h*ng/mL", "ng·h/mL"), ("h.ng/mL", "h*ng/mL"), ("1/h", "h^-1"), ("1/h", "h⁻¹"), ("L/h", "mL/min"))
        for a, b in same: self.assertEqual(gate_v2.unit_dimension(a)[0], gate_v2.unit_dimension(b)[0], (a, b))
        self.assertFalse(gate_v2.contradicts("µg/L", "ng/mL")); self.assertTrue(gate_v2.contradicts("mg/L", "ng/mL"))
        self.assertTrue(gate_v2.contradicts("L/h", "mL/min")); self.assertFalse(gate_v2.contradicts("h", "ng/mL"))
        self.assertTrue(gate_v2.contradicts("L/h", "dose unit/(h*ng/mL)")); self.assertFalse(gate_v2.contradicts("h", "dose unit/(h*ng/mL)"))
        for u in ("dose unit", "points", "", "mg/kg/j/x", "fois"): self.assertIsNone(gate_v2.unit_dimension(u), u)

    def test_a_per_kg_unit_must_keep_its_kg(self):
        # T-102: with a dose per kg the engine gives L/h/kg and L/kg; another scale or a dropped /kg is not its unit
        for w, r in (("L/h", "L/h/kg"), ("mL/min/kg", "L/h/kg"), ("L", "L/kg"), ("mL/kg", "L/kg"), ("L/h", "L/h / kg")):
            self.assertTrue(gate_v2.contradicts(w, r), (w, r))
        for w, r in (("L/h/kg", "L/h/kg"), ("L·h⁻¹/kg", "L/h/kg"), ("L/kg", "L/kg"), ("h", "L/h/kg"), ("L/h", "L/h"), ("L", "L")):
            self.assertFalse(gate_v2.contradicts(w, r), (w, r))

    # RT-A10 / T-058: sign through emphasis, signs and multipliers in words, English numerals, Unicode numerals
    def test_the_eight_probes_of_rt_a10(self):
        for t in ("Cmax = -**{{call_2.cmax}}**", "Cmax = negative {{call_2.cmax}}", "hundredfold higher than {{call_2.cmax}}",
                  "one third of {{call_2.cmax}}", "Cmax = ½ ng/mL", "The half-life is one hour.", "The half-life is eleven-hour.", "Cmax = ⁹⁹⁹ mg/L."):
            with self.subTest(t): self.bad(t, users=())
        self.ok("**{{call_2.cmax}}**", "**12.3457 ng/mL [Cmax]**")

    def test_a_sign_through_any_emphasis_is_next_to_the_reference(self):
        for w in ("**", "*", "_", "__", "`", "***", "~~"):
            for sign in ("-", "−", "+"):
                for t in (f"Cmax = {sign}{w}{{{{call_2.cmax}}}}{w}", f"Cmax = {w}{sign}{{{{call_2.cmax}}}}{w}", f"Cmax = {sign} {w}{{{{call_2.cmax}}}}{w}",
                          f"Cmax : {sign}{w}{{{{call_2.cmax}}}}{w}", f"({sign}{w}{{{{call_2.cmax}}}}{w})"):
                    with self.subTest(t): self.bad(t, "adjacent_to_reference")
                with self.subTest(w=w): self.ok(f"Cmax = {w}{{{{call_2.cmax}}}}{w}")
            for t in (f"{{{{call_2.cmax}}}}{w} mg/L", f"{w}{{{{call_2.cmax}}}}{w} × 10", f"{{{{call_2.cmax}}}} {w}mg/L{w}"):
                with self.subTest(t): self.bad(t, "adjacent_to_reference")

    def test_signs_in_words_next_to_a_reference(self):
        for t in ("Cmax = negative {{call_2.cmax}}", "Cmax = minus {{call_2.cmax}}", "Cmax = moins {{call_2.cmax}}", "la Cmax est négative de {{call_2.cmax}}",
                  "a negative of {{call_2.cmax}}", "Cmax = **negative** {{call_2.cmax}}"):
            with self.subTest(t): self.bad(t, "adjacent_to_reference", "sign written in words")
        for t in ("la différence est négative : {{call_4.auclast.difference}}", "soit moins de {{call_2.thresholds.max_extrapolated_percent}}",
                  "**Cmax** {{call_2.cmax}}", "{{call_2.cmax}} *(observée)*", "{{call_2.cmax}} **au pic**"):
            with self.subTest(t): self.ok(t)

    def test_multipliers_and_fractions_in_words(self):
        for t in ("hundredfold", "tenfold", "ten-fold", "two fold", "10-fold higher", "2 fois {{call_2.cmax}}", "3 times higher", "one third of the dose",
                  "two thirds of the dose", "a quarter of {{call_2.cmax}}", "thrice", "quadruple", "un cinquième de la dose", "halves"):
            with self.subTest(t): self.bad(t, users=())
        for t in ("a third analysis was run", "le cinquième sujet", "fold change", "une fois l'analyse faite", "les deux analyses"):
            with self.subTest(t): self.ok(t, users=())

    def test_english_numerals_with_a_unit(self):
        for t in ("one hour", "une heure", "one day", "eleven-hour", "a twelve-hour interval", "two-hour", "un litre", "one minute"):
            with self.subTest(t): self.bad(t, "number_word", users=())

    def test_unicode_numerals(self):
        for t in ("Cmax = ½ ng/mL", "Cmax = ¼ mg/L", "Cmax = ⁹⁹⁹ mg/L", "Cmax = ① mg/L", "Cmax = Ⅻ", "{{call_2.cmax}} ²", "Cmax ³⁴ ng/mL", "Cmax = １２ mg/L"):
            with self.subTest(t): self.bad(t, users=())
        for t in ("R² = {{call_2.r.squared}}", "AUC₀₋∞ = {{call_2.aucinf.obs}}", "t½ = {{call_2.half.life}}", "λz en h⁻¹", "AUC (h²·ng/mL)",
                  "10⁻³ près"):
            with self.subTest(t): self.ok(t, users=())

    # RT-A7: the formatting false positives Astra and Sol found stay fixed (non-regression)
    def test_italic_and_list_items_are_not_signs(self):
        for t in ("Cmax = *{{call_2.cmax}}*.", "- {{call_2.cmax}}", "* {{call_2.cmax}}", "+ {{call_2.cmax}}", "  - {{call_2.cmax}}", "- **{{call_2.cmax}}**",
                  "1. {{call_2.cmax}}", "_{{call_2.cmax}}_", "`{{call_2.cmax}}`", "Résultats :\n- Cmax : {{call_2.cmax}}\n- Tmax : *{{call_2.tmax}}*"):
            with self.subTest(t): self.ok(t)
        self.assertEqual(v2("- {{call_2.cmax}}")["rendered"], "- 12.3457 ng/mL [Cmax]")


# ---------------------------------------------------------------- the digest and the records built by the client
class TestDigestRef(unittest.TestCase):
    def test_ref_is_the_first_key_and_subjects_get_their_own(self):
        g = td.GOLDENS["edge_blq_6_subjects"]; units = {}
        apothicaire.render_tool_result("data_import", True, json.dumps(g["data_import_result"]), units)
        shown = apothicaire.render_tool_result("nca_run", True, json.dumps(g["nca_run_result"]), units, ref="call_2")
        self.assertTrue(shown.startswith('{"ref":"call_2",'), shown[:40])
        d = json.loads(shown)
        self.assertEqual([s["ref"] for s in d["subjects"]], [f"call_2.subject={s['subject']}" for s in d["subjects"]])
        self.assertTrue(all(list(s)[0] == "ref" for s in d["subjects"]))
        plain = apothicaire.render_tool_result("nca_run", True, json.dumps(g["nca_run_result"]), units)       # v1: unchanged
        self.assertNotIn('"ref"', plain)
        self.assertEqual(json.loads(plain), {k: v for k, v in d.items() if k != "ref"} | {"subjects": [{k: v for k, v in s.items() if k != "ref"} for s in d["subjects"]]})
        one = json.loads(apothicaire.render_tool_result("nca_run", True, json.dumps(td.GOLDENS["theoph_s1_oral_dose_arg"]["nca_run_result"]), units, ref="call_3"))
        self.assertEqual(one["ref"], "call_3"); self.assertNotIn("ref", one["subjects"][0])                  # one subject: no per-subject ref
        imp = json.loads(apothicaire.render_tool_result("data_import", True, json.dumps(g["data_import_result"]), units, ref="call_1"))
        self.assertEqual(list(imp)[0], "ref")

    def test_ref_record_units_are_the_digests(self):
        g = td.GOLDENS["theoph_s1_oral_dose_arg"]; d, units = td.digest_of(g)
        rec = apothicaire.ref_record("call_2", "nca_run", g["nca_run_result"], {1: units})
        self.assertEqual(rec["structured"], g["nca_run_result"])
        for pname, shown in d["subjects"][0]["parameters"].items():
            unit = shown.partition(" ")[2] if isinstance(shown, str) else ""
            self.assertEqual(rec["units"]["parameters"][pname], unit, pname)
        c = td.load(os.path.join("compare", "theoph_s1_compare_linear_vs_lin_up_log_down.json"))
        u = {1: units, ("analysis", 2): 1, ("analysis", 3): 1}
        rc = apothicaire.ref_record("call_5", "analysis_compare", c["compare_auclast_result"], u)
        self.assertEqual(rc["units"]["rows"]["auclast"], {"a": "h*mg/L", "b": "h*mg/L", "difference": "h*mg/L", "relative_percent": "%", "ratio": ""})
        dc = apothicaire.digest_compare(c["compare_auclast_result"], u)["parameters"]["auclast"]
        self.assertIn("difference -1.6883 h*mg/L", dc)                                                        # the digest is unchanged

# ---------------------------------------------------------------- the static prefix budget
def _tokenizer():
    """A Qwen tokenizer.json from the local Hugging Face cache (the Bonsai 2 family is Qwen-based), or None."""
    paths = [os.environ.get("APOTHICAIRE_TOKENIZER", "")] + glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                                                                   "models--*Qwen*", "snapshots", "*", "tokenizer.json"))
    for p in paths:
        if p and os.path.exists(p):
            try:
                from tokenizers import Tokenizer
                return Tokenizer.from_file(p), p
            except Exception: continue
    return None, None

class TestStaticPrefixBudget(unittest.TestCase):
    MEASURED_V1 = 2434          # docs/design.md: static prefix with the v1 addition and 7 tools, llama.cpp count of 2026-10-09b
    BUDGET = 2500

    def test_v2_addition_keeps_the_prefix_under_the_budget(self):
        a1, a2 = apothicaire.SYSTEM_ADDITION, apothicaire.SYSTEM_ADDITION_V2
        tok, path = _tokenizer()
        if tok is not None:
            delta = len(tok.encode(a2).ids) - len(tok.encode(a1).ids)
            self.assertLessEqual(self.MEASURED_V1 + delta, self.BUDGET, f"v2 adds {delta} tokens ({path})")
        base = optchat.SYSTEM_PROMPT
        for a in apothicaire._ADDITIONS: base = base.replace(a, "")
        tools = json.dumps([apothicaire.to_openai(t) for t in td.load("tools_list.json")["tools"] if t["name"] in apothicaire.EXPOSED])
        est = self.MEASURED_V1 * len(base + a2 + tools) / len(base + a1 + tools)          # proportional estimate, always checked
        self.assertLessEqual(est, self.BUDGET)

    def test_exact_measure_when_a_model_server_is_up(self):
        import httpx
        try: up = httpx.get(optchat.CFG["base_url"] + "/health", timeout=1.0).status_code == 200
        except Exception: up = False
        if not up or not os.path.exists(apothicaire.MCP_BIN): self.skipTest("no llama-server on " + optchat.CFG["base_url"])
        import tempfile, shutil
        tmp = tempfile.mkdtemp(prefix="apo_prefix_")
        try:
            for version in ("v1", "v2"):
                ag = apothicaire.Apothicaire(cfg=dict(optchat.CFG, data_dir=os.path.join(tmp, version)), gate_version=version)
                try: n = apothicaire.static_prefix_tokens(ag)
                finally: ag.close()
                self.assertLessEqual(n, self.BUDGET, version)
        finally: shutil.rmtree(tmp, ignore_errors=True)

    def test_the_addition_keeps_the_invariants_of_v1(self):
        a2 = apothicaire.SYSTEM_ADDITION_V2
        self.assertNotIn("gate", a2.lower()); self.assertNotIn("system reminder", a2)
        self.assertIn("{{call_3.cmax}}", a2); self.assertIn("analysis_compare", a2)
        apothicaire.install_prompt(apothicaire.SYSTEM_ADDITION_V2); self.assertTrue(optchat.SYSTEM_PROMPT.endswith(a2))
        self.assertNotIn(apothicaire.SYSTEM_ADDITION, optchat.SYSTEM_PROMPT)
        apothicaire.install_prompt(apothicaire.SYSTEM_ADDITION); self.assertTrue(optchat.SYSTEM_PROMPT.endswith(apothicaire.SYSTEM_ADDITION))
        self.assertNotIn(a2, optchat.SYSTEM_PROMPT); self.assertEqual(optchat.SYSTEM_PROMPT.count("You are Apothicaire"), 1)
        self.assertEqual(apothicaire.gate_version_of("V2"), "v2"); self.assertEqual(apothicaire.gate_version_of(None), os.environ.get("APOTHICAIRE_GATE", "v1"))
        self.assertEqual(apothicaire.gate_version_of("V3"), "v3")          # gate v3 (gate_v3.py): v2 plus a grammar on the regeneration
        with self.assertRaises(ValueError): apothicaire.gate_version_of("v4")


if __name__ == "__main__":
    unittest.main()
