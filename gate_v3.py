"""
Gate v3 for Apothicaire: gate v2 plus a grammar for the regeneration (pure Python, no model, no dependency).

Gate v2 (gate_v2.py, GATE_V2.md) reads a finished answer and, when it finds something, asks the model to write it again. v3
changes only that second call: `build(calls, user_texts, schemas)` returns a llama.cpp GBNF grammar for the turn, and the
regeneration (already `tools=None`) is sampled under it. Gate v2 still reads every answer; v1 and v2 are unchanged.

What the grammar lets the model write. A "free digit" is a digit that is none of these three:

  (a) a digit inside a reference `{{call_N.path}}` that resolves, exactly as gate v2 resolves it, against the closed tables
      (PARAMETERS, the dose, the selected λz regression, the quality thresholds, CONVENTIONS, the analysis_compare fields)
      and this chat's tool results. The references are enumerated, not described: `enumerate_refs` lists the paths and keeps
      those `gate_v2.resolve` accepts, so an unresolvable, untyped or malformed reference cannot be written.
  (b) a digit inside a closed label: the names the renderer prints and the notations gate v2 already reads as notation, not
      as a number (C0, t½, t1/2, R², AUC(0-tlast), 1/h). LABELS below.
  (c) a number the user typed, copied exactly: `12,5` is not `12.5`.

One extension, switchable (`idents=False`), kept apart because it goes beyond the letter of (a) to (c): an analysis id or a
subject label that is in this chat's tool results, after the words the model uses to name it ("analyse 3", "sujet 1"). Gate v2
exempts those small integers; without them the grammar would refuse about a quarter of the answers gate v2 passes.

Everything else is prose: no digit, no brace (PROSE below). The prose is a deterministic automaton of "modes", one GBNF rule
each, that mirrors what gate v2 flags around a reference and a number (gate_v2._adjacent, gate._read_unit):

  * after a reference: nothing that reads as a unit (an atom of gate._ATOM_RE, a unit word of gate_v2._UNIT_WORD), a digit, an
    operator, a sign or an "x" followed by a number, a glued second reference, an exponent, or ")" op "(". The unit rule is the
    union of the two regular expressions, with their look-ahead. A word that begins with a complete unit is cut at its last
    letter (see UNIT_ALIVE), so that the sampler, which only checks the characters of the token it has drawn, rejects the token
    " mg" or " %" itself instead of entering a state it can only leave with a junk letter;
  * before a reference: nothing that reads as a digit, an operator or a sign (a list bullet excepted), and no emphasis mark
    (bold or italic around a value is refused; v3 is stricter than v2 there);
  * after a typed number: no glue that would read as a longer number (".5", "e3", " x 10").

What the grammar does not do (gate v2 keeps those findings, the benchmark counts them): spelled-out numbers ("quinze"), a unit
written elsewhere in the clause that contradicts the rendered one, sign words ("négatif {{ref}}"), a unit in a table cell. It
does not know what the model means, only which characters may follow which.

One source of truth. The GBNF text is printed from the same rules that `Machine`, a re-implementation of llama.cpp b11700's
stack engine (src/llama-grammar.cpp), runs; `Grammar.accepts` is that recognizer; tests/gbnf_reader.py reads the printed text
independently, and bench/grammar_llamacpp.py puts it to llama.cpp b11700 itself (llama.dll through ctypes, vocabulary only, CPU).
See tests/test_gate_v3.py.

  build(calls, user_texts, schemas=None, *, idents=True) -> Grammar
  Grammar.gbnf          the text sent as `grammar`
  Grammar.accepts(text) True when the grammar derives the whole text
  Grammar.scan(text)    [(start, end, modes)] the spans the grammar refuses (skipping to the next acceptable character)
  Grammar.stats         sizes and vocabulary counts
  conformance(grammar, text, finish_reason)
                        what the agent records for a regeneration: did the text that came back obey the grammar it was sent
"""
import bisect, itertools, re, time

import gate
import gate_v2
from gate_v2 import PARAMETERS, CONVENTIONS, Unresolved

# ================================================================ character sets
class CS:
    """Immutable set of code points: sorted, disjoint, non-adjacent inclusive ranges."""
    __slots__ = ("r", "_starts")

    def __init__(self, ranges=()):
        out = []
        for a, b in sorted(ranges):
            if a > b: raise ValueError(f"empty range {a:#x}-{b:#x}")
            if out and a <= out[-1][1] + 1:
                if b > out[-1][1]: out[-1] = (out[-1][0], b)
            else: out.append((a, b))
        self.r = tuple(out)
        self._starts = tuple(a for a, _ in out)

    @classmethod
    def of(cls, text): return cls((ord(c), ord(c)) for c in text)

    def __contains__(self, c):
        cp = ord(c) if isinstance(c, str) else c
        i = bisect.bisect_right(self._starts, cp) - 1
        return i >= 0 and cp <= self.r[i][1]

    def __or__(self, o): return CS(self.r + o.r)

    def __and__(self, o):
        out, i, j = [], 0, 0
        while i < len(self.r) and j < len(o.r):
            lo, hi = max(self.r[i][0], o.r[j][0]), min(self.r[i][1], o.r[j][1])
            if lo <= hi: out.append((lo, hi))
            if self.r[i][1] < o.r[j][1]: i += 1
            else: j += 1
        return CS(out)

    def __sub__(self, o):
        out = []
        for a, b in self.r:
            cur = a
            for c, d in o.r:
                if d < cur: continue
                if c > b: break
                if c > cur: out.append((cur, c - 1))
                cur = max(cur, d + 1)
                if cur > b: break
            if cur <= b: out.append((cur, b))
        return CS(out)

    def __bool__(self): return bool(self.r)
    def __len__(self): return sum(b - a + 1 for a, b in self.r)
    def __eq__(self, o): return isinstance(o, CS) and self.r == o.r
    def __hash__(self): return hash(self.r)

    def __iter__(self):
        for a, b in self.r:
            for cp in range(a, b + 1): yield chr(cp)

    def __repr__(self): return "CS(" + " ".join(f"{a:04X}" if a == b else f"{a:04X}-{b:04X}" for a, b in self.r) + ")"


def _ranges(spec):
    out = []
    for part in spec.split():
        a, _, b = part.partition("-")
        out.append((int(a, 16), int(b or a, 16)))
    return out

# ================================================================ the prose alphabet
# What the model may type outside a reference, a label or a number: the code points of the blocks that carry text (Latin, Greek,
# Cyrillic, punctuation, arrows, mathematical operators, symbols, emoji) minus every digit and numeric character (categories
# Nd, No, Nl: "²", "½", "①", Arabic-Indic digits), minus braces, controls and separators other than the blanks gate.SPACES knows.
# Written as ranges (Unicode 15) so that the grammar does not depend on the interpreter's tables;
# tests/test_gate_v3.py checks the ranges against unicodedata.
_PROSE_SPEC = (
    "0009-000A 0020-002F 003A-007A 007C-007C 007E-007E 00A0-00AC 00AE-00B1 00B4-00B8 00BA-00BB 00BF-0377 037A-037F 0384-038A "
    "038C-038C 038E-03A1 03A3-04FF 1E00-1F15 1F18-1F1D 1F20-1F45 1F48-1F4D 1F50-1F57 1F59-1F59 1F5B-1F5B 1F5D-1F5D 1F5F-1F7D "
    "1F80-1FB4 1FB6-1FC4 1FC6-1FD3 1FD6-1FDB 1FDD-1FEF 1FF2-1FF4 1FF6-1FFE 2007-2007 2009-2009 200C-200D 2010-2027 202F-205E "
    "2071-2071 207A-207F 208A-208E 2090-209C 20A0-20C0 2100-214F 2183-2184 218A-218B 2190-23FF 2500-2775 2794-27EF 2900-2B73 "
    "2B76-2B95 2B97-2BFF FE00-FE0F 1F300-1F64F 1F680-1F6D7 1F6DC-1F6EC 1F6F0-1F6FC 1F900-1F9FF 1FA70-1FA7C 1FA80-1FA88 "
    "1FA90-1FABD 1FABF-1FAC5 1FACE-1FADB 1FAE0-1FAE8 1FAF0-1FAF8")
# Taken out on top of that: the carriage return (gate_v2 reads "\n" as the line end); the characters python's re.IGNORECASE
# folds onto an ASCII letter or µ (İ ı ſ K Μ), which would make the unit words case-fold differently in the grammar and in gate
# v2; the superscript and subscript signs and parentheses (they read as the sign or the exponent of a number written with
# Unicode numerals).
PROSE = CS(_ranges(_PROSE_SPEC)) - CS.of("\rİıſΜK") - CS(_ranges("207A-207E 208A-208E"))

def _letters(cs): return CS((ord(c), ord(c)) for c in cs if c.isalpha())

# The kinds partition PROSE; a mode maps each kind to the next mode (or refuses it).
BLK = CS.of(" \t    ")      # gate.SPACES and the tab
NL = CS.of("\n")
X = CS.of("xX")                                   # "2 x {{ref}}": a multiplier after a number, a reference or a ")"
E = CS.of("eE")                                   # "{{ref}}e3": an exponent
LET = _letters(PROSE) - X - E
STAR = CS.of("*")                                 # emphasis, or a multiplication
EMPH = CS.of("~`")
UND = CS.of("_")                                  # emphasis too, but a word character for gate_v2's label regexes (AUC_x)
OPS = CS.of("×/^÷")                               # gate_v2._OPS without "*"
SGN = CS.of("-+")                                 # a list bullet at the start of a line, an operator elsewhere
MINUS = CS.of("−")                                # never a bullet (gate_v2._BULLET_RE)
LPAR = CS.of("(")
RPAR = CS.of(")")
DOT = CS.of(".,")
MID = CS.of("·")                                  # gate._NUM_RE joins "2 · 10^3"
OTH = PROSE - (BLK | NL | X | E | LET | STAR | EMPH | UND | OPS | SGN | MINUS | LPAR | RPAR | DOT | MID)
KINDS = {"blk": BLK, "nl": NL, "x": X, "e": E, "let": LET, "star": STAR, "emph": EMPH, "und": UND, "ops": OPS, "sgn": SGN, "minus": MINUS, "lpar": LPAR,
         "rpar": RPAR, "dot": DOT, "mid": MID, "oth": OTH}
ASCII_LETTERS = CS(((65, 90), (97, 122)))
MICRO = CS.of("µμ")
APOS = CS.of("'’")
LOOK = ASCII_LETTERS | MICRO | APOS               # gate._ATOM_RE and gate_v2._UNIT_AFTER_WORD_RE: what must NOT follow a unit
_XL = (LET | X | E) - ASCII_LETTERS - MICRO       # the letters outside ASCII (µ and μ are counted with the units' letters)

# ================================================================ units: what reads as a unit right after a reference
# gate_v2._adjacent refuses a unit after a reference in two ways. gate._read_unit: at most one blank of gate.SPACES, then an atom
# of gate._ATOM_RE (case sensitive). gate_v2._UNIT_AFTER_WORD_RE: spaces and tabs, then a unit word (re.IGNORECASE). Both
# end with the look-ahead (?![A-Za-zµμ'’]). The union is one set of strings: words are case-insensitive items, atoms exact
# ones. tests/test_gate_v3.py rebuilds both sets from the regular expressions.
UNIT_WORDS = (
    "heure heures h minute minutes min seconde secondes s jour jours j d litre litres liter liters l millilitre millilitres "
    "milliliter milliliters ml décilitre décilitres decilitre decilitres dl gramme grammes gram grams g milligramme milligrammes "
    "milligram milligrams mg microgramme microgrammes microgram micrograms µg μg ug nanogramme nanogrammes nanogram nanograms ng "
    "mole moles mol millimole millimoles mmol micromole micromoles µmol μmol umol pourcent percent % hour hours day days second "
    "seconds fois times fold").split() + ["pour cent", "pour\tcent", "per cent", "per\tcent"]
UNIT_ATOMS = (["%", "‰", "°C"] + [p + b for p in ("", "k", "m", "M", "µ", "μ", "n", "p", "u") for b in ("mol", "Hz", "g", "L", "l", "M")]
              + ["mL", "ml", "dL", "dl", "IU", "min", "h", "s", "d", "j", "U"])
# "fold" belongs to neither expression: gate_v2._MULT_AFTER_RE takes the small integer of "analyse 3-fold" back, so it is
# refused after an identifier; the extra refusal after a reference is harmless.

def _fold(ch):
    """The characters of PROSE that python's re.IGNORECASE matches to `ch`."""
    if ch in "µμ": return MICRO
    return CS.of(ch.lower() + ch.upper()) if ch.isalpha() else CS.of(ch)

UNIT_ITEMS = tuple(dict.fromkeys([tuple(_fold(c) for c in w) for w in UNIT_WORDS] + [tuple(CS.of(c) for c in a) for a in UNIT_ATOMS]))

# A complete unit is a dead end for a token-by-token sampler: after " mg" the grammar can only go on with a letter, and the
# model, which wanted a unit, would write one. So a state that completes a unit has no continuation at all (the token that
# ends there is rejected), except these first letters, whose words are too common to cut: de du des dans demi, sur sous soit
# sont selon. A standalone " d" or " s" is then not a unit the model writes after a value (2 of 349 in the stored drafts).
UNIT_ALIVE = CS.of("dDsS")

class UnitDFA:
    """The subset automaton of UNIT_ITEMS. `trans[state]` maps a character to the next state; a state is a frozenset of
    (item, position). `complete`: some item ends here (a unit, if no letter follows). `live`: the states the grammar keeps."""

    def __init__(self, items, alive_first):
        self.items = items
        self.root = frozenset((i, 0) for i in range(len(items)))
        self.trans, order = {}, [self.root]
        seen = {self.root}
        for s in order:
            by = {}
            for i, p in s:
                if p < len(items[i]):
                    for ch in items[i][p]: by.setdefault(ch, set()).add((i, p + 1))
            mv = {ch: frozenset(v) for ch, v in by.items()}
            self.trans[s] = mv
            for t in mv.values():
                if t not in seen: seen.add(t); order.append(t)
        self.complete = {s: any(p == len(items[i]) for i, p in s) for s in order}
        self.name = {s: f"u-{k}" for k, s in enumerate(order) if k}
        alive = {t for ch, t in self.trans[self.root].items() if self.complete[t] and ch in alive_first}
        self.live = {s for s in order if s != self.root and (not self.complete[s] or s in alive)}
        self.start = CS()                                                # the characters that start a unit
        by = {}
        for ch, t in self.trans[self.root].items():
            self.start = self.start | CS.of(ch)
            if t in self.live: by.setdefault(t, []).append(ch)
        self.root_edges = {t: CS.of("".join(v)) for t, v in by.items()}  # live target -> its characters
        reach, todo = set(self.root_edges), list(self.root_edges)        # keep the states a text can reach ("dé" is not one)
        for s in todo:
            for t in self.edges(s):
                if t not in reach: reach.add(t); todo.append(t)
        self.live = reach
        # states that end with a blank ("pour "): the text goes on as after a blank, minus the letters that go on the unit
        self.after_blank = {}
        for s in self.live:
            last = {ch for u in order for ch, t in self.trans[u].items() if t == s}
            if not self.complete[s] and last <= set(" \t"): self.after_blank[s] = self.ext(s)

    def ext(self, s):
        """All the characters that go on some item from state s (live target or not)."""
        return CS.of("".join(self.trans[s]))

    def edges(self, s):
        """Live targets of a live state: target -> CS. A complete state goes on with letters only (the look-ahead)."""
        by = {}
        for ch, t in self.trans[s].items():
            if t in self.live and (not self.complete[s] or ch in LOOK): by.setdefault(t, []).append(ch)
        return {t: CS.of("".join(v)) for t, v in by.items()}

UD = UnitDFA(UNIT_ITEMS, UNIT_ALIVE)
UNIT_START = UD.start

# ================================================================ the modes
# One GBNF rule `m-<name>` per mode; the mode is what the grammar remembers about the text so far. flags: `ref` (a reference may
# start), `digit` (a typed number may), `letter` (a label or an identifier may), `acc` (the text may end here).
_TEXT = dict(x="fw", e="fw", let="fw", star="e", emph="e", und="eu", ops="o", sgn="o", lpar="lp", rpar="fcp", dot="fp", oth="fb")

def _table(blk, nl, **over):
    t = dict(_TEXT, blk=blk, nl=nl); t.update(over)
    t.setdefault("mid", t["oth"])
    t.setdefault("minus", "o" if t["sgn"] == "sgl" else t["sgn"])       # "−" is no bullet: at a line start it is an operator
    return t

_NX = dict(x="nx", e="nx", star="nx", emph="nx", und="nx", ops="nx", sgn="nx", mid="nx")

def _rtable(strict):
    t = dict(blk="r1s" if strict else "r1", nl="lsd", dot="nd" if strict else "fp", x="rs", e="re", let="fw", star=None, emph=None,
             und=None, ops=None, sgn="rs", lpar="rpar", rpar="fcp", oth="fb")
    if strict: t.update(x=None, sgn=None)
    t["mid"] = t["oth"]; t["minus"] = t["sgn"]
    return t

def _flags(ref, digit, letter, acc=True): return {"ref": ref, "digit": digit, "letter": letter, "acc": acc}

MODES = {
    # start of the text, of a line, after a digit and a newline, after a list bullet, free text
    "s":   (_table("ls", "ls", star="el", sgn="sgl"), _flags(1, 1, 1, False)),
    "ls":  (_table("ls", "ls", star="el", sgn="sgl"), _flags(1, 1, 1)),
    "lsd": (_table("lsd", "lsd", star="el", sgn="sgl", x="xd"), _flags(1, 1, 1)),
    "bul": (_table("bul", "ls", lpar=None), _flags(1, 1, 1)),
    "fb":  (_table("fb", "ls"), _flags(1, 1, 1)),                       # after a blank or a punctuation mark
    "fw":  (_table("fb", "ls"), _flags(1, 0, 0)),                       # after a letter
    "fp":  (_table("fb", "ls"), _flags(1, 0, 0)),                       # after a "." or a ","
    # emphasis, operators and signs: no reference may follow
    "e":   (_table("e", "ls"), _flags(0, 1, 1)),
    "eu":  (_table("e", "ls"), _flags(0, 1, 0)),
    "el":  (_table("bul", "ls"), _flags(0, 1, 1)),
    "o":   (_table("o", "ls", lpar=None), _flags(0, 1, 1)),
    "sgl": (_table("bul", "ls", lpar=None), _flags(0, 1, 1)),
    "xd":  (_table("xd", "xd", lpar=None), _flags(0, 1, 1)),
    "lp":  (_table("lp", "ls"), _flags(1, 1, 1)),
    "fcp": (_table("fcp", "lsd", x="xd", star="o"), _flags(1, 1, 1)),   # after a ")"
    # after a typed number or a label that ends with a digit
    "n":   (_table("nb", "lsd", dot="nd", **_NX), _flags(0, 0, 0)),
    "nb":  (_table("nb", "lsd", dot="fp", **_NX), _flags(0, 0, 0)),
    # ... that gate gate._read_unit would read as a number with a unit ("t1/2 %"): a number the user typed may have a unit, a label may not
    "nl":  (_table("nlb", "lsd", dot="nd", lpar="rpar", **dict(_NX, x=None, ops=None, sgn=None, mid=None)), _flags(0, 0, 0)),
    "nlb": (_table("nlb", "lsd", dot="fp", lpar="rpar", **dict(_NX, x=None, ops=None, sgn=None, mid=None)), _flags(0, 0, 0)),
    "nd":  (_table("fb", "ls"), _flags(0, 0, 0)),
    "nx":  (_table("nx", "nx", **_NX), _flags(0, 0, 0)),
    # right after a reference (r0 glued, r1 after blanks) or an identifier (the strict pair): what _adjacent reads after "}}"
    "r0":  (_rtable(False), _flags(0, 0, 0)),
    "r1":  (_rtable(False), _flags(1, 0, 1)),
    "r0s": (_rtable(True), _flags(0, 0, 0)),
    "r1s": (dict(_rtable(True), blk="r1s", dot="fp"), _flags(0, 0, 1)),     # "analyse 7 {{ref}}": a digit before a reference
    "rs":  (_table("rs", "rs", x="fw", e="fw", lpar=None), _flags(0, 0, 1)),     # a sign or an x after a reference: no number
    "re":  (_table("fb", "ls", sgn="re2"), _flags(1, 0, 0)),                      # an "e" after a reference: no exponent digit
    "re2": (_table("o", "ls", lpar=None), _flags(0, 0, 0)),
    "rpar": (_table("lp", "ls", lpar="rpar"), _flags(1, 1, 1)),                   # a "(" after a reference: no unit in it
}
_R_MODES = ("r0", "r1", "r0s", "r1s", "nl", "nlb", "rpar")   # the modes where a unit may not start

# ================================================================ closed labels and identifiers
# Digit-bearing notations gate v2 reads as notation, not as numbers: a numeric character glued to a letter (R², C₀, t½), a
# digit glued to a letter (C0), the 0 of AUC(0-...) (a small integer), 1/h (the unit fragment). The names the renderer prints
# that carry one are among them (renderer_labels, checked by a test).
LABELS = ("R²", "r²", "t½", "T½", "t1/2", "T1/2", "C0", "c0", "C₀", "c₀",
          "AUC(0-tlast)", "AUC(0–tlast)", "AUC(0-inf)", "AUC(0–inf)", "AUC(0-t)", "AUC(0–t)", "AUC(0-∞)", "AUC(0–∞)",
          "AUC₀₋∞", "AUC₀₋t", "AUC₀₋inf", "1/h", "1/min", "1/λz")
IDENT_WORDS = {"analysis": ("analyse", "Analyse", "analysis", "Analysis"), "subject": ("sujet", "Sujet", "subject", "Subject"),
               "worksheet": ("worksheet", "Worksheet", "feuille", "Feuille")}

def renderer_labels():
    """The tokens of the names the renderer prints (gate_v2 tables) that carry a digit or a numeric character."""
    names = list(PARAMETERS.values()) + list(gate_v2._LZ_NAMES.values()) + [r["name"] for r in CONVENTIONS.values()]
    return sorted({t for n in names for t in re.split(r"[\s,/]+", n) if re.search(r"[\d²³¹½¼¾₀-₉⁰-⁹]", t)})

def _label_kind(s):
    return ("d" if s[0] in "0123456789" else "l"), ("n" if s[-1] in "0123456789" else "p" if s[-1] == ")" else "w")

# ================================================================ the vocabulary of a turn
class Vocabulary:
    """The three open lists of a turn: the references, the typed numbers, the identifiers (and what was dropped, and why)."""
    __slots__ = ("refs", "numbers", "idents", "dropped")

    def __init__(self, refs, numbers, idents, dropped):
        self.refs, self.numbers, self.idents, self.dropped = refs, numbers, idents, dropped


def _nca_paths(sc):
    subs = (sc.get("result") or {}).get("subjects") or []
    thr = list(gate_v2._thresholds(sc))
    out = []
    for s in subs:
        label = str(s.get("subject"))
        ok = (s.get("outcome") or {}).get("ok") or {}
        keys = [] if s.get("dose") is None else ["dose"]
        keys += [p["name"] for p in ok.get("parameters") or [] if isinstance(p, dict) and p.get("name") in PARAMETERS]
        if len(gate_v2._selected_candidates(ok)) == 1:      # gate_v2._norm reads n.points and n_points alike
            keys += [f"lambda_z.{k}" for k in gate_v2._LZ_FIELDS] + [f"lambda_z.{k.replace('_', '.')}" for k in gate_v2._LZ_FIELDS if "_" in k]
        keys += [f"thresholds.{n}" for n in thr]
        out += [(label, k) for k in keys]
    return out, [f"thresholds.{n}" for n in thr], len(subs)

def _compare_paths(sc):
    return [f"{r.get('parameter')}.{f}" for r in sc.get("rows") or [] if r.get("parameter") in PARAMETERS
            for f in ("a", "b", "difference", "percent", "ratio")]

_PLAIN_LABEL = re.compile(r"[^\s.\[\]{}'\"“”‘’`:=]+")

def enumerate_refs(calls, schemas=None, dropped=None):
    """Every `{{...}}` text the model may write: a path of the closed tables that gate_v2.resolve accepts on this chat, in the
    forms the system prompt teaches (`subject=LABEL.` for an analysis with several subjects, optional for one)."""
    drop = {} if dropped is None else dropped
    out, seen = [], set()
    def add(ref, path):
        text = "{{" + (f"{ref}.{path}" if ref else path) + "}}"
        if text in seen: return
        try:
            if ref:
                if gate_v2.parse_ref(text[2:-2]) != (ref, path): raise Unresolved("round trip")
                gate_v2.resolve(ref, path, calls, schemas)
            else:
                if gate_v2.parse_ref(text[2:-2]) != (None, None) or gate_v2.parse_convention(text[2:-2]) != path[len("convention."):]:
                    raise Unresolved("round trip")
                gate_v2.resolve_convention(path[len("convention."):], calls)
        except Unresolved:
            drop["unresolved"] = drop.get("unresolved", 0) + 1; return
        seen.add(text); out.append(text)
    for ref, rec in (calls or {}).items():
        sc = rec.get("structured")
        if not isinstance(sc, dict): continue
        if sc.get("kind") == "nca" and isinstance(sc.get("result"), dict):
            pairs, analysis_level, n = _nca_paths(sc)
            for label, key in pairs:
                if not _PLAIN_LABEL.fullmatch(label): drop["label"] = drop.get("label", 0) + 1; continue
                add(ref, f"subject={label}.{key}")
                if n == 1: add(ref, key)
            for key in analysis_level: add(ref, key)
        elif isinstance(sc.get("rows"), list) and "a" in sc and "b" in sc:
            for key in _compare_paths(sc): add(ref, key)
    for key in CONVENTIONS: add(None, f"convention.{key}")
    return out

def user_tokens(user_texts, limit=4000):
    """The numbers the user typed, as written (what gate._BAG_RE reads, and, as gate._bag_readings does, the pieces of a token
    cut at "," and ";" when each is a plain decimal: "0.5,4.2" is a CSV row of 0.5 and 4.2), with the other decimal mark of a
    decimal (gate v2 reads 7.5 and 7,5 as one number), in order of first appearance."""
    out = {}
    def add(x):
        if len(out) < limit: out.setdefault(x, None)
        if re.fullmatch(r"\d+\.\d+", x): add_mark(x.replace(".", ","))
        elif re.fullmatch(r"\d+,\d+", x): add_mark(x.replace(",", "."))
    def add_mark(x):                  # gate v2 reads 7.5 and 7,5 as one number: the answer may use the other decimal mark
        if len(out) < limit: out.setdefault(x, None)
    for t in user_texts or ():
        for m in gate._BAG_RE.finditer(str(t)):
            tok = m.group(0); add(tok)
            pieces = re.split(r"[,;]", tok)
            if len(pieces) > 1 and all(re.fullmatch(r"\d+(?:\.\d+)?", p) for p in pieces):
                for p in pieces: add(p)
    return list(out)

def _clean_phrases(phrases, allowed, dropped, key):
    """The phrases gate v2 reads without a finding (one check for all of them, ' ; ' between)."""
    phrases = list(phrases)
    if not phrases: return []
    text, starts = "a ; ", []
    for p in phrases:
        starts.append(len(text)); text += p + " ; "
    bad = {bisect.bisect_right(starts, f["position"][0]) - 1 for f in gate_v2.check(text, {}, (), None, ".", allowed)["findings"]}
    if bad: dropped[key] = dropped.get(key, 0) + len(bad)
    return [p for k, p in enumerate(phrases) if k not in bad]

def ident_numbers(calls):
    """{kind: [id]} of this chat's tool results: the analysis ids, the all-digit subject labels, the worksheet ids."""
    analyses, subjects, sheets = {}, {}, {}
    def digits(x): return isinstance(x, str) and x.isascii() and x.isdigit()
    def ident(x): return isinstance(x, int) and not isinstance(x, bool) and x >= 0
    for rec in (calls or {}).values():
        sc = rec.get("structured")
        if not isinstance(sc, dict): continue
        if sc.get("kind") == "nca":
            if ident(sc.get("id")): analyses[str(sc["id"])] = None
            for s in (sc.get("result") or {}).get("subjects") or []:
                if digits(str(s.get("subject"))): subjects[str(s.get("subject"))] = None
        elif isinstance(sc.get("rows"), list):
            for side in (sc.get("a"), sc.get("b")):
                if isinstance(side, dict):
                    if ident(side.get("analysis")): analyses[str(side["analysis"])] = None
                    if digits(str(side.get("subject"))): subjects[str(side.get("subject"))] = None
        elif isinstance(sc.get("worksheet"), dict):
            for lab in sc["worksheet"].get("subjects") or []:
                if digits(str(lab)): subjects[str(lab)] = None
            if ident(sc["worksheet"].get("id")): sheets[str(sc["worksheet"]["id"])] = None
    return {"analysis": list(analyses), "subject": list(subjects), "worksheet": list(sheets)}

def vocabulary(calls, user_texts=(), schemas=None, *, idents=True):
    dropped = {}
    refs = enumerate_refs(calls, schemas, dropped)
    allowed = gate_v2.user_numbers(user_texts)
    numbers = _clean_phrases(user_tokens(user_texts), allowed, dropped, "number")
    ids = []
    if idents:
        found = ident_numbers(calls)
        for kind, words in IDENT_WORDS.items(): ids += [f"{w} {n}" for w in words for n in found[kind]]
        ids = _clean_phrases(ids, allowed, dropped, "ident")
    return Vocabulary(refs, numbers, ids, dropped)

# ================================================================ rules and GBNF text
# A rule is a list of alternatives, an alternative a list of elements: ("c", CS), ("l", literal), ("r", rule name).
def _chr(cp):
    c = chr(cp)
    if c.isascii() and c.isalnum(): return c
    return f"\\x{cp:02x}" if cp < 0x100 else f"\\u{cp:04x}" if cp < 0x10000 else f"\\U{cp:08x}"

def _class(cs): return "[" + "".join(_chr(a) if a == b else f"{_chr(a)}-{_chr(b)}" for a, b in cs.r) + "]"

def _literal(s):
    out = []
    for c in s:
        if c.isascii() and (c.isalnum() or c in " !#$%&'()*+,-./:;<=>?@^_`|~"): out.append(c)
        elif c == '"': out.append('\\"')
        elif c == "\\": out.append("\\\\")
        else: out.append(_chr(ord(c)))
    return '"' + "".join(out) + '"'

def _element(e):
    kind, v = e
    return _class(v) if kind == "c" else _literal(v) if kind == "l" else v

def rule_line(name, alts):
    return f"{name} ::= " + " | ".join(" ".join(_element(e) for e in alt) if alt else '""' for alt in alts)

def trie_rules(root, words):
    """Prefix tree of `words` as rules `root`, `root-1`, ...: one alternative per branch, single-child chains as literals."""
    tree = {}
    for w in words:
        node = tree
        for ch in w: node = node.setdefault(ch, {})
        node[None] = True
    rules, counter = {}, itertools.count(1)
    def emit(node, name):
        alts = [[("l", "")]] if node.get(None) else []
        for ch in sorted(k for k in node if k is not None):
            lit, cur = ch, node[ch]
            while not cur.get(None) and len(cur) == 1:
                nxt = next(iter(cur)); lit += nxt; cur = cur[nxt]
            if all(k is None for k in cur): alts.append([("l", lit)])
            else:
                sub = f"{root}-{next(counter)}"
                emit(cur, sub); alts.append([("l", lit), ("r", sub)])
        rules[name] = alts
    emit(tree, root)
    return rules

def _groups(table):
    """[(CS, target)] of a mode table: the kinds with the same target merged."""
    by = {}
    for kind, tgt in table.items():
        if tgt is not None: by[tgt] = by.get(tgt, CS()) | KINDS[kind]
    return sorted(((cs, t) for t, cs in by.items()), key=lambda ct: ct[0].r[0])

def _blank_exclusions():
    """The distinct sets of letters that go on a unit from a state that ends with a blank (here: c and C, for "pour cent")."""
    return sorted(set(UD.after_blank.values()), key=lambda c: c.r)

def _static_rules():
    """What does not depend on the turn: the unit automaton, the tails it shares, the labels."""
    rules = {}
    fw = MODES["fw"][0]
    non_letter = {k: v for k, v in fw.items() if k not in ("x", "e", "let")}
    blanks = CS.of(" \t")
    for k, drop in (("0", CS()), ("1", blanks)):
        rules[f"tail-{k}"] = [[("c", cs - drop), ("r", "m-" + t)] for cs, t in _groups(non_letter) if cs - drop]
    rules["xl-fw"] = [[("c", _XL), ("r", "m-fw")]]
    excl = _blank_exclusions()
    for s in UD.live:
        ext = UD.ext(s)
        assert UD.complete[s] or not (ext & _XL), "a unit word with a non-ASCII letter after its first character"
        alts = [[("c", cs), ("r", UD.name[t])] for t, cs in sorted(UD.edges(s).items(), key=lambda kv: kv[1].r[0])]
        alts.append([("c", (ASCII_LETTERS | MICRO) - ext), ("r", "m-fw")])
        if UD.complete[s]: alts.append([("c", APOS), ("r", "m-fb")])
        else:
            alts.append([("r", "xl-fw")])
            alts.append([("r", f"m-fbx{excl.index(UD.after_blank[s])}")] if s in UD.after_blank
                        else [("r", "tail-1" if ext & blanks else "tail-0")])
            alts.append([("l", "")])
        rules[UD.name[s]] = alts
    return rules

def _label_rules(prefix, exclude):
    by = {}
    for lab in LABELS:
        if lab[0] not in exclude: by.setdefault(_label_kind(lab), []).append(lab)
    rules = {}
    for (a, b), ws in by.items(): rules.update(trie_rules(f"{prefix}-{a}{b}", ws))
    return rules, set(by)

def _mode_alts(name, flags, exclude=CS(), labels="lab"):
    """Alternatives of mode `name`. `exclude`: first characters the mode must not accept (they go on a unit)."""
    table, fl = MODES[name]
    has_ref, has_num, has_id = flags
    alts = []
    for cs, tgt in _groups(table):
        if name in _R_MODES and tgt in ("fw", "fb"): cs = cs - UNIT_START
        cs = cs - exclude
        if cs: alts.append([("c", cs), ("r", "m-" + tgt)])
    if name in _R_MODES:
        for t, cs in sorted(UD.root_edges.items(), key=lambda kv: kv[1].r[0]): alts.append([("c", cs), ("r", UD.name[t])])
    _, kinds = _label_rules(labels, "".join(exclude))
    if fl["ref"] and has_ref: alts.append([("r", "ph-ref"), ("r", "m-r0")])
    if fl["digit"]:
        if has_num: alts.append([("r", "ph-num"), ("r", "m-n")])
        if ("d", "w") in kinds and name == "lp":       # elsewhere "Cmax 1/min": gate v2 takes the 1 for the value of Cmax
            alts.append([("r", f"{labels}-dw"), ("r", "m-fw")])
    if fl["letter"]:
        for end, nxt in (("n", "m-nl"), ("p", "m-fcp"), ("w", "m-fw")):
            if ("l", end) in kinds: alts.append([("r", f"{labels}-l{end}"), ("r", nxt)])
        if has_id: alts.append([("r", "ph-id"), ("r", "m-r0s")])
    if fl["acc"]: alts.append([("l", "")])
    return alts

_STATIC = None
_HOST = {}

def _host_rules(flags):
    """The mode rules for a turn that has (or lacks) references, typed numbers and identifiers."""
    global _STATIC
    if flags in _HOST: return _HOST[flags]
    if _STATIC is None: _STATIC = {**_static_rules(), **_label_rules("lab", "")[0]}
    rules = dict(_STATIC)
    for name in MODES: rules["m-" + name] = _mode_alts(name, flags)
    for k, excl in enumerate(_blank_exclusions()):
        rules.update(_label_rules(f"labx{k}", "".join(excl))[0])
        rules[f"m-fbx{k}"] = _mode_alts("fb", flags, exclude=excl, labels=f"labx{k}")
    rules["root"] = [[("r", "m-s")]]
    _HOST[flags] = rules
    return rules

def factor_classes(rules, min_ranges=8):
    """Big character classes become rules `k-N` (the text stays small; the stacks the engine builds are the same)."""
    out, names, extra = {}, {}, {}
    def ref(cs):
        if cs not in names:
            names[cs] = f"k-{len(names) + 1}"; extra[names[cs]] = [[("c", cs)]]
        return ("r", names[cs])
    for n, alts in rules.items():
        out[n] = [[ref(e[1]) if e[0] == "c" and len(e[1].r) >= min_ranges else e for e in alt] for alt in alts]
    out.update(extra)
    return out

# ---------------------------------------------------------------- the recognizer: llama.cpp's stack engine
def _pack(ranges): return (tuple(a for a, _ in ranges), tuple(b for _, b in ranges))

class Machine:
    """llama.cpp b11700 src/llama-grammar.cpp on in-memory rules. A stack is a tuple of positions (rule, alternative, index), the
    top is last; advance_stack expands rule references into one stack per alternative; accept_chr consumes one code point. A
    state is a frozenset of stacks; the empty stack in it means the grammar can end here."""

    def __init__(self, rules, root="root"):
        self.names = list(rules)
        index = {n: i for i, n in enumerate(self.names)}
        self.alts = []
        for n in self.names:
            alts = []
            for alt in rules[n]:
                seq = []
                for kind, v in alt:
                    if kind == "r":
                        if v not in index: raise ValueError(f"rule {n} uses the undefined rule {v}")
                        seq.append(index[v])
                    elif kind == "l": seq.extend(_pack(((ord(ch), ord(ch)),)) for ch in v)
                    else: seq.append(_pack(v.r))
                alts.append(tuple(seq))
            self.alts.append(tuple(alts))
        self.root = index[root]
        self._adv, self._acc = {}, {}
        self._check_left_recursion()
        start = set()
        for k, alt in enumerate(self.alts[self.root]):
            if alt: start.update(self._advance(((self.root, k, 0),)))
            else: start.add(())
        self.start = frozenset(start)

    def _check_left_recursion(self):
        n = len(self.alts)
        nullable = [False] * n
        changed = True
        while changed:
            changed = False
            for r in range(n):
                if not nullable[r] and any(all(isinstance(e, int) and nullable[e] for e in alt) for alt in self.alts[r]):
                    nullable[r] = changed = True
        state = [0] * n
        def visit(r):
            if state[r] == 1: raise ValueError(f"left recursion at {self.names[r]}")
            if state[r] == 2: return
            state[r] = 1
            for alt in self.alts[r]:
                for e in alt:
                    if not isinstance(e, int): break
                    visit(e)
                    if not nullable[e]: break
            state[r] = 2
        for r in range(n): visit(r)

    def _advance(self, stack):
        got = self._adv.get(stack)
        if got is not None: return got
        out, seen, todo = [], set(), [stack]
        while todo:
            st = todo.pop()
            if st in seen: continue
            seen.add(st)
            if not st: out.append(st); continue
            r, a, p = st[-1]
            el = self.alts[r][a][p]
            if isinstance(el, int):
                base = st[:-1]
                if p + 1 < len(self.alts[r][a]): base = base + ((r, a, p + 1),)
                for k, sub in enumerate(self.alts[el]): todo.append(base + (((el, k, 0),) if sub else ()))
            else: out.append(st)
        res = tuple(out)
        self._adv[stack] = res
        return res

    def step(self, state, ch):
        """The state after consuming `ch` (empty when no stack accepts it)."""
        key = (state, ch)
        got = self._acc.get(key)
        if got is not None: return got
        cp = ord(ch)
        new = set()
        for st in state:
            if not st: continue
            r, a, p = st[-1]
            starts, ends = self.alts[r][a][p]
            i = bisect.bisect_right(starts, cp) - 1
            if i >= 0 and cp <= ends[i]:
                base = st[:-1]
                if p + 1 < len(self.alts[r][a]): base = base + ((r, a, p + 1),)
                new.update(self._advance(base))
        res = frozenset(new)
        self._acc[key] = res
        return res

    def accepting(self, state): return () in state

    def allowed(self, state):
        """The characters some stack of `state` can consume next."""
        cs = CS()
        for st in state:
            if st:
                r, a, p = st[-1]; starts, ends = self.alts[r][a][p]
                cs = cs | CS(zip(starts, ends))
        return cs

    def modes(self, state):
        """The names of the mode (or unit) rules the stacks of `state` are in, for the diagnostics."""
        names = set()
        for st in state:
            for fr in reversed(st):
                n = self.names[fr[0]]
                if n.startswith(("m-", "u-")): names.add(n); break
        return sorted(names)

# ---------------------------------------------------------------- the grammar of a turn
class Grammar:
    __slots__ = ("rules", "gbnf", "vocab", "stats", "_machine")

    def __init__(self, rules, vocab, build_ms):
        self.rules, self.vocab, self._machine = rules, vocab, None
        self.gbnf = "\n".join(rule_line(n, a) for n, a in rules.items()) + "\n"
        self.stats = {"rules": len(rules), "bytes": len(self.gbnf.encode("utf-8")), "refs": len(vocab.refs),
                      "numbers": len(vocab.numbers), "idents": len(vocab.idents), "dropped": dict(vocab.dropped),
                      "build_ms": round(build_ms, 1)}

    @property
    def machine(self):
        if self._machine is None: self._machine = Machine(self.rules)
        return self._machine

    def accepts(self, text):
        m = self.machine
        state = m.start
        for ch in text:
            state = m.step(state, ch)
            if not state: return False
        return m.accepting(state)

    def scan(self, text):
        """[(start, end, modes)] where the grammar refuses the text: at `start` no stack accepts the character; the scan goes on
        at the first later character the same state accepts. `modes` names the rules the state was in (the context). A text that
        stops where the grammar cannot end gets a last empty span."""
        m = self.machine
        state, i, out = m.start, 0, []
        while i < len(text):
            nxt = m.step(state, text[i])
            if nxt: state, i = nxt, i + 1; continue
            j = i + 1
            while j < len(text) and not m.step(state, text[j]): j += 1
            out.append((i, j, m.modes(state)))
            i = j
        if not m.accepting(state): out.append((len(text), len(text), m.modes(state)))
        return out


def build(calls, user_texts=(), schemas=None, *, idents=True):
    """The grammar of one turn. `calls` is the dict of citable results (apothicaire.Apothicaire.refs), `user_texts` the user's
    messages of the chat, `schemas` the tools' outputSchema (as gate_v2.check gets them)."""
    t0 = time.perf_counter()
    vocab = vocabulary(calls, user_texts, schemas, idents=idents)
    rules = dict(_host_rules((bool(vocab.refs), bool(vocab.numbers), bool(vocab.idents))))
    if vocab.refs: rules.update(trie_rules("ph-ref", vocab.refs))
    if vocab.numbers: rules.update(trie_rules("ph-num", vocab.numbers))
    if vocab.idents: rules.update(trie_rules("ph-id", vocab.idents))
    return Grammar(factor_classes(rules), vocab, (time.perf_counter() - t0) * 1000)


def conformance(grammar, text, finish_reason=None):
    """How a regeneration sampled under `grammar` looks to the grammar. llama.cpp's sampler gives no token the grammar refuses a
    chance, so the text that comes back is a prefix of the language, and a text that stopped by itself is a sentence of it; if it
    is not, the server did not enforce the grammar it was sent. `alive`: no character of `text` is refused. `accepted`: `text` may
    end where it does. A text cut at the token limit (`finish_reason` "length") is owed to be alive only, and so is one whose
    reason is unknown; an empty text is owed nothing. `violation` is the verdict: the grammar was not enforced."""
    spans = grammar.scan(text)
    refused = [s[0] for s in spans if s[0] < len(text)]
    stopped = finish_reason not in (None, "length")
    return {"accepted": not spans, "alive": not refused, "refused_at": refused[0] if refused else None, "finish_reason": finish_reason,
            "violation": bool(refused) or (bool(text) and stopped and bool(spans))}
