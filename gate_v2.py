"""
Gate v2 for Apothicaire: typed rendering (pure Python, no dependency, no model). Spec: GATE_V2.md.

The model does not write tool numbers: it writes references, {{call_3.cmax}}, and this module replaces each one
with the value AND the unit read from the structuredContent of that tool call (checked against the tool's
outputSchema). Everything that still looks like a quantity in the text is checked against the user's own numbers
only; tool results are not a source any more. Fail-closed: an unresolvable reference, a wrong path, a number not in
the user's message, a unit or a sign next to a reference, a number spelled in words, are replaced by a visible
marker and listed in a badge, never passed through.

  check(answer, calls, user_texts, schemas, decimal_mark) -> {
      "rendered": the text shown to the user,
      "findings": [...], "exempt": [...],
      "numbers_total", "numbers_unverified", "numbers_exempt",        (same keys as gate v1: the bench reads them)
      "references_total", "references_unresolved"}

Aliases (GATE_V2.md, "Reference syntax"): `lambda_z.<field>` names a field of the SELECTED λz regression candidate
(`outcome.ok.lambda_z_candidates[j]` with `selected: true`; fail-closed when none is selected) and `thresholds.<name>` a
quality threshold echoed by the result (`spec.options.quality.<name>`). Both are checked against the schema on their
canonical path. The digest's own labels (`lambda_z_regression.*`, `options_used.quality_thresholds.*`) are NOT paths:
they are rejected with the alias as the closest name.

`calls`: ref -> record built by apothicaire.ref_record: {"ref", "name", "structured", "units"}, where units carries
the labels the client computed at call time ({"dose": u, "parameters": {name: unit}} for an NCA analysis,
{"rows": {parameter: {"a": u, "b": u, "difference": u, "relative_percent": "%", "ratio": ""}}} for a comparison).
`schemas`: tool name -> outputSchema from tools/list (optional; without it the data alone is checked).
"""
import difflib, re
from decimal import Decimal

import gate                       # v1: number tokeniser, unit reader, allowed set of the user's numbers
from numtext import value_text

MARK_OPEN, MARK_CLOSE = "⟦", "⟧"

# ---------------------------------------------------------------- display (same rule as the digest, apothicaire._shown)
def _sig(x, n=6):
    return float(f"{x:.{n}g}") if isinstance(x, float) else x

def _shown(x):
    return "0" if x == 0 else value_text(_sig(x))

def render_value(v, unit="", decimal_mark="."):
    """The text of a resolved value: 6 significant digits, no ".0" after an integral value, the unit after a space.
    A string is written as is, a list of scalars joined by commas, a boolean as true/false."""
    if isinstance(v, bool): s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = _shown(v)
        if decimal_mark != ".": s = s.replace(".", decimal_mark)
    elif isinstance(v, list): s = ", ".join(render_value(x, "", decimal_mark) for x in v)
    else: s = str(v)
    return f"{s} {unit}".strip() if unit else s

# ---------------------------------------------------------------- references
class Unresolved(Exception):
    """A reference that must not be rendered. `hint` is extra text for the reminder."""
    def __init__(self, reason, hint=None):
        super().__init__(reason); self.reason, self.hint = reason, hint

class Resolved:
    __slots__ = ("value", "unit", "path", "kind")
    def __init__(self, value, unit, path, kind): self.value, self.unit, self.path, self.kind = value, unit, list(path), kind
    def __repr__(self): return f"Resolved({self.value!r}, {self.unit!r}, {self.path})"

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
def _scalar(x): return x is None or isinstance(x, (bool, int, float, str))

def _resolve_generic(obj, segs, base=()):
    """A JSON path into any structuredContent: keys and [i] indexes, ending on a scalar or a list of scalars."""
    cur, path = obj, list(base)
    for s in segs:
        where = _join(path) or "the result"
        if isinstance(cur, dict):
            if isinstance(s, int) or s not in cur:
                raise Unresolved(f"no field {s!r} in {where}", "fields: " + ", ".join(list(cur)[:12]))
            cur = cur[s]; path.append(s)
        elif isinstance(cur, list):
            if isinstance(s, str) and s.isdigit(): s = int(s)
            if not isinstance(s, int) or not 0 <= s < len(cur):
                raise Unresolved(f"{where} is a list of {len(cur)}: write [i]")
            cur = cur[s]; path.append(s)
        else:
            raise Unresolved(f"{where} is a value, it has no field {s!r}")
    where = _join(path) or "the result"
    if isinstance(cur, dict): raise Unresolved(f"{where} is an object, not a value", "fields: " + ", ".join(list(cur)[:12]))
    if isinstance(cur, list) and not all(_scalar(x) for x in cur): raise Unresolved(f"{where} is a list of objects, not a value")
    if cur is None: raise Unresolved(f"{where} is null (no value)")
    return Resolved(cur, "", path, "generic")

_NCA_TOP = ("result", "spec", "id", "label", "status", "kind", "name")

# ---- aliases: the selected λz regression candidate and the quality thresholds (values the plain path syntax cannot name)
_LZ_ALIAS = ("lambda_z", "lambdaz", "lambda-z", "λz")        # `lambda.z` is the PKNCA parameter (the slope), not an alias prefix
_LZ_FIELDS = ("adj_r_squared", "r_squared", "n_points", "time_first", "time_last", "lambda_z", "intercept", "replaced_points")
_LZ_UNITS = {"lambda_z": "lambda.z", "time_first": "lambda.z.time.first", "time_last": "lambda.z.time.last"}   # the parameter whose unit the field shares
_TH_ALIAS = ("thresholds", "threshold")

def _norm(name): return re.sub(r"[.\-\s]+", "_", str(name).strip()).lower()

def _thresholds(sc):
    q = ((sc.get("spec") or {}).get("options") or {}).get("quality")
    return {k: v for k, v in q.items() if _scalar(v) and v is not None} if isinstance(q, dict) else {}

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
    return Resolved(q[name], "%" if name.endswith("percent") else "", ["spec", "options", "quality", name], "threshold")

def _selected_candidates(ok):
    return [(j, c) for j, c in enumerate((ok or {}).get("lambda_z_candidates") or []) if isinstance(c, dict) and c.get("selected") is True]

def _resolve_lambda_z(ok, rest, units, base):
    """{{call_N.lambda_z.adj_r_squared}}: a field of the SELECTED λz regression candidate (fail-closed when none is selected)."""
    sel = _selected_candidates(ok)
    if not sel: raise Unresolved("no λz regression candidate is selected in this analysis: say that Caladrius did not retain one")
    if len(sel) > 1: raise Unresolved(f"{len(sel)} λz candidates are marked selected: the selection is ambiguous")
    j, c = sel[0]
    fields = [k for k, v in c.items() if k not in ("selected", "valid") and _scalar(v) and v is not None]
    if not rest: raise Unresolved("say which field of the selected regression: lambda_z.<field>", "fields: " + ", ".join(f"lambda_z.{k}" for k in fields))
    name = _norm(_join(rest))
    if name not in fields:
        close = difflib.get_close_matches(name, fields, n=3, cutoff=0.5)
        raise Unresolved(f"no field {name!r} in the selected λz regression", ("closest: " + ", ".join(f"lambda_z.{k}" for k in close) + ". " if close else "")
                         + "fields: " + ", ".join(f"lambda_z.{k}" for k in fields))
    unit = (units.get("parameters") or {}).get(_LZ_UNITS[name], "") if name in _LZ_UNITS else ""
    return Resolved(c[name], unit, base + ["outcome", "ok", "lambda_z_candidates", j, name], "lambda_z")

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
    if isinstance(segs[0], str) and segs[0] in _NCA_TOP: return None          # plain JSON path
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
    key = _join(rest)
    if key.startswith("parameters."): key = key[len("parameters."):]
    if key.endswith(".value"): key = key[:-len(".value")]
    if key == "dose":
        if s.get("dose") is None: raise Unresolved("this subject has no dose")
        return Resolved(s["dose"], units.get("dose") or "", base + ["dose"], "dose")
    if key in ("route", "subject"):
        v = s.get(key); return Resolved(v if isinstance(v, str) else str(v), "", base + [key], "field")
    oc = s.get("outcome") or {}
    if "ok" not in oc: raise Unresolved(f"subject {s.get('subject')} has no result: {oc.get('error', 'error')}")
    ok = oc["ok"] or {}
    if len(rest) >= 2 and isinstance(rest[0], str) and _norm(rest[0]) in _LZ_ALIAS:     # `lambda_z` alone stays a parameter name
        return _resolve_lambda_z(ok, rest[1:], units, base)
    params = ok.get("parameters") or []
    names = [p.get("name") for p in params]
    if key not in names and key.lower() in names: key = key.lower()
    if key in names:
        j = names.index(key); v = params[j].get("value") or {}
        if "value" not in v:
            raise Unresolved(f"{key} was not calculated ({v.get('not_calculated')}): say that Caladrius did not return it")
        unit = params[j].get("unit") or (units.get("parameters") or {}).get(key, "")
        return Resolved(v["value"], unit, base + ["outcome", "ok", "parameters", j, "value", "value"], "parameter")
    try: return _resolve_generic(s, rest, base)                                # e.g. outcome.ok.flags[0].value
    except Unresolved:
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
            (s0 not in ("a", "b") or len(segs) > 1): return None              # plain JSON path (a.analysis, rows[0].a ...)
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
    k = names.index(param); row = rows[k]
    if row.get("a") is None and row.get("b") is None:
        raise Unresolved(f"{param} is not comparable: {row.get('not_comparable') or 'no value'}")
    v = row.get(field)
    if v is None: raise Unresolved(f"{param}.{last}: no value ({row.get('not_comparable') or 'missing on one side'})")
    unit = ((units.get("rows") or {}).get(param) or {}).get(field, "") or ("%" if field == "relative_percent" else "")
    return Resolved(v, unit, ["rows", k, field], "compare")

def _resolve_import(sc, segs):
    """{{call_N.rows}}: the fields of the worksheet without the `worksheet.` prefix."""
    ws = sc.get("worksheet")
    if isinstance(segs[0], str) and segs[0] not in sc and isinstance(ws, dict) and segs[0] in ws:
        return _resolve_generic(ws, segs, ["worksheet"])
    return None

def resolve(ref, path, calls, schemas=None):
    """The value a reference names, or Unresolved. `calls`: ref -> record (see the module docstring)."""
    c = calls.get(ref) if calls else None
    if c is None: raise Unresolved(f"{ref} is not a tool result of this chat", "available: " + ", ".join(calls or ()) if calls else None)
    sc = c.get("structured")
    if sc is None: raise Unresolved(f"{ref} ({c.get('name')}) has no structured result to cite (a tool error?)")
    segs = segments(path)
    if not segs: raise Unresolved("a reference needs a path after the ref, e.g. {{call_N.cmax}}")
    units = c.get("units") or {}
    r = None
    if isinstance(sc, dict):
        if sc.get("kind") == "nca" and isinstance(sc.get("result"), dict): r = _resolve_nca(sc, segs, units)
        elif isinstance(sc.get("rows"), list) and "a" in sc and "b" in sc: r = _resolve_compare(sc, segs, units)
        elif isinstance(sc.get("worksheet"), dict): r = _resolve_import(sc, segs)
    if r is None: r = _resolve_generic(sc, segs)
    schema = (schemas or {}).get(c.get("name"))
    if schema: check_schema(schema, r)
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
_FR_BIG = r"trente|quarante|cinquante|soixante|soixante-dix|quatre-vingts?|quatre-vingt-dix|cents?|mille|millions?|milliards?"
_EN_SMALL = r"zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
_EN_BIG = r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?"
_FRACTION = r"double|triple|moiti[ée]|demie?|tiers|quarts?|twice|half|quarter"
_SMALL = f"(?:{_FR_SMALL}|{_EN_SMALL})"
_BIG = f"(?:{_FR_BIG}|{_EN_BIG})"
_WORD = f"(?:{_BIG}|{_SMALL})"
_NUMWORDS_RE = re.compile(rf"(?<![\w-])(?:{_WORD})(?:(?:[ \t-]+(?:et[ \t-]+|and[ \t-]+)?)(?:{_WORD}))*(?![\w-])", re.I)
_FRACTION_RE = re.compile(rf"(?<![\w-])(?:{_FRACTION})(?![\w])", re.I)
_UNIT_WORD = (r"(?:heures?|h|minutes?|min|secondes?|s|jours?|j|d|litres?|liters?|l|millilitres?|milliliters?|ml|d[ée]cilitres?|dl|"
              r"grammes?|grams?|g|milligrammes?|milligrams?|mg|microgrammes?|micrograms?|[µμu]g|nanogrammes?|nanograms?|ng|"
              r"moles?|mol|millimoles?|mmol|micromoles?|[µμu]mol|pour[ \t]?cent|per[ \t]?cent|percent|%|fois|times|hours?|days?)")
_UNIT_AFTER_WORD_RE = re.compile(rf"^[ \t]*(?:{_UNIT_WORD})(?![A-Za-zµμ'’])", re.I)
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

# ---------------------------------------------------------------- what is written next to a reference
_OPS = "×*/^÷"

def _adjacent(text, s, e):
    """Violations around the reference text[s:e]: (reason, mark_start, mark_end)."""
    out = []
    before, after = text[:s], text[e:]
    pb = before.rstrip(" \t"); c = pb[-1:] or "\0"
    if c.isdigit():
        m = re.search(r"[\d.,]+$", pb); out.append(("digit before a reference", m.start(), e))
    elif c == "*" and pb.endswith("**") and before == pb: pass                   # markdown bold
    elif c in _OPS: out.append(("arithmetic next to a reference", len(pb) - 1, e))
    elif c == "(" and re.search(r"\)\s*(?:[-−+×*/^÷]|[x×])\s*\($", pb): out.append(("arithmetic next to a reference", len(pb) - 1, e))
    elif c in "-−+":
        prev = pb[:-1].rstrip(" \t")[-1:]                                      # "-" may be a hyphen; "−" and "+" never are
        if c != "-" or pb == before or prev.isdigit() or prev in ")}": out.append(("sign or arithmetic next to a reference", len(pb) - 1, e))
    elif c in ".," and pb[-2:-1].isdigit() and before == pb:                      # "2,{{ref}}" glued; "analyse 2, {{ref}}" is punctuation
        m = re.search(r"[\d.,]+$", pb); out.append(("digit before a reference", m.start(), e))
    elif re.search(r"(?:\d|\}\}|\))\s*[x×]\s*$", before, re.I): out.append(("arithmetic next to a reference", len(pb) - 1, e))
    pa = after.lstrip(" \t"); off = e + (len(after) - len(pa)); c = pa[:1] or "\0"
    if c.isdigit() or re.match(r"[.,]\d", pa):
        m = re.match(r"[\d.,]+", pa); out.append(("digit after a reference", s, off + m.end()))
    elif pa.startswith("{{") and after == pa: out.append(("two references glued together", s, off + 2))
    elif c == "*" and pa.startswith("**") and after == pa: pass                  # markdown bold
    elif c in _OPS: out.append(("arithmetic next to a reference", s, off + 1))
    elif c == ")" and re.match(r"\)\s*(?:[-−+×*/^÷]|[x×])\s*\(", pa): out.append(("arithmetic next to a reference", s, off + 1))
    elif c in "-−+" and re.match(r"[-−+]\s*(?:\d|\{\{|\()", pa): out.append(("sign or arithmetic next to a reference", s, off + 1))
    elif re.match(r"[x×]\s*(?:\d|\{\{|\()", pa, re.I): out.append(("arithmetic next to a reference", s, off + 1))
    elif re.match(r"[eE][-+]?\d", pa): out.append(("exponent after a reference", s, off + 1))
    else:
        unit, uend = gate._read_unit(text, e)
        if unit: out.append(("unit next to a reference (the client prints it)", s, uend))
        else:
            m = _UNIT_AFTER_WORD_RE.match(after)
            if m: out.append(("unit next to a reference (the client prints it)", s, e + m.end()))
    return out

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
    findings, exempt, marks = [], [], []          # marks: (start, end, replacement text or None for a marker)
    refs_total = refs_bad = 0
    spans = []                                    # brace spans blanked before the number pass

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
        spans.append((s, e)); refs_total += 1
        if ref is None:
            refs_bad += 1; reject("unresolved_reference", s, e, "a reference starts with the ref of a tool result, e.g. {{call_3.cmax}}"); continue
        try: r = resolve(ref, path, calls, schemas)
        except Unresolved as u:
            refs_bad += 1; reject("unresolved_reference", s, e, u.reason, ref=ref, hint=u.hint); continue
        adj = _adjacent(answer, s, e)
        if adj:
            refs_bad += 1
            for reason, a0, a1 in adj[:1]: reject("adjacent_to_reference", a0, a1, reason, ref=ref)
            continue
        marks.append((s, e, render_value(r.value, r.unit, decimal_mark), None))

    plain = list(answer)
    for s, e in spans:
        for i in range(s, e): plain[i] = " "
    plain = "".join(plain)

    total = unverified = 0
    def allowed_num(n): return any(abs(v) in values for v, _, _ in n.readings)
    for n in gate.extract_numbers(plain):
        reason = n.exempt
        if reason == "year": reason = None                                     # no year exemption in v2
        if reason == "small_integer" and _after_pk_label(plain, n.start): reason = None
        if reason:
            exempt.append({"number": n.raw, "position": [n.start, n.end], "reason": reason}); continue
        if allowed_num(n): total += 1; continue
        if n.parts and all(allowed_num(p) for p in n.parts): total += len(n.parts); continue
        total += 1; unverified += 1
        v, sig, _ = n.readings[0]
        f = _finding("bare_number", n.text, n.start, n.span_end, answer,
                     "a number typed by hand that is not in the user's message (tool values are cited, never typed)",
                     value=str(v.normalize() if v != 0 else 0), sig=sig, unit=n.unit, nearest=gate._nearest(abs(v), allowed), number=n.raw)
        findings.append(f); marks.append((n.start, n.span_end, None, "not in the user's message"))

    for m in _NUMWORDS_RE.finditer(plain):
        s, e, w = m.start(), m.end(), m.group(0)
        words = re.split(r"[ \t-]+", w.strip())
        compound = len(words) > 1 or re.fullmatch(_BIG, w, re.I) is not None
        if re.fullmatch(r"cents?", w, re.I) and re.search(r"(?:pour|per)[ \t]*$", plain[:s], re.I): continue   # pour cent
        after = plain[e:]
        why = None
        if compound: why = "a quantity spelled in words"
        elif _DECIMAL_WORD_RE.match(after): why = "a decimal spelled in words"
        elif _UNIT_AFTER_WORD_RE.match(after): why = "a quantity spelled in words with a unit"
        elif _after_pk_label(plain, s): why = "a parameter value spelled in words"
        if why is None:
            exempt.append({"number": w, "position": [s, e], "reason": "count_word"}); continue
        end = e
        for rx in (_DECIMAL_WORD_RE, _UNIT_AFTER_WORD_RE):
            mm = rx.match(after)
            if mm: end = e + mm.end(); break
        total += 1; unverified += 1
        findings.append(_finding("number_word", answer[s:end], s, end, answer, why)); marks.append((s, end, None, why))
    for m in _FRACTION_RE.finditer(plain):
        s, e, w = m.start(), m.end(), m.group(0)
        if re.match(r"-?\s?(?:vies?|li(?:fe|ves))\b", plain[e:], re.I): continue        # demi-vie(s), half-life, half-lives
        total += 1; unverified += 1
        findings.append(_finding("number_word", w, s, e, answer, "a multiple or a fraction spelled in words")); marks.append((s, e, None, "a multiple or a fraction in words"))

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
            "numbers_total": total + refs_total, "numbers_unverified": unverified + refs_bad, "numbers_exempt": len(exempt),
            "references_total": refs_total, "references_unresolved": refs_bad}

# ---------------------------------------------------------------- messages built from the findings
def describe(calls):
    """One line per citable tool result (the parameters of an analysis are listed in the finding that misnamed one)."""
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
        elif isinstance(sc.get("worksheet"), dict):
            desc = f"{ref} ({name}, worksheet {sc['worksheet'].get('id')}: rows, subjects)"
        else: desc = f"{ref} ({name})"
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
        elif f["kind"] == "adjacent_to_reference": lines.append(f"- \"{f['text']}\": {f['reason']}; write the reference alone")
        elif f["kind"] == "number_word": lines.append(f"- \"{f['text']}\": {f['reason']}; cite a tool value by reference or use the user's digits")
        else: lines.append(f"- {f['text']}: {f['reason']}")
    avail = describe(calls)
    aliases = alias_line(calls)
    return ("[system reminder] Your last answer was rejected by the renderer:\n" + "\n".join(lines[:limit]) + "\n"
            "Rule: never type a value a tool returned, not even rounded. Cite it as {{ref.parameter}}, e.g. {{call_3.cmax}}, and the "
            "client prints the value with its unit; write no unit, sign, digit or arithmetic next to a reference. The only digits you "
            "may type are those of the user's message. If a value is missing, say that Caladrius did not return it.\n"
            + ("Available references: " + "; ".join(avail) + "\n" if avail else "") + (aliases + "\n" if aliases else "")
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
