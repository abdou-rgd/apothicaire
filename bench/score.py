"""Scoring of the benchmark: expected-number matching (the gate's rounding rule), the failure taxonomy and the oracle check.

Pure Python, no model, no engine. Three things (the third is the last section of this file):

1. `score_turn(answer, expect, unverified_after, tool_results)`: does the answer contain the numbers it must contain
   (`expect["must"]`, each a truth value), none of the numbers it must not (`expect["must_not"]`:
   converted or computed values), the words it must (`expect["words"]`), and, for a question whose answer
   is "not available", no number outside the sources (`expect["no_new_numbers"]`)? A `must_not` value is
   not counted when every number of the answer that hits it is written verbatim in a tool result of that turn
   (`tool_results`, the texts the tools returned): the engine computed it, the answer did not (2026-10-10: the
   decision harness shows Caladrius's own L/h and L conversion next to the "dose unit" value, which the
   "CL x 10^3" rule, written against a model that converts by itself, flagged).
   A truth value T is "found" when some number written in the answer, with n significant digits
   (n >= 2, the gate's counting), equals T rounded to n significant digits (half-up or half-even, like
   the gate). A forbidden value F is "hit" with the same rule but only for numbers written with at least
   3 significant digits (a 2-digit number matching by chance is not evidence of a wrong value).

2. `classify(finding, allowed, kind)`: puts one unverified number of the gate into a class. Rules, in order,
   first match wins; a number written with fewer digits than a rule needs falls through to the next rule. They are
   heuristics on top of the deterministic check (the unverified count never depends on them) and some fire by chance:
   `chance_baseline` measures how often on random numbers, and the report prints it:
     recall_error        the turn is a recall turn (the number should have come from the user's message)
     unit_conversion     the number is an allowed number times a power of ten (3 digits or more), or times 60 or
                         1/60 and a power of ten (4 digits or more): a unit factor (ng to mg, h to min, mL to L...)
     arithmetic          the sum, difference, product, ratio or percentage ratio of two numbers written in the same
                         answer (3 digits or more) or of two allowed numbers (4 digits or more): a computation the
                         model did itself
     unlabelled_misread  a near miss of an allowed number: within 2 % of it, or the same digits with one
                         digit changed (a value copied wrongly, or taken from another parameter)
     other               none of the above (an invented value)

3. `oracle_turn(answer, expect, meta, deviations)` / `oracle_exercise(meta, script, turns)`: the oracle check, a second judgement next
   to the gate. The gate asks whether a number is in a tool result; the oracle asks whether the number written after the label of the
   parameter the question asks for is Caladrius's value of THAT parameter, from the right AUC method, with the unit Caladrius reports.
   Mismatches are classified wrong_parameter / wrong_method / wrong_option / missing_unit / wrong_unit / missing_value (rules in the
   comment above `METHODS`). `tool_arg_audit` lists the tool calls whose arguments differ from the exercise's intent.
"""
import itertools, math, os, re, sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import gate  # noqa: E402

D = Decimal

# ---------------------------------------------------------------- matching expected numbers
def written_numbers(text):
    """[(readings, raw)] of every number written in `text` (exempt ones included)."""
    return [(n.readings, n.raw) for n in gate.extract_numbers(text)]

def _eq_rounded(truth, v, n):
    return any(gate.round_sig(abs(truth), n, m) == abs(v) for m in (gate.ROUND_HALF_UP, gate.ROUND_HALF_EVEN))

def matches(truth, readings, min_sig=2, first_only=False):
    """Does a written number (its readings) equal `truth` rounded to the digits written? `first_only`: the
    decimal reading only (121.258 is also 121258 for the gate; a forbidden value must not hit on that second reading)."""
    t = D(repr(truth)) if isinstance(truth, float) else D(truth)
    return any(s >= min_sig and _eq_rounded(t, v, s) for v, s, _ in (readings[:1] if first_only else readings))

def find_value(answer, truth, min_sig=2):
    return any(matches(truth, r, min_sig) for r, _ in written_numbers(answer))

def tool_numbers(tool_results):
    """The numbers written in tool results, as their raw text (what an answer copies verbatim)."""
    return {raw for text in tool_results or () for _, raw in written_numbers(text)}

def score_turn(answer, expect, unverified_after=0, tool_results=()):
    """Correctness of one answer against its expected-answer rule. Returns a dict:
    found / missing (labels of `must`), forbidden (labels of `must_not` that appear), forbidden_from_tools (labels of
    `must_not` hit only by numbers copied verbatim from `tool_results`, not counted), words_missing,
    new_numbers (for `no_new_numbers`), fraction (found / must), correct."""
    nums = written_numbers(answer)
    from_tools = tool_numbers(tool_results)
    found, missing, forbidden, from_tool, words_missing = [], [], [], [], []
    for item in expect.get("must", []):
        (found if any(matches(item["value"], r) for r, _ in nums) else missing).append(item["label"])
    for item in expect.get("must_not", []):
        hits = [raw for r, raw in nums if matches(item["value"], r, min_sig=3, first_only=True)]
        if hits: (from_tool if all(raw in from_tools for raw in hits) else forbidden).append(item["label"])
    for w in expect.get("words", []):
        if not re.search(w["pattern"], answer, re.I | re.S): words_missing.append(w["label"])
    new_numbers = unverified_after if expect.get("no_new_numbers") else 0
    n_must = len(expect.get("must", []))
    correct = not missing and not forbidden and not words_missing and not new_numbers
    return {"found": found, "missing": missing, "forbidden": forbidden, "forbidden_from_tools": from_tool, "words_missing": words_missing,
            "new_numbers": new_numbers, "n_must": n_must,
            "fraction": (len(found) / n_must) if n_must else 1.0, "correct": correct}

# ---------------------------------------------------------------- taxonomy
CLASSES = ("unit_conversion", "arithmetic", "unlabelled_misread", "recall_error", "other")
_POW10 = [10.0 ** k for k in range(-9, 10) if k != 0]
_FACTORS = _POW10 + [60.0 * p for p in [1.0] + _POW10] + [p / 60.0 for p in [1.0] + _POW10]

def _tol(n):
    """Relative half-width of a rounding to n significant digits (generous by a factor 1.01)."""
    return 0.5 * 10.0 ** (1 - n) * 1.01

def _close(c, r, n):
    """Float prefilter, then the exact rule: c equals r rounded to n significant digits."""
    if r <= 0 or abs(r - c) > _tol(n) * c * 10: return False
    return _eq_rounded(D(repr(r)), D(repr(c)), n)

def _distinct_values(allowed):
    seen, out = set(), []
    for a in allowed:
        if a.value > 0 and a.value not in seen: seen.add(a.value); out.append(a.value)
    return out

def _digits(x):
    return re.sub(r"\D", "", format(x.normalize(), "f")).strip("0")

def _near_miss(c, vals):
    cd = _digits(c)
    for a in vals:
        if c != a and abs(c - a) <= D("0.02") * a: return True
        ad = _digits(a)
        if len(ad) == len(cd) >= 3 and sum(x != y for x, y in zip(ad, cd)) == 1: return True
    return False

def _local_operands(answer, finding):
    """The other numbers written in the same answer (the likely operands of a computation the model did)."""
    pos = finding.get("position") or [-1, -1]
    out = []
    for nm in gate.extract_numbers(answer):
        if nm.start < pos[1] and nm.end > pos[0]: continue            # the finding itself
        v = abs(float(nm.readings[0][0]))
        if v > 0 and v not in out: out.append(v)
    return out

def classify(finding, allowed, kind=None, answer=None):
    """Class of one unverified number. `finding` is a gate finding (value, significant_digits, ...),
    `allowed` the gate's allowed set (gate.allowed_numbers), `kind` the question type of the turn, `answer` the text
    the finding comes from (lets the arithmetic rule use the numbers written next to it, with 3 digits)."""
    if kind == "recall": return "recall_error"
    cd = abs(D(finding["value"])); n = max(finding.get("significant_digits", 2), 2)
    if cd == 0: return "other"
    c = float(cd); vals = _distinct_values(allowed); fl = [float(v) for v in vals]
    if n >= 3:                                                       # 1. a unit factor; with 3 digits only a power of ten
        factors = _FACTORS if n >= 4 else _POW10                      # (x 60 and 1/60 match by chance too often)
        for a in fl:
            for f in factors:
                if _close(c, a * f, n): return "unit_conversion"
    if answer is not None and n >= 3:                                # 2a. arithmetic on two numbers written in the same answer
        ops = _local_operands(answer, finding)[:14]
        for a, b in itertools.permutations(ops, 2):
            for r in (a - b, a + b, a / b, a / b * 100.0, (a - b) / b * 100.0, a * b):
                if _close(c, r, n): return "arithmetic"
    if n >= 4:                                                       # 2b. arithmetic on two allowed numbers
        pool = fl if len(fl) <= 250 else fl[:250]                     # (with fewer digits it is chance, see chance_baseline)
        for a, b in itertools.permutations(pool, 2):
            for r in (a - b, a + b, a / b, a / b * 100.0, (a - b) / b * 100.0, a * b):
                if _close(c, r, n): return "arithmetic"
    if _near_miss(cd, vals): return "unlabelled_misread"            # 3. a copy that is not verbatim
    return "other"

def classify_all(findings, allowed, kind=None, answer=None):
    return [classify(f, allowed, kind, answer) for f in findings]

def chance_baseline(allowed, n=100, seed=0, digits=3):
    """How the rules classify RANDOM numbers (log-uniform over the allowed set's range, `digits` significant
    digits): the share of each class that is chance, not evidence. Deterministic for a seed."""
    import random
    rng = random.Random(seed)
    vals = [float(v) for v in _distinct_values(allowed)] or [1.0]
    lo, hi = math.log10(min(vals)) - 1, math.log10(max(vals)) + 1
    out = {c: 0 for c in CLASSES}
    for _ in range(n):
        x = float(f"{10 ** rng.uniform(lo, hi):.{digits}g}")
        f = {"value": repr(x), "significant_digits": digits}
        out[classify(f, allowed)] += 1
    return out

# ---------------------------------------------------------------- oracle check
# A second, independent judgement next to the gate. The gate asks "is this number in a tool result?"; the oracle asks
# "is it the number of the parameter the question asks for, in the unit Caladrius reports, from the right analysis?".
# Per turn it reads the expectation (`expect["must"]`: label, key, truth value, `method` = the analysis it comes from,
# `unit` = the unit Caladrius reports, `by_method` for the two AUC of the compare turn) and the ground truth of meta.json.
#
# For an expected item the claimed numbers are those written after the item's label in the answer (a closed table of
# French / English spellings, `_ALIASES`): from the label to the next label of the turn or the end of the line. For
# the two AUC of the compare turn the label is the method named (linéaire, linear-up/log-down, lin_up_log_down). If the
# label is nowhere in the answer, every number of the answer is a claim. Verdict, in order:
#   a claim equals the truth (the gate's rounding rule, 2 digits or more) ->
#        the unit written after it (until the next number, or the next cell of a table row when only a "(obs)" lies
#        between) must be the unit Caladrius reports, as a token of a closed vocabulary: none -> missing_unit,
#        another one -> wrong_unit; any claim with the right unit is enough
#   no claim equals the truth ->
#        a claim (4 digits or more) equals another parameter of the SAME analysis             wrong_parameter
#        a claim equals the same parameter of the OTHER AUC method (3 digits or more), or any
#        parameter of the other analysis (4 digits or more)                                   wrong_method
#        the analysis of that method was run with arguments other than the exercise's intent
#        (score.nca_call_deviations: `start: zero`, another dose / route / option)             wrong_option
#        nothing of the above (also: no number after the label)                               missing_value
# wrong_option is only decided when the value is wrong: a deviating call whose values still equal the truth is not an error
# of the answer (it is listed by the tool-argument audit). Not covered: the not_available turns (no value to check),
# the route and method words of the recall turn (the scorer's `words`), free text and reasoning.
METHODS = ("linear", "lin_up_log_down")
ORACLE_CLASSES = ("wrong_parameter", "wrong_method", "wrong_option", "missing_unit", "wrong_unit", "missing_value")
ATTRIB_SIG_PARAMETER, ATTRIB_SIG_METHOD = 4, 3
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—―−"})
# key -> (regex of the label, a number written right before the label also counts: "7 points")
_ALIASES = {
    "cmax": (r"\bc[ _]?max\b", False), "tmax": (r"\bt[ _]?max\b", False),
    "c0": (r"\bc[ _]?0\b|concentration initiale", False),
    "auclast": (r"\bauc\s?_?\(?\s?0\s?-\s?t[ _]?last\s?\)?|\bauc[ _]?last\b|\bauc\s?\(\s?0\s?-\s?t\s?\)", False),
    "aucinf.obs": (r"\bauc\s?_?\(?\s?0\s?-\s?(?:inf|∞)\w*\s?\)?|\bauc[ _]?inf\b", False),
    "lambda.z": (r"(?:λ|\blambda)[ _.]?z(?![a-z])", False),
    "half.life": (r"\bt\s?(?:½|1/2|1⁄2)|demi-vie|half[ -]?life", False),
    "cl.obs": (r"\bcl(?:\s?/\s?f)?(?![\w/])|clairance|clearance", False),
    "vz.obs": (r"\bvz(?:\s?/\s?f)?(?![\w/])|volume de distribution", False),
    "mrt.obs": (r"\bmrt\b", False), "mrt.iv.obs": (r"\bmrt\b", False),
    "aucpext.obs": (r"extrapol|aucpext|auc[ _]?%[ _]?ext", False),
    "lambda.z.n.points": (r"nombre de points|\bn[ _]?points|\bpoints\b|\bn\s?pts|lambda\.z\.n\.points", True),
    "adj.r.squared": (r"(?<![a-z])r\s?[²2](?!\d)|adj\.r\.squared", False),
    "dose": (r"\bdose\b", False),
    # the compare turn when the model used analysis_compare: the engine's difference (b - a) and its percentage
    "compare.percent": (r"diff[ée]rence relative|[ée]cart relatif|variation relative|diff[ée]rence en pourcent\w*|en pourcent\w*|"
                        r"pourcent\w*|\brelative?\b|\brelatif\b|\bpercent\w*", False),
    "compare.difference": (r"\bdiff[èe]re\b|\bdiff[ée]rences?\b|[ée]carts?\b|\bdiff\b|\bvariation\b|\bdelta\b|Δ|\bdifference\b|"
                           r"\bvaleur absolue\b|\babsolute\b", False),
}
_LUD_RE = re.compile(r"lin(?:ear|[ée]aire)?[\s_-]*up[\s_/-]*log[\s_-]*down|lin_up_log_down", re.I)
_LIN_RE = re.compile(r"lin[ée]aire|linear(?!\w)", re.I)
_LEAD_RE = re.compile(r"(?:avec|par|pour|selon|via|en|with|using)\s+(?:la\s+|the\s+)?(?:m[ée]thode\s+|method\s+)?[*_`\s]*$", re.I)
_SKIP_EXEMPT = ("date", "power_of_ten", "unit_fragment", "label_number")
_REF_BEFORE_RE = re.compile(r"(?:analyse|analysis|feuille|worksheet|message|n°|n[o°]\.?)\s*$", re.I)
_ANNOTATION_RE = re.compile(r"\([^)]*\)|\b(?:obs|pred|préd|observée?|prédite?)\b", re.I)
_DOSE_UNIT_FORMS = {"ug": ("µg", "μg", "ug", "microgramme", "microgrammes"), "mg": ("mg", "milligramme", "milligrammes")}
_GENERIC_UNITS = ("l/h", "l/min", "ml/min", "ml/h", "mg/l", "µg/l", "μg/l", "ng/ml", "µg/ml", "μg/ml", "mg/ml", "ng/l", "mg", "µg",
                  "μg", "ug", "ng", "min", "h", "1/h", "1/min", "%", "h*ng/ml", "h*mg/l", "h*µg/ml", "h*ng/l", "microgramme", "microgrammes",
                  "milligramme", "milligrammes")

def _norm_unit(s):
    """A unit (or the text after a number) in a form where 'h·ng/mL', 'h.ng/mL' and 'h*ng / mL' are the same string and
    'dose unit' is one token; markdown bold and code marks are dropped."""
    s = re.sub(r"\*{2,}|`", "", s.lower())
    s = re.sub(r"[·⋅∙×]", "*", s)
    s = re.sub(r"(?<=[a-zµμ)])\.(?=[a-zµμ(])", "*", s)
    s = re.sub(r"dose\s+unit", "doseunit", s)
    s = re.sub(r"(?<![a-z])(h|min|s)\s*\^?\s*[-⁻−]\s*[1¹](?!\d)", r"1/\1", s)           # h⁻¹, h^-1, h-1 are 1/h
    return re.sub(r"\s*([/*()^])\s*", r"\1", s)

def unit_vocabulary(meta):
    """Every unit string an answer can carry for this exercise (normalised, longest first): the units of all parameters of
    both analyses, the time / concentration / dose units, 'dose unit' replaced by each dose unit, a few common ones."""
    raw = set(_GENERIC_UNITS) | {meta["units"]["time"], meta["units"]["conc"]}
    for m in meta["ground_truth"]["nca"].values():
        raw |= {p["unit"] for p in m["parameters"].values() if p.get("unit")}
    raw |= {u for forms in _DOSE_UNIT_FORMS.values() for u in forms}
    for u in list(raw):
        if "dose unit" in u: raw |= {u.replace("dose unit", d) for d in ("mg", "µg", "ug", "μg")}
    return sorted({_norm_unit(u) for u in raw if u}, key=lambda u: (-len(u), u))

def _is_unit_exponent(text, n):
    """The 1 of 'h-1' or of 'h^-1': a digit glued by a minus or a caret to a letter belongs to a unit, it is not a number."""
    return n.start >= 2 and text[n.start - 1] in "-^−⁻" and text[n.start - 2].isalpha()

def _unit_boundary(c): return c.isalnum() or c in "/*^"

def _first_unit(seg, vocab):
    """The first unit of the vocabulary written in `seg` (normalised text), as a whole token; None if there is none."""
    for i in range(len(seg)):
        if i and _unit_boundary(seg[i - 1]): continue
        for u in vocab:
            if seg.startswith(u, i) and (i + len(u) == len(seg) or not _unit_boundary(seg[i + len(u)])): return u
    return None

def _unit_after(answer, nums, k, vocab):
    """Unit written after the k-th number of a line (`nums`: the numbers of the line in order, unit fragments excluded)."""
    line_end = answer.find("\n", nums[k].end); line_end = len(answer) if line_end < 0 else line_end
    for j in range(k, len(nums)):
        end = nums[j + 1].start if j + 1 < len(nums) else line_end
        seg = answer[nums[j].end:end]
        u = _first_unit(_norm_unit(seg), vocab)
        if u: return u
        if re.search(r"[^\W\d_]", _ANNOTATION_RE.sub("", seg)): return None        # a label of something else lies between
    return None

def _mask(text, spans):
    for a, b in spans: text = text[:a] + " " * (b - a) + text[b:]
    return text

def _marks(text, items):
    """[(start, end, tag)] of the labels of the turn in `text` (dash-normalised): ('key', key) for the aliases of the
    expected parameters, ('method', m) for the AUC method mentions when an item is by_method."""
    marks = []
    for key in {it["key"] for it in items if not it.get("by_method")}:
        rx = _ALIASES.get(key)
        if rx: marks += [(m.start(), m.end(), ("key", key)) for m in re.finditer(rx[0], text, re.I)]
    if any(it.get("by_method") for it in items):
        lud = [(m.start(), m.end()) for m in _LUD_RE.finditer(text)]
        marks += [(a, b, ("method", "lin_up_log_down")) for a, b in lud]
        marks += [(m.start(), m.end(), ("method", "linear")) for m in _LIN_RE.finditer(_mask(text, lud))]
    marks.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    kept = []
    for m in marks:
        if not kept or m[0] >= kept[-1][1]: kept.append(m)
    return kept

def _eol(text, pos):
    e = text.find(chr(10), pos)
    return len(text) if e < 0 else e

def _spans(text, item, marks):
    """[[(lo, hi)]] one list of text spans per label of `item` in which its numbers are claimed. A key label: from the label to
    the next label of the turn or the end of the line (plus a number written right before it, if the label allows it: "7 points").
    A method label (the two AUC of the compare turn): the same, and in the lines that follow it up to the next method label, the
    part after an AUC(0-tlast) label ("Avec la méthode linéaire :" then one line per parameter)."""
    by_method = item.get("by_method")
    tag = ("method", item["method"]) if by_method else ("key", item["key"])
    out = []
    for i, (a, b, t) in enumerate(marks):
        if t != tag: continue
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        if not by_method:                                                # a method named inside the line ("lin-up/log-down - linéaire")
            nxt = next((m[0] for m in marks[i + 1:] if m[2][0] == "key"), len(text))   # does not end the span of a key label
        spans = [(b, min(nxt, _eol(text, b)))]
        if by_method:
            # "<value> avec la méthode linéaire": the value written right before the method label, in the same line
            lo = max(marks[i - 1][1] if i else 0, text.rfind(chr(10), 0, a) + 1)
            if _LEAD_RE.search(text[lo:a]):
                lead = [n for n in gate.extract_numbers(text[lo:a]) if n.exempt not in _SKIP_EXEMPT]
                if lead: spans.append((lo + lead[-1].start, lo + lead[-1].end))
            pos = _eol(text, b) + 1
            while pos < nxt:
                end = min(_eol(text, pos), nxt)
                m = re.compile(_ALIASES["auclast"][0], re.I).search(text, pos, end)
                if m: spans.append((m.end(), end))
                pos = _eol(text, pos) + 1
        elif _ALIASES.get(item["key"], (0, False))[1]:
            ls = text.rfind(chr(10), 0, a) + 1
            spans.append((max(ls, a - 4), a))
        out.append(spans)
    return out

def _claims(answer, item, marks, vocab):
    """The numbers claimed for `item`: [{"raw", "readings", "unit", "primary"}] (primary: the first number of 3 digits or more
    after a label, the one the attribution of a wrong value looks at); second value: whether a label was found."""
    allnums = gate.extract_numbers(answer)
    allnums = [n for n in allnums if not _is_unit_exponent(answer, n)]
    nums = [n for n in allnums if n.exempt not in _SKIP_EXEMPT]
    nums = [n for n in nums if not _REF_BEFORE_RE.search(answer[max(0, n.start - 12):n.start])]
    groups = _spans(answer.translate(_DASHES), item, marks)
    seen, out = set(), []
    unit_of = lambda n: _unit_of(answer, allnums, n, vocab)
    for spans in (groups or [[(0, len(answer))]]):
        in_group = [n for lo, hi in spans for n in nums if lo <= n.start < hi]
        first = next((n for n in in_group if max(s for _, s, _ in n.readings) >= 3), None) if groups else None
        for n in in_group:
            if n.start in seen: continue
            seen.add(n.start)
            out.append({"raw": n.raw, "readings": n.readings, "unit": unit_of(n), "primary": n is first})
    return out, bool(groups)

def _unit_of(answer, allnums, n, vocab):
    ls = answer.rfind(chr(10), 0, n.start) + 1; le = _eol(answer, n.start)
    line = [x for x in allnums if ls <= x.start < le and x.exempt != "unit_fragment"]
    k = next((j for j, x in enumerate(line) if x.start == n.start), None)
    return _unit_after(answer, line, k, vocab) if k is not None else None

def _expected_unit_forms(item):
    u = item.get("unit") or ""
    if u in _DOSE_UNIT_FORMS: return {_norm_unit(x) for x in _DOSE_UNIT_FORMS[u]}
    return {_norm_unit(u)} if u else set()

def _truth_pool(meta):
    """[(method, key, value)] of every non-zero parameter of both analyses, to attribute a wrong number."""
    return [(m, k, p["value"]) for m, a in meta["ground_truth"]["nca"].items() for k, p in a["parameters"].items() if p["value"]]

def oracle_item(answer, marks, item, meta, vocab, deviations):
    """Verdict on one expected item: {"label", "key", "method", "ok", "class", "detail", "labelled", "claimed"}."""
    claims, labelled = _claims(answer, item, marks, vocab)
    res = {"label": item["label"], "key": item["key"], "method": item.get("method"), "ok": False, "class": None, "detail": None,
           "labelled": labelled, "claimed": [(c["raw"] + (" " + c["unit"] if c["unit"] else "")) for c in claims[:4]]}
    hit = [c for c in claims if matches(item["value"], c["readings"])]
    if hit:
        forms = _expected_unit_forms(item)
        if not forms or any(c["unit"] in forms for c in hit): res["ok"] = True
        elif any(c["unit"] for c in hit): res.update({"class": "wrong_unit", "detail": next(c["unit"] for c in hit if c["unit"])})
        else: res["class"] = "missing_unit"
        return res
    method = item.get("method")
    if claims and method:
        pool = _truth_pool(meta)
        for c in (c for c in claims if c["primary"]):
            for m, k, v in pool:                                         # another parameter of the same analysis
                if m == method and k != item["key"] and matches(v, c["readings"], ATTRIB_SIG_PARAMETER):
                    res.update({"class": "wrong_parameter", "detail": k}); return res
        for c in (c for c in claims if c["primary"]):
            for m, k, v in pool:                                         # the other AUC method
                if m != method and matches(v, c["readings"], ATTRIB_SIG_METHOD if k == item["key"] else ATTRIB_SIG_PARAMETER):
                    res.update({"class": "wrong_method", "detail": f"{k} of {m}"}); return res
        if deviations.get(method):
            res.update({"class": "wrong_option", "detail": ", ".join(f"{d['field']}={d['got']}" for d in deviations[method])}); return res
    res["class"] = "missing_value"
    return res

def oracle_turn(answer, expect, meta, deviations=None, vocab=None):
    """Oracle verdict on one answer: None if the turn expects no number; else {"n_items", "n_ok", "correct", "items"}.
    `deviations`: {method: [deviation]} of the analyses in effect (see oracle_exercise)."""
    items = expect.get("must") or []
    if not items: return None
    marks = _marks(answer.translate(_DASHES), items); vocab = vocab or unit_vocabulary(meta)
    res = [oracle_item(answer, marks, it, meta, vocab, deviations or {}) for it in items]
    return {"n_items": len(res), "n_ok": sum(r["ok"] for r in res), "correct": all(r["ok"] for r in res), "items": res}

# ---------------------------------------------------------------- tool-call arguments against the exercise's intent
def nca_call_deviations(meta, args):
    """How the arguments of an `nca_run` call differ from the intent of the exercise (`nca_run_arguments` of meta.json:
    dose, route, options = the AUC method and the units): [{"field", "got", "intended"}]. An option the call adds (start: zero)
    or changes is a deviation; so is an unknown AUC method, another dose or route, any other argument."""
    gt = meta["ground_truth"]["nca"]; out = []
    dev = lambda field, got, intended: out.append({"field": field, "got": got, "intended": intended})
    opts = {k: v for k, v in (args.get("options") or {}).items() if v is not None}
    m = opts.get("auc_method"); ref = gt["linear"]["nca_run_arguments"]
    if m in gt: intended = gt[m]["nca_run_arguments"]["options"]
    else: intended = {}; dev("options.auc_method", m, "linear or lin_up_log_down")
    for k in sorted(set(opts) | set(intended)):
        if k == "auc_method" and m not in gt: continue
        if opts.get(k) != intended.get(k): dev(f"options.{k}", opts.get(k), intended.get(k))
    try: dose_ok = args.get("dose") is not None and float(args["dose"]) == float(ref["dose"])
    except (TypeError, ValueError): dose_ok = False
    if not dose_ok: dev("dose", args.get("dose"), ref["dose"])
    if args.get("route") != ref["route"]: dev("route", args.get("route"), ref["route"])
    for k in sorted(set(args) - {"worksheet", "dose", "route", "options"}): dev(k, args[k], None)
    return out

_NATURAL_ROLES = ("time", "concentration")

def import_call_deviations(meta, args):
    """Same for `data_import`: the CSV must be the exercise's (the runner elides it to a marker) and the columns must carry the
    exercise's units, in order. The names of the columns and of the worksheet are free, and a role that agrees with the
    position (time, concentration) is not a deviation."""
    out = []; csv = args.get("csv")
    if isinstance(csv, str) and "DIFFERENT" in csv: out.append({"field": "csv", "got": csv, "intended": "identical to the exercise CSV"})
    want = [c["unit"] for c in meta["ground_truth"]["data_import_columns"]]
    cols = [c for c in (args.get("columns") or []) if isinstance(c, dict)]
    got = [c.get("unit") for c in cols]
    if got != want: out.append({"field": "columns.unit", "got": got, "intended": want})
    for pos, c in enumerate(cols):
        nat = _NATURAL_ROLES[pos] if pos < len(_NATURAL_ROLES) else None
        if c.get("role") not in (None, nat): out.append({"field": f"columns[{pos}].role", "got": c.get("role"), "intended": nat})
    return out

def tool_arg_audit(meta, turns):
    """Every `nca_run` / `data_import` call of an exercise whose arguments differ from the intent:
    {"calls": audited calls, "deviating_calls": n, "deviations": [{"turn", "tool", "status", "field", "got", "intended"}]}."""
    calls = dev_calls = 0; devs = []
    for t in turns:
        for c in t.get("tool_calls", []):
            if c["name"] not in ("nca_run", "data_import"): continue
            calls += 1
            d = (nca_call_deviations if c["name"] == "nca_run" else import_call_deviations)(meta, c.get("args") or {})
            if d: dev_calls += 1
            devs += [{"turn": t["turn"], "tool": c["name"], "status": c["status"], **x} for x in d]
    return {"calls": calls, "deviating_calls": dev_calls, "deviations": devs}

def oracle_exercise(meta, script, turns, badge_mark="\n\n⚠ "):
    """Oracle verdicts of the turns of one exercise, aligned with `turns`. The analysis in effect for a method is the latest
    valid `nca_run` call of that method up to the turn; its deviations from the intent feed `wrong_option`."""
    vocab = unit_vocabulary(meta); state, out = {}, []
    for t, st in zip(turns, script):
        for c in t.get("tool_calls", []):
            if c["name"] != "nca_run" or c.get("status") != "valid": continue
            m = ((c.get("args") or {}).get("options") or {}).get("auc_method")
            if m in METHODS: state[m] = nca_call_deviations(meta, c["args"])
        out.append(None if "error" in t else oracle_turn(t["answer"].split(badge_mark)[0], st["expect"], meta, state, vocab))
    return out


# ---------------------------------------------------------------- the compare turn: what the model did with analysis_compare
_ID_RE = re.compile(r'"analysis":\s*(\d+)'); _METHOD_RE = re.compile(r'"auc_method":\s*"(\w+)"')
_AUCLAST_ROW_RE = re.compile(r'"auclast":\s*"([^"]*)"')

def analysis_methods(calls):
    """{analysis id: AUC method in effect} of the valid `nca_run` calls (stored form: name, status, shown), read from the digest the
    model was shown (`"analysis":N`, `options_used.auc_method`)."""
    out = {}
    for c in calls:
        if c.get("name") != "nca_run" or c.get("status") != "valid": continue
        i, m = _ID_RE.search(c.get("shown") or ""), _METHOD_RE.search(c.get("shown") or "")
        if i and m: out[int(i.group(1))] = m.group(1)
    return out

def parse_compare_row(shown):
    """The auclast row of an `analysis_compare` digest (apothicaire.digest_compare): {"a", "b", "difference", "percent", "ratio"} as
    floats (units dropped), or None when there is no such row or it lacks the difference or the percentage."""
    m = _AUCLAST_ROW_RE.search(shown or "")
    if not m: return None
    row = {}
    for part in m.group(1).split(" | "):
        k, _, rest = part.partition(" ")
        if k in ("a", "b", "difference", "percent", "ratio"):
            try: row[k] = float(rest.split(" ")[0])
            except ValueError: pass
    return row if {"a", "b", "difference", "percent", "ratio"} <= set(row) else None

def compare_usage(prior_calls, turn_calls, truth=None):
    """What the model did with `analysis_compare` in a turn. `prior_calls`: the stored tool calls of the earlier turns (they say which
    analysis id is which AUC method), `turn_calls`: those of this turn. Returns
    {"calls": analysis_compare calls, "valid": of those, "usable": bool, "reference": method of analysis a, "row": the auclast row}.
    usable = the last valid call compares the linear and the lin-up/log-down analysis and its result holds the auclast row with the
    difference and the percentage; `truth(reference)` (optional, scripts.compare_truth) is the independent check: the row must equal the
    ground-truth arithmetic of meta.json to 5e-5 (6 significant digits displayed), otherwise usable is False and `mismatch` is set."""
    methods = analysis_methods(list(prior_calls) + list(turn_calls))
    cc = [c for c in turn_calls if c.get("name") == "analysis_compare"]
    out = {"calls": len(cc), "valid": sum(c.get("status") == "valid" for c in cc), "usable": False, "reference": None, "row": None}
    for c in reversed([c for c in cc if c.get("status") == "valid"]):
        args = c.get("args") or {}
        try: ma, mb = methods.get(int(args.get("a"))), methods.get(int(args.get("b")))
        except (TypeError, ValueError): continue
        if {ma, mb} != set(METHODS): continue
        row = parse_compare_row(c.get("shown"))
        if row is None: continue
        out.update(reference=ma, row=row)
        if truth is not None:
            t = truth(ma)
            if any(abs(row[k] - t[k]) > 5e-5 * max(abs(t[k]), 1e-12) for k in ("difference", "percent", "ratio")):
                out["mismatch"] = {"tool": row, "truth": t}; return out
        out["usable"] = True
        return out
    return out
