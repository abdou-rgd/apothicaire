"""Fixed French turn scripts of the Apothicaire benchmark, with the expected-answer rule of each turn.

One script of 8 turns per exercise type (oral, iv_bolus, iv_infusion), built from the exercise's meta.json
(the truth) and its CSV, like run_exo1.py but for 25 exercises:

  1 import_nca           data, dose, route, units, trapezoid method given; asks Cmax, Tmax, AUC, lambda_z, t1/2, CL, Vz, MRT
  2 cmax_tmax            Cmax and Tmax (C0 too after an IV bolus)
  3 clearance_volume     CL(/F) and Vz(/F) "with their units as Caladrius reports them": tempts a unit conversion
  4 half_life            terminal half-life and % of the AUC extrapolated
  5 lambda_z_regression  number of points of the lambda_z regression and the adjusted R2
  6 recall               dose, route and AUC method given in turn 1 (memory)
  7 compare              re-run with lin-up/log-down and "by how much do the two AUC differ, in value and in %":
                         tempts arithmetic. Since the tool `analysis_compare` exists the right answer calls it and quotes its
                         difference and percentage (see `resolve_compare`); the static rule below is the one that applies when
                         the model did not use the tool: quote both values, compute nothing
  8 not_available        a parameter Caladrius did not compute (C0 after an oral dose, Tlag after an IV dose)

Expectation of a turn (JSON-serialisable): {"must": [{"label", "key", "value"}], "must_not": [{"label", "value"}],
"words": [{"label", "pattern"}], "no_new_numbers": bool}; see score.score_turn for how it is applied. `must` values
are Caladrius truth (the oracle), matched with the gate's rounding rule, and carry the analysis (`method`) and the unit
they come from for the oracle check of bench/score.py (`oracle_turn`); `must_not` are the converted / computed
values a wrong answer would contain (a unit factor of the CL and V, the difference, the percentage and the ratio
of the two AUC), without those that coincide with a legitimate number of the exercise.
"""
import csv as _csv, io, os, sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import gate  # noqa: E402
from bench import score  # noqa: E402

KINDS = ("import_nca", "cmax_tmax", "clearance_volume", "half_life", "lambda_z_regression", "recall", "compare", "not_available")
# "the parameter is not available": any of these phrasings (French or English). The turn is also required to
# contain no number outside the sources (no_new_numbers), so a made-up value with a negation still fails.
NOT_AVAILABLE = (r"pas (?:de |d')?(?:valeur|param[èe]tre|r[ée]sultat|d[ée]fini|disponible|calcul|applicable|fourni|renvoy|retourn|rapport)|"
                 r"\bne (?:retourne|renvoie|fournit|donne|calcule|contient|rapporte|produit|permet|peut|dispose)|n'(?:a|est|y a) pas|"
                 r"\bnon (?:calcul|disponible|d[ée]fini|applicable)|impossible|indisponible|sans objet|"
                 r"not (?:calculated|available|applicable|defined|returned)|no value|does not|did not")
UNIT_FR = {"ug": "µg", "mg": "mg"}

def kind_of(meta):
    """Exercise type of the scripts: oral, iv_bolus or iv_infusion."""
    if isinstance(meta["route"], dict): return "iv_infusion"
    return "iv_bolus" if meta["route"] == "iv_bolus" else "oral"

def fr(x):
    """A number the way a French user writes it (decimal comma)."""
    return f"{x:g}".replace(".", ",")

def route_fr(meta):
    if isinstance(meta["route"], dict):
        return f"en perfusion intraveineuse de {fr(meta['route']['iv_infusion']['duration'])} {meta['units']['time']}"
    return "en bolus intraveineux" if meta["route"] == "iv_bolus" else "par voie orale"

def truth_value(meta, key, method="linear"):
    return meta["ground_truth"]["nca"][method]["parameters"][key]["value"]

def csv_numbers(csv_text):
    return [float(x) for row in list(_csv.reader(io.StringIO(csv_text)))[1:] for x in row]

def pool_of(meta, csv_text):
    """Every legitimate number of the exercise: all truth parameters (both methods), the dose, the CSV, the LLOQ."""
    pool = [meta["dose"]["amount"]] + csv_numbers(csv_text)
    if meta.get("blq"): pool.append(meta["blq"]["lloq"])
    for m in meta["ground_truth"]["nca"].values():
        pool += [p["value"] for p in m["parameters"].values()]
    return [abs(float(p)) for p in pool if p]

def _round3(x):
    return gate.round_sig(Decimal(repr(float(x))), 3)

def forbidden(label, base, factors, pool):
    """must_not entries: `base` times each factor, except values that coincide (3 significant digits) with a
    legitimate number of the exercise, which a correct answer may contain."""
    legit = {_round3(p) for p in pool}
    out, seen = [], set()
    for f in factors:
        v = base * f[0]
        if v <= 0 or _round3(v) in legit or _round3(v) in seen: continue
        seen.add(_round3(v)); out.append({"label": f"{label} {f[1]}", "value": v})
    return out

UNIT_FACTORS = [(1e3, "x 10^3"), (1e6, "x 10^6"), (1e-3, "x 10^-3"), (1e-6, "x 10^-6"), (60.0, "x 60"), (1 / 60, "/ 60"),
                (10.0, "x 10"), (100.0, "x 100"), (0.1, "/ 10"), (0.01, "/ 100"), (1e4, "x 10^4"), (1e-4, "x 10^-4")]

def truth_unit(meta, key, method="linear"):
    return meta["ground_truth"]["nca"][method]["parameters"][key]["unit"]

def must(meta, key, label, method="linear"):
    """An expected number: the truth value (the oracle) and, for the oracle check of bench/score.py, the analysis it comes
    from (`method`) and the unit Caladrius reports for it."""
    return {"label": label, "key": key, "value": truth_value(meta, key, method), "method": method,
            "unit": truth_unit(meta, key, method)}

def first_message(meta, csv_text):
    """The first user message of the script (dose / route / units sentence, table, BLQ note, request of the NCA). It needs only the
    route, dose, units, blq and the table of the exercise, not the NCA oracle (decision/eval_ood.py uses it for exercises written blind)."""
    kind = kind_of(meta); u = meta["units"]; du = UNIT_FR[meta["dose"]["unit"]]
    cl_name, vz_name = ("CL/F", "Vz/F") if kind == "oral" else ("CL", "Vz")
    dose_txt = f"{fr(meta['dose']['amount'])} {du}"
    blq = meta.get("blq")
    lines = [f"Voici les données d'un exercice ({dose_txt} {route_fr(meta)} ; temps en {u['time']}, concentration en {u['conc']}) :",
             csv_text.strip()]
    if blq:
        lines.append(f"Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = {fr(blq['lloq'])} {u['conc']}).")
    lines.append(f"Fais l'analyse non compartimentale avec la méthode linéaire des trapèzes et donne-moi Cmax, Tmax, "
                 f"AUC(0-tlast), AUC(0-inf), λz, t½, {cl_name}, {vz_name} et MRT, avec les unités.")
    return chr(10).join(lines)

# ---------------------------------------------------------------- frozen-set wordings (FROZEN_SET.md §5.3)
# A wordings file holds, per turn kind, several questions written by people who never tune the system. The expectation of a
# turn never depends on its wording: build_script builds it from the gold, then the question is replaced. A wording is a
# template; the placeholders below are filled from the exercise (the data, the dose, the route...), in the wording's language.
# Required placeholders make sure every wording asks the question its expectation scores.
WORDING_PLACEHOLDERS = {
    "import_nca": ("table", "dose", "route", "blq_note", "param_list", "time_unit", "conc_unit", "cl_name", "vz_name"),
    "cmax_tmax": ("cmax_params",), "clearance_volume": ("cl_name", "vz_name"), "half_life": (), "lambda_z_regression": (),
    "recall": (), "compare": (), "not_available": ("missing_param",)}
WORDING_REQUIRED = {"import_nca": ("table", "dose", "route", "blq_note", "param_list"), "cmax_tmax": ("cmax_params",),
                    "clearance_volume": ("cl_name", "vz_name"), "not_available": ("missing_param",)}
# what a wording of the kind must also say in words, since the expectation scores it
WORDING_MUST_SAY = {"import_nca": r"lin[ée]air|linear|trap[èe]z|trapezoid", "half_life": r"accept", "compare": r"log[\s_-]*down"}

def wording_values(meta, csv_text, lang="fr"):
    """The values of the placeholders for one exercise, in French or English."""
    kind = kind_of(meta); u = meta["units"]; blq = meta.get("blq"); oral = kind == "oral"
    cl_name, vz_name = ("CL/F", "Vz/F") if oral else ("CL", "Vz")
    if lang == "en":
        num = lambda x: f"{x:g}"
        dose_u = {"ug": "µg", "mg": "mg"}[meta["dose"]["unit"]]
        route = (f"as an intravenous infusion of {num(meta['route']['iv_infusion']['duration'])} {u['time']}" if kind == "iv_infusion"
                 else "as an intravenous bolus" if kind == "iv_bolus" else "orally")
        blq_note = f"Values equal to 0 are below the limit of quantification (LLOQ = {num(blq['lloq'])} {u['conc']})." if blq else ""
        cmax = "the extrapolated initial concentration C0, Cmax and Tmax" if kind == "iv_bolus" else "Cmax and Tmax"
        missing = "the extrapolated initial concentration C0" if oral else "the lag time Tlag"
        plist = f"Cmax, Tmax, AUC(0-tlast), AUC(0-inf), λz, t½, {cl_name}, {vz_name} and MRT"
    else:
        num = fr; dose_u = UNIT_FR[meta["dose"]["unit"]]
        route = route_fr(meta)
        blq_note = f"Les valeurs égales à 0 sont sous la limite de quantification (LLOQ = {fr(blq['lloq'])} {u['conc']})." if blq else ""
        cmax = "la concentration initiale C0 (extrapolée), la Cmax et le Tmax" if kind == "iv_bolus" else "la Cmax et le Tmax"
        missing = "la concentration initiale extrapolée C0" if oral else "le temps de latence Tlag"
        plist = f"Cmax, Tmax, AUC(0-tlast), AUC(0-inf), λz, t½, {cl_name}, {vz_name} et MRT"
    return {"table": csv_text.strip(), "dose": f"{num(meta['dose']['amount'])} {dose_u}", "route": route, "blq_note": blq_note,
            "param_list": plist, "time_unit": u["time"], "conc_unit": u["conc"], "cl_name": cl_name, "vz_name": vz_name,
            "cmax_params": cmax, "missing_param": missing}

def validate_wordings(w, min_per_kind=3):
    """Errors of a wordings file ({"wordings": {kind: [{"text", "author", "lang"}]}}): a kind missing or with fewer than
    `min_per_kind` wordings, an unknown or a missing required placeholder, a wording that does not say what is scored."""
    import string, re as _re
    errs, ws = [], (w or {}).get("wordings") or {}
    for kind in KINDS:
        items = ws.get(kind) or []
        if len(items) < min_per_kind: errs.append(f"{kind}: {len(items)} wordings, {min_per_kind} needed")
        for i, it in enumerate(items):
            text = it.get("text") if isinstance(it, dict) else None
            if not isinstance(text, str) or not text.strip(): errs.append(f"{kind}[{i}]: no text"); continue
            if it.get("lang", "fr") not in ("fr", "en"): errs.append(f"{kind}[{i}]: lang must be fr or en")
            try: names = {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
            except ValueError as e: errs.append(f"{kind}[{i}]: {e}"); continue
            bad = names - set(WORDING_PLACEHOLDERS[kind])
            if bad: errs.append(f"{kind}[{i}]: unknown placeholder(s) {sorted(bad)}")
            miss = set(WORDING_REQUIRED.get(kind, ())) - names
            if miss: errs.append(f"{kind}[{i}]: missing placeholder(s) {sorted(miss)}")
            must = WORDING_MUST_SAY.get(kind)
            if must and not _re.search(must, text, _re.I): errs.append(f"{kind}[{i}]: does not say /{must}/")
    for kind in ws:
        if kind not in KINDS: errs.append(f"unknown kind {kind}")
    return errs

def wording_choice(exercise_id, kind, n, seed):
    """Which of the n wordings of a kind an exercise gets: a seeded draw, the same on every machine (str seeds hash with SHA-512)."""
    import random as _random
    return _random.Random(f"{seed}:{exercise_id}:{kind}").randrange(n)

def apply_wordings(script, meta, csv_text, wordings, seed):
    """The script with each question replaced by its drawn wording; each turn records `wording` = {"index", "author", "lang"}.
    The expectations are untouched."""
    ws = wordings["wordings"]; vals = {}
    out = []
    for t in script:
        items = ws[t["kind"]]; i = wording_choice(meta["id"], t["kind"], len(items), seed); it = items[i]
        lang = it.get("lang", "fr")
        if lang not in vals: vals[lang] = wording_values(meta, csv_text, lang)
        q = it["text"].format(**vals[lang]).strip()
        out.append({**t, "question": q, "wording": {"index": i, "author": it.get("author"), "lang": lang}})
    return out

def build_script(meta, csv_text):
    """The 8 turns for an exercise: [{"id", "kind", "question", "expect"}]."""
    kind = kind_of(meta); u = meta["units"]; du = UNIT_FR[meta["dose"]["unit"]]
    oral = kind == "oral"; iv = not oral
    cl_name, vz_name = ("CL/F", "Vz/F") if oral else ("CL", "Vz")
    mrt_key = "mrt.obs" if oral else "mrt.iv.obs"
    pool = pool_of(meta, csv_text)
    dose_txt = f"{fr(meta['dose']['amount'])} {du}"
    blq = meta.get("blq")
    t1 = first_message(meta, csv_text)
    turns = []
    # 1
    m1 = [must(meta, "cmax", "Cmax"), must(meta, "tmax", "Tmax"), must(meta, "auclast", "AUC(0-tlast)"),
          must(meta, "aucinf.obs", "AUC(0-inf)"), must(meta, "lambda.z", "lambda_z"), must(meta, "half.life", "t1/2"),
          must(meta, "cl.obs", cl_name), must(meta, "vz.obs", vz_name), must(meta, mrt_key, "MRT")]
    mn1 = forbidden(cl_name, truth_value(meta, "cl.obs"), UNIT_FACTORS, pool) + forbidden(vz_name, truth_value(meta, "vz.obs"), UNIT_FACTORS, pool)
    turns.append(("import_nca", t1, {"must": m1, "must_not": mn1}))
    # 2
    if kind == "iv_bolus":
        q2 = "Quelles sont la concentration initiale C0 (extrapolée), la Cmax et le Tmax ?"
        m2 = [must(meta, "c0", "C0"), must(meta, "cmax", "Cmax"), must(meta, "tmax", "Tmax")]
    else:
        q2 = "Quels sont la Cmax et le Tmax ? Donne-les avec leurs unités."
        m2 = [must(meta, "cmax", "Cmax"), must(meta, "tmax", "Tmax")]
    turns.append(("cmax_tmax", q2, {"must": m2}))
    # 3
    q3 = f"Donne-moi {cl_name} et {vz_name} avec leurs unités, exactement comme Caladrius les rapporte."
    turns.append(("clearance_volume", q3, {"must": [must(meta, "cl.obs", cl_name), must(meta, "vz.obs", vz_name)], "must_not": mn1}))
    # 4
    q4 = "Quelle est la demi-vie terminale et quel pourcentage de l'AUC est extrapolé ? Est-ce acceptable ?"
    turns.append(("half_life", q4, {"must": [must(meta, "half.life", "t1/2"), must(meta, "aucpext.obs", "AUC % extrapolated")]}))
    # 5
    q5 = "Combien de points ont servi à la régression de λz et quel est le R² ajusté ?"
    turns.append(("lambda_z_regression", q5, {"must": [must(meta, "lambda.z.n.points", "lambda_z points"),
                                                      must(meta, "adj.r.squared", "adjusted R2")]}))
    # 6
    q6 = "Rappelle-moi la dose, la voie d'administration et la méthode d'AUC que j'ai indiquées au premier message."
    route_words = {"oral": r"orale?|oral|extravasculaire|per os", "iv_bolus": r"bolus|intraveineu|IV|i\.v\.",
                   "iv_infusion": r"perfusion|infusion"}[kind]
    unit_words = r"µg|μg|\bug\b|microgramme" if meta["dose"]["unit"] == "ug" else r"\bmg\b|milligramme"
    turns.append(("recall", q6, {"must": [{"label": "dose", "key": "dose", "value": float(meta["dose"]["amount"]),
                                           "unit": meta["dose"]["unit"]}],
                                 "words": [{"label": "dose unit", "pattern": unit_words},
                                           {"label": "route", "pattern": route_words},
                                           {"label": "method", "pattern": r"lin[ée]aire|linear|trap[èe]ze"}]}))
    # 7
    q7 = ("Refais l'analyse avec la méthode linear-up/log-down. De combien l'AUC(0-tlast) diffère-t-elle de celle de la "
          "méthode linéaire, en valeur absolue et en pourcentage ?")
    a_lin, a_ll = truth_value(meta, "auclast"), truth_value(meta, "auclast", "lin_up_log_down")
    diff, pct, ratio = abs(a_ll - a_lin), abs(a_ll - a_lin) / a_lin * 100, a_ll / a_lin
    comp_factors = [(1.0, "")]
    mn7 = (forbidden("AUC difference", diff, comp_factors, pool + [a_lin, a_ll]) +
           forbidden("AUC difference in % of the linear AUC", pct, comp_factors, pool + [a_lin, a_ll]) +
           forbidden("AUC difference in % of the log-down AUC", diff / a_ll * 100, comp_factors, pool + [a_lin, a_ll]) +
           forbidden("AUC ratio", ratio, comp_factors, pool + [a_lin, a_ll]) +
           forbidden("AUC ratio in %", ratio * 100, comp_factors, pool + [a_lin, a_ll]))
    turns.append(("compare", q7, {"must": [dict(must(meta, "auclast", "AUC(0-tlast) linear"), by_method=True),
                                           dict(must(meta, "auclast", "AUC(0-tlast) lin-up/log-down", "lin_up_log_down"), by_method=True)],
                                  "must_not": mn7, "no_new_numbers": True}))
    # 8
    if oral:
        q8, what = "Quelle est la concentration initiale extrapolée C0 ?", "c0"
    else:
        q8, what = "Quel est le temps de latence Tlag ?", "tlag"
    assert what in meta["ground_truth"]["nca"]["linear"]["not_calculated"], (meta["id"], what)
    turns.append(("not_available", q8, {"words": [{"label": "says it is not available",
                  "pattern": NOT_AVAILABLE}],
                  "no_new_numbers": True, "not_calculated_parameter": what}))
    return [{"id": f"t{i + 1}", "kind": k, "question": q, "expect": e} for i, (k, q, e) in enumerate(turns)]


# ---------------------------------------------------------------- the compare turn when the model used analysis_compare
def compare_truth(meta, reference):
    """What `analysis_compare(a, b)` returns for the AUC(0-tlast) of the two analyses when `reference` (the method of analysis a) is
    'linear' or 'lin_up_log_down', from the ground truth of meta.json alone: {"difference": b - a, "percent": (b - a) / a * 100, "ratio": b / a}."""
    lin, lud = truth_value(meta, "auclast"), truth_value(meta, "auclast", "lin_up_log_down")
    a, b = (lin, lud) if reference == "linear" else (lud, lin)
    return {"difference": b - a, "percent": (b - a) / a * 100.0, "ratio": b / a}

def resolve_compare(turn, meta, usage):
    """The expected-answer rule of the compare turn once it is known what the model did. `turn` is the static turn of build_script
    (the strict rule: both AUC, no computed value allowed); `usage` is score.compare_usage(...). When the model called
    analysis_compare on the two analyses (linear and lin-up/log-down) and the result holds the auclast row with its difference and
    percentage, the engine's difference and percentage are EXPECTED (added to `must`, read from the tool result, unit: the AUC unit and %)
    and ALLOWED (removed from `must_not`: the difference, the percentage of the reference AUC, the ratio b / a); every other computed
    value stays forbidden (the percentage of the other AUC, the inverse ratio, a ratio written as a percentage). Without a usable call the
    static rule applies unchanged. Returns (turn, resolved) with a copy of the turn."""
    if not usage or not usage.get("usable"): return turn, False
    ref, row = usage["reference"], usage["row"]
    expect = {**turn["expect"], "must": list(turn["expect"]["must"]), "must_not": list(turn["expect"].get("must_not", []))}
    auc_unit = truth_unit(meta, "auclast")
    expect["must"] += [{"label": "AUC difference (analysis_compare)", "key": "compare.difference", "value": abs(row["difference"]), "unit": auc_unit},
                       {"label": "AUC difference in % (analysis_compare)", "key": "compare.percent", "value": abs(row["percent"]), "unit": "%"}]
    allowed = {"AUC difference", "AUC difference in % of the linear AUC" if ref == "linear" else "AUC difference in % of the log-down AUC"}
    if ref == "linear": allowed.add("AUC ratio")                 # b / a = log-down / linear is the ratio the script forbids otherwise
    expect["must_not"] = [m for m in expect["must_not"] if m["label"].strip() not in allowed]
    expect["compare_tool"] = {"reference": ref, **row}
    return {**turn, "expect": expect}, True
