"""An independent reader of the GBNF subset that gate_v3 prints, for tests/test_gate_v3.py.

It shares no code with gate_v3. It parses the text of a grammar (rules, alternatives, string literals, character classes, rule
references; the syntax of llama.cpp's grammars/README.md, with the escapes parse_char of src/llama-grammar.cpp accepts) and
recognises with an Earley parser, so that a text and each of its prefixes can be compared with gate_v3.Machine, the
re-implementation of llama.cpp's stack engine that runs on the rules gate_v3 builds. If the printer escaped a character wrongly
or the engine parted from a textbook reading of the same rules, the two would disagree.
"""
import re

_NAME = re.compile(r"[a-zA-Z0-9-]+")
# parse_char: \x \u \U with 2, 4, 8 hex digits, and these escapes; "\-" and "\^" are no escapes there
_SIMPLE = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "[": "[", "]": "]"}


class GBNFError(ValueError):
    pass


def _char(s, i):
    """One (possibly escaped) character of a literal or a class at s[i]; returns (code point, next index)."""
    if s[i] != "\\": return ord(s[i]), i + 1
    c = s[i + 1]
    if c in "xuU":
        n = {"x": 2, "u": 4, "U": 8}[c]
        digits = s[i + 2:i + 2 + n]
        if len(digits) != n or not re.fullmatch(r"[0-9a-fA-F]+", digits): raise GBNFError(f"bad escape at {i}: {s[i:i + 2 + n]!r}")
        return int(digits, 16), i + 2 + n
    if c in _SIMPLE: return ord(_SIMPLE[c]), i + 2
    raise GBNFError(f"unknown escape \\{c}")


def _class(s, i):
    """A character class [..] at s[i] == '['; returns ([(lo, hi)], next index)."""
    assert s[i] == "["
    i += 1
    if s[i] == "^": raise GBNFError("negated classes are not in the subset")
    out = []
    while s[i] != "]":
        lo, i = _char(s, i)
        if s[i] == "-" and s[i + 1] != "]":
            hi, i = _char(s, i + 1)
            if hi < lo: raise GBNFError("reversed range")
        else: hi = lo
        out.append((lo, hi))
    return out, i + 1


def parse(text):
    """{name: [alternative]} with alternative = [symbol] and symbol = ("t", [(lo, hi)]) | ("r", name). One rule per line."""
    rules = {}
    for ln, line in enumerate(text.split("\n"), 1):
        if not line.strip(): continue
        m = re.match(r"([a-zA-Z0-9-]+) ::= ", line)
        if not m: raise GBNFError(f"line {ln}: not a rule: {line[:60]!r}")
        name, i, alts, cur = m.group(1), m.end(), [], []
        if name in rules: raise GBNFError(f"line {ln}: rule {name} defined twice")
        while i < len(line):
            c = line[i]
            if c == " ": i += 1
            elif c == "|": alts.append(cur); cur = []; i += 1
            elif c == '"':
                i += 1
                while line[i] != '"':
                    cp, i = _char(line, i)
                    cur.append(("t", [(cp, cp)]))
                i += 1
            elif c == "[":
                rng, i = _class(line, i)
                cur.append(("t", rng))
            else:
                mm = _NAME.match(line, i)
                if not mm: raise GBNFError(f"line {ln}: unexpected {line[i:i + 20]!r}")
                cur.append(("r", mm.group(0))); i = mm.end()
        alts.append(cur)
        rules[name] = alts
    for name, alts in rules.items():
        for alt in alts:
            for kind, v in alt:
                if kind == "r" and v not in rules: raise GBNFError(f"rule {name} uses the undefined rule {v}")
    if "root" not in rules: raise GBNFError("no root rule")
    return rules


class Reader:
    """An Earley recogniser (with the nullable shortcut of Aycock and Horspool) of a parsed grammar."""

    def __init__(self, text):
        self.rules = parse(text)
        self.nullable = self._nullable()

    def _nullable(self):
        nl, changed = set(), True
        while changed:
            changed = False
            for n, alts in self.rules.items():
                if n not in nl and any(all(k == "r" and v in nl for k, v in alt) for alt in alts):
                    nl.add(n); changed = True
        return nl

    def productive(self):
        """The rules that derive at least one string: a rule that does not is a dead end a sampler could walk into."""
        ok, changed = set(), True
        while changed:
            changed = False
            for n, alts in self.rules.items():
                if n not in ok and any(all(k == "t" or v in ok for k, v in alt) for alt in alts):
                    ok.add(n); changed = True
        return ok

    def run(self, text):
        """[(alive, complete)] after 0, 1, ... len(text) characters. alive: the text so far is a prefix of the language (some item
        survived the scan); complete: the text so far is a sentence."""
        rules = self.rules
        charts, waiting = [], []                   # item = (rule, alternative, dot, origin); waiting[i][rule] = items of chart i whose dot is before rule

        def add(i, item, work):
            chart = charts[i]
            if item in chart: return
            chart.add(item); work.append(item)
            r, a, d, o = item
            alt = rules[r][a]
            if d < len(alt) and alt[d][0] == "r": waiting[i].setdefault(alt[d][1], []).append(item)

        def close(i, work):
            while work:
                r, a, d, o = work.pop()
                alt = rules[r][a]
                if d < len(alt):
                    kind, v = alt[d]
                    if kind == "r":                                                    # predict
                        for k in range(len(rules[v])): add(i, (v, k, 0, i), work)
                        if v in self.nullable: add(i, (r, a, d + 1, o), work)
                else:                                                                  # complete
                    for (r2, a2, d2, o2) in list(waiting[o].get(r, ())): add(i, (r2, a2, d2 + 1, o2), work)

        charts.append(set()); waiting.append({})
        work = []
        for k in range(len(rules["root"])): add(0, ("root", k, 0, 0), work)
        close(0, work)
        out = [(True, self._complete(charts[0]))]
        for i, ch in enumerate(text):
            cp = ord(ch)
            charts.append(set()); waiting.append({})
            work = []
            for (r, a, d, o) in list(charts[i]):
                alt = rules[r][a]
                if d < len(alt) and alt[d][0] == "t" and any(lo <= cp <= hi for lo, hi in alt[d][1]): add(i + 1, (r, a, d + 1, o), work)
            if not charts[i + 1]:
                out.extend([(False, False)] * (len(text) - i)); break
            close(i + 1, work)
            out.append((True, self._complete(charts[i + 1])))
        return out

    def _complete(self, chart):
        return any(r == "root" and o == 0 and d == len(self.rules["root"][a]) for (r, a, d, o) in chart)

    def accepts(self, text):
        return self.run(text)[-1][1]
