#!/usr/bin/env python
"""Offline check of the gate v3 grammar against the stored gate v2 development runs: no model, no engine, no GPU.

Gate v3 (gate_v3.py) samples the regeneration under a grammar. Before a GPU is spent on it, two questions can be put to the runs
already on disk (bench/runs/decision/v2: gate v2, development tier, seeds 1-3, 25 exercises, 8 turns each):

  (a) The answers gate v2 let through with no finding (the kept answer of a turn whose gate record has `findings: []`). The
      grammar must accept them, or it forbids answers that were fine. A refusal is put in a cause by the first character the
      grammar refuses (`refusal_cause`).
  (b) The first drafts gate v2 found something in (`first_answer` and `first_findings` of the turns it regenerated). The grammar
      must refuse them, and where the finding is: a finding is caught when a span the grammar refuses (`Grammar.scan`) touches
      the finding's position, one character either side (`touches`); "inside" counts only the overlap with no slack.

For each turn the grammar is the one the turn would have had: `gate_v3.build(calls, users)` with the references of the tool results
above the answer and the user's messages up to it. The tools' output schemas are not stored; the closed tables of gate v2 alone
reproduce the stored gate counts on all 600 turns (tests/test_grammar_offline.py replays them), so `schemas` is None here.

What "accepts" means. Nothing here is a regular expression, so there is no regex-to-GBNF equivalence to prove, and llama.cpp b11700
ships no stand-alone grammar validator (its tools are the server, the CLI and the library). `Grammar.accepts` and `Grammar.scan`
run the rules of the grammar on `gate_v3.Machine`, a Python re-implementation of the stack engine of llama.cpp b11700
(src/llama-grammar.cpp: the same rule table, alternatives, character classes, empty-stack acceptance, left-recursion refusal).
Its rules are the very rules that `Grammar.gbnf` prints, the text the server receives, one rule per line. The printed text is read
a second time by tests/gbnf_reader.py, an Earley recogniser that shares no code with gate_v3; the two agree on every prefix of the
texts tested (tests/test_gate_v3.py::TestGrammarText), and tests/test_grammar_offline.py repeats the agreement on stored answers.
What is not tested here is that b11700 itself takes the text as the two readers do; the first GPU run checks it (`Grammar.accepts`
on every regenerated answer, recorded in the gate record).

Two grammars are run: the one the arm uses (`identifiers`: an analysis or subject number after the word that names it, "analyse 3",
is allowed, as gate v2 exempts it) and `strict` (the letter of the three cases: no such number).

  python bench/grammar_offline.py [runs_dir] [--json] [--no-strict]

prints the report in Markdown (about 20 s a grammar set); `--json` prints every record instead. Nothing is written to disk.
"""
import argparse, collections, glob, json, os, re, statistics, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import gate_v3  # noqa: E402

RUNS = os.path.join(HERE, "runs", "decision", "v2")

# ---------------------------------------------------------------- the stored runs
def _jsonl(path):
    with open(path, encoding="utf-8") as f: return [json.loads(l) for l in f if l.strip()]

def turns_of(log):
    """[(index of the user message, index of the last assistant message of the turn)], one pair per user message."""
    users = [i for i, m in enumerate(log) if m["role"] == "user"]
    out = []
    for k, u in enumerate(users):
        end = users[k + 1] if k + 1 < len(users) else len(log)
        out.append((u, max(i for i in range(u, end) if log[i]["role"] == "assistant")))
    return out

_REF = re.compile(r'^\{"ref":"(call_\d+)"')

def load_turns(runs=RUNS):
    """Every turn of the stored runs: seed, exercise, turn (from 1), `users` (the user's messages up to the answer), `calls` (the
    reference records the model could cite: the tool results above the answer), `final` (the kept answer, references unrendered)
    and `gate` (its gate record)."""
    folders = sorted(glob.glob(os.path.join(runs, "seed-*", "*-data")))
    if not folders: raise FileNotFoundError(f"no stored run in {runs} (expected seed-N/exNN_name-data/)")
    out = []
    for d in folders:
        if not os.path.exists(os.path.join(d, "refs.jsonl")): raise FileNotFoundError(f"{d} has no refs.jsonl: only gate v2 runs store the references")
        log, gate, refs = (_jsonl(os.path.join(d, n)) for n in ("log.jsonl", "gate.jsonl", "refs.jsonl"))
        by_ref = {r["ref"]: r for r in refs}
        spans = turns_of(log)
        if len(spans) != len(gate): raise ValueError(f"{d}: {len(spans)} turns in log.jsonl, {len(gate)} in gate.jsonl")
        seed, ex = os.path.basename(os.path.dirname(d)), os.path.basename(d)[:-len("-data")]
        for k, ((u, a), g) in enumerate(zip(spans, gate), 1):
            seen = [m.group(1) for m in (_REF.match(x["content"] or "") for x in log[:a] if x["role"] == "tool_result") if m]
            out.append(dict(seed=int(seed.split("-")[1]), exercise=ex, turn=k, users=[x["content"] for x in log[:a] if x["role"] == "user"],
                            calls={r: by_ref[r] for r in seen}, final=log[a]["content"], gate=g))
    return out

# ---------------------------------------------------------------- what the grammar refuses, and why
CAUSES = {
    "number": "a number the user did not type ('3 points', '(2 ou 4)'); gate v2 exempts integers up to 20, the grammar does not",
    "identifier": "an analysis or subject number after its word ('analyse 7'); the strict grammar only",
    "label": "a label that starts with a digit, outside a parenthesis ('1/h pour λz')",
    "numeric character": "a superscript or fraction character outside the closed labels ('A²')",
    "unit-like word": "a word that begins like a unit right after a reference ('{{ref}} (les', '(MRT'); see UNIT_ALIVE in gate_v3",
    "other": "none of these",
    "unfinished": "the text stops where the grammar cannot end",
}
_IDENT_BEFORE = re.compile(r"(?:analyses?|analysis|sujets?|subjects?|worksheets?|feuilles?)\s*#?\s*$", re.I)
_DIGITS = "0123456789"
_UNIT_MODES = {"m-" + n for n in gate_v3._R_MODES}

def refusal_cause(text, span):
    """The key of CAUSES for the first span the grammar refuses in `text` (a (start, end, modes) of Grammar.scan)."""
    a, _, modes = span
    c = text[a] if a < len(text) else ""
    if c == "" and text.rfind("{{") > text.rfind("}}"): return "unfinished"               # the text stops inside a reference
    digit = c != "" and c in _DIGITS
    after = None if digit else re.search(r"[0-9][0-9.,]*$", text[:a])    # else the number the refused character comes right after
    if digit or after:
        j = a if digit else after.start()
        while j and text[j - 1] in _DIGITS + ".,": j -= 1
        if re.match(r"1/(?:h|min)(?![A-Za-z])", text[j:]): return "label"
        return "identifier" if _IDENT_BEFORE.search(text[:j]) else "number"
    if c == "": return "unfinished"
    if unicodedata.category(c).startswith("N"): return "numeric character"
    if c.isalpha() and _UNIT_MODES & set(modes): return "unit-like word"
    return "other"

def excerpt(text, a, before=24, after=16):
    """The text around the refused character `a`, which is put in brackets; newlines are shown as \\n."""
    s = text[max(0, a - before):a] + "[" + (text[a:a + 1] or "end") + "]" + text[a + 1:a + 1 + after]
    return s.replace("\n", "\\n").replace("`", "'")

def touches(spans, start, end, slack=1):
    """True when a span the grammar refuses touches [start, end): it overlaps it, `slack` characters either side counted (an empty
    span, the text stopping where the grammar cannot end, counts when it lies in [start, end])."""
    for a, b, _ in spans:
        if a == b:
            if start <= a <= end: return True
        elif a < end + slack and b > start - slack: return True
    return False

# the findings of gate v2, in the order they are reported
FINDINGS = (
    ("unit", "a unit next to a reference (the client prints it)"),
    ("unresolved", "a reference that does not resolve (unknown or misspelt path, a comparison field not named)"),
    ("untyped", "a reference to a raw JSON path or to a text or export field (not a quantity the client prints)"),
    ("malformed", "a malformed reference"),
    ("digit", "a digit after a reference"),
    ("arithmetic", "arithmetic or a sign next to a reference"),
    ("bare", "a number typed by hand that is not the user's"),
    ("spelled", "a quantity spelled in words with a unit"),
    ("contradictory", "a unit that contradicts the rendered one"),
)
FAMILIES = {"unit": "unit after a reference", "unresolved": "reference that cannot be printed", "untyped": "reference that cannot be printed",
            "malformed": "reference that cannot be printed", "digit": "other text next to a reference", "arithmetic": "other text next to a reference",
            "bare": "bare number", "spelled": "spelled-out number", "contradictory": "unit that contradicts"}

def finding_class(f):
    """The key of FINDINGS for a finding of gate v2 (its `kind` and `reason`)."""
    k, why = f["kind"], f["reason"]
    if k == "adjacent_to_reference":
        return "unit" if why.startswith("unit next to") else "digit" if why.startswith("digit after") else "arithmetic"
    return {"unresolved_reference": "unresolved", "untyped_reference": "untyped", "malformed_reference": "malformed", "bare_number": "bare",
            "number_word": "spelled", "contradictory_unit": "contradictory"}[k]

# ---------------------------------------------------------------- the two checks
def check(turns, idents=True):
    """Both checks on every turn, with the identifier extension on (the arm) or off (`strict`). Returns plain data:
    {"idents", "turns", "clean": [one record per final answer without a finding], "drafts": [one per regenerated turn], "sizes"}."""
    clean, drafts, sizes = [], [], []
    for T in turns:
        g = T["gate"]
        is_clean, draft = not g.get("findings"), g.get("first_answer") if g.get("regenerated") else None
        if not is_clean and not draft: continue
        grammar = gate_v3.build(T["calls"], T["users"], None, idents=idents)
        sizes.append([grammar.stats["rules"], grammar.stats["bytes"], grammar.stats["build_ms"]])
        who = dict(seed=T["seed"], exercise=T["exercise"], turn=T["turn"])
        if is_clean:
            spans = grammar.scan(T["final"])
            clean.append(dict(who, accepted=not spans, regenerated=bool(g.get("regenerated")),
                              cause=refusal_cause(T["final"], spans[0]) if spans else None, at=excerpt(T["final"], spans[0][0]) if spans else None))
        if draft:
            spans = grammar.scan(draft)
            found = []
            for f in g["first_findings"]:
                s, e = f["position"]
                found.append(dict(cls=finding_class(f), kind=f["kind"], reason=f["reason"], text=f["text"], caught=touches(spans, s, e), inside=touches(spans, s, e, 0)))
            drafts.append(dict(who, refused=bool(spans), findings=found, at=excerpt(draft, spans[0][0]) if spans else None))
    return {"idents": idents, "turns": len(turns), "seeds": sorted({T["seed"] for T in turns}), "clean": clean, "drafts": drafts, "sizes": sizes}

def tally(res):
    """The counts of one result, as the report prints them."""
    clean, drafts = res["clean"], res["drafts"]
    found = [f for d in drafts for f in d["findings"]]
    by_class = {k: [f for f in found if f["cls"] == k] for k, _ in FINDINGS}
    families = collections.Counter()
    for f in found: families[FAMILIES[f["cls"]]] += 1
    caught_by_family = collections.Counter(FAMILIES[f["cls"]] for f in found if f["caught"])
    sizes = res["sizes"]
    return {
        "turns": res["turns"], "seeds": res["seeds"], "clean": len(clean), "accepted": sum(c["accepted"] for c in clean),
        "causes": dict(collections.Counter(c["cause"] for c in clean if not c["accepted"])),
        "drafts": len(drafts), "refused": sum(d["refused"] for d in drafts),
        "findings": len(found), "caught": sum(f["caught"] for f in found), "inside": sum(f["inside"] for f in found),
        "by_class": {k: {"findings": len(v), "caught": sum(f["caught"] for f in v), "inside": sum(f["inside"] for f in v)} for k, v in by_class.items() if v},
        "by_family": {k: {"findings": families[k], "caught": caught_by_family[k]} for k in families},
        "bytes": (min(s[1] for s in sizes), int(statistics.median(s[1] for s in sizes)), max(s[1] for s in sizes)) if sizes else (0, 0, 0),
        "rules": (min(s[0] for s in sizes), int(statistics.median(s[0] for s in sizes)), max(s[0] for s in sizes)) if sizes else (0, 0, 0),
    }

# ---------------------------------------------------------------- the report
def pct(a, b): return f"{100.0 * a / b:.1f} %" if b else "-"

def markdown(runs, results):
    """The report; `results` = {"identifiers": check(...), "strict": check(..., idents=False) or absent}."""
    t = {k: tally(r) for k, r in results.items()}
    m = t["identifiers"]; s = t.get("strict")
    rel = os.path.relpath(runs, AGENT).replace(os.sep, "/") if os.path.isabs(runs) and runs.startswith(AGENT) else runs
    out = [f"# Gate v3 grammar, offline, on the stored gate v2 development runs",
           "",
           f"Runs: `{rel}`, {m['turns']} turns (seeds {', '.join(map(str, m['seeds']))}). Each turn gets the grammar `gate_v3.build` would have given it: the references above the "
           f"answer, the user's messages up to it. No model, no engine, no GPU. Grammar size per turn: {m['rules'][0]}-{m['rules'][2]} rules (median {m['rules'][1]}), "
           f"{m['bytes'][0] / 1000:.1f}-{m['bytes'][2] / 1000:.1f} KB (median {m['bytes'][1] / 1000:.1f} KB).",
           "",
           "## (a) Final answers gate v2 passed without a finding: the grammar must accept them",
           "",
           "| grammar | final answers | accepted | refused |", "|---|---|---|---|",
           f"| with identifiers (the arm) | {m['clean']} | {m['accepted']} ({pct(m['accepted'], m['clean'])}) | {m['clean'] - m['accepted']} |"]
    if s: out.append(f"| strict | {s['clean']} | {s['accepted']} ({pct(s['accepted'], s['clean'])}) | {s['clean'] - s['accepted']} |")
    out += ["", "First refused character, by cause:", "", "| cause | " + ("with identifiers | strict |" if s else "with identifiers |"), "|---|" + ("---|---|" if s else "---|")]
    for k, why in CAUSES.items():
        row = [m["causes"].get(k, 0)] + ([s["causes"].get(k, 0)] if s else [])
        if any(row): out.append(f"| {why} | " + " | ".join(map(str, row)) + " |")
    out += ["", f"The {m['clean'] - m['accepted']} refusals of the arm, each at its first refused character in brackets:", ""]
    for c in results["identifiers"]["clean"]:
        if not c["accepted"]: out.append(f"- seed {c['seed']} {c['exercise']} turn {c['turn']}, {c['cause']}: `{c['at']}`")
    out += ["", "## (b) First drafts gate v2 found something in: the grammar must refuse them", "",
            "| grammar | drafts | refused | accepted | findings | caught | caught inside |", "|---|---|---|---|---|---|---|",
            f"| with identifiers (the arm) | {m['drafts']} | {m['refused']} | {m['drafts'] - m['refused']} | {m['findings']} | {m['caught']} | {m['inside']} |"]
    if s: out.append(f"| strict | {s['drafts']} | {s['refused']} | {s['drafts'] - s['refused']} | {s['findings']} | {s['caught']} | {s['inside']} |")
    out += ["", "Findings by class (the arm). Caught: a refused span touches the finding, one character either side (a bare \"3\" is refused at the blank after it); inside: no slack.", "",
            "| finding | gate v2 findings | caught | inside |", "|---|---|---|---|"]
    for k, why in FINDINGS:
        if k in m["by_class"]: c = m["by_class"][k]; out.append(f"| {why} | {c['findings']} | {c['caught']} | {c['inside']} |")
    out.append(f"| **total** | {m['findings']} | {m['caught']} | {m['inside']} |")
    out += ["", "In families:", "", "| family | findings | caught |", "|---|---|---|"]
    for k in dict.fromkeys(FAMILIES[c] for c, _ in FINDINGS):
        if k in m["by_family"]: c = m["by_family"][k]; out.append(f"| {k} | {c['findings']} | {c['caught']} |")
    accepted = [d for d in results["identifiers"]["drafts"] if not d["refused"]]
    if accepted:
        out += ["", f"The {len(accepted)} drafts the grammar accepts:", ""]
        for d in accepted:
            out.append(f"- seed {d['seed']} {d['exercise']} turn {d['turn']}: " + "; ".join(f"{f['cls']} (`{f['text']}`)" for f in d["findings"]))
    out += ["", "Gate v2 keeps reading every answer: the findings the grammar cannot see (spelled-out numbers, a unit that contradicts the rendered one, sign words, a unit in a table cell) "
            "are still found, and the regeneration is still asked for.", ""]
    return "\n".join(out)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline check of the gate v3 grammar on the stored gate v2 development runs.")
    ap.add_argument("runs", nargs="?", default=RUNS, help="stored gate v2 runs, seed-N/exNN_name-data/ (default bench/runs/decision/v2)")
    ap.add_argument("--json", action="store_true", help="print every record as JSON instead of the Markdown report")
    ap.add_argument("--no-strict", action="store_true", help="skip the run of the strict grammar (no identifiers)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    turns = load_turns(args.runs)
    results = {"identifiers": check(turns, idents=True)}
    if not args.no_strict: results["strict"] = check(turns, idents=False)
    if args.json: json.dump({"runs": args.runs, **results}, sys.stdout, ensure_ascii=False, indent=1)
    else: print(markdown(args.runs, results))
    return 0

if __name__ == "__main__":
    sys.exit(main())
