#!/usr/bin/env python
"""The reading of the grammar arm (gate v3): GRAMMAR_ARM.md §4 and §5 as code.

The thresholds below are those of the pre-registration (bench/GRAMMAR_ARM.md and the entry of 2026-10-23 in bench/frozen/LEDGER.md),
written before this file existed; tests/test_grammar_arm.py checks them against that text. If this code and that text ever disagree,
the text wins (GRAMMAR_ARM.md §4).

`bench/run_frozen.py analyse` calls `read` when configuration v3 is among the runs and writes `render` at the top of ANALYSIS.md, next
to the usual endpoints. Nothing here runs a model or a server. It reads run folders: the turn records, through
run_frozen.config_section, and `<id>-data/gate.jsonl`, where the agent keeps, for every turn, the findings left in the answer shown
and, for gate v3, what the regeneration was sent and what came back.

  read(configs, where, runs, infos)   the measures of v1, v2 and v3 side by side, what the regenerations say about the grammar, the
                                      validity of the run, the kill conditions, the five thresholds and the reading (a dict for
                                      analysis.json)
  judge(m, enforcement, invalid)      the pure decision of §4 and §5 on the measures of v3
  render(arm)                         the Markdown lines of ANALYSIS.md
"""
import collections, glob, json, os, statistics

ARM = "v3"
LLAMA_BUILD = "b11700-23f7aabc1"            # GRAMMAR_ARM.md §3: the llama-server build the run must name in run.json
SEEDS = [1, 2, 3]
EXERCISES = 25
TURNS = 600

# GRAMMAR_ARM.md §4, the success column: five thresholds, of which the first four are "the four effects" of §5
FREE_DIGITS_MAX = 0
UNVERIFIABLE_MAX = 3                        # exercises with an unverifiable quantity shown
CORRECT_MIN = 576                           # turns CORRECT
MEDIAN_MAX_S = 9.0                          # median time per turn
REGENERATIONS_MAX = 50
# GRAMMAR_ARM.md §4, the kill column: four conditions
KILL_CORRECT_BELOW = 562
KILL_MEDIAN_ABOVE_S = 13.5
KILL_LOOP_ABSTAINED_ABOVE = 12              # 2 % of the 600 turns
# (the fourth kill condition is the server not enforcing the grammar: grammar_facts, `enforcement` of judge)

# GRAMMAR_ARM.md §5, the readings
NO_READING = "no reading: the run is invalid"
KILLED = "killed"
SUCCESS = "success"
COUNT_UNCHANGED = "the grammar does what it is for; the regeneration count is unchanged"
NO_DECISION = "no decision"


# ---------------------------------------------------------------- the records
def is_free_digit(f):
    """GRAMMAR_ARM.md §4: a finding of gate v2 that is a number typed by hand which is not the user's (`bare_number`) or a digit next to
    a reference (`adjacent_to_reference`, reason "digit after a reference")."""
    return f.get("kind") == "bare_number" or (f.get("kind") == "adjacent_to_reference" and str(f.get("reason", "")).startswith("digit after"))

def gate_records(base, config, seeds):
    """Every line of every <id>-data/gate.jsonl of a configuration, with its seed and exercise: one line per turn that went through the
    gate, `findings` being what the answer shown still carries."""
    out = []
    for s in seeds:
        for p in sorted(glob.glob(os.path.join(base, config, f"seed-{s}", "*-data", "gate.jsonl"))):
            ex = os.path.basename(os.path.dirname(p))[:-len("-data")]
            with open(p, encoding="utf-8") as f:
                out += [{**json.loads(line), "seed": s, "exercise": ex} for line in f if line.strip()]
    return out

def free_digits(records):
    return sum(is_free_digit(f) for r in records for f in r.get("findings") or [])

def findings_left(records):
    """{kind: count} of the findings of gate v2 still in the answers shown."""
    return dict(sorted(collections.Counter(f.get("kind") for r in records for f in r.get("findings") or []).items()))

def _at(r): return {"seed": r.get("seed"), "exercise": r.get("exercise"), "turn": r.get("turn")}
def _median(xs): return statistics.median(xs) if xs else None
def _max(xs): return max(xs) if xs else None

def grammar_facts(records):
    """What the regenerations of a gate v3 run say about the grammar: were they all sent one (validity), and did the server enforce it
    (the fourth kill condition: an error that mentions the grammar, or a text that breaks the grammar it was sent)."""
    reg = [r for r in records if r.get("regenerated")]
    stat = lambda r: r.get("regen_stats") or {}
    gram = lambda r: r.get("grammar") or {}
    errors = [(r, str(stat(r)["error"])) for r in reg if "error" in stat(r)]
    conf = [(r, gram(r)["conformance"]) for r in reg if gram(r).get("conformance")]
    sent = [gram(r) for r in reg if gram(r).get("sent") is True]
    return {
        "records": len(records),
        "other_versions": sum(1 for r in records if r.get("version") != ARM),
        "regenerations": len(reg),
        "sent": len(sent),
        "not_sent": [{**_at(r), "error": gram(r).get("error")} for r in reg if gram(r).get("sent") is not True],
        "server_errors": [{**_at(r), "error": e[:300]} for r, e in errors],
        "server_errors_mentioning_the_grammar": sum(1 for _, e in errors if "grammar" in e.lower()),
        "conformance_recorded": len(conf),
        "accepted": sum(1 for _, c in conf if c.get("accepted")),
        "cut_at_max_tokens": sum(1 for _, c in conf if c.get("finish_reason") == "length"),
        "violations": [{**_at(r), "refused_at": c.get("refused_at"), "accepted": c.get("accepted"), "finish_reason": c.get("finish_reason"),
                        "text": (gram(r).get("text") or "")[:1200]} for r, c in conf if c.get("violation")],
        "kept": dict(collections.Counter(str(r.get("kept")) for r in reg)),
        "regeneration_call_median_s": _median([stat(r)["wall_s"] for r in reg if stat(r).get("wall_s") is not None]),
        "rules": [_median([g["rules"] for g in sent if "rules" in g]), _max([g["rules"] for g in sent if "rules" in g])],
        "bytes": [_median([g["bytes"] for g in sent if "bytes" in g]), _max([g["bytes"] for g in sent if "bytes" in g])],
        "build_ms": [_median([g["build_ms"] for g in sent if "build_ms" in g]), _max([g["build_ms"] for g in sent if "build_ms" in g])],
    }

def enforcement_failures(facts):
    """The fourth kill condition of §4, as sentences (empty: nothing found)."""
    out = []
    if facts["server_errors_mentioning_the_grammar"]:
        out.append(f"{facts['server_errors_mentioning_the_grammar']} regeneration(s) got a server error that mentions the grammar")
    if facts["violations"]:
        out.append(f"{len(facts['violations'])} regeneration(s) returned a text that breaks the grammar it was sent")
    return out


# ---------------------------------------------------------------- the measures
def measures(section, records, config):
    """The numbers of §4 for one configuration, from run_frozen.config_section and its gate.jsonl records (free digits are only
    defined for the typed gates, v2 and v3)."""
    o = section["outcomes"]
    typed = config in ("v2", ARM)
    return {"exercises": section["exercises"], "passed": section["exercises"] - section["failed"]["failed"],
            "turns": section["turns"], "turns_correct": section["turns_correct"],
            "unverifiable_exercises": len(section["unverified_shown_ids"]), "regenerations": section["regenerations"],
            "median_s": section["wall_s_median"], "p95_s": section["wall_s_p95"], "loop": o["LOOP"], "abstained": o["ABSTAINED"],
            "free_digits": free_digits(records) if typed else None, "findings_left": findings_left(records) if typed else None}

def invalid_reasons(section, infos, facts):
    """GRAMMAR_ARM.md §4, Validity: all 600 turns recorded, the llama.cpp build of §3, and a grammar sent with every regeneration."""
    out = []
    if section["seeds"] != SEEDS: out.append(f"seeds {section['seeds']} instead of {SEEDS}")
    missing = sorted(i for i, p in section["per_exercise"].items() if p["missing_seeds"])
    if missing: out.append(f"{len(missing)} exercise(s) have no record on some seed ({', '.join(missing[:5])}{', ...' if len(missing) > 5 else ''})")
    if section["turns"] != TURNS: out.append(f"{section['turns']} turns instead of {TURNS}")
    wrong = sorted({i.get("model", "?") for i in infos if LLAMA_BUILD not in i.get("model", "")})
    if wrong: out.append(f"run.json does not name llama-server {LLAMA_BUILD}: {'; '.join(wrong)}")
    if facts["other_versions"]: out.append(f"{facts['other_versions']} gate record(s) are not gate v3")
    if facts["not_sent"]: out.append(f"{len(facts['not_sent'])} regeneration(s) were not sent a grammar")
    return out


# ---------------------------------------------------------------- the decision
def judge(m, enforcement, invalid):
    """GRAMMAR_ARM.md §4 and §5 on the measures `m` of gate v3. `enforcement`: sentences from enforcement_failures; `invalid`: the reasons
    the run is not valid. Returns every value the reading rests on, and the reading."""
    loop_abstained = m["loop"] + m["abstained"]
    median = m["median_s"]
    kill = []
    if m["turns_correct"] < KILL_CORRECT_BELOW: kill.append(f"{m['turns_correct']} / {m['turns']} turns CORRECT, fewer than {KILL_CORRECT_BELOW} / {TURNS}")
    if median is not None and median > KILL_MEDIAN_ABOVE_S: kill.append(f"median {median} s per turn, more than {KILL_MEDIAN_ABOVE_S} s")
    if loop_abstained > KILL_LOOP_ABSTAINED_ABOVE:
        kill.append(f"{loop_abstained} LOOP + ABSTAINED turns, more than {KILL_LOOP_ABSTAINED_ABOVE} of {TURNS} (2 %)")
    if enforcement: kill.append("the server does not enforce the grammar: " + "; ".join(enforcement))
    fd = m["free_digits"]
    thresholds = [
        {"name": "free digits shown", "value": fd, "rule": f"{FREE_DIGITS_MAX}", "met": fd is not None and fd <= FREE_DIGITS_MAX, "effect": True},
        {"name": "exercises with an unverifiable quantity shown", "value": f"{m['unverifiable_exercises']} / {m['exercises']}",
         "rule": f"at most {UNVERIFIABLE_MAX} / {EXERCISES}", "met": m["unverifiable_exercises"] <= UNVERIFIABLE_MAX, "effect": True},
        {"name": "turns CORRECT", "value": f"{m['turns_correct']} / {m['turns']}", "rule": f"at least {CORRECT_MIN} / {TURNS}",
         "met": m["turns_correct"] >= CORRECT_MIN, "effect": True},
        {"name": "median time per turn", "value": None if median is None else f"{median} s", "rule": f"at most {MEDIAN_MAX_S:g} s",
         "met": median is not None and median <= MEDIAN_MAX_S, "effect": True},
        {"name": "regenerations", "value": m["regenerations"], "rule": f"at most {REGENERATIONS_MAX}", "met": m["regenerations"] <= REGENERATIONS_MAX,
         "effect": False}]
    effects = all(t["met"] for t in thresholds if t["effect"])
    regen_ok = thresholds[-1]["met"]
    reading = (NO_READING if invalid else KILLED if kill else (SUCCESS if regen_ok else COUNT_UNCHANGED) if effects else NO_DECISION)
    return {"valid": not invalid, "invalid_reasons": list(invalid), "kill": kill, "thresholds": thresholds, "four_effects_met": effects,
            "missed": [t["name"] for t in thresholds if not t["met"]], "reading": reading}


def read(configs, where, runs, infos):
    """`configs`: run_frozen's {configuration: config_section}; `where`: {configuration: the folder it was read from}; `runs`:
    {configuration: {seed: {id: record}}}; `infos`: {configuration: [run.json, ...]}. Gate v3 must be among them."""
    records = {g: gate_records(where[g], g, sorted(runs[g])) if g in ("v2", ARM) else [] for g in ("v1", "v2", ARM) if g in configs}
    arm = {"preregistration": "bench/GRAMMAR_ARM.md", "configs": {g: measures(configs[g], records[g], g) for g in records}}
    facts = grammar_facts(records[ARM])
    invalid = invalid_reasons(configs[ARM], infos.get(ARM, []), facts)
    arm["v3"] = {"facts": facts, "judgement": judge(arm["configs"][ARM], enforcement_failures(facts), invalid)}
    if "v2" in records: arm["v2"] = {"facts": grammar_facts(records["v2"])}
    return arm


# ---------------------------------------------------------------- the rendering
def _f(x, unit=""):
    if x is None: return "n/a"
    if isinstance(x, float): x = f"{x:.2f}".rstrip("0").rstrip(".")
    return f"{x}{unit}"

def _excerpt(text, at, width=40):
    if not text: return ""
    at = len(text) if at is None else at
    return text[max(0, at - width):at].replace("\n", "\\n") + "[" + (text[at:at + 1] or "end").replace("\n", "\\n") + "]" + text[at + 1:at + 1 + width].replace("\n", "\\n")

def render(arm):
    """The Markdown lines of the grammar arm: the three configurations side by side, the validity, the kill conditions, the five
    thresholds, the reading, and what the regenerations say about the grammar."""
    cfg, v3, j = arm["configs"], arm["v3"], arm["v3"]["judgement"]
    cols = [g for g in ("v1", "v2", ARM) if g in cfg]
    f3 = v3["facts"]
    L = ["## Grammar arm: gate v3 next to v1 and v2 (GRAMMAR_ARM.md §4 and §5)", "",
         "Development set, in-sample, exploratory. The thresholds were fixed before the run command existed (`bench/GRAMMAR_ARM.md`, "
         "`bench/frozen/LEDGER.md` of 2026-10-23); if this section and that text disagree, the text wins. v1 and v2 are the stored runs of the "
         "demo-gate decision, read here and not rerun.", "",
         "| Measure | " + " | ".join(cols) + " | Success | Kill |", "|---|" + "---|" * (len(cols) + 2)]
    def row(label, fn, success="", kill=""): L.append(f"| {label} | " + " | ".join(fn(cfg[g]) for g in cols) + f" | {success} | {kill} |")
    row("free digits shown", lambda m: _f(m["free_digits"]), f"{FREE_DIGITS_MAX}")
    row("exercises with an unverifiable quantity shown", lambda m: f"{m['unverifiable_exercises']} / {m['exercises']}", f"at most {UNVERIFIABLE_MAX} / {EXERCISES}")
    row("turns CORRECT", lambda m: f"{m['turns_correct']} / {m['turns']}", f"at least {CORRECT_MIN} / {TURNS}", f"fewer than {KILL_CORRECT_BELOW} / {TURNS}")
    row("regenerations", lambda m: str(m["regenerations"]), f"at most {REGENERATIONS_MAX}")
    row("median time per turn", lambda m: _f(m["median_s"], " s"), f"at most {MEDIAN_MAX_S:g} s", f"more than {KILL_MEDIAN_ABOVE_S:g} s")
    row("LOOP + ABSTAINED turns", lambda m: str(m["loop"] + m["abstained"]), "", f"more than {KILL_LOOP_ABSTAINED_ABOVE} of {TURNS}")
    L.append("| the server enforces the grammar | " + " | ".join(("n/a" if g != ARM else "yes" if not enforcement_failures(f3) else "NO") for g in cols) + " | | it does not |")
    row("exercises passed (strict rule of §6.3, descriptive)", lambda m: f"{m['passed']} / {m['exercises']}")
    row("95th percentile time per turn (descriptive)", lambda m: _f(m["p95_s"], " s"))
    L += ["", "**Validity:** " + ("valid." if j["valid"] else "INVALID, " + "; ".join(j["invalid_reasons"]) + "."),
          "**Kill conditions:** " + ("none holds." if not j["kill"] else "; ".join(j["kill"]) + "."), "",
          "| Success threshold of §4 | gate v3 | rule | met |", "|---|---|---|---|"]
    L += [f"| {t['name']} | {_f(t['value'])} | {t['rule']} | {'yes' if t['met'] else 'no'} |" for t in j["thresholds"]]
    L += ["", f"**Reading (GRAMMAR_ARM.md §5): {j['reading']}.**"
          + (f" Missed: {', '.join(j['missed'])}." if j["reading"] in (NO_DECISION, COUNT_UNCHANGED) and j["missed"] else ""), ""]
    L += ["### What the regenerations say about the grammar (gate v3)", "", "| | |", "|---|---|",
          f"| gate records / of which not gate v3 | {f3['records']} / {f3['other_versions']} |",
          f"| regenerations / sent with a grammar | {f3['regenerations']} / {f3['sent']} |",
          f"| server errors (the first answer is kept) / of which mention the grammar | {len(f3['server_errors'])} / {f3['server_errors_mentioning_the_grammar']} |",
          f"| text obeyed the grammar (accepted) | {f3['accepted']} |",
          f"| text cut at max_tokens (only a valid prefix is owed) | {f3['cut_at_max_tokens']} |",
          f"| violations (a refused character, or a stop where the grammar cannot end) | {len(f3['violations'])} |",
          f"| kept | {', '.join(f'{k}: {n}' for k, n in sorted(f3['kept'].items())) or 'n/a'} |",
          f"| regeneration call, median wall time | {_f(f3['regeneration_call_median_s'], ' s')}"
          + (f" (v2: {_f(arm['v2']['facts']['regeneration_call_median_s'], ' s')})" if "v2" in arm else "") + " |",
          f"| grammar, rules / bytes / build ms: median (largest) | {_f(f3['rules'][0])} ({_f(f3['rules'][1])}) / {_f(f3['bytes'][0])} ({_f(f3['bytes'][1])}) / "
          f"{_f(f3['build_ms'][0])} ({_f(f3['build_ms'][1])}) |", ""]
    for kind, items in (("Violations", f3["violations"]), ("Server errors", f3["server_errors"]), ("Regenerations not sent a grammar", f3["not_sent"])):
        if items:
            L += [f"{kind}:", ""]
            for x in items[:10]:
                tail = f" refused at character {x['refused_at']}: `{_excerpt(x.get('text'), x['refused_at'])}`" if "refused_at" in x else f" {x.get('error')}"
                L.append(f"- seed {x['seed']} {x['exercise']} turn {x['turn']}:{tail}")
            if len(items) > 10: L.append(f"- ... and {len(items) - 10} more")
            L.append("")
    kinds = sorted({k for g in ("v2", ARM) if g in cfg for k in cfg[g]["findings_left"]})
    if kinds:
        L += ["### Findings of gate v2 left in the answers shown, by kind", "", "| kind | " + " | ".join(g for g in ("v2", ARM) if g in cfg) + " |",
              "|---|" + "---|" * len([g for g in ("v2", ARM) if g in cfg])]
        for k in kinds: L.append(f"| {k} | " + " | ".join(str(cfg[g]["findings_left"].get(k, 0)) for g in ("v2", ARM) if g in cfg) + " |")
        L.append("")
    for other, p in arm.get("paired", {}).items():
        L += [f"- {ARM} against {other} (exact McNemar on the exercises passed, descriptive): both pass {p['both_pass']}, neither {p['neither_passes']}, "
              f"only {other} {len(p['only_c1_passes'])}, only {ARM} {len(p['only_c2_passes'])}; p = {p['mcnemar_p']:.3g}"]
    if arm.get("paired"): L.append("")
    L += ["The `caladrius-mcp` hash is not recorded in the run folder: check it with `sha256sum` before the run (GRAMMAR_ARM.md §3) and write it in the ledger entry "
          "that follows the run.", ""]
    return L
