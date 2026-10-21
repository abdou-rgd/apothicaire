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


# ---------------------------------------------------------------- rubric of the frozen sets (FROZEN_SET.md §6.2, T-066)
# The scorer of the frozen sets. `score_turn` above stays as the development scorer of the in-sample runs (its figures are
# kept next to the rubric's, T-066); `rubric_turn` is the one FROZEN_SET.md §6.2 writes down. It reads the text the user sees
# (the badge of gate v1 cut off, the values rendered by gate v2 kept) and does not depend on the gate: the same answer gets
# the same verdict under v1 and v2. A quantity is STATED when a number is attached to its label (the closed table `_ALIASES`)
# in the same clause or table row; then, per expected item:
#   1. label-bound      a number without its label never counts (no fallback on the whole answer)
#   2. signed value     the value equals the engine value under the gate's rounding rule, sign included; the unit, when
#                       written, is the engine's or an exact rewriting of it (`_canon_unit`); the dose of the recall turn
#                       needs its unit
#   3. negation         a number in a negated or disowned clause (`NEGATION_RE`) is not a statement
#   4. contradiction    another value (3 significant digits or more, same unit or none) for the same asked quantity
#   5. no dump          outside turn 1, more than 3 quantities the turn did not ask for (`DUMP_LIMIT`); a forbidden value
#                       (the `must_not` lists of scripts.py: converted or computed by the model) fails at any count
#   6. verdict          turn 4 states whether the extrapolation is acceptable, and the verdict matches the gold
#                       (acceptable when AUC % extrapolated <= 20 %; between 18 % and 22 % either verdict passes)
#   7. turn specifics   recall: dose with its unit, route and AUC method, no other route stated; compare: the
#                       lin-up/log-down AUC(0-tlast), the difference and the percentage (the linear AUC optional, but right
#                       if stated); not available: says it is not calculated and states no value labelled with the parameter
RUBRIC_VERSION = "2026-10-21"
DUMP_LIMIT = 3
VERDICT_THRESHOLD, VERDICT_BAND = 20.0, (18.0, 22.0)
NEGATION_RE = re.compile(r"\bnot\b|\bisn'?t\b|\bwasn'?t\b|n'(?:est|était|a|ont|avait)\s+(?:pas|plus)\b|\bne\b[^.;:\n|]{0,40}?\b(?:pas|plus)\b|"
                         r"\bwrong\b|\bfau(?:x|sses?)\b|\bincorrecte?s?\b|\berron[ée]e?s?\b|\bobsol[eè]te?s?\b|\bprevious\b|"
                         r"\bancien(?:ne)?s?\b|\bpr[ée]c[ée]dente?s?\b", re.I)
_BOUNDARY_RE = re.compile(r"[;!?|\n]|[.,:](?=\s|$)")
_AFTER_STOP_RE = re.compile(r"[;!?|\n(]|[.,:](?=\s|$)")
RUBRIC_ALIASES = {**_ALIASES,
                  "tlag": (r"\bt[ _]?lag\b|temps de latence|lag[ -]?time", False),
                  "c0": (r"\bc[ _]?[0₀](?!\w)|concentration initiale", False),
                  "tlast": (r"(?<![-\d])(?<!- )\bt[ _]?last\b(?!\s?\))", False), "clast": (r"\bc[ _]?last\b", False),
                  "aumclast": (r"\baumc", False), "vss.obs": (r"\bvss\b", False)}
# the % of the AUC extrapolated: stricter than the oracle's "extrapol" (which also reads "C0 (extrapolée)"); a number written
# right before the label counts ("2,57 % de l'AUC est extrapolé")
RUBRIC_ALIASES["aucpext.obs"] = (r"aucpext|auc[ _]?%[ _]?ext|(?:pourcentage|part|fraction|%)[^.;:\n|]{0,25}extrapol|"
                                 r"\bauc\s?(?:\(\s?0\s?-\s?(?:inf|∞)\w*\s?\)\s?)?extrapol|extrapolat\w*\s+(?:de\s+l'|of\s+the\s+)auc|"
                                 r"extrapol\w*[^.;:\n|\d]{0,12}(?:%|pourcent)", True)
_UNASKED_SKIP = {"dose", "compare.percent", "compare.difference"}
_RUBRIC_LUD_RE = re.compile(r"lin(?:[ée]a(?:r|ire))?[\s_-]*up[\s_/-]*log[\s_-]*down|lin_up_log_down", re.I)
# the quality thresholds an answer quotes next to the extrapolation or the regression (GATE_V2.md, named conventions)
THRESHOLDS = (20.0, 0.9, 2.0)
_ABSTAIN_RE = re.compile(r"je ne (?:peux|sais) pas|n'ai pas pu|ne suis pas en mesure|impossible|cannot|can't|unable|could not", re.I)
_VERDICT_NEG_RE = re.compile(r"\b(?:in|un)acceptables?\b|(?:\bnon|\bpas|\bnot|n'est\s+pas|n'est\s+plus|isn'?t)\s+(?:\w+\s+)?acceptables?\b|"
                             r"\bd[ée]passe\s+(?:le|la|ce|the)\s+(?:seuil|limite|threshold)|au[- ]dessus\s+du\s+seuil|sup[ée]rieure?\s+au\s+seuil|"
                             r"\babove\s+the\s+threshold|\bexceeds\b", re.I)
_VERDICT_POS_RE = re.compile(r"\bacceptables?\b|ne\s+d[ée]passe\s+pas|en[- ]dessous\s+du\s+seuil|sous\s+le\s+seuil|inf[ée]rieure?\s+au\s+seuil|"
                             r"\bbelow\s+the\s+threshold|within\s+the\s+(?:limit|threshold)", re.I)
_ROUTE_WORDS = {"oral": r"\borale?s?\b|\boral\b|extravasculaire|per os", "iv_bolus": r"\bbolus\b",
                "iv_infusion": r"perfusion|infusion"}
_UNIT_EQUIV = {"ug/ml": "mg/l", "ng/ul": "mg/l", "ug/l": "ng/ml", "pg/ul": "ng/ml", "mg/ml": "g/l"}

def _canon_unit(u):
    """A unit in a form where exact rewritings are equal: normalised like the oracle's (`_norm_unit`), µ/μ/mcg as u, the
    concentrations of factor 1 merged (µg/mL = mg/L, µg/L = ng/mL), the factors of a product sorted (ng·h/mL = h·ng/mL)."""
    if not u: return None
    s = _norm_unit(u).replace("µ", "u").replace("μ", "u").replace("mcg", "ug").replace("microgrammes", "ug").replace("microgramme", "ug")
    s = s.replace("milligrammes", "mg").replace("milligramme", "mg").replace("litres", "l").replace("litre", "l")
    for a, b in _UNIT_EQUIV.items(): s = re.sub(rf"(?<![a-z]){re.escape(a)}(?![a-z])", b, s)
    return re.sub(r"[a-z0-9^]+(?:\*[a-z0-9^]+)+", lambda m: "*".join(sorted(m.group(0).split("*"))), s)

def _signed(answer, n, value):
    """The written value with its sign: a minus (or a Unicode minus/dash) right before the number, not glued to a letter or a
    digit (the dash of "0-tlast" or of "h-1" is not a sign)."""
    i = n.start - 1
    if i >= 0 and answer[i] in "-−–‒" and (i == 0 or not answer[i - 1].isalnum()): return -value
    return value

def _matches_signed(truth, claim, min_sig=2, magnitude_too=False):
    """`claim` (one written number: signed readings) equals `truth` rounded to the digits written, sign included. With
    `magnitude_too` the absolute value of the truth also passes (the compare turn asks for the difference "en valeur absolue")."""
    t = D(repr(truth)) if isinstance(truth, float) else D(truth)
    targets = [t, abs(t)] if magnitude_too else [t]
    for v, s, _ in claim["readings"]:
        if s < min_sig: continue
        sv = -abs(v) if claim["negative"] else abs(v)
        for x in targets:
            if (x < 0) != (sv < 0) and sv != 0: continue
            if _eq_rounded(x, sv, s): return True
    return False

def _clause_start(text, pos):
    last = 0
    for m in _BOUNDARY_RE.finditer(text, 0, pos): last = m.end()
    return last

def _after_window(text, pos):
    m = _AFTER_STOP_RE.search(text, pos)
    return text[pos:m.start() if m else len(text)]

def _negated(text, label_start, n):
    """A number is disowned when a negation word lies in its clause before it (from the clause start before the label) or in
    the words right after it (up to the next comma, parenthesis or end of clause)."""
    lo = min(_clause_start(text, label_start), _clause_start(text, n.start)) if label_start is not None else _clause_start(text, n.start)
    return bool(NEGATION_RE.search(text[lo:n.start]) or NEGATION_RE.search(_after_window(text, n.end)))

def _rubric_marks(text, items, kind):
    """Labels of the turn (asked items as the oracle reads them) and of every other parameter of `RUBRIC_ALIASES`, so that the
    span of a label ends at the next label of any parameter. The keys read by method in the compare turn are left out (their
    label is the method)."""
    by_method_keys = {it["key"] for it in items if it.get("by_method")}
    asked = {it["key"] for it in items}
    marks = []
    for key, (rx, _) in sorted(RUBRIC_ALIASES.items(), key=lambda kv: kv[0] not in asked):   # an asked key wins a shared label
        if key in by_method_keys: continue
        if key.startswith("compare.") and kind != "compare": continue
        marks += [(m.start(), m.end(), ("key", key)) for m in re.finditer(rx, text, re.I)]
    if any(it.get("by_method") for it in items):
        lud = [(m.start(), m.end()) for m in _RUBRIC_LUD_RE.finditer(text)]
        marks += [(a, b, ("method", "lin_up_log_down")) for a, b in lud]
        marks += [(m.start(), m.end(), ("method", "linear")) for m in _LIN_RE.finditer(_mask(text, lud))]
    marks.sort(key=lambda m: (m[0], -(m[1] - m[0])))                  # stable: at equal spans the asked key stays first
    kept = []
    for m in marks:
        if not kept or m[0] >= kept[-1][1]: kept.append(m)
    return kept

def _absorb(marks, nums, text, items):
    """Drops the label of another parameter written inside the label of an asked one, before its number ("Nombre de points pour
    la régression de λz : 3": the λz is part of the label of the number of points)."""
    asked = {("method", it["method"]) if it.get("by_method") else ("key", it["key"]) for it in items}
    drop = set()
    for a, b, t in marks:
        if t not in asked: continue
        nxt = next((n.start for n in nums if n.start >= b), None)
        if nxt is None or re.search(r"[;!?\n]|\.(?=\s)", text[b:nxt]): continue              # a table cell is no boundary here
        drop |= {(x, y, u) for x, y, u in marks if b <= x < nxt and u not in asked}
    return [m for m in marks if m not in drop]

def _legit_values(meta, csv_numbers=()):
    """Every number an answer may legitimately write next to a label of another quantity: the computed parameters of both
    analyses, the analysis_compare row for both references (signed), the dose, the LLOQ, the data."""
    from bench import scripts
    vals = list(_gold_values(meta).values()) + [meta["dose"]["amount"]] + list(csv_numbers) + list(THRESHOLDS)
    if meta.get("blq"): vals.append(meta["blq"]["lloq"])
    for a in meta["ground_truth"]["nca"].values():                   # the selected λz regression (intercept, R², times)
        vals += [v for v in (a.get("lambda_z_regression") or {}).values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    try:
        for r in METHODS: vals += [abs(x) for x in scripts.compare_truth(meta, r).values()]
    except KeyError: pass
    return [v for v in vals if v]

def rubric_vocabulary(meta):
    """The oracle's unit vocabulary plus the units of the same dimensions in the other time and concentration units, so that
    a unit the exercise never uses is read as a unit (and fails rule 2), not as text."""
    ts, cs, ds = ("h", "min"), ("ng/mL", "mg/L", "µg/mL", "µg/L", "ng/L"), ("mg", "µg", "ug", "ng", "dose unit")
    extra = [f"{t}*{c}" for t in ts for c in cs] + [f"{t}^2*{c}" for t in ts for c in cs] + [f"1/{t}" for t in ts] + \
            [f"{d}/({t}*{c})" for d in ds for t in ts for c in cs] + [f"{d}/({c})" for d in ds for c in cs] + \
            ["L/h", "L/min", "mL/h", "mL/min", "L", "mL"]
    return sorted(set(unit_vocabulary(meta)) | {_norm_unit(u) for u in extra}, key=lambda u: (-len(u), u))

def _numbers(answer):
    allnums = [n for n in gate.extract_numbers(answer) if not _is_unit_exponent(answer, n)]
    nums = [n for n in allnums if n.exempt not in _SKIP_EXEMPT]
    nums = [n for n in nums if not _REF_BEFORE_RE.search(answer[max(0, n.start - 12):n.start])]
    return allnums, nums

_UNIT_LEAD_RE = re.compile(r"[\s*_`]*(?:\|[\s*_`]*)?")

def _rubric_unit(answer, allnums, n, vocab):
    """The unit written right after a number: the first token after it (markdown marks skipped), or the first token of the next
    table cell; None when a word or another number comes first ("t½ = 3,9 h" -> h; "t1/2 = 3.9, AUC % ..." -> None)."""
    nxt = next((x.start for x in allnums if x.start >= n.end and x.exempt != "unit_fragment"), len(answer))
    seg = answer[n.end:min(nxt, _eol(answer, n.end))]
    lead = _UNIT_LEAD_RE.match(seg).end()
    norm = _norm_unit(seg[lead:])
    u = _first_unit(norm, vocab)
    return u if u and norm.startswith(u) else None

def _label_claims(answer, text, item, marks, vocab, allnums, nums, lookback=False):
    """The numbers attached to the labels of `item`: [{"raw", "readings", "negative", "unit", "negated", "sig", "start"}]."""
    tag = ("method", item["method"]) if item.get("by_method") else ("key", item["key"])
    starts = {a for a, _, t in marks if t == tag}
    out, seen = [], set()
    for spans, label_start in zip(_spans(text, item, marks), sorted(starts)):
        if lookback:                                                     # a number before the label, in the same clause
            lo = _clause_start(text, label_start)
            before = [n for n in nums if lo <= n.start and n.end <= label_start]
            if before: spans = spans + [(before[-1].start, before[-1].end)]
        for lo, hi in spans:
            for n in nums:
                if not (lo <= n.start < hi) or n.start in seen: continue
                seen.add(n.start)
                out.append({"raw": n.raw, "readings": n.readings, "negative": _signed(answer, n, 1) < 0, "start": n.start,
                            "unit": _rubric_unit(answer, allnums, n, vocab), "negated": _negated(text, label_start, n),
                            "sig": max(s for _, s, _ in n.readings)})
    return out

def _item_verdict(claims, item, required_unit=False, magnitude_too=False, legit=()):
    """(stated, contradiction, detail) of one expected item from its claims. A claim that is another number of the exercise
    (`legit`: every computed parameter of both analyses, the dose, the data; "3170,4 (observation) ; 3172,2 (prédiction)") is
    another quantity, not a contradicting value."""
    want = {_canon_unit(u) for u in _expected_unit_forms(item)}
    unit_ok = lambda c: (not c["unit"] and not required_unit) or (c["unit"] and (not want or _canon_unit(c["unit"]) in want))
    live = [c for c in claims if not c["negated"]]
    hit = [c for c in live if _matches_signed(item["value"], c, magnitude_too=magnitude_too)]
    stated = any(unit_ok(c) for c in hit)
    is_legit = lambda c: any(_eq_rounded(D(repr(float(v))), abs(x), s) for x, s, _ in c["readings"][:1] for v in legit)
    other = [c for c in live if c not in hit and c["sig"] >= 3 and (not c["unit"] or not want or _canon_unit(c["unit"]) in want)
             and not is_legit(c)]
    if stated and other: return False, True, f"contradicted by {other[0]['raw']}"
    if stated: return True, False, None
    if hit: return False, False, f"unit {hit[0]['unit'] or 'missing'}"
    if any(c["negated"] for c in claims): return False, False, "negated"
    if other: return False, True, f"wrong value {other[0]['raw']}"
    return False, False, "not stated with its label"

_VERDICT_ECHO_RE = re.compile(r"(?:est[- ]ce\s+(?:que\s+)?(?:c'est\s+|l'extrapolation\s+est\s+)?|is\s+(?:it|this|that)\s+)acceptable\s*\?|"
                              r"acceptabilit[ée]|acceptability", re.I)
_VERDICT_YESNO_RE = re.compile(r"[\s*_:`»«\"'-]*(oui|yes|non|no)\b", re.I)

def verdict_of(answer):
    """'acceptable', 'not_acceptable', 'both' or None: the acceptability verdict an answer states (closed phrase lists). The echo
    of the question ("Est-ce acceptable ?", "Acceptabilité :") is not a verdict; a "oui" or "non" right after it is."""
    echoes = list(_VERDICT_ECHO_RE.finditer(answer))
    yesno = [_VERDICT_YESNO_RE.match(answer, m.end()) for m in echoes]
    answer = _mask(answer, [(m.start(), m.end()) for m in echoes])
    neg = list(_VERDICT_NEG_RE.finditer(answer)) + [y for y in yesno if y and y.group(1).lower() in ("non", "no")]
    pos_yes = [y for y in yesno if y and y.group(1).lower() in ("oui", "yes")]
    masked = _mask(answer, [(m.start(), m.end()) for m in neg])
    pos = [m for m in _VERDICT_POS_RE.finditer(masked) if not _VERDICT_NEG_RE.search(answer[max(0, m.start() - 12):m.end()])] + pos_yes
    if neg and pos: return "both"
    return "not_acceptable" if neg else ("acceptable" if pos else None)

def _gold_values(meta):
    """{qualified key: value} of every computed parameter of both analyses ('lud:' prefix for the lin-up/log-down one)."""
    out = {}
    for m, a in meta["ground_truth"]["nca"].items():
        for k, p in a["parameters"].items():
            if p["value"]: out[k if m == "linear" else f"lud:{k}"] = p["value"]
    return out

def _unasked(answer, text, marks, asked_keys, asked_values, meta, allnums, nums, vocab):
    """Quantities the answer states that the turn did not ask for: a label of another parameter with a number attached, or a
    number (3 significant digits or more) equal to another computed parameter of the exercise. Values equal to an asked value
    or to a number of the user's message are not counted."""
    skip = set(asked_keys) | _UNASKED_SKIP
    legit = {_round3(v) for v in asked_values}
    found = {}                                                        # value (3 digits) or key -> key: one value counts once
    gold = _gold_values(meta)
    for k, v in gold.items():                                         # by value, under any name
        if k.split(":", 1)[-1] in skip or _round3(v) in legit: continue
        if any(s >= 3 and _eq_rounded(D(repr(float(v))), abs(x), s) for n in nums for x, s, _ in n.readings[:1]):
            found.setdefault(_round3(v), k)
    seen_keys = set(found.values())
    for a, b, (kind_, key) in marks:                                  # by label, when the value is not one of the above
        if kind_ != "key" or key in skip or key in seen_keys: continue
        claims = [c for c in _label_claims(answer, text, {"key": key, "label": key}, marks, vocab, allnums, nums) if not c["negated"]]
        if not claims: continue
        vals = [c["readings"][0][:2] for c in claims]
        if any(any(gold_v and _eq_rounded(D(repr(float(gold_v))), abs(v), sg) for gold_v in gold.values()) for v, sg in vals): continue
        if all(_round3(float(v)) in legit for v, _ in vals if v): continue
        found.setdefault(key, key); seen_keys.add(key)
    return sorted(found.values())

def _round3(x):
    return gate.round_sig(D(repr(float(x))), 3) if x else D(0)

def rubric_items(turn, meta, usage=None):
    """The items the rubric checks for a script turn: the `must` items of the static rule, with the compare turn rewritten as
    FROZEN_SET.md §6.2 rule 7 says (lin-up/log-down AUC, difference, percentage required; linear AUC optional). The difference
    and the percentage are the engine's (scripts.compare_truth), relative to the linear analysis, or to the lin-up/log-down one
    when the model's analysis_compare call took it as reference (`usage`, score.compare_usage)."""
    e = turn["expect"]; items = [dict(it) for it in e.get("must", []) if not it.get("key", "").startswith("compare.")]
    if turn["kind"] != "compare": return items, []
    from bench import scripts                                        # (scripts imports this module)
    lud = [it for it in items if it.get("method") == "lin_up_log_down"]
    lin = [dict(it, optional=True) for it in items if it.get("method") == "linear"]
    ref = (usage or {}).get("reference") if (usage or {}).get("usable") else "linear"
    refs = ["linear"] + (["lin_up_log_down"] if ref == "lin_up_log_down" else [])
    auc_unit = scripts.truth_unit(meta, "auclast")
    diffs = [{"label": f"AUC difference ({r})", "key": "compare.difference", "value": scripts.compare_truth(meta, r)["difference"],
              "unit": auc_unit, "magnitude_too": True} for r in refs]
    pcts = [{"label": f"AUC difference in % ({r})", "key": "compare.percent", "value": scripts.compare_truth(meta, r)["percent"],
             "unit": "%", "magnitude_too": True} for r in refs]
    return lud + lin, [diffs, pcts]

_PCT_CLAIM_RE = re.compile(r"\s*%")
_COMPARATIVE_RE = re.compile(r"de moins|de plus|inf[ée]rieure?|sup[ée]rieure?|plus (?:faible|basse|petite|[ée]lev[ée]e|grande|haute)|"
                             r"\blower\b|\bhigher\b|\bless\b|\bmore\b|\bsmaller\b|\blarger\b|diff[èe]re|[ée]cart|diff[ée]rence|difference", re.I)

def _compare_claims(answer, text, item, marks, vocab, allnums, nums):
    """Claims of the difference or the percentage: those after their label (`_ALIASES`), plus, for the percentage, any number
    written with a % sign, and for the difference any number with the AUC unit in a clause that says it is a difference."""
    out = _label_claims(answer, text, item, marks, vocab, allnums, nums)
    seen = {c["start"] for c in out}
    for n in nums:
        if n.start in seen: continue
        u = _rubric_unit(answer, allnums, n, vocab)
        if item["key"] == "compare.percent" and u == "%": pass
        elif item["key"] == "compare.difference" and u and _canon_unit(u) == _canon_unit(item["unit"]) and \
                _COMPARATIVE_RE.search(text[_clause_start(text, n.start):n.start] + _after_window(text, n.end)): pass
        else: continue
        out.append({"raw": n.raw, "readings": n.readings, "negative": _signed(answer, n, 1) < 0, "start": n.start, "unit": u,
                    "negated": _negated(text, None, n), "sig": max(s for _, s, _ in n.readings)})
    return out

def rubric_turn(answer, turn, meta, tool_results=(), usage=None, badge_mark="\n\n⚠ ", csv_numbers=()):
    """Verdict of FROZEN_SET.md §6.2 on one answer (the text the user sees); `csv_numbers`: the numbers of the exercise's data
    (scripts.csv_numbers), which never count as a contradicting value. Returns {"correct", "reasons", "items",
    "unasked", "forbidden", "verdict", "rubric"}; `reasons` lists every rule the answer breaks (empty when correct)."""
    answer = (answer or "").split(badge_mark)[0]
    text = answer.translate(_DASHES)
    kind, e = turn["kind"], turn["expect"]
    items, alternatives = rubric_items(turn, meta, usage)
    marks = _rubric_marks(text, items + [a[0] for a in alternatives], kind)
    vocab = rubric_vocabulary(meta)
    allnums, nums = _numbers(answer)
    marks = _absorb(marks, nums, text, items + [a[0] for a in alternatives])
    legit = _legit_values(meta, csv_numbers)
    reasons, verdicts = [], []
    for it in items:
        claims = _label_claims(answer, text, it, marks, vocab, allnums, nums, lookback=RUBRIC_ALIASES.get(it["key"], (0, False))[1])
        stated, contra, detail = _item_verdict(claims, it, required_unit=(kind == "recall" and it["key"] == "dose"), legit=legit)
        if it.get("optional") and not stated and not contra and detail in ("not stated with its label", "negated"): stated = True
        verdicts.append({"label": it["label"], "ok": stated, "detail": detail, "claimed": [c["raw"] for c in claims[:4]]})
        if not stated: reasons.append(f"{it['label']}: {'contradiction' if contra else detail}")
    for alts in alternatives:                                        # compare: the difference, the percentage (one reference)
        res = []
        for it in alts:
            claims = _compare_claims(answer, text, it, marks, vocab, allnums, nums)
            res.append((it, claims, _item_verdict(claims, it, magnitude_too=True, legit=legit)))
        ok = [r for r in res if r[2][0]]                                 # one reference is enough; the other's value is no contradiction
        it, claims, (stated, contra, detail) = ok[0] if ok else res[0]
        verdicts.append({"label": it["label"], "ok": bool(ok), "detail": None if ok else detail, "claimed": [c["raw"] for c in claims[:4]]})
        if not ok: reasons.append(f"{it['label']}: {'contradiction' if contra else detail}")
    # 5. forbidden values (any count) and the dump of unasked quantities (outside turn 1)
    forb = [x for x in score_turn(answer, {"must_not": e.get("must_not", [])}, 0, tool_results)["forbidden"]] if e.get("must_not") else []
    if usage and usage.get("usable") and kind == "compare":          # the engine's own difference / percentage / ratio are allowed
        allowed = {"AUC difference", "AUC ratio", "AUC difference in % of the linear AUC", "AUC difference in % of the log-down AUC"}
        forb = [f for f in forb if f.strip() not in allowed]
    elif kind == "compare":                                              # the difference and the percentage are now asked for
        forb = [f for f in forb if f.strip() not in ("AUC difference", "AUC difference in % of the linear AUC")]
    if forb: reasons.append("forbidden value: " + ", ".join(forb))
    asked_keys = {it["key"] for it in items} | {a[0]["key"] for a in alternatives}
    if kind == "not_available": asked_keys.add(e.get("not_calculated_parameter"))
    asked_values = [it["value"] for it in items] + [x["value"] for a in alternatives for x in a] + \
                   ([v for k, v in _gold_values(meta).items() if k.split(":")[-1] == "auclast"] if kind == "compare" else []) + \
                   [meta["dose"]["amount"]]
    unasked = _unasked(answer, text, marks, asked_keys, asked_values, meta, allnums, nums, vocab) if kind != "import_nca" else []
    if len(unasked) > DUMP_LIMIT: reasons.append(f"dump: {len(unasked)} unasked quantities ({', '.join(unasked[:8])})")
    # 6. the acceptability verdict
    verdict = None
    if kind == "half_life":
        from bench import scripts
        pext = scripts.truth_value(meta, "aucpext.obs")
        verdict = verdict_of(answer)
        gold = "acceptable" if pext <= VERDICT_THRESHOLD else "not_acceptable"
        band = VERDICT_BAND[0] <= pext <= VERDICT_BAND[1]
        if verdict is None: reasons.append("verdict: none stated")
        elif verdict == "both": reasons.append("verdict: both stated")
        elif verdict != gold and not band: reasons.append(f"verdict: {verdict}, gold {gold} ({pext:.3g} %)")
    # 7. turn specifics
    if kind == "recall":
        mk_kind = "iv_infusion" if isinstance(meta["route"], dict) else ("iv_bolus" if meta["route"] == "iv_bolus" else "oral")
        for w in e.get("words", []):
            if w["label"] == "dose unit": continue                       # the dose item carries its unit (rule 2)
            if not any(not _negated(text, None, _Span(m)) for m in re.finditer(w["pattern"], answer, re.I | re.S)):
                reasons.append(f"{w['label']}: not stated")
        for other, rx in _ROUTE_WORDS.items():
            if other == mk_kind or (mk_kind == "iv_infusion" and other == "iv_bolus"): continue
            if any(not _negated(text, None, _Span(m)) for m in re.finditer(rx, answer, re.I)):
                reasons.append(f"route: {other} stated as well")
    if kind == "not_available":
        if not re.search(e["words"][0]["pattern"], answer, re.I | re.S): reasons.append("not available: not said")
        what = e.get("not_calculated_parameter")
        rx = RUBRIC_ALIASES.get(what, (None,))[0]
        if rx:
            for m in re.finditer(rx, text, re.I):
                hi = _AFTER_STOP_RE.search(text, m.end()); hi = hi.start() if hi else len(text)
                if [n for n in nums if m.end() <= n.start < hi]:
                    reasons.append(f"not available: a value is labelled {what}"); break
    return {"rubric": RUBRIC_VERSION, "correct": not reasons, "reasons": reasons, "items": verdicts, "unasked": unasked,
            "forbidden": forb, "verdict": verdict}

class _Span:
    """A regex match seen as a number span (start, end) for `_negated`."""
    def __init__(self, m): self.start, self.end = m.start(), m.end()

def abstained(answer, rubric, kind):
    """ABSTAINED (§6.1): values were expected, the answer states none of them and says it cannot or will not answer."""
    if kind == "not_available" or not rubric["items"]: return False
    return not any(i["ok"] for i in rubric["items"]) and bool(_ABSTAIN_RE.search(answer or "") or re.search(
        r"pas (?:de |d')?(?:valeur|r[ée]sultat)|not (?:calculated|available)", answer or "", re.I))

OUTCOMES = ("ERROR", "TIMEOUT", "LOOP", "ABSTAINED", "WRONG", "CORRECT")
WALL_CAP_S = 300
# the text optchat shows when the tool-round cap stops a turn, and apothicaire.FAILED_TURN (a tool-call text replaced, T-062)
LOOP_TEXTS = ("(stopped: too many tool rounds)", "Je n'ai pas pu terminer cette demande : l'appel d'outil",
              "I could not finish this request: the tool call")

def outcome_of(rec, rubric=None, wall_cap_s=WALL_CAP_S, max_tool_rounds=8):
    """The outcome of a turn record (FROZEN_SET.md §6.1), in order: ERROR (an exception or no answer), TIMEOUT (over the
    wall-clock cap), LOOP (ended by the tool-round cap or the repeated-call guard), ABSTAINED, WRONG, CORRECT."""
    ans = rec.get("answer")
    if "error" in rec or ans is None or not str(ans).strip(): return "ERROR"
    if (rec.get("wall_s") or 0) > wall_cap_s: return "TIMEOUT"
    if rec.get("tools_withdrawn") or (rec.get("rounds") or 0) >= rec.get("max_tool_rounds", max_tool_rounds) or \
            any(str(ans).startswith(t) for t in LOOP_TEXTS): return "LOOP"
    if rubric is None: return "WRONG"
    if abstained(ans, rubric, rec.get("kind")): return "ABSTAINED"
    return "CORRECT" if rubric["correct"] else "WRONG"
