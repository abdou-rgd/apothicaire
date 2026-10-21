#!/usr/bin/env python
"""Mutation suite of the frozen-set rubric (FROZEN_SET.md §7, T-066): no model, no engine, only the gold.

For every exercise and every turn of its script, a canonical correct answer is built from the gold (`canonical`), with the
legitimate variants of §7 (`variants`: three significant digits, a decimal comma, a unit written another way, a sentence of
explanation, a Markdown table), and the mutations of §7 (`mutations`: sign, negation, contradiction, wrong label, stale
result, unit, unlabelled, dump, reversed verdict, a number labelled with the not-calculated parameter). The pass criterion:
every canonical answer and variant scores CORRECT with `score.rubric_turn`, every mutation scores WRONG.

  python bench/mutations.py [exercises_dir ...]      (default bench/exercises/; prints the kill rate and every failure)
"""
import json, os, sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import gate  # noqa: E402
from bench import make_exercises as mk, scripts, score  # noqa: E402

def num(x, digits=6, comma=False):
    """A value the way the digest shows it (6 significant digits, no trailing .0), or rounded half-up from the decimal
    the digest prints (2.295 -> 2.30 at 3 digits, as a reader would round it), optionally with a decimal comma."""
    shown = Decimal(f"{x:.6g}")
    r = gate.round_sig(shown, digits, gate.ROUND_HALF_UP) if digits < 6 else shown
    t = format(r.normalize(), "f") if r != r.to_integral() or abs(r) < 1e15 else str(r)
    if "." in t and digits < 6:
        lead = len(t.lstrip("-").replace(".", "").lstrip("0"))
        if lead < digits: t += "0" * (digits - lead)              # keep the zeros a reader writes: 2.30, not 2.3
    return t.replace(".", ",") if comma else t

def unit_of(item):
    u = item.get("unit") or ""
    return {"ug": "µg"}.get(u, u)

ROUTE_FR = {"oral": "voie orale", "iv_bolus": "bolus intraveineux", "iv_infusion": "perfusion intraveineuse"}
NOT_CALC = {"c0": "C0", "tlag": "Tlag"}

def _items(turn, meta):
    items, alts = score.rubric_items(turn, meta)
    return items, [a[0] for a in alts]

def _line(label, value, unit, digits=6, comma=False):
    return f"{label} = {num(value, digits, comma)} {unit}".rstrip()

def canonical(turn, meta, digits=6, comma=False, table=False, unit_map=None):
    """A correct answer to one turn, from the gold alone."""
    kind = turn["kind"]; um = unit_map or (lambda u: u)
    items, alts = _items(turn, meta)
    rows = []
    if kind == "recall":
        k = scripts.kind_of(meta)
        return (f"Dose : {num(meta['dose']['amount'], digits, comma)} {unit_of(meta['dose'])} ; voie : {ROUTE_FR[k]} ; "
                "méthode d'AUC : linéaire (trapèzes linéaires).")
    if kind == "not_available":
        what = NOT_CALC[turn["expect"]["not_calculated_parameter"]]
        return f"Caladrius n'a pas calculé {what} pour cette voie d'administration : le paramètre n'est pas disponible."
    if kind == "compare":
        lud = next(i for i in items if i["method"] == "lin_up_log_down")
        d, p = alts
        rows = [("AUC(0-tlast) lin-up/log-down", lud["value"], um(unit_of(lud))),
                ("Différence", d["value"], um(unit_of(d))), ("Pourcentage", p["value"], "%")]
    else:
        rows = [(i["label"], i["value"], um(unit_of(i))) for i in items]
    if table:
        out = ["| Paramètre | Valeur | Unité |", "|---|---|---|"] + [f"| {l} | {num(v, digits, comma)} | {u} |" for l, v, u in rows]
    else:
        out = [_line(l, v, u, digits, comma) for l, v, u in rows]
    if kind == "half_life":
        pext = scripts.truth_value(meta, "aucpext.obs")
        out.append("C'est acceptable." if pext <= score.VERDICT_THRESHOLD else "Ce n'est pas acceptable.")
    return "\n".join(out)

def _swap_unit(u):
    """Another spelling of the same unit (an exact rewriting), or None."""
    for a, b in (("h·mg/L", "mg·h/L"), ("h*mg/L", "mg*h/L"), ("h·ng/mL", "ng·h/mL"), ("h*ng/mL", "ng*h/mL"), ("mg/L", "µg/mL"),
                 ("1/h", "h⁻¹"), ("1/min", "min⁻¹")):
        if a in u: return u.replace(a, b)
    return None

def variants(turn, meta):
    """[(name, answer)] legitimate answers that must score CORRECT."""
    out = [("canonical", canonical(turn, meta)), ("three digits", canonical(turn, meta, digits=3)),
           ("decimal comma", canonical(turn, meta, comma=True)),
           ("explanation", "D'après le résultat de Caladrius :\n" + canonical(turn, meta) + "\nCes valeurs viennent de l'analyse non compartimentale.")]
    if turn["kind"] not in ("recall", "not_available"):
        out.append(("markdown table", canonical(turn, meta, table=True)))
        alt = canonical(turn, meta, unit_map=lambda u: _swap_unit(u) or u)
        if alt != out[0][1]: out.append(("unit rewritten", alt))
    return out

def _value_text(item, digits=6):
    return num(item["value"], digits)

def mutations(turn, meta):
    """[(name, answer)] answers that must score WRONG (FROZEN_SET.md §7)."""
    kind = turn["kind"]; items, alts = _items(turn, meta); base = canonical(turn, meta)
    out = []
    if kind in ("recall", "not_available"):
        if kind == "recall":
            amt = meta["dose"]["amount"]
            out += [("dose without unit", base.replace(f" {unit_of(meta['dose'])} ;", " ;")),
                    ("wrong dose", base.replace(f"Dose : {num(amt)}", f"Dose : {num(amt * 2)}")),
                    ("negated dose", base.replace("Dose : ", "La dose n'était pas ")),
                    ("other route", base.replace("méthode", "ou bien en perfusion ; méthode") if scripts.kind_of(meta) != "iv_infusion"
                     else base.replace("méthode", "ou bien par voie orale ; méthode"))]
        else:
            what = NOT_CALC[turn["expect"]["not_calculated_parameter"]]
            out += [("not available: value", f"{what} = 12.5 {meta['units']['time' if what == 'Tlag' else 'conc']}."),
                    ("not available: value with negation", f"Caladrius ne calcule pas {what} ; {what} = 12.5 environ.")]
        return out
    first = items[0] if kind != "compare" else next(i for i in items if i["method"] == "lin_up_log_down")
    v = _value_text(first)
    legit = score._legit_values(meta)
    factor = next(f for f in (1.37, 1.53, 1.71, 1.89, 2.17, 2.63) if not any(abs(first["value"] * f - x) <= 0.01 * abs(x) for x in legit))
    out += [("sign", base.replace(f"= {v}", f"= -{v}", 1)),
            ("negation", base.replace(f"= {v}", f"n'est pas {v}", 1)),
            ("contradiction", base + f"\n{first['label'] if kind != 'compare' else 'AUC(0-tlast) lin-up/log-down'} = {num(first['value'] * factor)} {unit_of(first)} (autre valeur)"),
            ("disowned", base.replace(f"= {v}", f"= {num(first['value'] * factor)}", 1) + f"\nL'ancienne valeur, fausse, était {v}."),
            ("unit x1000", base.replace(f"= {v}", f"= {num(first['value'] * 1000)}", 1)),
            ("unlabelled", " ; ".join(num(i["value"]) for i in items + alts)),
            ]
    if first.get("unit") and first["unit"] not in ("%", ""):
        other = "ng/mL" if "mg/L" in first["unit"] else ("mg/L" if "ng/mL" in first["unit"] else ("min" if first["unit"] == "h" else "h"))
        wrong_u = first["unit"].replace("mg/L", "ng/mL") if "mg/L" in first["unit"] else (
            first["unit"].replace("ng/mL", "mg/L") if "ng/mL" in first["unit"] else other)
        out.append(("wrong unit", base.replace(f"= {v} {unit_of(first)}", f"= {v} {wrong_u}", 1)))
    if len(items) >= 2 and kind != "compare":
        a, b = items[0], items[1]
        if scripts.score._round3(a["value"]) != scripts.score._round3(b["value"]):
            out.append(("labels swapped", base.replace(f"= {_value_text(a)}", "= @A@", 1).replace(f"= {_value_text(b)}", f"= {_value_text(a)}", 1)
                        .replace("= @A@", f"= {_value_text(b)}", 1)))
    if kind == "half_life":
        out.append(("verdict reversed", base.replace("C'est acceptable.", "@@").replace("Ce n'est pas acceptable.", "C'est acceptable.")
                    .replace("@@", "Ce n'est pas acceptable.")))
        out.append(("verdict missing", "\n".join(base.split("\n")[:-1])))
    if kind != "import_nca":
        p = meta["ground_truth"]["nca"]["linear"]["parameters"]
        dump = " ; ".join(f"{k} = {num(x['value'])}" for k, x in p.items() if x["value"])
        out.append(("dump", base + "\nTous les paramètres : " + dump + (". Oui, acceptable." if kind == "half_life" else ".")))
    if kind == "compare":
        lin = scripts.truth_value(meta, "auclast")
        out.append(("stale result", base.replace(f"= {v}", f"= {num(lin)}", 1)))
        out.append(("difference missing", "\n".join(l for l in base.split("\n") if not l.startswith("Différence"))))
    return out

def run(dirs, verbose=True):
    """Runs the suite over exercise folders. Returns {"canonical": [ok, n], "mutations": [killed, n], "failures": [...]}."""
    res = {"canonical": [0, 0], "mutations": [0, 0], "failures": []}
    for d in dirs:
        meta, csv = mk.load(d)
        for turn in scripts.build_script(meta, csv):
            for name, ans in variants(turn, meta):
                r = score.rubric_turn(ans, turn, meta)
                res["canonical"][1] += 1; res["canonical"][0] += r["correct"]
                if not r["correct"]: res["failures"].append({"exercise": meta["id"], "turn": turn["kind"], "case": name, "expected": "CORRECT",
                                                            "reasons": r["reasons"], "answer": ans})
            for name, ans in mutations(turn, meta):
                r = score.rubric_turn(ans, turn, meta)
                res["mutations"][1] += 1; res["mutations"][0] += not r["correct"]
                if r["correct"]: res["failures"].append({"exercise": meta["id"], "turn": turn["kind"], "case": name, "expected": "WRONG",
                                                        "reasons": [], "answer": ans})
    if verbose:
        c, m = res["canonical"], res["mutations"]
        print(f"canonical answers and variants CORRECT: {c[0]} / {c[1]}; mutations killed (WRONG): {m[0]} / {m[1]}")
        for f in res["failures"]: print(json.dumps(f, ensure_ascii=False))
    return res

if __name__ == "__main__":
    roots = sys.argv[1:] or [mk.OUT]
    dirs = [d for r in roots for d in mk.list_exercises(r)]
    r = run(dirs)
    sys.exit(0 if not r["failures"] else 1)
