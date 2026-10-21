"""Tests of the decision harness (decision/harness.py, decision/run_harness.py; D-01 step 4).

* the French templates on fixed engine results (golden strings), through the digests of apothicaire.py, with a fake MCP client that
  answers synthetic engine JSON;
* the action mapping of every turn kind (which MCP calls, with which arguments) and the refusal / question paths (unknown route,
  missing dose unit, missing infusion duration, a duration in another time unit, a parameter not computed for the route, a fit that
  is not wired, an answer outside the options);
* the state: built exactly as decision/make_dataset.py builds it (compared with the scripted rows of the 25 benchmark exercises);
* end to end against the real caladrius-mcp (skipped when it is not built): one turn, then one whole exercise through
  run_harness.run_exercise with gold decisions, judged by the oracle of bench/score.py.
Synthetic numbers only.
"""
import copy, json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, os.path.join(AGENT, "decision"))
import apothicaire, gate  # noqa: E402
import harness as H  # noqa: E402
import make_dataset as md  # noqa: E402
import run_harness as rh  # noqa: E402
from bench import make_exercises as mk, scripts, score  # noqa: E402

# ---------------------------------------------------------------- a fake engine (synthetic values, engine JSON shapes)
UNIT_WARNING = {"code": "missing_unit", "message": "the dose has no unit; derived units (AUC, clearance, volume) cannot be named"}
WORKSHEET = {"worksheet": {"id": 1, "name": "donnees", "rows": 6, "subjects": ["1"],
                           "columns": [{"name": "time", "role": "time", "unit": "h"}, {"name": "conc", "role": "concentration", "unit": "mg/L"}],
                           "derived_units": {"auc": "h*mg/L", "aumc": "h^2*mg/L", "half_life": "h", "lambda_z": "1/h", "mrt": "h"},
                           "unit_warnings": [UNIT_WARNING]}}
ENGINE_ORDER = ("cmax", "tmax", "auclast", "lambda.z", "adj.r.squared", "lambda.z.n.points", "half.life", "aucinf.obs", "aucpext.obs",
                "mrt.iv.obs", "mrt.obs", "cl.obs", "vz.obs", "tlag")       # the order of the engine's parameters (not the order of the questions)
_LIN = {"cmax": 812.5, "tmax": 1.5, "auclast": 4012.25, "aucinf.obs": 4210.5, "aucpext.obs": 4.7083, "lambda.z": 0.1155,
        "lambda.z.n.points": 4.0, "adj.r.squared": 0.9981, "half.life": 6.0012, "cl.obs": 0.0475, "vz.obs": 0.4113,
        "mrt.obs": 7.25, "mrt.iv.obs": 6.75, "tlag": 0.0}
_LUD = {**_LIN, "auclast": 3950.75, "aucinf.obs": 4149.0, "aucpext.obs": 4.7843, "cl.obs": 0.0482, "vz.obs": 0.4174, "mrt.obs": 7.31, "mrt.iv.obs": 6.81}
VALUES = {"linear": {k: _LIN[k] for k in ENGINE_ORDER}, "lin_up_log_down": {k: _LUD[k] for k in ENGINE_ORDER}}
REASON = "not defined for this route of administration"

class FakeMCP:
    """Answers data_import / nca_run / analysis_get / analysis_compare with synthetic engine JSON; records every call."""
    def __init__(self):
        self.tools = {n: {} for n in ("data_import", "nca_run", "analysis_get", "analysis_compare")}
        self.calls, self.analyses = [], {}

    def call(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "data_import": return True, json.dumps(WORKSHEET)
        if name == "nca_run":
            aid, m = 2 + len(self.analyses), (args.get("options") or {}).get("auc_method", "linear")
            params = [{"name": "c0", "value": {"not_calculated": "not_applicable_to_route"}}] + \
                     [{"name": k, "value": {"value": v}} for k, v in VALUES[m].items()]
            subject = {"subject": "1", "dose": float(args["dose"]), "route": args["route"], "flag_messages": [],
                       "not_calculated_messages": {"c0": REASON}, "outcome": {"ok": {"parameters": params, "flags": []}}}
            self.analyses[aid] = {"id": aid, "kind": "nca", "label": "NCA of donnees, all subjects", "status": {"state": "fresh"},
                                  "spec": {"worksheet": args["worksheet"], "dose": float(args["dose"]), "route": args["route"],
                                           "options": {"auc_method": m}},
                                  "result": {"kind": "nca", "subjects": [subject]}}
            return True, json.dumps(self.analyses[aid])
        if name == "analysis_get":
            if args["analysis"] not in self.analyses: return False, f"unknown_analysis: there is no analysis {args['analysis']}"
            return True, json.dumps(self.analyses[args["analysis"]])
        if name == "analysis_compare":
            info = lambda i: {"analysis": i, "kind": "nca", "label": "NCA of donnees, all subjects", "status": "fresh", "subject": "1"}
            row = {"parameter": "auclast", "a": 4012.25, "b": 3950.75, "difference": -61.5, "difference_unit": None,
                   "relative_percent": -1.5328, "ratio": 0.984672, "unit_a": None, "unit_b": None, "not_comparable": None}
            return True, json.dumps({"a": info(args["a"]), "b": info(args["b"]), "rows": [row]})
        return False, f"unknown tool {name}"

    def close(self): pass

def message(route="par voie orale", dose="400 mg"):
    return (f"Voici les données d'un exercice ({dose} {route} ; temps en h, concentration en mg/L) :\n"
            "time (h),conc (mg/L)\n0,0\n0.5,310.2\n1.5,812.5\n4,520.1\n8,250.3\n12,120.7\n"
            "Fais l'analyse non compartimentale avec la méthode linéaire des trapèzes et donne-moi les paramètres.")

def asking(*keys):
    """The 14 `asked_<key>` answers of the question set: true for the keys given, false for the others."""
    assert set(keys) <= set(md.PARAMETERS), keys
    return {f"asked_{k}": "true" if k in keys else "false" for k in md.PARAMETERS}

BASE = {"analysis": "none_needed", "route": "oral", "auc_method": "not_applicable", "dose_has_unit": "true",
        "is_not_available": "false", "compare_pair": "not_applicable", **asking()}
USUAL = ("cmax", "tmax", "auclast", "aucinf", "lambda_z", "half_life", "cl", "vz", "mrt")        # what the first message of the benchmark asks
NCA = dict(BASE, analysis="nca", auc_method="linear", **asking(*USUAL))

class Scripted:
    """A decision model that answers a fixed sequence of answer sets and records the states it was shown."""
    def __init__(self, *answers): self.answers, self.states = list(answers), []
    def __call__(self, state, questions):
        self.states.append((state, questions)); return self.answers.pop(0)

def run(*turns, msg=None):
    """Runs (answers per decide call, ...) turns: each item is (user text or None for the first message, [answer sets])."""
    answers = [a for _, aa in turns for a in aa]
    dec = Scripted(*answers); h = H.Harness(dec, mcp=FakeMCP()); out = []
    for text, _ in turns: out.append(h.turn(text or msg or message()))
    return h, out, dec

HEADER = "Résultats de Caladrius (analyse 2, méthode d'AUC trapèzes linéaires (linear), dose 400 mg, voie orale (extravasculaire)) :"
WARN = "Avertissement de Caladrius : « the dose has no unit; derived units (AUC, clearance, volume) cannot be named »."
TABLE = "\n".join([HEADER, "- Cmax : 812.5 mg/L", "- Tmax : 1.5 h", "- AUC(0-tlast) : 4012.25 h*mg/L",
                   "- λz (constante d'élimination terminale) : 0.1155 1/h", "- t½ (demi-vie terminale) : 6.0012 h",
                   "- AUC(0-inf) : 4210.5 h*mg/L", "- MRT (temps moyen de résidence) : 7.25 h",
                   "- CL/F (clairance) : 0.0475 dose unit/(h*mg/L)", "- Vz/F (volume de distribution) : 0.4113 dose unit/(mg/L)", WARN])
# all 14 questions true: the engine's order again, and C0 (not computed after an oral dose) said at the end
TABLE_ALL = "\n".join([HEADER, "- Cmax : 812.5 mg/L", "- Tmax : 1.5 h", "- AUC(0-tlast) : 4012.25 h*mg/L",
                       "- λz (constante d'élimination terminale) : 0.1155 1/h", "- R² ajusté de la régression terminale : 0.9981",
                       "- Nombre de points de la régression terminale : 4", "- t½ (demi-vie terminale) : 6.0012 h",
                       "- AUC(0-inf) : 4210.5 h*mg/L", "- AUC extrapolée (%) : 4.7083 %", "- MRT (temps moyen de résidence) : 7.25 h",
                       "- CL/F (clairance) : 0.0475 dose unit/(h*mg/L)", "- Vz/F (volume de distribution) : 0.4113 dose unit/(mg/L)",
                       "- Tlag (temps de latence) : 0 h",
                       "C0 (concentration initiale extrapolée) n'est pas calculé par Caladrius (« not defined for this route of administration »).",
                       WARN])
RECALL = "\n".join(["Réglages de l'analyse 2 tels que Caladrius les a enregistrés :",
                    "- Dose : 400 mg (unité de votre premier message ; Caladrius a reçu la dose sans unité)",
                    "- Voie d'administration : voie orale (extravasculaire)", "- Méthode d'AUC : trapèzes linéaires (linear)"])
COMPARE = "\n".join(["Comparaison calculée par Caladrius entre l'analyse 2 et l'analyse 3 (b - a ; a = analyse 2, la référence ; "
                     "b = analyse 3, comparée à la référence) :",
                     "- AUC(0-tlast), méthode linéaire (analyse 2) : 4012.25 h*mg/L",
                     "- AUC(0-tlast), méthode linear-up/log-down (analyse 3) : 3950.75 h*mg/L",
                     "- Différence (b - a) : -61.5 h*mg/L", "- Différence relative : -1.5328 %", "- Rapport b/a : 0.984672"])
REFUSAL_C0 = ("C0 (concentration initiale extrapolée) n'est pas calculé par Caladrius pour cette voie d'administration : voie orale "
              "(extravasculaire). Raison donnée par Caladrius : « not defined for this route of administration ».")

class TestTemplates(unittest.TestCase):
    """Golden strings: what the harness writes for fixed engine results."""
    def test_nca_prints_the_parameters_asked_in_the_engines_order(self):
        h, out, _ = run((None, [NCA]))
        self.assertEqual(out[0][0], TABLE)
        self.assertNotIn("C0", out[0][0]); self.assertNotIn("Nombre de points", out[0][0])           # not asked, not printed

    def test_every_parameter_asked(self):
        h, out, _ = run((None, [dict(NCA, **asking(*md.PARAMETERS))]))
        self.assertEqual(out[0][0], TABLE_ALL)

    def test_one_parameter_of_the_nca_turn(self):
        h, out, _ = run((None, [dict(NCA, **asking("cmax"))]))
        self.assertEqual(out[0][0], "\n".join([HEADER, "- Cmax : 812.5 mg/L", WARN]))

    def test_order_follows_the_engine_not_the_questions(self):
        """Six parameters asked: printed in the engine's order, which is not the order of the questions."""
        h, out, _ = run((None, [dict(NCA, **asking("half_life", "auclast", "cmax", "vz", "mrt", "cl"))]))
        self.assertEqual(out[0][0], "\n".join([HEADER, "- Cmax : 812.5 mg/L", "- AUC(0-tlast) : 4012.25 h*mg/L", "- t½ (demi-vie terminale) : 6.0012 h",
                                               "- MRT (temps moyen de résidence) : 7.25 h", "- CL/F (clairance) : 0.0475 dose unit/(h*mg/L)",
                                               "- Vz/F (volume de distribution) : 0.4113 dose unit/(mg/L)", WARN]))
        # the question set lists cl, vz, mrt; the engine lists mrt, cl, vz: the printed order is the engine's
        order = list(md.PARAMETERS)
        self.assertLess(order.index("cl"), order.index("vz")); self.assertLess(order.index("vz"), order.index("mrt"))
        self.assertLess(out[0][0].index("MRT"), out[0][0].index("CL/F")); self.assertLess(out[0][0].index("CL/F"), out[0][0].index("Vz/F"))

    def test_nca_with_no_parameter_asked_prints_nothing_numeric(self):
        h, out, _ = run((None, [dict(NCA, **asking())]))
        self.assertEqual(out[0][0], H.T_NO_PARAMETER)
        self.assertIsNone(re.search(r"\d", out[0][0]))
        self.assertEqual([c[0] for c in h.mcp.calls], ["data_import", "nca_run"])          # the analysis is run and recorded, no value is shown

    def test_reading_with_no_parameter_asked_is_the_recall(self):
        h, out, _ = run((None, [NCA]), ("Rappelle-moi.", [BASE]))
        self.assertEqual(out[1][0], RECALL)

    def test_single_parameter(self):
        h, out, _ = run((None, [NCA]), ("Et la clairance ?", [dict(BASE, **asking("cl"))]))
        self.assertEqual(out[1][0], "\n".join([HEADER, "- CL/F (clairance) : 0.0475 dose unit/(h*mg/L)", WARN]))

    def test_recall(self):
        h, out, _ = run((None, [NCA]), ("Rappelle-moi la dose.", [BASE]))
        self.assertEqual(out[1][0], RECALL)

    def test_compare(self):
        cmp_ = dict(BASE, analysis="compare", auc_method="lin_up_log_down", **asking("auclast"), compare_pair="2+3")
        h, out, _ = run((None, [NCA]), ("Compare avec lin-up/log-down.", [cmp_, cmp_]))
        self.assertEqual(out[1][0], COMPARE)

    def test_refusal(self):
        h, out, _ = run((None, [NCA]), ("Quelle est C0 ?", [dict(BASE, is_not_available="true", **asking("c0"))]))
        self.assertEqual(out[1][0], REFUSAL_C0)
        self.assertRegex(out[1][0], scripts.NOT_AVAILABLE)

    def test_value_text_drops_only_a_float_trailing_zero(self):
        self.assertEqual(H.value_text("1701680.0 min*ng/mL"), "1701680 min*ng/mL")
        self.assertEqual(H.value_text(4.0), "4")
        self.assertEqual(H.value_text(0.996288), "0.996288")
        self.assertEqual(H.value_text("10.05 h^2*mg/L"), "10.05 h^2*mg/L")
        self.assertEqual(H.value_text("3.0e-05 1/h"), "3.0e-05 1/h")
        self.assertEqual(H.value_text("-41195.6 min*ng/mL"), "-41195.6 min*ng/mL")

    def test_answers_hold_only_engine_numbers(self):
        """The gate finds no number outside the tool results and the user's messages in any template above."""
        cmp_ = dict(BASE, analysis="compare", auc_method="lin_up_log_down", **asking("auclast"), compare_pair="2+3")
        h, out, _ = run((None, [NCA]), ("cl", [dict(BASE, **asking("cl"))]), ("recall", [BASE]), ("cmp", [cmp_, cmp_]),
                        ("c0", [dict(BASE, is_not_available="true", **asking("c0"))]))
        allowed = gate.allowed_numbers([c["shown"] for c in h.tool_log], h.user_texts)
        for ans, _ in out:
            g = gate.check(ans, allowed=allowed)
            self.assertEqual(g["numbers_unverified"], 0, (ans, g["findings"]))

class TestActions(unittest.TestCase):
    """Which MCP calls each kind of turn makes."""
    def test_import_and_nca_once(self):
        h, out, _ = run((None, [NCA]), ("Cmax ?", [dict(BASE, **asking(*USUAL))]))
        csv = "time (h),conc (mg/L)\n0,0\n0.5,310.2\n1.5,812.5\n4,520.1\n8,250.3\n12,120.7"
        self.assertEqual(h.mcp.calls, [
            ("data_import", {"name": "donnees", "csv": csv, "columns": [{"name": "time", "unit": "h"}, {"name": "conc", "unit": "mg/L"}]}),
            ("nca_run", {"worksheet": 1, "dose": 400, "route": "extravascular", "options": {"auc_method": "linear"}}),
            ("analysis_get", {"analysis": 2})])
        self.assertEqual(out[1][0], TABLE)

    def test_routes(self):
        for phrase, route, want in (("en bolus intraveineux", "iv_bolus", "iv_bolus"),
                                    ("en perfusion intraveineuse de 2 h", "iv_infusion", {"iv_infusion": {"duration": 2}}),
                                    ("en perfusion IV de 0,5 h", "iv_infusion", {"iv_infusion": {"duration": 0.5}})):
            h, _, _ = run((None, [dict(NCA, route=route)]), msg=message(phrase))
            self.assertEqual(h.mcp.calls[1], ("nca_run", {"worksheet": 1, "dose": 400, "route": want, "options": {"auc_method": "linear"}}))

    def test_auc_method_not_applicable_leaves_the_engine_default(self):
        h, _, _ = run((None, [dict(NCA, auc_method="not_applicable")]))
        self.assertEqual(h.mcp.calls[1], ("nca_run", {"worksheet": 1, "dose": 400, "route": "extravascular"}))

    def test_compare_reruns_then_decides_again(self):
        cmp_ = dict(BASE, analysis="compare", auc_method="lin_up_log_down", **asking("auclast"), compare_pair="2+3")
        h, out, dec = run((None, [NCA]), ("Compare.", [cmp_, cmp_]))
        self.assertEqual(h.mcp.calls[2:], [("nca_run", {"worksheet": 1, "dose": 400, "route": "extravascular", "options": {"auc_method": "lin_up_log_down"}}),
                                           ("analysis_compare", {"a": 2, "b": 3, "parameters": ["auclast"]})])
        info = out[1][1]
        self.assertEqual([d["outside_options"] for d in info["decisions"]], [["compare_pair"], []])   # "2+3" is offered only after the re-run
        self.assertEqual([[a["id"] for a in s["analyses"]] for s, _ in dec.states[1:]], [[2], [2, 3]])
        self.assertIn("2+3", dec.states[2][1]["compare_pair"]["criteria"])

    def test_compare_without_a_pair_asks(self):
        cmp_ = dict(BASE, analysis="compare")
        h, out, _ = run((None, [NCA]), ("Compare.", [cmp_]))
        self.assertEqual(out[1][0], "Quelles analyses faut-il comparer ? Analyses du projet : analyse 2 (NCA, linéaire).")
        self.assertEqual([c[0] for c in h.mcp.calls], ["data_import", "nca_run"])

    def test_reading_uses_the_analysis_of_the_decided_method(self):
        cmp_ = dict(BASE, analysis="compare", auc_method="lin_up_log_down", **asking("auclast"), compare_pair="2+3")
        h, out, _ = run((None, [NCA]), ("cmp", [cmp_, cmp_]), ("AUC lud ?", [dict(BASE, auc_method="lin_up_log_down", **asking("auclast"))]),
                        ("AUC ?", [dict(BASE, **asking("auclast"))]))
        self.assertEqual(h.mcp.calls[-2:], [("analysis_get", {"analysis": 3}), ("analysis_get", {"analysis": 2})])
        self.assertIn("- AUC(0-tlast) : 3950.75 h*mg/L", out[2][0]); self.assertIn("- AUC(0-tlast) : 4012.25 h*mg/L", out[3][0])

class TestRefusals(unittest.TestCase):
    """Nothing is run, nothing is guessed: the template says what is missing."""
    def no_engine_call(self, answers, msg=None):
        h, out, _ = run((None, [answers]), msg=msg)
        self.assertEqual(h.mcp.calls, [])
        self.assertIsNone(re.search(r"(?<![A-Za-z])\d", out[0][0]), out[0][0])     # no number (the 0 of "C0" is a name)
        return out[0][0]

    def test_unknown_route(self):
        self.assertEqual(self.no_engine_call(dict(NCA, route="unknown")), H.T_ASK_ROUTE)

    def test_dose_without_unit(self):
        self.assertEqual(self.no_engine_call(dict(NCA, dose_has_unit="false"), msg=message(dose="400")), H.T_ASK_DOSE_UNIT)

    def test_dose_not_found(self):
        self.assertEqual(self.no_engine_call(NCA, msg=message(dose="une dose")), H.T_ASK_DOSE)

    def test_infusion_without_duration(self):
        out = self.no_engine_call(dict(NCA, route="iv_infusion"), msg=message("en perfusion intraveineuse"))
        self.assertEqual(out, H.T_ASK_DURATION.format(t="h"))

    def test_infusion_duration_in_another_unit(self):
        out = self.no_engine_call(dict(NCA, route="iv_infusion"), msg=message("en perfusion intraveineuse de 30 min"))
        self.assertEqual(out, H.T_ASK_DURATION_UNIT.format(u="min", t="h"))

    def test_fit_not_wired(self):
        self.assertEqual(self.no_engine_call(dict(NCA, analysis="fit_pk1")),
                         H.T_NOT_WIRED.format(what="ajustement d'un modèle à un compartiment"))

    def test_answer_outside_the_options(self):
        self.assertEqual(self.no_engine_call(dict(NCA, analysis="dance")), H.T_UNDECIDED.format(qs="type d'analyse"))

    def test_no_data(self):
        h = H.Harness(Scripted(), mcp=FakeMCP())
        self.assertEqual(h.turn("Bonjour, peux-tu m'aider ?")[0], H.T_NO_DATA)

    def test_reading_before_any_analysis(self):
        self.assertEqual(self.no_engine_call(dict(BASE, **asking("cmax"))), H.T_NO_ANALYSIS)

    def test_refusal_before_any_analysis(self):
        out = self.no_engine_call(dict(BASE, is_not_available="true", **asking("c0")))
        self.assertEqual(out, "C0 (concentration initiale extrapolée) n'est pas calculé par Caladrius pour cette voie d'administration ; "
                              "aucune analyse n'est encore faite.")

    def test_refusal_overruled_when_the_engine_computed_the_parameter(self):
        h, out, _ = run((None, [NCA]), ("Tlag ?", [dict(BASE, is_not_available="true", **asking("tlag"))]))
        self.assertEqual(out[1][0], "\n".join([HEADER, "- Tlag (temps de latence) : 0 h", WARN]))
        self.assertEqual(out[1][1]["notes"], ["is_not_available overruled: Caladrius computed tlag"])

    def test_engine_error_is_quoted_not_hidden(self):
        h = H.Harness(Scripted(NCA, dict(BASE, **asking("cmax"))), mcp=FakeMCP())
        h.turn(message()); h.analyses[0]["id"] = 9                       # a stale id: the engine refuses it
        ans = h.turn("Cmax ?")[0]
        self.assertEqual(ans, "Caladrius a refusé l'appel analysis_get : « unknown_analysis: there is no analysis 9 ». Je ne donne aucune valeur.")

    def test_normalize_answers(self):
        qs = md.questions_for([2])
        got, outside = H.normalize_answers({"analysis": {"label": "nca"}, "dose_has_unit": True, "route": "boat"}, qs)
        self.assertEqual((got["analysis"], got["dose_has_unit"], got["route"]), ("nca", "true", None))
        self.assertEqual(sorted(outside), sorted(["auc_method", "compare_pair", "is_not_available", "route"] + [f"asked_{k}" for k in md.PARAMETERS]))

def ood_message(first_line, request=None, conc="mg/L", time_unit="h"):
    """A first message written like the reviewer's natural requests (decision/ood/requests.jsonl): the user's own sentence first, then
    the table, then the request (the sentence again when it holds the request)."""
    return (f"{first_line}\ntime ({time_unit}),conc ({conc})\n0,0\n0.5,310.2\n1.5,812.5\n4,520.1\n8,250.3\n12,120.7\n"
            + (request or first_line))

class FakeMCPng(FakeMCP):
    """The fake engine with a worksheet in ng/mL; with the `units` option, nca_run reports a unit per parameter and CL / V in L/h and L
    (synthetic values: the conversion factor of mg against ng/mL, 1000, applied by this fake engine, not by the harness)."""
    def call(self, name, args):
        ok, text = super().call(name, args)
        d = json.loads(text) if ok else None
        if name == "data_import":
            d["worksheet"]["columns"][1]["unit"] = "ng/mL"
            d["worksheet"]["derived_units"] = {"auc": "h*ng/mL", "aumc": "h^2*ng/mL", "half_life": "h", "lambda_z": "1/h", "mrt": "h"}
            return ok, json.dumps(d)
        units = ((args.get("options") or {}).get("units") or {}) if name == "nca_run" else {}
        if units:
            for p in d["result"]["subjects"][0]["outcome"]["ok"]["parameters"]:
                if p["name"] == "cl.obs": p.update(unit="L/h", value={"value": 47.5})
                elif p["name"] == "vz.obs": p.update(unit="L", value={"value": 411.3})
                elif "value" in p["value"]: p["unit"] = "ng/mL"
            return ok, json.dumps(d)
        return ok, text

class TestReviewDefects(unittest.TestCase):
    """The six harness defects found by the independent review (decision/ood/REVIEW.md, 2026-10-09), each from a failing request of
    decision/ood/requests.jsonl run through the gold path."""
    # 1. infusion duration: 0 of 8 natural wordings were read (ood-008, 010, 011, 037, 043, 055, 062, 070)
    def test_duration_read_anywhere_in_the_message(self):
        cases = {"Perfusion de 150 mg sur 2 h. Donne-moi le Cmax et l'AUC(0-t).": (2, "h"),                         # ood-008
                 "Perfusion de 500 µg pendant 1,5 h, Cmax et AUC0-inf.": (1.5, "h"),                                 # ood-010
                 "Perfusion de 500 µg pendant 90 minutes : que vaut l'AUC(0-t) ?": (90, "min"),                    # ood-011
                 "Perfusion de 150 mg sur 2 h : clairance et volume de distribution.": (2, "h"),                    # ood-037
                 "Perfusion IV de 150 mg sur 2 h, CL et Vz svp.": (2, "h"),                                         # ood-043
                 "Perfusion de 500 µg sur 90 min : Cmax.": (90, "min"),                                             # ood-055
                 "Perfusion de 75 mg sur 1,5 h, les temps sont en minutes : Cmax.": (1.5, "h"),                     # ood-062
                 "Perfusion de 750 µg sur 1 h : Vz et CL.": (1, "h"),                                               # ood-070
                 "perfusion de 30 min": (30, "min"), "perfusée sur 1 h": (1, "h"), "en 2 heures": (2, "h"),
                 "150 mg en perfusion intraveineuse de 2 h": (2, "h"),                                              # the benchmark's wording
                 "Quel est le Tlag de cette perfusion de 150 mg ?": (None, None)}
        for text, want in cases.items(): self.assertEqual(H.parse_duration(text), want, text)

    def test_infusion_runs_with_the_duration_of_a_natural_sentence(self):
        msg = ood_message("Perfusion de 150 mg sur 2 h. Donne-moi le Cmax et l'AUC(0-t).")                                  # ood-008
        h, out, _ = run((None, [dict(NCA, route="iv_infusion", **asking("cmax", "auclast"))]), msg=msg)
        self.assertEqual(h.mcp.calls[1], ("nca_run", {"worksheet": 1, "dose": 150, "route": {"iv_infusion": {"duration": 2}},
                                                      "options": {"auc_method": "linear"}}))
        self.assertIn("- Cmax : 812.5 mg/L", out[0][0])

    def test_minutes_in_words_match_data_in_min(self):
        msg = ood_message("Perfusion de 500 µg pendant 90 minutes : que vaut l'AUC(0-t) ?", time_unit="min")             # ood-011
        h, _, _ = run((None, [dict(NCA, route="iv_infusion", **asking("auclast"))]), msg=msg)
        self.assertEqual(h.mcp.calls[1][1]["route"], {"iv_infusion": {"duration": 90}})

    def test_duration_absent_is_asked_not_guessed(self):
        msg = ood_message("Perfusion intraveineuse de 150 mg : Cmax.")
        h, out, _ = run((None, [dict(NCA, route="iv_infusion", **asking("cmax"))]), msg=msg)
        self.assertEqual(out[0][0], H.T_ASK_DURATION.format(t="h")); self.assertEqual(h.mcp.calls, [])

    # 2. compare direction: "2+1" was outside the options (ood-015, ood-072)
    def test_reversed_pair_is_offered_and_kept_in_order(self):
        rev = dict(BASE, analysis="compare", auc_method="lin_up_log_down", compare_pair="3+2")
        lud = dict(NCA, auc_method="lin_up_log_down")
        h, out, dec = run((None, [NCA]), ("Refais en lin-up/log-down.", [lud]), ("Compare l'analyse 2 à l'analyse 1.", [rev]))
        self.assertEqual(out[2][1]["decisions"][0]["outside_options"], [])
        self.assertEqual(h.mcp.calls[-1], ("analysis_compare", {"a": 3, "b": 2}))
        self.assertTrue(out[2][0].startswith("Comparaison calculée par Caladrius entre l'analyse 3 et l'analyse 2 (b - a ; "
                                             "a = analyse 3, la référence ; b = analyse 2, comparée à la référence) :"), out[2][0])

    # 3. the refusal named the first parameter in table order ("Cmax n'est pas calculé" when C0 is the missing one)
    def test_mixed_request_names_only_the_unavailable_parameter(self):
        mixed = dict(BASE, is_not_available="true", **asking("cmax", "c0"))
        h, out, _ = run((None, [NCA]), ("Donne-moi la Cmax et la C0.", [mixed]))
        ans = out[1][0]
        self.assertIn("- Cmax : 812.5 mg/L", ans)
        self.assertIn("C0 (concentration initiale extrapolée) n'est pas calculé par Caladrius (« not defined for this route of administration »).", ans)
        self.assertNotIn("Cmax n'est pas calculé", ans); self.assertEqual(out[1][1]["notes"], [])

    def test_several_unavailable_are_each_refused_by_name(self):
        both = dict(BASE, is_not_available="true", auc_method="linear", **asking("c0", "tlag"))
        eng = FakeMCP()
        h = H.Harness(Scripted(NCA, both), mcp=eng)
        h.turn(message())
        eng.analyses[2]["result"]["subjects"][0]["outcome"]["ok"]["parameters"] = [
            p for p in eng.analyses[2]["result"]["subjects"][0]["outcome"]["ok"]["parameters"] if p["name"] != "tlag"]
        ans = h.turn("C0 et Tlag ?")[0]
        self.assertEqual(ans.split("\n")[0].split(" n'est pas")[0], "C0 (concentration initiale extrapolée)")
        self.assertTrue(ans.split("\n")[1].startswith("Tlag (temps de latence) n'est pas calculé par Caladrius pour cette voie"), ans)

    def test_several_parameters_before_any_analysis_are_not_guessed(self):
        h, out, _ = run((None, [dict(BASE, is_not_available="true", **asking("cmax", "c0"))]))
        self.assertEqual(out[0][0], H.T_NOT_AVAILABLE_UNCHECKED.format(labels="Cmax, C0")); self.assertEqual(h.mcp.calls, [])

    def test_nca_turn_with_an_unavailable_parameter_runs_and_lets_the_engine_say_which(self):
        h, out, _ = run((None, [dict(NCA, is_not_available="true", **asking("cmax", "c0"))]),
                        msg=ood_message("Prise orale de 400 mg : la Cmax et la C0."))
        self.assertEqual([c[0] for c in h.mcp.calls], ["data_import", "nca_run"])
        self.assertIn("- Cmax : 812.5 mg/L", out[0][0]); self.assertIn("C0 (concentration initiale extrapolée) n'est pas calculé", out[0][0])

    # 4. "no dose" was answered "the dose has no unit" (ood-021); a dose without unit stays a unit question (ood-022)
    def test_no_dose_at_all_asks_for_the_dose(self):
        msg = ood_message("Après une prise orale, voici mes concentrations : quelle est la demi-vie ?")                   # ood-021
        h, out, _ = run((None, [dict(NCA, dose_has_unit="false", **asking("half_life"))]), msg=msg)
        self.assertEqual(out[0][0], H.T_ASK_DOSE); self.assertEqual(h.mcp.calls, [])

    def test_dose_without_unit_asks_for_the_unit(self):
        msg = ood_message("Prise orale de 100, voici les données. Cmax ?")                                                 # ood-022
        for unit_answer in ("false", "true"):                                  # even when the decision says the unit is there
            h, out, _ = run((None, [dict(NCA, dose_has_unit=unit_answer, **asking("cmax"))]), msg=msg)
            self.assertEqual(out[0][0], H.T_ASK_DOSE_UNIT, unit_answer); self.assertEqual(h.mcp.calls, [])

    def test_dose_units_read(self):
        self.assertEqual(H.parse_dose("J'ai pris 0,25 g par voie orale"), (0.25, "g"))                                   # ood-069
        self.assertEqual(H.parse_dose("Bolus de 2000 mcg : CL et Vz."), (2000, "mcg"))                                   # ood-024
        self.assertEqual(H.parse_dose("2 gélules de 100 mg"), (100, "mg"))

    # 5. out-of-scope asks got "not calculated for this route" (ood-019, 020, 064, 065)
    def test_out_of_scope_gets_the_not_supported_answer(self):
        msg = ood_message("Ce produit de 400 mg est-il bioéquivalent au princeps ?")                                       # ood-019
        for answers in (dict(BASE, analysis="not_supported"), dict(BASE, is_not_available="true")):
            h, out, _ = run((None, [answers]), msg=msg)
            self.assertEqual(out[0][0], H.T_NOT_SUPPORTED); self.assertEqual(h.mcp.calls, [])
            self.assertNotIn("pour cette voie", out[0][0])
        self.assertIn("not_supported", md.questions_for([])["analysis"]["criteria"])

    # 6. "2 mg" on a 2000 µg exercise ran dose = 2 silently (ood-023)
    def test_dose_unit_in_the_header_and_conversion_by_the_engine(self):
        msg = ood_message("Bolus IV de 2 mg : donne-moi la clairance et le Vz.", conc="ng/mL")                           # ood-023
        dec = Scripted(dict(NCA, route="iv_bolus", **asking("cl", "vz")), dict(BASE, route="iv_bolus", **asking("cl")),
                       dict(BASE, route="iv_bolus"))
        units = FakeMCPng()
        h = H.Harness(dec, mcp=FakeMCPng(), units_mcp=units)
        ans = h.turn(msg)[0]
        self.assertTrue(ans.startswith("Résultats de Caladrius (analyse 2, méthode d'AUC trapèzes linéaires (linear), dose 2 mg, bolus intraveineux) :"), ans)
        self.assertIn("- CL (clairance) : 0.0475 dose unit/(h*ng/mL), soit 47.5 L/h (conversion faite par Caladrius avec la dose en mg)", ans)
        self.assertIn("- Vz (volume de distribution) : 0.4113 dose unit/(ng/mL), soit 411.3 L (conversion faite par Caladrius avec la dose en mg)", ans)
        # the conversation's session is unchanged (no unit: the benchmark's convention); the units session got the unit
        self.assertEqual(h.mcp.calls[1], ("nca_run", {"worksheet": 1, "dose": 2, "route": "iv_bolus", "options": {"auc_method": "linear"}}))
        self.assertEqual(units.calls[1], ("nca_run", {"worksheet": 1, "dose": 2, "route": "iv_bolus",
                                                      "options": {"auc_method": "linear", "units": {"time": "h", "concentration": "ng/mL", "dose": "mg"}}}))
        allowed = gate.allowed_numbers([c["shown"] for c in h.tool_log + h.unit_log], h.user_texts)
        self.assertEqual(gate.check(ans, allowed=allowed)["numbers_unverified"], 0)
        # a later reading reuses the conversion (no new call); the recall says what each session received
        self.assertIn("soit 47.5 L/h", h.turn("Et la clairance ?")[0]); self.assertEqual(len(units.calls), 2)
        self.assertIn("Caladrius l'a reçue avec son unité pour convertir la clairance et le volume", h.turn("Rappelle-moi la dose.")[0])

    def test_no_conversion_when_the_dose_unit_is_the_concentrations_mass_unit(self):
        units = FakeMCPng()
        h = H.Harness(Scripted(NCA), mcp=FakeMCP(), units_mcp=units)
        ans = h.turn(message())[0]                                             # 400 mg against mg/L
        self.assertEqual(ans, TABLE); self.assertEqual(units.calls, []); self.assertEqual(h.unit_log, [])

    def test_needs_conversion(self):
        self.assertTrue(H.needs_conversion("mg", "ng/mL")); self.assertTrue(H.needs_conversion("µg", "ng/mL"))
        self.assertTrue(H.needs_conversion("mg", "µg/mL")); self.assertFalse(H.needs_conversion("mg", "mg/L"))
        self.assertFalse(H.needs_conversion("mcg", "µg/L")); self.assertFalse(H.needs_conversion(None, "ng/mL"))

    def test_gold_asked_is_accepted_as_the_gold_decider(self):
        if not os.path.exists(rh.BENCH_JSONL): self.skipTest("decision/data/bench.jsonl is not generated")
        self.assertEqual(rh.load_decider("gold-asked").name, rh.load_decider("gold").name)

class TestState(unittest.TestCase):
    """The harness's state is the dataset's state: compared with the scripted-wording rows of the 25 benchmark exercises."""
    def test_states_match_the_dataset(self):
        n = 0
        for d in mk.list_exercises():
            meta, csv = mk.load(d)
            rows = [r for r in md.exercise_rows(meta, csv, True) if json.loads(r["factors"])["scripted_wording"]]
            gold = {rh.state_key(json.loads(r["state"])): (json.loads(r["state"]), {q: g["label"] for q, g in json.loads(r["gold"]).items()})
                    for r in rows}
            seen = []
            def decide(state, questions):
                ref, answers = gold[rh.state_key(state)]
                seen.append((state, ref, questions)); return answers
            h = H.Harness(decide, mcp=FakeMCP())
            for t in scripts.build_script(meta, csv): h.turn(t["question"])
            self.assertEqual(len({rh.state_key(s) for s, _, _ in seen}), 8, meta["id"])
            for state, ref, questions in seen:
                if state["analyses"] == ref["analyses"]:
                    self.assertEqual(state, ref); self.assertEqual(questions, md.questions_for([a["id"] for a in ref["analyses"]])); n += 1
                else:                                                    # a "late" row, or the compare turn before its re-run
                    self.assertEqual({**state, "analyses": None}, {**ref, "analyses": None})
        self.assertGreater(n, 100)

    def test_split_first_message(self):
        meta, csv = mk.load(mk.list_exercises()[0])
        t1 = scripts.build_script(meta, csv)[0]["question"]
        parts = md.split_first_message(t1)
        self.assertEqual(parts["csv"], csv.strip())
        self.assertEqual(parts["intro"], t1.split("\n")[0]); self.assertEqual(parts["request"], t1.split("\n")[-1])
        self.assertEqual(md.split_first_message("Bonjour\nrien\nFais une NCA.")["csv"], "")

def unitless_gold(meta, csv):
    """The exercise with the gold of the harness's convention: nca_run with the dose amount alone, no options.units (CL and V in
    dose unit/...; decision/harness.py), computed by the engine. The benchmark's gold carries the units since T-059."""
    client = apothicaire.MCPClient([apothicaire.MCP_BIN])
    try: truth = mk.run_oracle(client.call, meta, csv, units=False)
    finally: client.close()
    meta = copy.deepcopy(meta); meta["ground_truth"].update(truth)
    return meta

@unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built (see apothicaire.MCP_BIN)")
class TestRealEngine(unittest.TestCase):
    def test_first_turn(self):
        meta, csv = mk.load(os.path.join(mk.OUT, "ex05_iv_infusion"))
        meta = unitless_gold(meta, csv)
        st = scripts.build_script(meta, csv)[0]
        h = H.Harness(lambda s, q: dict(NCA, route="iv_infusion"))
        try: ans, _ = h.turn(st["question"])
        finally: h.close()
        o = score.oracle_turn(ans, st["expect"], meta)
        self.assertTrue(o["correct"], (ans, o))
        allowed = gate.allowed_numbers([c["shown"] for c in h.tool_log], h.user_texts)
        self.assertEqual(gate.check(ans, allowed=allowed)["numbers_unverified"], 0)
        self.assertEqual([c["name"] for c in h.tool_log], ["data_import", "nca_run"])
        self.assertEqual(h.tool_log[1]["args"], meta["ground_truth"]["nca"]["linear"]["nca_run_arguments"] | {"worksheet": 1})

    def test_whole_exercise_with_gold_decisions(self):
        """ex18: AUC values above a million (the trailing '.0' of the 6-digit digest must not reach the answer)."""
        meta, csv = mk.load(os.path.join(mk.OUT, "ex18_pk2_iv_bolus"))
        meta = unitless_gold(meta, csv)
        index = {rh.state_key(json.loads(r["state"])): {q: g["label"] for q, g in json.loads(r["gold"]).items()}
                 for r in md.exercise_rows(meta, csv, True) if json.loads(r["factors"])["scripted_wording"]}
        decide = lambda state, questions: index[rh.state_key(state)]
        with tempfile.TemporaryDirectory() as tmp:
            ex_dir = os.path.join(tmp, meta["id"]); os.makedirs(ex_dir); run_dir = os.path.join(tmp, "run"); os.makedirs(run_dir)
            with open(os.path.join(ex_dir, "meta.json"), "w", encoding="utf-8") as f: json.dump(meta, f, ensure_ascii=False)
            with open(os.path.join(ex_dir, "data.csv"), "w", encoding="utf-8", newline="\n") as f: f.write(csv)
            rec = rh.run_exercise(ex_dir, run_dir, decide)
        turns = rec["turns"]
        self.assertEqual([t.get("error") for t in turns], [None] * 8)
        self.assertTrue(all(t["oracle"]["correct"] for t in turns if t.get("oracle")), [t["answer"] for t in turns])
        # 200 mg against ng/mL: CL and Vz also carry Caladrius's conversion (L/min, L), which the scorer's must_not rule (CL x 10^3,
        # written against a model converting by itself) would read as a conversion; since 2026-10-10 the scorer gets the turn's tool
        # results and the units session's (cached from turn 1 and reused on the clearance turn) and does not count a value copied
        # verbatim from them, so every turn is correct; the converted values are
        # engine values (gate: 0 unverified, the units session is a source)
        for t in turns:
            sc = t["score"]
            self.assertEqual((sc["missing"], sc["forbidden"], sc["words_missing"], sc["new_numbers"]), ([], [], [], 0), t["kind"])
            self.assertTrue(sc["correct"], t["kind"])
            self.assertLessEqual(set(sc["forbidden_from_tools"]), {"CL x 10^3", "Vz x 10^3"}, t["kind"])
        self.assertEqual(set(turns[0]["score"]["forbidden_from_tools"]), {"CL x 10^3", "Vz x 10^3"})
        self.assertEqual(set(turns[2]["score"]["forbidden_from_tools"]), {"CL x 10^3", "Vz x 10^3"})            # clearance turn, cache
        self.assertEqual([c["name"] for c in turns[0]["unit_calls"]], ["data_import", "nca_run"])
        self.assertIn("0.115015 L/min", turns[0]["unit_calls"][1]["shown"])                     # the units session's result is recorded
        self.assertEqual(turns[0]["unit_calls"][1]["args"]["options"]["units"], {"time": "min", "concentration": "ng/mL", "dose": "mg"})
        self.assertIn("soit 0.115015 L/min (conversion faite par Caladrius avec la dose en mg)", turns[0]["answer"])
        self.assertEqual(sum(t["numbers_unverified_after"] for t in turns), 0)
        self.assertEqual(rec["tool_arg_audit"]["deviating_calls"], 0)
        self.assertTrue(turns[6]["compare_tool"]["usable"])

if __name__ == "__main__":
    unittest.main()
