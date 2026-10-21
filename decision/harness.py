#!/usr/bin/env python
"""Deterministic harness of the decision path (D-01, step 4): the decision model decides, the harness acts and renders.

One `Harness` holds one Caladrius MCP session (the client of apothicaire.py, imported) for one conversation. Per user turn it

  (a) builds the state exactly as decision/make_dataset.py does (`make_dataset.make_state`, `make_dataset.split_first_message`)
      and the closed question set (`make_dataset.questions_for`);
  (b) asks the injected decision model, `decide(state, questions) -> {question: label}` (a label string, or a dict with "label",
      or a bool for a noul question);
  (c) acts on the closed answers: `data_import` once per conversation, `nca_run` with the decided route, the dose of the user's
      sentence and the decided AUC method, `analysis_get` to read the parameter asked (or the settings, for a recall),
      `analysis_compare` on the decided pair, a stated refusal for `is_not_available`, nothing else for `none_needed`;
  (d) renders a French answer from fixed templates. Every number of an answer is an engine value as the digest of apothicaire.py
      shows it ("value unit", 6 significant digits, the unit labelled from the worksheet), or a number the user wrote (the dose of
      the recall). The harness computes nothing: no arithmetic on engine values, no unit conversion, no language model.

What the harness reads from the user's text itself, deterministically (not a decision): the dose amount and its unit token (the
number right before mg / µg / ug / mcg / g / ng), the infusion duration (a number followed by a time unit, "2 h", "90 minutes",
"1,5 h", anywhere in the first message, the first one after the word "perfusion" when there are several), the column names and units
of the CSV header. A missing route, dose, dose unit or infusion duration is asked for, never guessed ("no dose" and "a dose without a
unit" are two different questions); an infusion duration in another time unit than the data is asked again in the data's unit (no
conversion).

Dose unit (2026-10-10, after the review): the analysis of record is run as before (`nca_run` with the dose amount, no unit: CL and V
are labelled "dose unit/..." by the digest, the convention of the benchmark's oracle), and the header of every reading names the dose
with the user's unit. When the user's dose unit is not the mass unit of the concentrations (mg against ng/mL, µg against ng/mL...), the
harness also gives Caladrius the units (`nca_run` option `units`: time, concentration, dose) in a second Caladrius session (so that the
analysis ids of the conversation do not move) and shows, next to every value labelled "dose unit/...", the value converted by
Caladrius ("soit 5.02147 L/h"). The calls of that session are in `unit_log`, not in `tool_log`.

Conventions:
  * the reference analysis of a reading turn is the analysis of the decided AUC method when there is one, else the first NCA of the
    project (the one run with the user's settings);
  * a compare whose AUC method has no analysis yet re-runs the reference analysis with that method (same dose, same route), then asks
    the decision model again on the new state: the dataset describes the compare turn after the re-run (decision/README.md), so the
    pair to compare is decided on that state;
  * the parameters shown are the ones whose `asked_<key>` answer is true, in the engine's order, nothing else: an NCA turn where no
    `asked_*` is true runs the analysis, prints no value and says that no parameter was designated; a reading turn where none is true
    is a recall of the settings (dose, route, AUC method);
  * `is_not_available` = true is checked against the engine, parameter by parameter: the refusal names the parameters asked that
    Caladrius did not compute, and the ones it computed are given in the same answer (a mixed request); when all were computed the
    turn records the conflict (a false refusal would be a wrong answer). With no parameter asked, `is_not_available` = true is an
    out-of-scope request and gets the `not_supported` answer, like `analysis` = `not_supported`;
  * a compare pair "a+b" is directed: `analysis_compare` gets a and b in that order (b minus a, a is the reference) and the answer
    says which analysis is the reference.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
for p in (AGENT, HERE):
    if p not in sys.path: sys.path.insert(0, p)
import apothicaire  # noqa: E402
from numtext import value_text  # noqa: E402,F401  (shared with the digest of apothicaire.py)
import make_dataset as md  # noqa: E402

METHODS = ("linear", "lin_up_log_down")
ENGINE_ROUTE = {"oral": "extravascular", "iv_bolus": "iv_bolus", "iv_infusion": "iv_infusion"}
# parameter key (asked_<key>) -> engine (PKNCA) key; mrt depends on the route (see engine_key)
ENGINE_KEY = {"cmax": "cmax", "tmax": "tmax", "c0": "c0", "auclast": "auclast", "aucinf": "aucinf.obs", "lambda_z": "lambda.z",
              "half_life": "half.life", "cl": "cl.obs", "vz": "vz.obs", "aucpext": "aucpext.obs",
              "lambda_z_points": "lambda.z.n.points", "adj_r2": "adj.r.squared", "tlag": "tlag"}
METHOD_FR = {"linear": "trapèzes linéaires (linear)", "lin_up_log_down": "linear-up/log-down", "lin_log": "lin-log"}
METHOD_SHORT_FR = {"linear": "linéaire", "lin_up_log_down": "linear-up/log-down", "lin_log": "lin-log"}
ANALYSIS_FR = {"fit_pk1": "ajustement d'un modèle à un compartiment", "fit_pk2": "ajustement d'un modèle à deux compartiments",
               "simulate": "simulation à partir d'un modèle ajusté"}

# ---------------------------------------------------------------- templates (French; no number is ever written in them)
T_NO_DATA = ("Je n'ai pas encore de données : collez le tableau concentration-temps (une ligne d'en-tête avec les unités, puis les "
             "mesures), avec la dose, la voie d'administration et la question.")
T_ASK_ROUTE = ("Je ne lance pas l'analyse : la voie d'administration n'est pas indiquée. Précisez-la (bolus intraveineux, perfusion "
               "intraveineuse avec sa durée, ou voie orale).")
T_ASK_DOSE_UNIT = "Je ne lance pas l'analyse : la dose n'a pas d'unité que je reconnaisse. Précisez-la (mg, µg, g...)."
T_ASK_DOSE = "Je ne lance pas l'analyse : je ne trouve pas la dose dans votre message. Indiquez-la avec son unité (mg, µg...)."
T_ASK_DURATION = ("Je ne lance pas l'analyse : la durée de la perfusion n'est pas indiquée. Précisez-la, dans l'unité de temps des "
                  "données ({t}).")
T_ASK_DURATION_UNIT = ("Je ne lance pas l'analyse : la durée de la perfusion est donnée en {u} et les temps des données en {t}. "
                       "Donnez la durée en {t} (je ne convertis pas les unités).")
T_NO_ANALYSIS = ("Aucune analyse n'est encore faite dans ce projet : demandez d'abord une analyse non compartimentale (avec la dose, "
                 "la voie et la méthode d'AUC).")
T_NOT_WIRED = ("Cette demande ({what}) n'est pas encore prise en charge par le harnais de décision : seules l'analyse non "
               "compartimentale, la lecture de ses résultats et la comparaison de deux analyses le sont.")
T_NO_PARAMETER = ("L'analyse non compartimentale est faite, mais votre demande ne désigne aucun paramètre à afficher : "
                  "je ne donne aucune valeur. Indiquez le ou les paramètres voulus (Cmax, Tmax, AUC, λz, t½, CL, Vz, MRT...).")
T_UNDECIDED = "Je n'ai pas pu interpréter la demande ({qs}). Pouvez-vous la reformuler ?"
T_TOOL_FAILED = "Caladrius a refusé l'appel {tool} : « {error} ». Je ne donne aucune valeur."
T_WHICH_PAIR = "Quelles analyses faut-il comparer ? Analyses du projet : {analyses}."
T_NOT_AVAILABLE = "{label} n'est pas calculé par Caladrius pour cette voie d'administration : {route}."
T_NOT_AVAILABLE_REASON = " Raison donnée par Caladrius : « {reason} »."
T_NOT_AVAILABLE_NO_ANALYSIS = "{label} n'est pas calculé par Caladrius pour cette voie d'administration ; aucune analyse n'est encore faite."
T_NOT_AVAILABLE_UNCHECKED = ("Je ne peux pas dire lesquels de ces paramètres Caladrius ne calcule pas pour cette voie ({labels}) : aucune "
                             "analyse n'est encore faite. Demandez d'abord une analyse non compartimentale.")
T_NOT_SUPPORTED = ("Cette demande (hors du périmètre du harnais) n'est pas prise en charge : le harnais de décision sait lancer une analyse "
                   "non compartimentale, en donner les paramètres usuels (Cmax, Tmax, C0, AUC, λz, t½, CL, Vz, MRT, Tlag...), rappeler ses "
                   "réglages et comparer deux analyses ; il ne fait rien d'autre (ni bioéquivalence, ni modèle de population, ni état "
                   "d'équilibre, ni excrétion urinaire, ni explication rédigée). Je ne donne aucune valeur.")
T_CONVERTED = ", soit {value} (conversion faite par Caladrius avec la dose en {unit})"

# ---------------------------------------------------------------- reading the user's text (no arithmetic)
_NUM = r"(?<![\w.,])(\d+(?:[.,]\d+)?)"
_DOSE_RE = re.compile(_NUM + r"\s*(mg|µg|μg|ug|mcg|ng|g)(?![\w/])", re.I)
# a duration: a number and a time unit (the plural, an abbreviation, a decimal comma); bare "s" and "d" are left out (too ambiguous)
_DURATION_RE = re.compile(_NUM + r"\s*(minutes?|mins?|heures?|hours?|hrs?|h|jours?|days?|j|secondes?|sec)(?![\w/])", re.I)
TIME_UNIT = {"minute": "min", "minutes": "min", "min": "min", "mins": "min", "heure": "h", "heures": "h", "hour": "h", "hours": "h",
             "hr": "h", "hrs": "h", "h": "h", "jour": "d", "jours": "d", "day": "d", "days": "d", "j": "d", "d": "d",
             "seconde": "s", "secondes": "s", "sec": "s", "s": "s"}
# a number standing alone (not glued to a letter, a unit or another number): what a dose without its unit looks like ("de 100, voici")
_BARE_NUM_RE = re.compile(r"(?<![\w.,/=^-])\d+(?:[.,]\d+)?(?![\w/^%°]|[.,]\d)")
_HEADER_CELL_RE = re.compile(r"^\s*(.*?)\s*\(([^()]*)\)\s*$")
# mass units as the engine spells them (options.units.dose): the user's token -> engine token
MASS_UNIT = {"g": "g", "mg": "mg", "µg": "ug", "ug": "ug", "mcg": "ug", "ng": "ng"}
ENGINE_TIME_UNITS = ("s", "min", "h", "d")

def parse_number(text):
    """A number as the user wrote it (decimal comma or point): int when it has no decimal part, else float."""
    t = text.replace(",", ".")
    return float(t) if "." in t else int(t)

def parse_dose(sentence):
    """(amount, unit token as written) of the first number followed by a mass unit, or (None, None)."""
    m = _DOSE_RE.search(sentence or "")
    return (parse_number(m.group(1)), m.group(2)) if m else (None, None)

def time_unit_of(token):
    """The time unit of a token ("minutes" -> "min", "heures" -> "h"), or the token itself when it is not one."""
    return TIME_UNIT.get((token or "").strip().lower(), token)

def parse_duration(text):
    """(duration, time unit: h / min / d / s) of an infusion, or (None, None). The duration is a number followed by a time unit anywhere in
    the text ("Perfusion de 150 mg sur 2 h", "pendant 90 minutes", "perfusée sur 1,5 h", "en 2 heures"); when there are several, the
    first one after the word "perfusion" (or "perfusé...") wins, else the first one."""
    text = text or ""
    found = list(_DURATION_RE.finditer(text))
    if not found: return None, None
    cue = re.search(r"perfus", text, re.I)
    after = [m for m in found if cue and m.start() > cue.start()]
    m = (after or found)[0]
    return parse_number(m.group(1)), time_unit_of(m.group(2))

def has_bare_number(text):
    """Whether the text holds a number that is not part of a name (AUC0-t, t1/2, C0), a duration or a dose with its unit: what a dose
    written without its unit looks like. Used to tell "no dose" from "a dose without a unit"."""
    text = _DOSE_RE.sub(" ", _DURATION_RE.sub(" ", text or ""))
    return _BARE_NUM_RE.search(text) is not None

def _mass(token):
    return MASS_UNIT.get((token or "").strip().lower().replace("\u03bc", "\u00b5"))

def _units_digest(d):
    """{subject label: {engine key: "value unit"}} of an nca_run answer run with the `units` option: every computed parameter with the
    unit the engine reports (6 significant digits, as the digest of apothicaire.py shows values)."""
    out = {}
    for s in (d.get("result") or {}).get("subjects", []):
        ok = (s.get("outcome") or {}).get("ok")
        if not ok: continue
        out[str(s.get("subject"))] = {p["name"]: f"{apothicaire._shown(p['value']['value'])} {p.get('unit') or ''}".strip()
                                      for p in ok.get("parameters", []) if "value" in (p.get("value") or {})}
    return out

def needs_conversion(dose_unit, conc_unit):
    """True when the dose's mass unit is not the mass unit of the concentrations (mg against ng/mL): CL and V labelled
    "dose unit/(h*ng/mL)" then need the engine's conversion to be read in L/h and L. False when either unit is unknown."""
    du, cm = _mass(dose_unit), _mass((conc_unit or "").split("/")[0])
    return bool(du and cm and du != cm)

def header_columns(csv_text):
    """data_import columns from a header "time (h),conc (ng/mL)": [{"name", "unit"}]; a cell without a unit gives its name only."""
    out = []
    for cell in csv_text.strip().splitlines()[0].split(","):
        m = _HEADER_CELL_RE.match(cell)
        out.append({"name": m.group(1), "unit": m.group(2).strip()} if m else {"name": cell.strip()})
    return out

def split_message_anywhere(text):
    """make_dataset.split_first_message for a first message written freely (the frozen-set wordings): the table is the first header line
    followed by numeric rows with as many cells, wherever it is (words glued before the header, up to ": ", go to the text before it;
    words glued after the last row go to the text after it); blank lines are dropped. Lines before it are the dose sentence (joined), lines after it the notes, the last line the request. On the benchmark's layout (sentence, table, notes, request) the result is the
    one of split_first_message, so the decision model sees the states it was trained on. A message with nothing after the table takes
    its last line before the table as the request (and as the sentence when it is the only one); a table first takes the first line
    after it as the sentence. No table: split_first_message's answer (csv "")."""
    lines = [l.strip() for l in (text or "").strip().split(chr(10)) if l.strip()]
    data = md._is_data_row
    head = lambda line: line.rpartition(": ")[2]           # the header part of a line: what follows its last ": ", if any
    start = next((i for i in range(len(lines) - 1) if not data(lines[i]) and data(lines[i + 1])
                  and head(lines[i]).count(",") == lines[i + 1].count(",") > 0), None)
    if start is None: return md.split_first_message(text)
    end = start + 1
    while end < len(lines) and data(lines[end]): end += 1
    k = head(lines[start]).count(",")
    glued = end < len(lines) and re.match(r"(-?\d+(?:\.\d+)?(?:,-?\d+(?:\.\d+)?){%d})\s+(\S.*)$" % k, lines[end])
    if glued:                                              # "86,0 500 mg par voie orale...": the last row, then the text after it
        lines = lines[:end] + [glued.group(1), glued.group(2)] + lines[end + 1:]; end += 1
    header, before, after = head(lines[start]), lines[:start], lines[end:]
    if header != lines[start]:                             # "Voici les données : time (h),conc (mg/L)": the words go to the sentence
        before = before + [lines[start][:len(lines[start]) - len(header)].strip()]
    csv = chr(10).join([header] + lines[start + 1:end])
    if before and after: intro, notes, request = " ".join(before), after[:-1], after[-1]
    elif before: intro, notes, request = (" ".join(before[:-1]) or before[-1]), [], before[-1]
    elif after: intro, notes, request = (after[0] if len(after) > 1 else ""), after[1:-1], after[-1]
    else: intro, notes, request = "", [], ""
    return {"intro": intro, "csv": csv, "notes": notes, "request": request}

# ---------------------------------------------------------------- the decision model's answers
def normalize_answers(raw, questions):
    """({question: label or None}, [questions whose answer is outside the offered options]). A label may come as a string, a dict
    with "label" (the typed-decisions gold format) or a bool (noul)."""
    out, outside = {}, []
    raw = raw if isinstance(raw, dict) else {}
    for q, spec in questions.items():
        v = raw.get(q)
        if isinstance(v, dict): v = v.get("label")
        if isinstance(v, bool): v = "true" if v else "false"
        v = None if v is None else str(v)
        opts = set(spec["criteria"]) if spec["type"] == "choice" else {"false", "true"}
        if v not in opts: outside.append(q); v = None
        out[q] = v
    return out, outside

# ---------------------------------------------------------------- rendering (pure functions of engine digests)
def engine_key(param, route):
    """Engine key of a parameter asked (key of make_dataset.PARAMETERS); MRT is mrt.obs after an extravascular dose, mrt.iv.obs otherwise."""
    if param == "mrt": return "mrt.obs" if route == "extravascular" else "mrt.iv.obs"
    return ENGINE_KEY.get(param)

def label_fr(param, route):
    """French label of a parameter; its first words are the labels the oracle of bench/score.py reads (CL/F and Vz/F after an oral dose)."""
    f = "/F" if route == "extravascular" else ""
    return {"cmax": "Cmax", "tmax": "Tmax", "c0": "C0 (concentration initiale extrapolée)", "auclast": "AUC(0-tlast)",
            "aucinf": "AUC(0-inf)", "aucpext": "AUC extrapolée (%)", "lambda_z": "λz (constante d'élimination terminale)",
            "lambda_z_points": "Nombre de points de la régression terminale", "adj_r2": "R² ajusté de la régression terminale",
            "half_life": "t½ (demi-vie terminale)", "cl": f"CL{f} (clairance)", "vz": f"Vz{f} (volume de distribution)",
            "mrt": "MRT (temps moyen de résidence)", "tlag": "Tlag (temps de latence)"}.get(param, param)

def route_fr(route, time_unit=None, with_duration=True):
    if route == "extravascular": return "voie orale (extravasculaire)"
    if route == "iv_bolus": return "bolus intraveineux"
    if isinstance(route, dict) and "iv_infusion" in route:
        d = (route["iv_infusion"] or {}).get("duration")
        if with_duration and d is not None: return f"perfusion intraveineuse de {value_text(d)} {time_unit or '(unité de temps des données)'}"
        return "perfusion intraveineuse"
    return f"{route}"

def _subject_blocks(digest):
    subs = digest.get("subjects") or []
    return [(s, (f"Sujet {s.get('subject')} :" if len(subs) > 1 else None)) for s in subs]

def _not_calculated_reason(subject, key):
    for msg, names in (subject.get("not_calculated_messages") or {}).items():
        if key in names: return msg
    for code, names in (subject.get("not_calculated") or {}).items():
        if key in names: return code
    return None

def _warnings(digest, subject):
    """The engine's unit warnings and quality flags, as it words them. The worksheet's "the dose has no unit" warning is left out when
    the analysis itself received the dose unit (options.units, Harness engine_units): it describes the table, not this analysis."""
    dose_given = bool(((digest.get("options_used") or {}).get("units") or {}).get("dose"))
    out = [f"Avertissement de Caladrius : « {w.get('message', w)} »." for w in (digest.get("unit_warnings") or [])
           if not (dose_given and isinstance(w, dict) and w.get("code") == "missing_unit" and "dose" in str(w.get("message", "")))]
    out += [f"Alerte qualité de Caladrius : « {m} »." for m in (subject.get("flag_messages") or [])]
    return out

def render_header(digest, time_unit=None, dose_unit=None):
    """First line of a reading: which analysis, method, dose and route the values come from (all from the engine; the dose unit is the
    token of the user's message, the analysis of record receives the amount only)."""
    s = (digest.get("subjects") or [{}])[0]
    method = (digest.get("options_used") or {}).get("auc_method")
    dose = s.get("dose")
    dose_txt = (value_text(dose) + (f" {dose_unit}" if dose_unit else "")) if dose is not None else "non indiquée"
    return (f"Résultats de Caladrius (analyse {digest.get('analysis')}, méthode d'AUC {METHOD_FR.get(method, method)}, "
            f"dose {dose_txt}, {route_fr(s.get('route'), time_unit)}) :")

def _converted_text(value, converted, subject, key, dose_unit):
    """", soit 5.02147 L/h (conversion faite par Caladrius avec la dose en mg)" after a value labelled "dose unit/..." when the engine
    converted it (`converted`: {subject label: {engine key: "value unit"}} of the units session), else ""."""
    if not converted or "dose unit" not in str(value): return ""
    c = (converted.get(str(subject)) or {}).get(key)
    return T_CONVERTED.format(value=value_text(c), unit=dose_unit) if c else ""

def render_verdict(digest, subject):
    """The engine's verdict on the extrapolation of AUC(0-inf): not acceptable when Caladrius raised its high-extrapolation flag on
    aucpext.obs, acceptable otherwise, with the engine's threshold (options_used.quality_thresholds). The harness compares nothing."""
    thr = ((digest.get("options_used") or {}).get("quality_thresholds") or {}).get("max_extrapolated_percent")
    thr_txt = f" ({value_text(thr)} %)" if thr is not None else ""
    high = any(isinstance(f, dict) and f.get("code") == "high_extrapolation" and f.get("parameter") == "aucpext.obs"
               for f in (subject.get("flags") or []))
    if high: return f"Extrapolation non acceptable : Caladrius signale que l'AUC extrapolée dépasse son seuil de qualité{thr_txt}."
    return f"Extrapolation acceptable : Caladrius ne signale pas de dépassement de son seuil de qualité{thr_txt}."

def render_params(digest, params, time_unit=None, footer=True, dose_unit=None, converted=None, verdict=False):
    """Lines "- label : value unit" for the parameters asked (keys of make_dataset.PARAMETERS), per subject, in the order of the engine's
    parameters; a parameter Caladrius did not compute is listed with the engine's reason. footer=False writes the not-computed ones
    inline instead of at the end. `dose_unit`: the user's token, written in the header; `converted`: the values of the same analysis
    run by Caladrius with the units (see Harness._converted), written after the values labelled "dose unit/...". `verdict`: when the
    extrapolated percentage is shown, the engine's verdict on it follows (render_verdict, Harness extrapolation_verdict)."""
    lines = [render_header(digest, time_unit, dose_unit)]
    for s, head in _subject_blocks(digest):
        if head: lines.append(head)
        if "parameters" not in s:
            lines.append(f"Caladrius n'a pas pu analyser ce sujet : « {json.dumps(s.get('outcome'), ensure_ascii=False)} ».")
            continue
        route, vals, missing, found = s.get("route"), s["parameters"], [], []
        order = {k: i for i, k in enumerate(vals)}
        for p in params:
            k = engine_key(p, route)
            if k in vals: found.append((order[k], p, k))
            else: missing.append((p, _not_calculated_reason(s, k)))
        lines += [f"- {label_fr(p, route)} : {value_text(vals[k])}" + _converted_text(vals[k], converted, s.get("subject"), k, dose_unit)
                  for _, p, k in sorted(found)]                                                            # the engine's order
        for p, why in missing:
            text = f"{label_fr(p, route)} n'est pas calculé par Caladrius" + (f" (« {why} »)" if why else "") + "."
            lines.append(("- " + text) if not footer else text)
        if verdict and "aucpext" in [p for _, p, _ in found]: lines.append(render_verdict(digest, s))
        lines += _warnings(digest, s)
    return "\n".join(lines)

def render_recall(digest, dose_unit=None, time_unit=None, converted=False):
    """The settings of an analysis as Caladrius recorded them; the dose unit is the token of the user's sentence (the analysis of record
    receives the amount only, unless it was run with options.units (Harness engine_units); `converted`: Caladrius also received the unit,
    in the units session, to convert CL and V)."""
    s = (digest.get("subjects") or [{}])[0]
    method = (digest.get("options_used") or {}).get("auc_method")
    dose = value_text(s.get("dose")) if s.get("dose") is not None else "non indiquée"
    engine_dose = ((digest.get("options_used") or {}).get("units") or {}).get("dose")
    unit = ((f" {dose_unit} (unité de votre premier message, transmise à Caladrius)" if engine_dose else
             f" {dose_unit} (unité de votre premier message ; " + (f"l'analyse {digest.get('analysis')} a reçu la dose sans unité, Caladrius "
             "l'a reçue avec son unité pour convertir la clairance et le volume)" if converted else "Caladrius a reçu la dose sans unité)"))
            if dose_unit else " (sans unité : vous n'en avez pas indiqué)")
    return "\n".join([f"Réglages de l'analyse {digest.get('analysis')} tels que Caladrius les a enregistrés :",
                      f"- Dose : {dose}{unit}",
                      f"- Voie d'administration : {route_fr(s.get('route'), time_unit)}",
                      f"- Méthode d'AUC : {METHOD_FR.get(method, method)}"])

def compare_parts(row):
    """A row of the analysis_compare digest ("a 14.6515 h*mg/L | b 14.3537 h*mg/L | difference ... | percent ... | ratio ...") as
    {"a": "14.6515 h*mg/L", ...}: the shown text split at its separators, nothing parsed as a number."""
    out = {}
    for part in row.split(" | "):
        if part.startswith("not comparable: "): out["not_comparable"] = part[len("not comparable: "):]; continue
        k, _, rest = part.partition(" ")
        out[k] = value_text(rest)
    return out

def render_compare(cdigest, method_a, method_b, route=None):
    """The analysis_compare result (b minus a, computed by Caladrius). method_a / method_b: the AUC methods of the two analyses. The first
    line says which analysis is the reference (a) and which is compared with it (b): the pair is directed."""
    ia, ib = (cdigest.get("a") or {}).get("analysis"), (cdigest.get("b") or {}).get("analysis")
    ma, mb = METHOD_SHORT_FR.get(method_a, method_a), METHOD_SHORT_FR.get(method_b, method_b)
    lines = [f"Comparaison calculée par Caladrius entre l'analyse {ia} et l'analyse {ib} (b - a ; a = analyse {ia}, la référence ; "
             f"b = analyse {ib}, comparée à la référence) :"]
    inv = {v: k for k, v in ENGINE_KEY.items()}; inv.update({"mrt.obs": "mrt", "mrt.iv.obs": "mrt"})
    rows = cdigest.get("parameters") or {}
    for name, row in rows.items():
        p, lab = compare_parts(row), label_fr(inv.get(name, name), route)
        if len(rows) == 1:
            lines += [f"- {lab}, méthode {ma} (analyse {ia}) : {p.get('a', 'aucune valeur')}",
                      f"- {lab}, méthode {mb} (analyse {ib}) : {p.get('b', 'aucune valeur')}"]
            if "difference" in p: lines.append(f"- Différence (b - a) : {p['difference']}")
            if "percent" in p: lines.append(f"- Différence relative : {p['percent']}")
            if "ratio" in p: lines.append(f"- Rapport b/a : {p['ratio']}")
            if "not_comparable" in p: lines.append(f"- Non comparable : « {p['not_comparable']} »")
        else:
            bits = [f"analyse {ia} {p.get('a', 'aucune valeur')}", f"analyse {ib} {p.get('b', 'aucune valeur')}"]
            bits += [f"{fr} {p[k]}" for k, fr in (("difference", "différence"), ("percent", "différence relative"), ("ratio", "rapport b/a")) if k in p]
            lines.append(f"- {lab} : " + " ; ".join(bits))
    for why, names in (cdigest.get("not_comparable") or {}).items():
        lines.append(f"Non comparables (« {why} ») : {', '.join(names)}.")
    if not rows and not cdigest.get("not_comparable"): lines.append("Caladrius ne renvoie aucun paramètre commun.")
    return "\n".join(lines)

def render_refusal(param, digest=None, route=None):
    """The stated refusal of a parameter Caladrius does not compute for the route, with the engine's reason when an analysis exists."""
    lab = label_fr(param, route) if param in ENGINE_KEY or param == "mrt" else "Ce paramètre"
    if digest is None: return T_NOT_AVAILABLE_NO_ANALYSIS.format(label=lab)
    s = (digest.get("subjects") or [{}])[0]
    text = T_NOT_AVAILABLE.format(label=lab, route=route_fr(s.get("route"), with_duration=False))
    why = _not_calculated_reason(s, engine_key(param, s.get("route"))) if param in ENGINE_KEY or param == "mrt" else None
    return text + (T_NOT_AVAILABLE_REASON.format(reason=why) if why else "")

# ---------------------------------------------------------------- the harness
class Harness:
    """One conversation: one MCP session, the project's analyses, the tool log. `decide(state, questions)` is the decision model."""
    def __init__(self, decide, mcp=None, mcp_bin=None, units_mcp=None, engine_units=False, free_layout=False, extrapolation_verdict=False):
        """`units_mcp`: the client of the units session (a second Caladrius session, see the module doc). With the real engine (mcp None)
        it is started on first use; with an injected `mcp` and no `units_mcp`, no conversion is made.

        Three switches for the decider-only arm of the frozen set (bench/NO_LM_ARM.md), all off by default so the D-01 runs and the
        dataset keep their behaviour: `engine_units` gives the analysis of record options.units (time, concentration, the user's dose
        unit), as the agent's client does since T-059, so CL and V come in L/time and L like the frozen gold; `free_layout` reads a first
        message whose table is not on the second line (split_message_anywhere); `extrapolation_verdict` follows the extrapolated
        percentage with the engine's verdict on it (render_verdict), the question set having no question for it."""
        self.decide = decide
        self.engine_units, self.free_layout, self.extrapolation_verdict = engine_units, free_layout, extrapolation_verdict
        self.mcp = mcp if mcp is not None else apothicaire.MCPClient([mcp_bin or apothicaire.MCP_BIN])
        self._units_mcp = units_mcp
        self._units_factory = (lambda: apothicaire.MCPClient([mcp_bin or apothicaire.MCP_BIN])) if mcp is None and units_mcp is None else None
        self._units_ws = None
        self.unit_log = []         # the calls of the units session: turn, name, args, ok, text, shown
        self.converted = {}        # analysis id of record -> {subject label: {engine key: "value unit"}} (Caladrius's conversion)
        self.units = {}            # worksheet id -> units reported by Caladrius (filled by apothicaire.render_tool_result)
        self.tool_log = []         # every MCP call: turn, name, args, ok, text, shown (the digest)
        self.user_texts = []
        self.data = None           # {"intro", "csv", "notes"} of the first message that carried data
        self.worksheet = None
        self.analyses = []         # [{"id", "kind", "auc_method", "args"}] in creation order
        self.turns = 0
        self._info = None

    def close(self):
        self.mcp.close()
        if self._units_mcp is not None: self._units_mcp.close()

    # -- engine calls
    def _call(self, name, args):
        """One MCP call, logged; returns the digest (dict) or None when the call failed (the error text is in the log)."""
        try: ok, text = self.mcp.call(name, args)
        except apothicaire.MCPError as e: ok, text = False, f"mcp error: {e}"
        shown = apothicaire.render_tool_result(name, ok, text, self.units)
        self.tool_log.append({"turn": self.turns, "name": name, "args": args, "ok": ok, "text": text, "shown": shown})
        if not ok: return None
        try: return json.loads(shown)
        except ValueError: return None

    def _failed(self, name):
        last = self.tool_log[-1]
        return T_TOOL_FAILED.format(tool=name, error=last["text"].strip()[:300])

    def _time_unit(self):
        return (self.units.get(self.worksheet) or {}).get("time")

    def _import(self):
        if self.worksheet is None:
            d = self._call("data_import", {"name": "donnees", "csv": self.data["csv"], "columns": header_columns(self.data["csv"])})
            if d is not None: self.worksheet = (d.get("worksheet") or {}).get("id")
        return self.worksheet

    def _run_nca(self, dose, route, method):
        args = {"worksheet": self.worksheet, "dose": dose, "route": route}
        if method: args["options"] = {"auc_method": method}
        if self.engine_units:
            units = apothicaire.nca_units(self.units.get(self.worksheet), _mass(self.dose_unit()))
            if units: args["options"] = {**args.get("options", {}), "units": units}
        d = self._call("nca_run", args)
        if d is None: return None
        self.analyses.append({"id": d.get("analysis"), "kind": "nca", "auc_method": (d.get("options_used") or {}).get("auc_method"), "args": args})
        return d

    # -- the dose unit: the units session
    def _dose_text(self):
        """The text of the first message where the dose, its unit and the infusion duration are read: the dose sentence, then the request."""
        notes = self.data.get("notes") if self.free_layout else None       # a free layout may put the dose on a line of its own
        return "\n".join(t for t in (self.data.get("intro"), *(notes or ()), self.data.get("request")) if t)

    def dose_unit(self):
        """The unit token of the user's dose (first message), or None."""
        return parse_dose(self._dose_text())[1] if self.data else None

    def _conc_unit(self):
        cols = header_columns(self.data["csv"]) if self.data else []
        return cols[1].get("unit") if len(cols) > 1 else None

    def _converted(self, ref):
        """{subject: {engine key: "value unit"}} of analysis `ref` run again by Caladrius with the units (time, concentration, dose) in the
        units session, when the dose unit is not the concentrations' mass unit; None otherwise or when the engine refuses (logged)."""
        if ref is None: return None
        if ref["id"] in self.converted: return self.converted[ref["id"]]
        unit, conc, time_u = self.dose_unit(), self._conc_unit(), time_unit_of(self._time_unit() or "")
        if not (needs_conversion(unit, conc) and time_u in ENGINE_TIME_UNITS): return None
        if self._units_mcp is None:
            if self._units_factory is None: return None
            self._units_mcp = self._units_factory()
        if self._units_ws is None:
            args = {"name": "donnees", "csv": self.data["csv"], "columns": header_columns(self.data["csv"])}
            d = self._unit_call("data_import", args)
            if d is None: self.converted[ref["id"]] = None; return None
            self._units_ws = (d.get("worksheet") or {}).get("id")
        opts = dict((ref["args"].get("options") or {}), units={"time": time_u, "concentration": conc, "dose": _mass(unit)})
        d = self._unit_call("nca_run", {**ref["args"], "worksheet": self._units_ws, "options": opts}, digest=_units_digest)
        self.converted[ref["id"]] = d
        return d

    def _unit_call(self, name, args, digest=None):
        """One call of the units session, logged in unit_log; returns the parsed answer (or its digest) or None."""
        try: ok, text = self._units_mcp.call(name, args)
        except apothicaire.MCPError as e: ok, text = False, f"mcp error: {e}"
        out = None
        if ok:
            try: out = json.loads(text)
            except ValueError: ok = False
        if ok and digest is not None: out = digest(out)
        shown = json.dumps(out, ensure_ascii=False, separators=(",", ":")) if ok and digest is not None else text
        self.unit_log.append({"turn": self.turns, "name": name, "args": args, "ok": ok, "text": text, "shown": shown})
        if not ok: self._info["notes"].append(f"units session: {name} failed: {text.strip()[:200]}")
        return out if ok else None

    def _reference(self, method):
        same = [a for a in self.analyses if a["auc_method"] == method]
        return same[0] if same else (self.analyses[0] if self.analyses else None)

    # -- decisions
    @staticmethod
    def asked(a):
        """The parameters asked: the keys of make_dataset.PARAMETERS whose `asked_<key>` answer is true."""
        return [k for k in md.PARAMETERS if a.get(f"asked_{k}") == "true"]

    def _ask(self, request):
        state = md.make_state(self.data["csv"], self.data["intro"], list(self.data["notes"]), request,
                              [{"id": a["id"], "kind": a["kind"], "auc_method": a["auc_method"]} for a in self.analyses])
        questions = md.questions_for(sorted(a["id"] for a in self.analyses))
        answers, outside = normalize_answers(self.decide(state, questions), questions)
        self._info["decisions"].append({"state": state, "answers": answers, "outside_options": outside,
                                        "model_info": getattr(self.decide, "last_info", None)})   # confidences and seconds of a trained decider
        return answers

    def turn(self, text):
        """One user message -> (answer, info). info: {"decisions": [{"state", "answers", "outside_options"}], "notes": [...]}."""
        self.turns += 1; self.user_texts.append(text)
        self._info = {"decisions": [], "notes": []}
        if self.data is None:
            first = split_message_anywhere(text) if self.free_layout else md.split_first_message(text)
            if not first["csv"]: return T_NO_DATA, self._info
            self.data = {"intro": first["intro"], "csv": first["csv"], "notes": first["notes"], "request": first["request"]}
            request = first["request"]
        else:
            request = text.strip()
        a = self._ask(request)
        return self._act(a, request), self._info

    def _act(self, a, request):
        kind = a["analysis"]
        if kind == "not_supported": return T_NOT_SUPPORTED
        if a["is_not_available"] == "true" and kind != "nca": return self._refuse(a)    # an NCA turn checks availability on its own result
        if kind == "nca": return self._nca(a)
        if kind == "compare": return self._compare(a, request)
        if kind in ANALYSIS_FR: return T_NOT_WIRED.format(what=ANALYSIS_FR[kind])
        if kind == "none_needed": return self._read(a)
        return T_UNDECIDED.format(qs="type d'analyse")

    # -- actions
    def _nca_arguments(self, a):
        """(dose, engine route) of the NCA the decisions ask for, or the template that asks for what is missing: the route, the dose ("no
        dose" and "a dose without a unit" are two questions), the infusion duration (read anywhere in the first message)."""
        text = self._dose_text()
        if a["route"] in (None, "unknown"): return T_ASK_ROUTE
        dose, unit = parse_dose(text)
        if dose is None: return T_ASK_DOSE_UNIT if has_bare_number(text) else T_ASK_DOSE
        if a["dose_has_unit"] != "true": return T_ASK_DOSE_UNIT
        route = ENGINE_ROUTE[a["route"]]
        cols = header_columns(self.data["csv"])
        data_time = cols[0].get("unit") if cols else None
        if route == "iv_infusion":
            dur, dur_unit = parse_duration(text)
            if dur is None: return T_ASK_DURATION.format(t=data_time or "l'unité des données")
            if data_time and dur_unit != time_unit_of(data_time): return T_ASK_DURATION_UNIT.format(u=dur_unit, t=data_time)
            route = {"iv_infusion": {"duration": dur}}
        return dose, route

    def _render(self, d, ps, ref):
        """render_params with the user's dose unit and, when the units differ, Caladrius's conversion of the analysis `ref`."""
        conv = self._converted(ref) if any("dose unit" in str(v) for s in (d.get("subjects") or [])
                                           for k, v in (s.get("parameters") or {}).items()
                                           if k in {engine_key(p, s.get("route")) for p in ps}) else None
        return render_params(d, ps, self._time_unit(), dose_unit=self.dose_unit(), converted=conv, verdict=self.extrapolation_verdict)

    def _nca(self, a):
        args = self._nca_arguments(a)
        if isinstance(args, str): return args
        dose, route = args
        if self._import() is None: return self._failed("data_import")
        method = a["auc_method"] if a["auc_method"] in METHODS else None
        d = self._run_nca(dose, route, method)
        if d is None: return self._failed("nca_run")
        ps = self.asked(a)
        if not ps: return T_NO_PARAMETER
        return self._render(d, ps, self.analyses[-1])

    def _read(self, a):
        ref = self._reference(a["auc_method"])
        if ref is None: return T_NO_ANALYSIS
        d = self._call("analysis_get", {"analysis": ref["id"]})
        if d is None: return self._failed("analysis_get")
        ps = self.asked(a)
        if not ps: return render_recall(d, self.dose_unit(), self._time_unit(), converted=bool(self.converted.get(ref["id"])))
        return self._render(d, ps, ref)

    def _refuse(self, a):
        """`is_not_available` = true on a turn that runs no NCA. No parameter asked: an out-of-scope request (not_supported). Otherwise each
        parameter asked is checked against the reference analysis: the ones Caladrius computed are given, the others are refused by name."""
        ps = self.asked(a)
        if not ps: return T_NOT_SUPPORTED
        ref = self._reference(a["auc_method"])
        if ref is None:                                   # nothing to check against: one parameter is named, several are not guessed
            if len(ps) == 1: return render_refusal(ps[0])
            return T_NOT_AVAILABLE_UNCHECKED.format(labels=", ".join(label_fr(p, None).split(" (")[0] for p in ps))
        d = self._call("analysis_get", {"analysis": ref["id"]})
        if d is None: return self._failed("analysis_get")
        s = (d.get("subjects") or [{}])[0]
        computed = [p for p in ps if engine_key(p, s.get("route")) in (s.get("parameters") or {})]
        if len(computed) == len(ps):                      # the engine did compute them all: their values, not a false refusal
            self._info["notes"].append("is_not_available overruled: Caladrius computed " + ", ".join(engine_key(p, s.get("route")) for p in ps))
            return self._render(d, ps, ref)
        if computed: return self._render(d, ps, ref)      # mixed: the values computed, then the ones not computed with the engine's reason
        return "\n".join(render_refusal(p, d, s.get("route")) for p in ps)

    def _compare(self, a, request):
        if not self.analyses: return T_NO_ANALYSIS
        m = a["auc_method"]
        if m in METHODS and not any(x["auc_method"] == m for x in self.analyses):
            ref = self.analyses[0]
            if self._run_nca(ref["args"]["dose"], ref["args"]["route"], m) is None: return self._failed("nca_run")
            a = self._ask(request)                            # decided again on the state after the re-run
        pair = a["compare_pair"]
        if not pair or "+" not in pair:
            lst = ", ".join(f"analyse {x['id']} (NCA, {METHOD_SHORT_FR.get(x['auc_method'], x['auc_method'])})" for x in self.analyses)
            return T_WHICH_PAIR.format(analyses=lst)
        ia, ib = (int(x) for x in pair.split("+"))
        by_id = {x["id"]: x for x in self.analyses}
        route = (by_id.get(ia) or {}).get("args", {}).get("route")
        args = {"a": ia, "b": ib}
        keys = [engine_key(p, route) for p in self.asked(a)]
        if keys: args["parameters"] = keys
        d = self._call("analysis_compare", args)
        if d is None: return self._failed("analysis_compare")
        return render_compare(d, (by_id.get(ia) or {}).get("auc_method"), (by_id.get(ib) or {}).get("auc_method"), route)
