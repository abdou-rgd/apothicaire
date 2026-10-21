"""
Gate v2 for Apothicaire: typed rendering (pure Python, no dependency, no model). Spec: GATE_V2.md.

The model does not write tool numbers: it writes references, {{call_3.cmax}}, and this module replaces each one
with a closed typed assertion read from the structuredContent of that tool call (checked against the tool's
outputSchema): the signed value, the unit and the canonical name of the quantity, "12.3457 ng/mL [Cmax]". Only the
quantities of closed tables are renderable (PARAMETERS, the dose, the selected λz regression, the quality thresholds,
CONVENTIONS, the analysis_compare fields of a parameter); a raw JSON path, a text field (a name, a label, a route, a
status) or a value that is not a number is never rendered. Everything that still looks like a quantity in the text is
checked against the user's own numbers only; tool results are not a source any more. Fail-closed: an unresolvable
reference, a reference to something that is not a typed quantity, a number not in the user's message, a unit or a sign
next to a reference, a unit in the same clause (or table column) that contradicts the rendered one, a number spelled in
words or written with Unicode numeric characters, are replaced by a visible marker and listed in a badge, never
passed through.

  check(answer, calls, user_texts, schemas, decimal_mark) -> {
      "rendered": the text shown to the user,
      "findings": [...], "exempt": [...],
      "numbers_total", "numbers_unverified", "numbers_exempt",        (same keys as gate v1: the bench reads them)
      "references_total", "references_unresolved",                    (references in the typed namespace)
      "references_untyped",                                            (references to a field that is not a quantity)
      "assertions": [{"ref", "analysis", "subject", "quantity", "name", "value", "unit", "path"}]}   (what was rendered)

Aliases (GATE_V2.md, "Reference syntax"): `lambda_z.<field>` names a field of the SELECTED λz regression candidate
(`outcome.ok.lambda_z_candidates[j]` with `selected: true`; fail-closed when none is selected) and `thresholds.<name>` a
quality threshold echoed by the result (`spec.options.quality.<name>`). Both are checked against the schema on their
canonical path. The digest's own labels (`lambda_z_regression.*`, `options_used.quality_thresholds.*`) are NOT paths:
they are rejected with the alias as the closest name.

Named conventions (decision of 2026-10-17): the model never types a domain constant (the 20 % extrapolation limit, the 0.9
adjusted R²); it writes `{{convention.<name>}}` and the renderer prints the value and unit from the closed table CONVENTIONS
below. When a citable analysis echoes that threshold (spec.options.quality), the analysis's value wins, so a threshold the
user changed is never shadowed by the table; two analyses with different values make the convention ambiguous (rejected:
cite `{{call_N.thresholds.<name>}}`).

`calls`: ref -> record built by apothicaire.ref_record: {"ref", "name", "structured", "units"}, where units carries
the labels the client computed at call time ({"dose": u, "parameters": {name: unit}} for an NCA analysis,
{"rows": {parameter: {"a": u, "b": u, "difference": u, "relative_percent": "%", "ratio": ""}}} for a comparison).
`schemas`: tool name -> outputSchema from tools/list (optional; without it the data alone is checked).
"""
import difflib, math, re, unicodedata
from decimal import Decimal

import gate                       # v1: number tokeniser, unit reader, allowed set of the user's numbers
from numtext import value_text

MARK_OPEN, MARK_CLOSE = "⟦", "⟧"

# ---------------------------------------------------------------- the closed tables of renderable quantities
# PKNCA name (as Caladrius returns it) -> the name the renderer prints next to the value. Closed: a parameter the engine
# returns that is not here is not renderable (fail-closed) until it is added with its name. The `.dn` (dose-normalised)
# names are derived below. Source of the list: caladrius-nca units.rs (`unit_of`) and the goldens of tests/golden.
PARAMETERS = {
    "c0": "C0", "cmax": "Cmax", "tmax": "Tmax", "tfirst": "Tfirst", "tlag": "Tlag", "tlast": "Tlast",
    "clast.obs": "Clast,obs", "clast.pred": "Clast,pred",
    "auclast": "AUClast", "aucall": "AUCall", "aucinf.obs": "AUCinf,obs", "aucinf.pred": "AUCinf,pred",
    "aumclast": "AUMClast", "aumcall": "AUMCall", "aumcinf.obs": "AUMCinf,obs", "aumcinf.pred": "AUMCinf,pred",
    "aucpext.obs": "AUC%extrap,obs", "aucpext.pred": "AUC%extrap,pred", "aumcpext.obs": "AUMC%extrap,obs", "aumcpext.pred": "AUMC%extrap,pred",
    "lambda.z": "λz", "r.squared": "R² of λz", "adj.r.squared": "adjusted R² of λz", "lambda.z.n.points": "λz points",
    "lambda.z.time.first": "λz first time", "lambda.z.time.last": "λz last time", "half.life": "half-life", "span.ratio": "span ratio",
    "mrt.last": "MRTlast", "mrt.obs": "MRTinf,obs", "mrt.pred": "MRTinf,pred",
    "mrt.iv.last": "MRTiv,last", "mrt.iv.obs": "MRTiv,obs", "mrt.iv.pred": "MRTiv,pred",
    "cl.obs": "CL,obs", "cl.pred": "CL,pred", "vz.obs": "Vz,obs", "vz.pred": "Vz,pred",
    "vss.obs": "Vss,obs", "vss.pred": "Vss,pred", "vss.iv.last": "Vss,iv,last", "vss.iv.obs": "Vss,iv,obs", "vss.iv.pred": "Vss,iv,pred",
    "aucivlast": "AUCiv,last", "aucivall": "AUCiv,all", "aucivinf.obs": "AUCiv,inf,obs", "aucivinf.pred": "AUCiv,inf,pred",
    "aucivpbextlast": "AUCiv%back-extrap,last", "aucivpbextall": "AUCiv%back-extrap,all",
    "aucivpbextinf.obs": "AUCiv%back-extrap,inf,obs", "aucivpbextinf.pred": "AUCiv%back-extrap,inf,pred",
}
_DN = ("cmax", "clast.obs", "auclast", "aucall", "aucinf.obs", "aucinf.pred", "aumclast", "aumcall", "aumcinf.obs", "aumcinf.pred")
PARAMETERS.update({f"{p}.dn": f"{PARAMETERS[p]}/dose" for p in _DN})

# ---------------------------------------------------------------- display (same rule as the digest, apothicaire._shown)
def _sig(x, n=6):
    return float(f"{x:.{n}g}") if isinstance(x, float) else x

def _shown(x):
    return "0" if x == 0 else value_text(_sig(x))

def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def render_value(v, unit="", decimal_mark="."):
    """The text of a resolved number: 6 significant digits, no ".0" after an integral value, the sign of the engine, the
    unit after a space. Only finite numbers are renderable: a string, a boolean or a list is never a quantity."""
    if not _number(v): raise TypeError(f"not a renderable quantity: {v!r}")
    s = _shown(v)
    if decimal_mark != ".": s = s.replace(".", decimal_mark)
    return f"{s} {unit}".strip() if unit else s

# ---------------------------------------------------------------- references
class Unresolved(Exception):
    """A reference that must not be rendered. `hint` is extra text for the reminder."""
    def __init__(self, reason, hint=None):
        super().__init__(reason); self.reason, self.hint = reason, hint

class Untyped(Unresolved):
    """A reference to something that exists but is not a typed quantity (a raw JSON path, a text field, a flag): never
    rendered, and not counted among the references (references_total counts the typed namespace only)."""

class Resolved:
    """A closed typed assertion: the value and unit of one quantity, its printed name, the subject and the call."""
    __slots__ = ("value", "unit", "path", "kind", "name", "quantity", "subject", "ref", "analysis")
    def __init__(self, value, unit, path, kind, name="", quantity="", subject=None):
        self.value, self.unit, self.path, self.kind = value, unit, list(path), kind
        self.name, self.quantity, self.subject, self.ref, self.analysis = name, quantity, subject, None, None
    def __repr__(self): return f"Resolved({self.value!r}, {self.unit!r}, {self.name!r}, {self.path})"
    def tag(self):
        return self.name + (f", subject {self.subject}" if self.subject is not None else "")
    def render(self, decimal_mark="."):
        """What the client prints in place of the reference: value, unit and, in brackets, the name of the quantity."""
        return f"{render_value(self.value, self.unit, decimal_mark)} [{self.tag()}]"
    def record(self):
        return {"ref": self.ref, "analysis": self.analysis, "subject": self.subject, "quantity": self.quantity, "name": self.name,
                "value": self.value, "unit": self.unit, "path": self.path}

_BRACE_RE = re.compile(r"\{+[^{}\n]*\}+")
_CALL_RE = re.compile(r"^call[_\- ]?(\d+)\s*(?:[.:]\s*(.*))?$", re.I | re.S)
_SEG_RE = re.compile(r"\[(\d+)\]|([^.\[\]]+)")
_SUBJ_RE = re.compile(r"^subject\s*[=: ]\s*(.+)$", re.I)

def parse_ref(body):
    """'call_3.cmax' -> ('call_3', 'cmax'); (None, None) when the body does not start with a call ref."""
    b = re.sub(r"[\"'“”‘’`]", "", body).strip()
    m = _CALL_RE.match(b)
    if not m: return None, None
    return f"call_{int(m.group(1))}", (m.group(2) or "").strip()

def segments(path):
    out = []
    for m in _SEG_RE.finditer(path):
        if m.group(1) is not None: out.append(int(m.group(1)))
        else:
            s = m.group(2).strip()
            if s: out.append(s)
    return out

def _join(segs): return ".".join(str(x) for x in segs)

_TYPED_HELP = ("cite a quantity: a parameter ({{call_N.cmax}}), the dose ({{call_N.dose}}), the selected λz regression "
               "({{call_N.lambda_z.adj_r_squared}}), a threshold ({{call_N.thresholds.max_extrapolated_percent}}), an analysis_compare "
               "field ({{call_N.auclast.difference}}) or a convention ({{convention.max_extrapolated_percent}}); say anything else in words")

def _untyped(path, what="a raw JSON path", alias=None):
    """A reference into the JSON of a result that is not a typed quantity: never rendered (T-055, T-056)."""
    return Untyped(f"{path} is {what}, not a quantity the client prints", (f"closest: {alias}. " if alias else "") + _TYPED_HELP)

_NCA_TOP = ("result", "spec", "id", "label", "status", "kind", "name")
_SUBJECT_KEYS = ("subject", "route", "outcome", "flag_messages", "not_calculated_messages")       # JSON keys of a subject: never quantities
_OK_KEYS = ("flags", "lambda_z_candidates", "parameters", "profile", "removed")                  # JSON keys of outcome.ok

# ---- aliases: the selected λz regression candidate and the quality thresholds (values the plain path syntax cannot name)
_LZ_ALIAS = ("lambda_z", "lambdaz", "lambda-z", "λz")        # `lambda.z` is the PKNCA parameter (the slope), not an alias prefix
_LZ_FIELDS = ("adj_r_squared", "r_squared", "n_points", "time_first", "time_last", "lambda_z", "intercept", "replaced_points")
_LZ_NAMES = {"adj_r_squared": "adjusted R² of λz", "r_squared": "R² of λz", "n_points": "λz points", "time_first": "λz first time",
             "time_last": "λz last time", "lambda_z": "λz", "intercept": "λz intercept", "replaced_points": "λz replaced points"}
_LZ_UNITS = {"lambda_z": "lambda.z", "time_first": "lambda.z.time.first", "time_last": "lambda.z.time.last"}   # the parameter whose unit the field shares
_TH_ALIAS = ("thresholds", "threshold")

# Closed table of named conventions (GATE_V2.md, "Named conventions"). Nothing configurable at runtime. Values = the engine's
# defaults (caladrius-nca options.rs, QualityThresholds::default, spec rule NCA-LZ-12b), which are PKNCA's conventions; the
# source column says where each number comes from. A convention is rendered only when no citable analysis echoes the
# threshold (see resolve_convention).
CONVENTIONS = {
    "max_extrapolated_percent": {"value": 20.0, "unit": "%", "name": "max AUC%extrap", "source": "PKNCA exclusion helper `max.aucinf.pext` (20 %): the usual upper limit on the share of AUCinf that is extrapolated; Caladrius default `quality.max_extrapolated_percent`"},
    "min_adj_r_squared": {"value": 0.9, "unit": "", "name": "min adjusted R²", "source": "PKNCA exclusion helper `min.hl.r.squared` (0.9) on the adjusted R² of the terminal regression; Caladrius default `quality.min_adj_r_squared`"},
    "min_span_ratio": {"value": 2.0, "unit": "", "name": "min span ratio", "source": "PKNCA exclusion helper `min.span.ratio` (2): the regression window must span at least two half-lives; Caladrius default `quality.min_span_ratio`"},
    "min_points": {"value": 3, "unit": "", "name": "min λz points", "source": "PKNCA `min.hl.points` (3): fewest points in a terminal regression; Caladrius defaults `quality.min_points` and `lambda_z.min_points`"},
}
_CONV_RE = re.compile(r"^conventions?\s*[.:]\s*(.+)$", re.I)

def parse_convention(body):
    """'convention.max_extrapolated_percent' -> 'max_extrapolated_percent'; None when the body is not a convention reference."""
    m = _CONV_RE.match(re.sub(r"[\"'“”‘’`]", "", body).strip())
    return m.group(1).strip() if m else None

def echoed_thresholds(name, calls):
    """ref -> value of the threshold `name` echoed by each citable NCA analysis (spec.options.quality)."""
    out = {}
    for ref, c in (calls or {}).items():
        sc = c.get("structured")
        if isinstance(sc, dict) and sc.get("kind") == "nca" and name in _thresholds(sc): out[ref] = _thresholds(sc)[name]
    return out

def resolve_convention(name, calls):
    """The value of a named convention. Precedence: an analysis that echoes the threshold wins over the table; two analyses
    with different values are ambiguous (rejected); the table is used only when no analysis carries the threshold."""
    key = _norm(name)
    if key not in CONVENTIONS:
        close = difflib.get_close_matches(key, list(CONVENTIONS), n=3, cutoff=0.5)
        raise Unresolved(f"no convention {name!r}", ("closest: " + ", ".join(f"convention.{c}" for c in close) + ". " if close else "")
                         + "conventions: " + ", ".join(f"convention.{k}" for k in CONVENTIONS))
    row = CONVENTIONS[key]
    echoed = echoed_thresholds(key, calls)
    if echoed:
        if len(set(echoed.values())) > 1:
            raise Unresolved(f"the analyses use different values of {key} (" + ", ".join(f"{r}: {v}" for r, v in echoed.items()) + ")",
                             "cite the analysis you mean: " + " or ".join(f"{{{{{r}.thresholds.{key}}}}}" for r in echoed))
        ref = list(echoed)[-1]
        r = Resolved(echoed[ref], row["unit"], ["spec", "options", "quality", key], "threshold", f"threshold: {row['name']}", f"thresholds.{key}")
        r.ref = ref; return r                                                                                   # the analysis's own value
    return Resolved(row["value"], row["unit"], ["convention", key], "convention", f"convention: {row['name']}", f"convention.{key}")

def convention_of(value, unit, calls):
    """The hint for a bare number that is a convention typed by hand (rule 7): the alias of an analysis that echoes it, else the convention."""
    for key, row in CONVENTIONS.items():
        same_unit = (unit or "") == row["unit"] or (row["unit"] == "%" and (unit or "").strip() in ("%", "pour cent", "percent"))
        try: same = Decimal(str(value)) == Decimal(str(row["value"]))
        except Exception: same = False
        if same and same_unit:
            echoed = echoed_thresholds(key, calls)
            ref = list(echoed)[-1] if echoed else None
            return f"the convention {key}: write {{{{{ref}.thresholds.{key}}}}}" if ref else f"the convention {key}: write {{{{convention.{key}}}}}"
    return None

def _norm(name): return re.sub(r"[.\-\s]+", "_", str(name).strip()).lower()

def _thresholds(sc):
    """The quality thresholds echoed by an analysis that the closed table names (CONVENTIONS), numbers only."""
    q = ((sc.get("spec") or {}).get("options") or {}).get("quality")
    return {k: v for k, v in q.items() if k in CONVENTIONS and _number(v)} if isinstance(q, dict) else {}

def _resolve_thresholds(sc, rest):
    """{{call_N.thresholds.max_extrapolated_percent}}: a quality threshold echoed by the result (spec.options.quality)."""
    q = _thresholds(sc)
    if not q: raise Unresolved("this analysis carries no quality thresholds")
    if not rest: raise Unresolved("say which threshold: thresholds.<name>", "thresholds: " + ", ".join(q))
    name = _norm(_join(rest))
    if name not in q:
        close = difflib.get_close_matches(name, list(q), n=3, cutoff=0.5)
        raise Unresolved(f"no quality threshold {name!r}", ("closest: " + ", ".join(f"thresholds.{c}" for c in close) + ". " if close else "")
                         + "thresholds: " + ", ".join(f"thresholds.{k}" for k in q))
    return Resolved(q[name], CONVENTIONS[name]["unit"], ["spec", "options", "quality", name], "threshold",
                    f"threshold: {CONVENTIONS[name]['name']}", f"thresholds.{name}")

def _selected_candidates(ok):
    return [(j, c) for j, c in enumerate((ok or {}).get("lambda_z_candidates") or []) if isinstance(c, dict) and c.get("selected") is True]

def _resolve_lambda_z(ok, rest, units, base, subject):
    """{{call_N.lambda_z.adj_r_squared}}: a field of the SELECTED λz regression candidate (fail-closed when none is selected)."""
    sel = _selected_candidates(ok)
    if not sel: raise Unresolved("no λz regression candidate is selected in this analysis: say that Caladrius did not retain one")
    if len(sel) > 1: raise Unresolved(f"{len(sel)} λz candidates are marked selected: the selection is ambiguous")
    j, c = sel[0]
    fields = [k for k in _LZ_FIELDS if _number(c.get(k))]
    if not rest: raise Unresolved("say which field of the selected regression: lambda_z.<field>", "fields: " + ", ".join(f"lambda_z.{k}" for k in fields))
    name = _norm(_join(rest))
    if name not in fields:
        close = difflib.get_close_matches(name, fields, n=3, cutoff=0.5)
        raise Unresolved(f"no field {name!r} in the selected λz regression", ("closest: " + ", ".join(f"lambda_z.{k}" for k in close) + ". " if close else "")
                         + "fields: " + ", ".join(f"lambda_z.{k}" for k in fields))
    unit = (units.get("parameters") or {}).get(_LZ_UNITS[name], "") if name in _LZ_UNITS else ""
    return Resolved(c[name], unit, base + ["outcome", "ok", "lambda_z_candidates", j, name], "lambda_z", _LZ_NAMES[name], f"lambda_z.{name}", subject)

def _alias_hint(key, sc, ok):
    """The alias an invented path most likely meant. The digest labels the selected candidate `lambda_z_regression` and the
    thresholds `options_used.quality_thresholds`; the grammar names them `lambda_z.<field>` and `thresholds.<name>`."""
    low = key.lower(); segs = [_norm(s) for s in segments(key)]
    sel = _selected_candidates(ok)
    fields = set(_LZ_FIELDS) | ({k for k in sel[0][1] if k not in ("selected", "valid")} if len(sel) == 1 else set())
    q = _thresholds(sc)
    for k in (3, 2, 1):
        if len(segs) <= k: continue                                   # the first segment is the invented prefix, never part of the field
        name = "_".join(segs[-k:])
        if name in fields and re.search(r"lambda|λ|regress|candidate", low): return f"lambda_z.{name}"
        if name in q and re.search(r"threshold|quality|option|limit", low): return f"thresholds.{name}"
    return None

def _resolve_nca(sc, segs, units):
    """{{call_N.cmax}}, {{call_N.subject=2.cmax}}, {{call_N.dose}}; a `parameters.` prefix and a `.value` suffix are ignored."""
    if isinstance(segs[0], int) or segs[0] in _NCA_TOP: raise _untyped(_join(segs))                     # a raw JSON path (T-056)
    if isinstance(segs[0], str) and segs[0].lower() in _TH_ALIAS: return _resolve_thresholds(sc, segs[1:])   # analysis-level, no subject
    subjects = (sc.get("result") or {}).get("subjects") or []
    labels = ", ".join(str(s.get("subject")) for s in subjects)
    m = _SUBJ_RE.match(segs[0]) if isinstance(segs[0], str) else None
    if m:
        label = m.group(1).strip().strip("\"'")
        idx = next((i for i, s in enumerate(subjects) if str(s.get("subject")) == label), None)
        if idx is None: raise Unresolved(f"no subject {label!r} in this analysis", f"subjects: {labels}")
        rest = segs[1:]
    elif len(subjects) == 1: idx, rest = 0, segs
    elif not subjects: raise Unresolved("the analysis has no subject")
    else: raise Unresolved(f"the analysis has {len(subjects)} subjects: write subject=LABEL before the parameter", f"subjects: {labels}")
    if not rest: raise Unresolved("name a parameter after the ref, e.g. {{call_N.cmax}}")
    if isinstance(rest[0], str) and rest[0].lower() in _TH_ALIAS: return _resolve_thresholds(sc, rest[1:])
    s = subjects[idx]; base = ["result", "subjects", idx]
    shown = str(s.get("subject")) if len(subjects) > 1 else None             # printed with the value when the analysis has several
    key = _join(rest)
    if key.startswith("parameters."): key = key[len("parameters."):]
    if key.endswith(".value"): key = key[:-len(".value")]
    if key == "dose":
        if s.get("dose") is None: raise Unresolved("this subject has no dose")
        return Resolved(s["dose"], units.get("dose") or "", base + ["dose"], "dose", "dose", "dose", shown)
    first = key.split(".")[0]
    if any(isinstance(x, int) for x in rest) or first in _SUBJECT_KEYS or first in _OK_KEYS:
        raise _untyped(key, "a text field" if key in ("route", "subject") else "a raw JSON path", _alias_hint(key, sc, (s.get("outcome") or {}).get("ok")))
    oc = s.get("outcome") or {}
    if "ok" not in oc: raise Unresolved(f"subject {s.get('subject')} has no result: {oc.get('error', 'error')}")
    ok = oc["ok"] or {}
    if len(rest) >= 2 and isinstance(rest[0], str) and _norm(rest[0]) in _LZ_ALIAS:     # `lambda_z` alone stays a parameter name
        return _resolve_lambda_z(ok, rest[1:], units, base, shown)
    params = ok.get("parameters") or []
    names = [p.get("name") for p in params]
    if key not in names and key.lower() in names: key = key.lower()
    if key in names:
        j = names.index(key); v = params[j].get("value") or {}
        if "value" not in v:
            raise Unresolved(f"{key} was not calculated ({v.get('not_calculated')}): say that Caladrius did not return it")
        if key not in PARAMETERS: raise Unresolved(f"{key} is not in the renderer's table of parameters: say that it cannot be cited")
        unit = params[j].get("unit") or (units.get("parameters") or {}).get(key, "")
        return Resolved(v["value"], unit, base + ["outcome", "ok", "parameters", j, "value", "value"], "parameter", PARAMETERS[key], key, shown)
    computed = sorted(n for n, p in zip(names, params) if "value" in (p.get("value") or {}))
    alias = _alias_hint(key, sc, ok)
    close = ([alias] if alias else []) + difflib.get_close_matches(key, computed, n=3, cutoff=0.5)
    raise Unresolved(f"no parameter {key!r} in this analysis",
                     ("closest: " + ", ".join(close) + ". " if close else "") + "computed parameters: " + ", ".join(computed))

_COMPARE_FIELDS = {"a": "a", "b": "b", "difference": "difference", "diff": "difference", "delta": "difference",
                   "percent": "relative_percent", "relative_percent": "relative_percent", "pct": "relative_percent",
                   "ratio": "ratio"}

def _resolve_compare(sc, segs, units):
    """{{call_N.auclast.difference}} / .percent / .ratio / .a / .b from an analysis_compare answer."""
    s0 = segs[0]
    if isinstance(s0, str) and s0 in sc and (s0 != "rows" or (len(segs) > 1 and isinstance(segs[1], int))) and \
            (s0 not in ("a", "b") or len(segs) > 1): raise _untyped(_join(segs))     # a raw JSON path (a.analysis, rows[0].a ...)
    rows = sc.get("rows") or []; names = [r.get("parameter") for r in rows]
    last = str(segs[-1]).lower() if len(segs) >= 2 else None
    field = _COMPARE_FIELDS.get(last) if last else None
    if field is None:
        raise Unresolved(f"{_join(segs)}: say which field of the comparison: .a, .b, .difference, .percent or .ratio")
    param = _join(segs[:-1])
    if param not in names and param.lower() in names: param = param.lower()
    if param not in names:
        close = difflib.get_close_matches(param, names, n=3, cutoff=0.5)
        raise Unresolved(f"{param!r} is not a compared parameter", ("closest: " + ", ".join(close) + ". " if close else "") +
                         "compared: " + ", ".join(str(n) for n in names[:30]))
    if param not in PARAMETERS: raise Unresolved(f"{param} is not in the renderer's table of parameters: say that it cannot be cited")
    k = names.index(param); row = rows[k]
    if row.get("a") is None and row.get("b") is None:
        raise Unresolved(f"{param} is not comparable: {row.get('not_comparable') or 'no value'}")
    v = row.get(field)
    if v is None: raise Unresolved(f"{param}.{last}: no value ({row.get('not_comparable') or 'missing on one side'})")
    unit = ((units.get("rows") or {}).get(param) or {}).get(field, "") or ("%" if field == "relative_percent" else "")
    return Resolved(v, unit, ["rows", k, field], "compare", f"{PARAMETERS[param]}, {_COMPARE_NAMES[field]}", f"{param}.{field}")

_COMPARE_NAMES = {"a": "a", "b": "b", "difference": "b−a", "relative_percent": "(b−a)/a", "ratio": "b/a"}

def resolve(ref, path, calls, schemas=None):
    """The value a reference names, or Unresolved. `calls`: ref -> record (see the module docstring)."""
    c = calls.get(ref) if calls else None
    if c is None: raise Unresolved(f"{ref} is not a tool result of this chat", "available: " + ", ".join(calls or ()) if calls else None)
    sc = c.get("structured")
    if sc is None: raise Unresolved(f"{ref} ({c.get('name')}) has no structured result to cite (a tool error?)")
    segs = segments(path)
    if not segs: raise Unresolved("a reference needs a path after the ref, e.g. {{call_N.cmax}}")
    units = c.get("units") or {}
    if isinstance(sc, dict) and sc.get("kind") == "nca" and isinstance(sc.get("result"), dict): r = _resolve_nca(sc, segs, units)
    elif isinstance(sc, dict) and isinstance(sc.get("rows"), list) and "a" in sc and "b" in sc: r = _resolve_compare(sc, segs, units)
    elif isinstance(sc, dict) and isinstance(sc.get("worksheet"), dict):
        raise _untyped(_join(segs), "a field of the worksheet description (data_import)")                # not a computed quantity
    else: raise _untyped(_join(segs), f"a field of a {c.get('name')} result")
    schema = (schemas or {}).get(c.get("name"))
    if schema: check_schema(schema, r)
    if not _number(r.value): raise Unresolved(f"{_join(r.path)}: the engine's value is not a number ({r.value!r})")
    r.ref = ref
    r.analysis = sc.get("id") if sc.get("kind") == "nca" else None
    return r

# ---------------------------------------------------------------- outputSchema check
def _deref(s, root):
    seen = 0
    while isinstance(s, dict) and "$ref" in s and seen < 20:
        s = (root.get("$defs") or {}).get(s["$ref"].split("/")[-1], {}); seen += 1
    return s

def _types(s, root, depth=0):
    """Declared JSON types of a schema node ('any' when it constrains nothing)."""
    s = _deref(s, root)
    if not isinstance(s, dict) or depth > 8: return {"any"}
    out = set()
    for alt in s.get("oneOf", []) + s.get("anyOf", []): out |= _types(alt, root, depth + 1)
    t = s.get("type")
    if isinstance(t, list): out |= set(t)
    elif isinstance(t, str): out.add(t)
    if "const" in s: out.add(_json_type(s["const"]))
    if "enum" in s: out |= {_json_type(x) for x in s["enum"]}
    return out or {"any"}

def _json_type(v):
    if isinstance(v, bool): return "boolean"
    if isinstance(v, int): return "integer"
    if isinstance(v, float): return "number"
    if isinstance(v, str): return "string"
    if isinstance(v, list): return "array"
    if v is None: return "null"
    return "object"

def _step(s, key, root):
    """Schema nodes reached from `s` by one path step, or Unresolved when the schema forbids the step."""
    s = _deref(s, root)
    if not isinstance(s, dict): return [{}]
    if "oneOf" in s or "anyOf" in s:
        outs, err = [], None
        for alt in s.get("oneOf", []) + s.get("anyOf", []):
            try: outs += _step(alt, key, root)
            except Unresolved as e: err = e
        if not outs: raise err or Unresolved(f"the result schema has no field {key!r}")
        return [o for o in outs if o] or outs                  # a branch that constrains the step wins over one that does not
    if isinstance(key, int):
        if s.get("type") not in (None, "array"): raise Unresolved(f"the result schema says a {s.get('type')} here, not a list")
        items = s.get("items"); return [items if isinstance(items, dict) else {}]
    props = s.get("properties") or {}
    if key in props: return [props[key]]
    ap = s.get("additionalProperties", True)
    if ap is False: raise Unresolved(f"the result schema has no field {key!r}")
    return [ap if isinstance(ap, dict) else {}]

def check_schema(schema, r):
    """Walks r.path through the tool's outputSchema; the path must be allowed and the leaf type must agree with the value."""
    nodes = [schema]
    for key in r.path:
        nxt, err = [], None
        for n in nodes:
            try: nxt += _step(n, key, schema)
            except Unresolved as e: err = e
        if not nxt: raise err or Unresolved("path not in the result schema")
        nodes = [n for n in nxt if n] or nxt
    declared = set()
    for n in nodes: declared |= _types(n, schema)
    if "any" in declared: return
    v = r.value
    actual = "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else _json_type(v)
    ok = actual in declared or (actual == "number" and "integer" in declared) or (actual == "array" and "array" in declared)
    if not ok:
        raise Unresolved(f"{_join(r.path)}: the result schema declares {'/'.join(sorted(declared))}, the value is a {actual}")

# ---------------------------------------------------------------- the user's numbers (the only digits the model may type)
def user_numbers(user_texts):
    """gate v1's reading of the user's messages (every plausible reading, CSV included); tool results are NOT a source."""
    return gate.allowed_numbers((), list(user_texts or ()))

# ---------------------------------------------------------------- words, labels, units
_FR_SMALL = r"z[ée]ro|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|dix-sept|dix-huit|dix-neuf|vingt"
_FR_BIG = r"trente|quarante|cinquante|soixante|soixante-dix|quatre-vingts?|quatre-vingt-dix|cents?|mille|millions?|milliards?|douzaines?"
_EN_SMALL = r"zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
_EN_BIG = r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?"
_FRACTION = r"double|triple|quadruple|quintuple|d[ée]cuple|centuple|moiti[ée]|demie?|tiers|quarts?|twice|thrice|half|halves|quarters?"
_SMALL = f"(?:{_FR_SMALL}|{_EN_SMALL})"
_BIG = f"(?:{_FR_BIG}|{_EN_BIG})"
_WORD = f"(?:{_BIG}|{_SMALL})"
_NUMWORDS_RE = re.compile(rf"(?<![\w-])(?:{_WORD})(?:(?:[ \t-]+(?:et[ \t-]+|and[ \t-]+)?)(?:{_WORD}))*(?!\w)", re.I)   # "eleven-hour": the hyphen ends the numeral
_FRACTION_RE = re.compile(rf"(?<![\w-])(?:{_FRACTION})(?![\w])", re.I)
_FOLD_RE = re.compile(rf"(?<![\w-])(?:{_WORD}|one|several|many)[ \t-]?fold(?!\w)", re.I)        # hundredfold, ten-fold, two fold
_ORDINAL = (r"thirds?|fourths?|fifths?|sixths?|sevenths?|eighths?|ninths?|tenths?|hundredths?|thousandths?|"
            r"cinqui[èe]mes?|sixi[èe]mes?|septi[èe]mes?|huiti[èe]mes?|neuvi[èe]mes?|dixi[èe]mes?|centi[èe]mes?|milli[èe]mes?")
_ORDFRAC_RE = re.compile(rf"(?<![\w-])(?:(?:{_SMALL})[ \t-]+(?:{_ORDINAL})|(?:one|an?|une?)[ \t-]+(?:{_ORDINAL})(?=[ \t]+(?:of|de|du|des|d['’])))(?!\w)", re.I)
_UNIT_WORD_BASE = (r"heures?|h|minutes?|min|secondes?|s|jours?|j|d|litres?|liters?|l|millilitres?|milliliters?|ml|d[ée]cilitres?|dl|"
                   r"grammes?|grams?|g|milligrammes?|milligrams?|mg|microgrammes?|micrograms?|[µμu]g|nanogrammes?|nanograms?|ng|"
                   r"moles?|mol|millimoles?|mmol|micromoles?|[µμu]mol|pour[ \t]?cent|per[ \t]?cent|percent|%|hours?|days?|seconds?")
_UNIT_WORD = rf"(?:{_UNIT_WORD_BASE}|fois|times)"
_UNIT_AFTER_WORD_RE = re.compile(rf"^[ \t]*(?:{_UNIT_WORD})(?![A-Za-zµμ'’])", re.I)
_UNIT_AFTER_NUMWORD_RE = re.compile(rf"^[ \t]*-?[ \t]*(?:{_UNIT_WORD})(?![A-Za-zµμ'’])", re.I)                    # "eleven-hour"
_ONE_UNIT_RE = re.compile(rf"(?<![\w-])(?:one|une?)[ \t-]+(?:{_UNIT_WORD_BASE})(?![A-Za-zµμ'’-])", re.I)        # "one hour", "une heure"; not "une fois"
_MULT_AFTER_RE = re.compile(r"[ \t]*-?[ \t]*(?:fold|fois|times|[x×](?![A-Za-z]))", re.I)                          # "10-fold", "3 fois", "2 x"
_DECIMAL_WORD_RE = re.compile(r"^[ \t]*(?:virgule|point|comma)[ \t]+" + _WORD, re.I)
_PK_LABEL = (r"(?:c\s?max|t\s?max|t\s?last|c\s?last|t\s?lag|c\s?0|auc[\w.]*|aumc[\w.]*|cl(?:/f)?|clairance|clearance|v[zd]?(?:/f)?|vss|volume|"
             r"demi-?\s?vie|half-?\s?life|t\s?1/2|t½|[λ]\s?z|lambda[_.\s]?z|kel?|mrt|dose|concentration|conc|extrapol\w*|ratio|rapport|"
             r"diff[ée]rence|[ée]cart|pourcentage|percent(?:age)?|r[²2]|r\.squared|span(?:\.ratio)?|pente|slope)")
_CONNECT = (r"(?:\s*\([^()]{0,40}\))?(?:\s*(?:=|:|≈|~|est|sont|de|d'|d’|du|des|vaut|valent|[ée]gale?|à|a|is|are|of|equals?|about|environ|"
            r"approximately|roughly|around|the|la|le|les|l'|l’|une?|value|valeur|obtenue?|calcul[ée]e?|estim[ée]e?|mesur[ée]e?|observ[ée]e?|"
            r"was|were|reaches|reach|atteint|at|en|in|pour|for|moyenne|mean))*\s*$")
_LABEL_BEFORE_RE = re.compile(r"(?<![\w.])" + _PK_LABEL + _CONNECT, re.I)

def _after_pk_label(text, pos):
    """True when the token at `pos` follows a PK parameter label with only connector words between."""
    return _LABEL_BEFORE_RE.search(text[max(0, pos - 72):pos]) is not None

# ---------------------------------------------------------------- numbers written with Unicode numeric characters (T-058)
_EXPONENT_CHARS = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻₀₁₂₃₄₅₆₇₈₉₊₋")

def _unicode_numeric_runs(text):
    """Runs of non-ASCII numeric characters (Unicode categories No and Nl: superscripts, subscripts, vulgar fractions, circled
    and Roman numerals; what NFKC would turn into digits) that are not an exponent or an index glued to a label or a unit
    ("R²", "h⁻¹", "AUC₀₋∞", "t½", "10⁻³"). Decimal digits of other scripts (category Nd) are read by the number tokeniser."""
    out, i = [], 0
    numeric = lambda ch: not ch.isascii() and unicodedata.category(ch) in ("No", "Nl")
    while i < len(text):
        if not numeric(text[i]): i += 1; continue
        a = i
        while a > 0 and text[a - 1] in "⁺⁻₊₋": a -= 1
        b = i
        while b < len(text) and (numeric(text[b]) or text[b] in "⁺⁻₊₋"): b += 1
        run, prev = text[a:b], text[a - 1:a]
        glued = prev.isalpha() or prev in ")]"
        if all(c in _EXPONENT_CHARS for c in run) and len(run) <= 3 and (glued or text[:a].endswith("10")): pass
        elif run == "½" and prev in ("t", "T"): pass
        else: out.append((a, b))
        i = b
    return out

# ---------------------------------------------------------------- units: dimension and scale (T-057)
_PREFIX = {"": 1.0, "k": 1e3, "d": 1e-1, "m": 1e-3, "µ": 1e-6, "μ": 1e-6, "u": 1e-6, "mc": 1e-6, "n": 1e-9, "p": 1e-12}
_TIME = {"h": 60.0, "hr": 60.0, "min": 1.0, "s": 1 / 60, "d": 1440.0, "j": 1440.0}
_BASES = (("mol", (0, 0, 0, 1, 0)), ("g", (1, 0, 0, 0, 0)), ("L", (0, 1, 0, 0, 0)), ("l", (0, 1, 0, 0, 0)), ("M", (0, -1, 0, 1, 0)))
_UTOK_RE = re.compile(r"\s*(\(|\)|[*·.×⋅]|/|\^?[-−⁻]?[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]+|%|[A-Za-zµμ]+)")
_UNIT_WORDS = {"heure": "h", "heures": "h", "hour": "h", "hours": "h", "minute": "min", "minutes": "min", "seconde": "s", "secondes": "s",
               "second": "s", "seconds": "s", "jour": "d", "jours": "d", "day": "d", "days": "d", "litre": "L", "litres": "L", "liter": "L",
               "liters": "L", "millilitre": "mL", "millilitres": "mL", "milliliter": "mL", "milliliters": "mL", "gramme": "g", "grammes": "g",
               "gram": "g", "grams": "g", "milligramme": "mg", "milligrammes": "mg", "milligram": "mg", "milligrams": "mg",
               "microgramme": "µg", "microgrammes": "µg", "microgram": "µg", "micrograms": "µg", "nanogramme": "ng", "nanogrammes": "ng",
               "nanogram": "ng", "nanograms": "ng", "percent": "%", "pourcent": "%", "pourcentage": "%"}

def _atom(t):
    if t == "%": return (0, 0, 0, 0, 1), 1.0
    if t in _TIME: return (0, 0, 1, 0, 0), _TIME[t]
    for base, dim in _BASES:
        if t.endswith(base) and t[:-len(base)] in _PREFIX: return dim, _PREFIX[t[:-len(base)]]
    return None

def unit_dimension(u):
    """(dimension, scale) of a unit string made of the closed atoms (mass, volume, time, amount, %; SI prefixes; `*` `·` `.` `/`,
    parentheses, exponents), or None (a dose unit, a word, anything else). Dimension: exponents of (mass, volume, time, amount,
    percent); scale: the factor to the base atoms (g, L, min, mol), so that ng/mL and µg/L are the same unit."""
    u = _UNIT_WORDS.get((u or "").strip().lower(), (u or "").strip())
    if not u: return None
    toks, pos = [], 0
    while pos < len(u):
        m = _UTOK_RE.match(u, pos)
        if not m: return None
        toks.append(m.group(1)); pos = m.end()
    toks = [t for t in toks if t.strip()]
    i = 0
    def exponent():
        nonlocal i
        if i < len(toks) and re.fullmatch(r"\^?[-−⁻]?[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]+", toks[i]) and (toks[i][0] in "^-−⁻" or toks[i][0] in gate._SUP):
            t = toks[i].lstrip("^"); i += 1
            sign = -1 if t[0] in "-−⁻" else 1
            return sign * int("".join(gate._SUP.get(c, c) for c in t.lstrip("-−⁻")))
        return 1
    def term():
        nonlocal i
        if i >= len(toks): return None
        t = toks[i]
        if t == "(":
            i += 1; r = expr()
            if r is None or i >= len(toks) or toks[i] != ")": return None
            i += 1; d, s = r
        elif t == "1": i += 1; d, s = (0, 0, 0, 0, 0), 1.0          # the 1 of 1/h
        else:
            a = _atom(t)
            if a is None: return None
            i += 1; d, s = a
        k = exponent()
        return tuple(x * k for x in d), s ** k
    def expr():
        nonlocal i
        r = term()
        if r is None: return None
        d, s = r
        while i < len(toks) and toks[i] in ("*", "·", ".", "×", "⋅", "/"):
            op = toks[i]; i += 1
            r = term()
            if r is None: return None
            if op == "/": d, s = tuple(x - y for x, y in zip(d, r[0])), s / r[1]
            else: d, s = tuple(x + y for x, y in zip(d, r[0])), s * r[1]
        return d, s
    r = expr()
    return r if r is not None and i == len(toks) else None

def contradicts(written, rendered):
    """True when the unit `written` by the model has the dimension of the `rendered` one but another scale (mg/L for ng/mL,
    µg/mL for ng/mL, min for h), or a per-kg unit written without its /kg (L/h for L/h/kg). When the engine's unit carries "dose unit" (the dose unit was not given), any written unit of
    that dimension (L/h for dose unit/(h*ng/mL)) is a conversion the engine did not make. A unit of another dimension (a time
    next to a concentration) is not a contradiction; a unit the closed atoms cannot read is not judged."""
    dose_unit = "dose unit" in (rendered or "")            # the engine did not know the dose unit: any unit of that dimension is a conversion
    a, b = unit_dimension(written), unit_dimension(re.sub(r"dose\s+unit", "g", rendered or ""))
    if a is None or b is None or not any(b[0]): return False
    if re.search(r"/\s*kg\s*$", rendered or "") and a[0] == (b[0][0] + 1,) + b[0][1:]:
        return True                                        # a per-kg value (L/h/kg) written without its /kg (L/h): not the engine's unit
    if a[0] != b[0]: return False
    return dose_unit or abs(a[1] / b[1] - 1) > 1e-9

_INTRO_RE = re.compile(r"(?<![\w])(?:exprim[ée]e?s?[ \t]+en|expressed[ \t]+in|unit[ée]s?[ \t]*:?|units?[ \t]*:?|en|in)[ \t]+$", re.I)
_PAREN_UNIT_RE = re.compile(r"(?<![A-Za-zÀ-ÿ])[(\[][ \t]*(?:en[ \t]+|in[ \t]+)?([^()\[\]\n|]{1,24}?)[ \t]*[)\]]")
_WORD_AT_RE = re.compile(r"[A-Za-zÀ-ÿµμ%]+")

def written_units(text, lo, hi, numbers):
    """[(unit, start, end)] the model wrote in text[lo:hi] (references already blanked): the unit after a number, a unit alone in
    parentheses or brackets ("Cmax (µg/mL)", "[ng/mL]"), and a unit or unit word after "en", "in", "unit:", "exprimée en"."""
    out = [(n.unit, n.end, n.span_end) for n in numbers if lo <= n.start < hi and n.unit]
    for m in _PAREN_UNIT_RE.finditer(text, lo, hi):
        if unit_dimension(m.group(1)) is not None: out.append((m.group(1), m.start(1), m.end(1)))
    for m in re.finditer(r"[ \t]", text[lo:hi]):
        p = lo + m.end()
        if p >= hi or not _INTRO_RE.search(text[max(lo, p - 24):p]): continue
        unit, uend = gate._read_unit(text, p)
        if not unit:
            w = _WORD_AT_RE.match(text, p)
            if w and w.group(0).lower() in _UNIT_WORDS: unit, uend = w.group(0), w.end()
        if unit and uend <= hi: out.append((unit, p, uend))
    return out

_SEPARATOR_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$")

def _line(text, pos):
    a = text.rfind("\n", 0, pos) + 1; b = text.find("\n", pos)
    return a, len(text) if b < 0 else b

def _cells(text, a, b):
    """[(start, end)] of the cells of the table row text[a:b] (between the pipes)."""
    pipes = [i for i in range(a, b) if text[i] == "|"]
    return [(p + 1, q) for p, q in zip(pipes, pipes[1:])]

def clause_spans(text, s, e):
    """Where a unit written by the model applies to the reference text[s:e], as [(start, end, whole)]: the clause around it (from
    the previous ";", line end or sentence end to the next; a comma does not end it), or, in a Markdown table, its cell, the row's
    first cell, the cell just before it and the column's header cell; `whole` False marks the other cells of the row, where only a cell that is a unit
    alone counts ("| Cmax | {{ref}} | mg/L |")."""
    a, b = _line(text, s)
    line = text[a:b]
    if line.lstrip().startswith("|") and line.count("|") >= 2:
        cells = _cells(text, a, b)
        k = next((i for i, (p, q) in enumerate(cells) if p <= s and e <= q), None)
        if k is None: return [(a, b, True)]
        label = {0, k - 1} if k else set()                                  # the row's first cell and the cell just before (a label)
        out = [(*cells[k], True)] + [(*cells[i], True) for i in sorted(label)] + [(p, q, False) for i, (p, q) in enumerate(cells) if i not in label | {k}]
        pos = a                                                             # the header: the line above the |---| separator
        while pos > 0:
            pa, pb = _line(text, pos - 1); row = text[pa:pb]
            if _SEPARATOR_RE.match(row):
                if pa > 0:
                    ha, hb = _line(text, pa - 1); hcells = _cells(text, ha, hb)
                    if k < len(hcells): out.append((*hcells[k], True))
                break
            if not row.lstrip().startswith("|"): break
            pos = pa
        return out
    ends = [a + m.end() for m in re.finditer(r";|[.!?](?=\s)", text[a:s])]
    lo = ends[-1] if ends else a
    m = re.search(r";|[.!?](?=\s|$)", text[e:b])
    return [(lo, e + m.start() if m else b, True)]

def _cell_unit(text, p, q):
    """The cell text[p:q] when it is a unit alone ("| ng/mL |"); "min" alone is a column name, not a unit."""
    t = text[p:q].strip().strip("*_`")
    return t if t and t.lower() != "min" and unit_dimension(t) is not None else None

# ---------------------------------------------------------------- what is written next to a reference
_OPS = "×*/^÷"
_EMPH = "*_~`"
_BULLET_RE = re.compile(r"[ \t]*[-*+•][ \t]+")
_SIGN_WORD_RE = re.compile(r"(?<![\w-])(?:(?:n[ée]gati(?:f|ve)s?|negative)[*_~`]*(?:[ \t]+(?:de|of|d['’]))?|(?:minus|moins)[*_~`]*)[ \t]*[*_~`]*[ \t]*$", re.I)

def _open_emphasis(text, s):
    """Start of a Markdown emphasis opener glued to the reference at s ("**{{ref}}", "_{{ref}}", "`{{ref}}"), else s. A run
    glued to a digit, a letter or another reference on its other side is an operator ("2*{{ref}}", "}}*{{"), not emphasis."""
    i = s
    while i > 0 and text[i - 1] in _EMPH: i -= 1
    prev = text[i - 1:i]
    return i if i < s and not (prev.isalnum() or prev == "}") else s

def _close_emphasis(text, e):
    i = e
    while i < len(text) and text[i] in _EMPH: i += 1
    nxt = text[i:i + 1]
    return i if i > e and not (nxt.isalnum() or (nxt and nxt in "{(")) else e

def _adjacent(text, s, e):
    """Violations around the reference text[s:e]: (reason, mark_start, mark_end). Markdown emphasis glued to the reference
    (bold, italic, code) is looked through, so a sign or a unit outside it is still next to the reference (T-058)."""
    out = []
    s2, e2 = _open_emphasis(text, s), _close_emphasis(text, e)
    before, after = text[:s2], text[e2:]
    pb = before.rstrip(" \t")
    m = re.search(r"(?<=[^\W\d]|[)\]%])[*_~`]+$", pb)                          # "**Cmax** {{ref}}": a closing emphasis after a word, no operator
    if m and pb != before: pb = pb[:m.start()]
    c = pb[-1:] or "\0"
    line_before = before[before.rfind("\n") + 1:]
    if _BULLET_RE.fullmatch(line_before): pass                                   # "- {{ref}}", "* {{ref}}": a list item
    elif c.isdecimal():                                                          # not isdigit(): "R² {{ref}}" is a label, ² is no digit of a number
        m = re.search(r"[\d.,]+$", pb); out.append(("digit before a reference", m.start(), e))
    elif c in _OPS: out.append(("arithmetic next to a reference", len(pb) - 1, e))
    elif c == "(" and re.search(r"\)\s*(?:[-−+×*/^÷]|[x×])\s*\($", pb): out.append(("arithmetic next to a reference", len(pb) - 1, e))
    elif c in "-−+":
        prev = pb[:-1].rstrip(" \t")[-1:]                                      # "-" may be a hyphen; "−" and "+" never are
        if c != "-" or pb == before or not prev or prev.isdigit() or prev in ")}=:([|≈~<>≤≥/":
            out.append(("sign or arithmetic next to a reference", len(pb) - 1, e))
    elif c in ".," and pb[-2:-1].isdecimal() and before == pb:                      # "2,{{ref}}" glued; "analyse 2, {{ref}}" is punctuation
        m = re.search(r"[\d.,]+$", pb); out.append(("digit before a reference", m.start(), e))
    elif re.search(r"(?:\d|\}\}|\))\s*[x×]\s*$", before, re.I): out.append(("arithmetic next to a reference", len(pb) - 1, e))
    else:
        m = _SIGN_WORD_RE.search(before[-40:])
        if m: out.append(("a sign written in words next to a reference (the client prints the sign)", len(before) - len(before[-40:]) + m.start(), e))
    pa = after.lstrip(" \t"); off = e2 + (len(after) - len(pa))
    m = re.match(r"[*_~`]+(?=[^\W\d]|[(%µμ])", pa) if pa != after else None      # "{{ref}} *(n = 3)*", "{{ref}} **mg/L**": an opening emphasis
    if m: pa, off = pa[m.end():], off + m.end()
    c = pa[:1] or "\0"
    if c.isdecimal() or re.match(r"[.,]\d", pa):
        m = re.match(r"[\d.,]+", pa); out.append(("digit after a reference", s, off + m.end()))
    elif pa.startswith("{{") and after == pa: out.append(("two references glued together", s, off + 2))
    elif c in _OPS: out.append(("arithmetic next to a reference", s, off + 1))
    elif c == ")" and re.match(r"\)\s*(?:[-−+×*/^÷]|[x×])\s*\(", pa): out.append(("arithmetic next to a reference", s, off + 1))
    elif c in "-−+" and re.match(r"[-−+]\s*(?:\d|\{\{|\()", pa): out.append(("sign or arithmetic next to a reference", s, off + 1))
    elif re.match(r"[x×]\s*(?:\d|\{\{|\()", pa, re.I): out.append(("arithmetic next to a reference", s, off + 1))
    elif re.match(r"[eE][-+]?\d", pa): out.append(("exponent after a reference", s, off + 1))
    else:
        unit, uend = gate._read_unit(text, off if m else e2)
        if unit: out.append(("unit next to a reference (the client prints it)", s, uend))
        else:
            mm = _UNIT_AFTER_WORD_RE.match(pa if m else after)
            if mm: out.append(("unit next to a reference (the client prints it)", s, (off if m else e2) + mm.end()))
    return out

def _contradiction(plain, s, e, r, numbers):
    """The first unit written in the reference's clause (or table cell, row label, column header) that has the dimension of the
    rendered unit but another scale: "La Cmax en mg/L vaut {{call_2.cmax}}" when the engine's Cmax is in ng/mL (T-057)."""
    if not r.unit: return None
    for lo, hi, whole in clause_spans(plain, s, e):
        units = written_units(plain, lo, hi, numbers) if whole else []
        cu = _cell_unit(plain, lo, hi) if plain[lo - 1:lo] == "|" else None
        if cu: units.append((cu, lo, hi))
        for u, _, _ in units:
            if contradicts(u, r.unit): return u
    return None

# ---------------------------------------------------------------- the check
def _finding(kind, text, start, end, answer, reason, value="0", sig=2, unit="", ref=None, hint=None, nearest=None, number=None):
    return {"kind": kind, "number": text if number is None else number, "text": text, "value": value, "position": [start, end],
            "line": gate._line_of(answer, start), "unit": unit, "significant_digits": sig,
            "nearest_allowed": nearest.text if nearest else None, "nearest_source": nearest.source if nearest else None,
            "hint": hint, "reason": reason, "ref": ref}

def check(answer, calls, user_texts=(), schemas=None, decimal_mark=".", allowed=None):
    """Resolves the references of `answer`, checks everything else, renders. See the module docstring."""
    answer = answer or ""
    allowed = user_numbers(user_texts) if allowed is None else allowed
    values = {a.value for a in allowed}
    findings, exempt, marks, assertions = [], [], [], []      # marks: (start, end, replacement text or None for a marker)
    refs_total = refs_bad = refs_untyped = 0
    spans, resolved = [], []                      # brace spans blanked before the number pass; references to render

    def reject(kind, start, end, reason, **kw):
        f = _finding(kind, answer[start:end], start, end, answer, reason, **kw); findings.append(f); marks.append((start, end, None, reason))

    for m in _BRACE_RE.finditer(answer):
        s, e, raw = m.start(), m.end(), m.group(0)
        body = raw.strip("{}")
        ref, path = parse_ref(body)
        well_formed = raw.startswith("{{") and raw.endswith("}}") and not raw.startswith("{{{") and not raw.endswith("}}}")
        if not well_formed:
            if ref is not None or re.search(r"call[_\- ]?\d", body, re.I):
                refs_total += 1; refs_bad += 1; spans.append((s, e))
                reject("malformed_reference", s, e, "a reference is written {{call_N.path}} with exactly two braces on each side")
            continue                                                            # other braces (quoted JSON): the digits inside are checked
        spans.append((s, e))
        try:
            if ref is not None: r = resolve(ref, path, calls, schemas)
            else:
                cname = parse_convention(body)
                if cname is None: raise Unresolved("a reference starts with the ref of a tool result, e.g. {{call_3.cmax}}, or names a convention, e.g. {{convention.max_extrapolated_percent}}")
                r = resolve_convention(cname, calls)
        except Untyped as u:
            refs_untyped += 1; reject("untyped_reference", s, e, u.reason, ref=ref, hint=u.hint); continue
        except Unresolved as u:
            refs_total += 1; refs_bad += 1; reject("unresolved_reference", s, e, u.reason, ref=ref, hint=u.hint); continue
        refs_total += 1; resolved.append((s, e, ref, r))

    plain = list(answer)
    for s, e in spans:
        for i in range(s, e): plain[i] = " "
    plain = "".join(plain)
    numbers = gate.extract_numbers(plain)

    for s, e, ref, r in resolved:
        adj = _adjacent(answer, s, e)
        if adj:
            refs_bad += 1
            for reason, a0, a1 in adj[:1]: reject("adjacent_to_reference", a0, a1, reason, ref=ref)
            continue
        u = _contradiction(plain, s, e, r, numbers)
        if u:
            refs_bad += 1
            reject("contradictory_unit", s, e, f"the unit {u} written in the same clause or column contradicts the engine's {r.unit}", ref=ref,
                   unit=u, hint="write no unit: the client prints the engine's unit")
            continue
        marks.append((s, e, r.render(decimal_mark), None)); assertions.append(r.record())

    total = unverified = 0
    def allowed_num(n): return any(abs(v) in values for v, _, _ in n.readings)
    for n in numbers:
        reason = n.exempt
        if reason == "year": reason = None                                     # no year exemption in v2
        if reason == "small_integer" and (_after_pk_label(plain, n.start) or _MULT_AFTER_RE.match(plain, n.span_end)): reason = None
        if reason:
            exempt.append({"number": n.raw, "position": [n.start, n.end], "reason": reason}); continue
        if allowed_num(n): total += 1; continue
        if n.parts and all(allowed_num(p) for p in n.parts): total += len(n.parts); continue
        total += 1; unverified += 1
        v, sig, _ = n.readings[0]
        f = _finding("bare_number", n.text, n.start, n.span_end, answer,
                     "a number typed by hand that is not in the user's message (tool values are cited, never typed)",
                     value=str(v.normalize() if v != 0 else 0), sig=sig, unit=n.unit, nearest=gate._nearest(abs(v), allowed), number=n.raw,
                     hint=convention_of(abs(v), n.unit, calls))
        findings.append(f); marks.append((n.start, n.span_end, None, "not in the user's message"))

    def word_finding(s, end, why, mark=None):
        nonlocal total, unverified
        total += 1; unverified += 1
        findings.append(_finding("number_word", answer[s:end], s, end, answer, why)); marks.append((s, end, None, mark or why))

    for m in _NUMWORDS_RE.finditer(plain):
        s, e, w = m.start(), m.end(), m.group(0)
        words = re.split(r"[ \t-]+", w.strip())
        compound = len(words) > 1 or re.fullmatch(_BIG, w, re.I) is not None
        if re.fullmatch(r"cents?", w, re.I) and re.search(r"(?:pour|per)[ \t]*$", plain[:s], re.I): continue   # pour cent
        if re.match(r"[ \t-]?fold(?!\w)", plain[e:], re.I): continue                     # "tenfold": the multiplier pass below
        after = plain[e:]
        why = None
        if compound: why = "a quantity spelled in words"
        elif _DECIMAL_WORD_RE.match(after): why = "a decimal spelled in words"
        elif _UNIT_AFTER_NUMWORD_RE.match(after): why = "a quantity spelled in words with a unit"
        elif _after_pk_label(plain, s): why = "a parameter value spelled in words"
        if why is None:
            exempt.append({"number": w, "position": [s, e], "reason": "count_word"}); continue
        end = e
        for rx in (_DECIMAL_WORD_RE, _UNIT_AFTER_NUMWORD_RE):
            mm = rx.match(after)
            if mm: end = e + mm.end(); break
        word_finding(s, end, why)
    for m in _ONE_UNIT_RE.finditer(plain):
        word_finding(m.start(), m.end(), "a quantity spelled in words with a unit")
    for m in _FRACTION_RE.finditer(plain):
        s, e, w = m.start(), m.end(), m.group(0)
        if re.match(r"-?\s?(?:vies?|li(?:fe|ves))\b", plain[e:], re.I): continue        # demi-vie(s), half-life, half-lives
        word_finding(s, e, "a multiple or a fraction spelled in words", "a multiple or a fraction in words")
    for rx, why in ((_FOLD_RE, "a multiple spelled in words"), (_ORDFRAC_RE, "a fraction spelled in words")):
        for m in rx.finditer(plain): word_finding(m.start(), m.end(), why)
    for s, e in _unicode_numeric_runs(plain):
        word_finding(s, e, "a number written with Unicode numeric characters (fraction, superscript, ...)", "a number in Unicode numerals")

    # render: replacements and markers, overlapping spans merged into one marker
    marks.sort(key=lambda t: (t[0], -t[1]))
    pieces, pos, merged = [], 0, []
    for s, e, rep, reason in marks:
        if merged and s < merged[-1][1]:
            ms, me, mrep, mreason = merged[-1]
            merged[-1] = (ms, max(me, e), None, mreason or reason); continue
        merged.append((s, e, rep, reason))
    for s, e, rep, reason in merged:
        pieces.append(answer[pos:s])
        if rep is not None: pieces.append(rep)
        else: pieces.append(f"{MARK_OPEN}{reason}: {answer[s:e]}{MARK_CLOSE}")
        pos = e
    pieces.append(answer[pos:])
    findings.sort(key=lambda f: f["position"][0])
    return {"rendered": "".join(pieces), "findings": findings, "exempt": exempt,
            "numbers_total": total + refs_total + refs_untyped, "numbers_unverified": unverified + refs_bad + refs_untyped,
            "numbers_exempt": len(exempt), "references_total": refs_total, "references_unresolved": refs_bad,
            "references_untyped": refs_untyped, "assertions": assertions}

# ---------------------------------------------------------------- messages built from the findings
def describe(calls):
    """One line per citable tool result (the parameters of an analysis are listed in the finding that misnamed one). A data_import
    result is not listed: the worksheet description is not a quantity."""
    lines = []
    for ref, c in (calls or {}).items():
        sc = c.get("structured"); name = c.get("name")
        if not isinstance(sc, dict): continue
        if sc.get("kind") == "nca" and isinstance(sc.get("result"), dict):
            subs = sc["result"].get("subjects") or []
            desc = f"{ref} ({name}, analysis {sc.get('id')}, " + (f"subject {subs[0].get('subject')}" if len(subs) == 1 else
                   f"{len(subs)} subjects: " + ", ".join(f"{ref}.subject={s.get('subject')}" for s in subs[:8])) + ")"
        elif isinstance(sc.get("rows"), list) and "a" in sc:
            names = [r.get("parameter") for r in sc["rows"] if r.get("a") is not None or r.get("b") is not None]
            desc = f"{ref} ({name}: {', '.join(str(n) for n in names[:12])}{', ...' if len(names) > 12 else ''}; fields .a .b .difference .percent .ratio)"
        else: continue                                                      # a worksheet description has nothing citable
        lines.append(desc)
    return lines

def badge(findings, limit=8):
    """The visible mark added to an answer that still has problems."""
    if not findings: return ""
    shown = []
    for f in findings:
        t = f["text"] if f["kind"] != "unresolved_reference" else f["text"]
        if t not in shown: shown.append(t)
    more = f", +{len(shown) - limit}" if len(shown) > limit else ""
    return f"⚠ {len(findings)} problem(s) in the answer (typed rendering): {', '.join(shown[:limit])}{more}"

def reminder(findings, calls=None, limit=12):
    """System reminder appended at the END of the messages for the one regeneration (the static prefix is not touched)."""
    lines, seen = [], set()
    for f in findings:
        if f["text"] in seen: continue
        seen.add(f["text"])
        if f["kind"] == "unresolved_reference":
            lines.append(f"- {f['text']}: {f['reason']}" + (f" ({f['hint']})" if f.get("hint") else ""))
        elif f["kind"] == "malformed_reference": lines.append(f"- {f['text']}: {f['reason']}")
        elif f["kind"] == "untyped_reference": lines.append(f"- {f['text']}: {f['reason']}" + (f" ({f['hint']})" if f.get("hint") else ""))
        elif f["kind"] == "contradictory_unit": lines.append(f"- {f['text']}: {f['reason']}; {f['hint']}")
        elif f["kind"] == "adjacent_to_reference": lines.append(f"- \"{f['text']}\": {f['reason']}; write the reference alone")
        elif f["kind"] == "number_word": lines.append(f"- \"{f['text']}\": {f['reason']}; cite a tool value by reference or use the user's digits")
        else: lines.append(f"- {f['text']}: {f['reason']}" + (f" ({f['hint']})" if f.get("hint") else ""))
    avail = describe(calls)
    aliases = alias_line(calls)
    return ("[system reminder] Your last answer was rejected by the renderer:\n" + "\n".join(lines[:limit]) + "\n"
            "Rule: never type a value a tool returned, not even rounded. Cite it as {{ref.parameter}}, e.g. {{call_3.cmax}}, and the "
            "client prints its name, value and unit; write no unit, sign, digit or arithmetic next to a reference, and no other unit "
            "for it in the sentence. Only quantities can be cited, never a name, a label or a raw JSON path. The only digits you "
            "may type are those of the user's message. If a value is missing, say that Caladrius did not return it.\n"
            + ("Available references: " + "; ".join(avail) + "\n" if avail else "") + (aliases + "\n" if aliases else "")
            + "Conventions (never type them): " + ", ".join(f"{{{{convention.{k}}}}}" for k in CONVENTIONS)
            + "; prefer {{call_N.thresholds.<name>}} when an analysis carries the threshold.\n"
            + "Write the answer again.")

def alias_line(calls):
    """The aliases of the NCA results among `calls` (for the reminder): the selected regression, the thresholds when carried."""
    ncas = [(ref, c["structured"]) for ref, c in (calls or {}).items()
            if isinstance(c.get("structured"), dict) and c["structured"].get("kind") == "nca" and isinstance(c["structured"].get("result"), dict)]
    parts = []
    lz = next((ref for ref, sc in reversed(ncas) if any(len(_selected_candidates(s.get("outcome", {}).get("ok"))) == 1
                                                        for s in sc["result"].get("subjects") or [])), None)
    if lz: parts.append(f"{lz}.lambda_z.adj_r_squared, .r_squared, .n_points, .time_first, .time_last (the selected λz regression)")
    th = next(((ref, list(_thresholds(sc))) for ref, sc in reversed(ncas) if _thresholds(sc)), None)
    if th:
        ref, names = th
        parts.append(f"{ref}.thresholds.{names[0]}" + (" (also " + ", ".join(f".{n}" for n in names[1:]) + ")" if len(names) > 1 else "") + " (quality thresholds)")
    return "Aliases: " + "; ".join(parts) + "." if parts else ""
