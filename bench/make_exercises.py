#!/usr/bin/env python
"""Exercise generator of the Apothicaire benchmark: 25 synthetic DMPK exercises with ground truth.

Every exercise is a single-subject concentration-time profile simulated by Caladrius (`model_simulate`
over MCP) with proportional noise from a fixed seed. The ground truth of the NCA questions is the
Caladrius `nca_run` answer on the written CSV (the oracle: exactly what the agent can obtain with the
same arguments); the simulation parameters are the truth of fit questions. All data are synthetic and
public. Deterministic: same seed, same engine => byte-identical files.

  python bench/make_exercises.py [out_dir]        (default bench/exercises/; needs caladrius-mcp built)

bench/exercises/<id>/data.csv   header `time (h),conc (ng/mL)` (units in the header), 8-12 rows
bench/exercises/<id>/meta.json  model, parameters, dose, route, units, noise, BLQ, ground truth
"""
import json, math, os, random, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import apothicaire  # noqa: E402

SEED = 20261009
METHODS = ("linear", "lin_up_log_down")
OUT = os.path.join(HERE, "exercises")

# (family, model id, dose unit, concentration unit, time unit, BLQ)
# The mix: pk1 iv_bolus x4, iv_infusion x3, oral_1 x5, oral_1_lag x3, oral_0 x3; pk2 iv_bolus x4, oral_1 x3 (25).
# Doses in mg and ug, concentrations in ng/mL and mg/L, times in h (and min for a few).
PLAN = [
    ("iv_bolus",     "pk1.iv_bolus",     "mg", "mg/L",  "h",   False),
    ("oral_1",       "pk1.oral_1",       "mg", "ng/mL", "h",   False),
    ("pk2_iv_bolus", "pk2.iv_bolus",     "mg", "mg/L",  "h",   False),
    ("oral_1_lag",   "pk1.oral_1_lag",   "mg", "ng/mL", "h",   False),
    ("iv_infusion",  "pk1.iv_infusion",  "mg", "mg/L",  "h",   False),
    ("oral_0",       "pk1.oral_0",       "mg", "ng/mL", "h",   False),
    ("iv_bolus",     "pk1.iv_bolus",     "ug", "ng/mL", "h",   True),
    ("oral_1",       "pk1.oral_1",       "ug", "ng/mL", "min", False),
    ("pk2_oral_1",   "pk2.oral_1",       "mg", "ng/mL", "h",   False),
    ("oral_1_lag",   "pk1.oral_1_lag",   "mg", "mg/L",  "h",   False),
    ("pk2_iv_bolus", "pk2.iv_bolus",     "ug", "ng/mL", "h",   False),
    ("iv_infusion",  "pk1.iv_infusion",  "ug", "ng/mL", "min", False),
    ("oral_1",       "pk1.oral_1",       "mg", "ng/mL", "h",   True),
    ("iv_bolus",     "pk1.iv_bolus",     "mg", "ng/mL", "h",   False),
    ("oral_0",       "pk1.oral_0",       "mg", "mg/L",  "h",   False),
    ("pk2_oral_1",   "pk2.oral_1",       "ug", "ng/mL", "h",   False),
    ("oral_1",       "pk1.oral_1",       "mg", "mg/L",  "h",   False),
    ("pk2_iv_bolus", "pk2.iv_bolus",     "mg", "ng/mL", "min", False),
    ("oral_1_lag",   "pk1.oral_1_lag",   "ug", "ng/mL", "h",   False),
    ("iv_infusion",  "pk1.iv_infusion",  "mg", "ng/mL", "h",   False),
    ("oral_0",       "pk1.oral_0",       "ug", "ng/mL", "h",   False),
    ("pk2_oral_1",   "pk2.oral_1",       "mg", "mg/L",  "h",   False),
    ("iv_bolus",     "pk1.iv_bolus",     "mg", "ng/mL", "min", False),
    ("pk2_iv_bolus", "pk2.iv_bolus",     "mg", "ng/mL", "h",   False),
    ("oral_1",       "pk1.oral_1",       "mg", "ng/mL", "h",   False),
]
assert len(PLAN) == 25

# Simulating with the dose in `dose unit` and volumes in L gives concentrations in dose unit/L; this is the
# factor to the concentration unit written in the CSV (1 mg/L = 1000 ng/mL, 1 ug/L = 1 ng/mL).
CONC_FACTOR = {("mg", "mg/L"): 1, ("mg", "ng/mL"): 1000, ("ug", "ng/mL"): 1}
TIME_SCALE = {"h": 1, "min": 60}
DOSES = {"mg": [50, 100, 150, 200, 250, 300, 400, 500], "ug": [500, 800, 1000, 2000, 2500, 5000]}
CLIP_SD = 2.0

def sig(x, n=3):
    return float(f"{x:.{n}g}") if x else 0.0

def beta_alpha(cl, vc, q, vp):
    k10, k12, k21 = cl / vc, q / vc, q / vp
    s = k10 + k12 + k21
    r = math.sqrt(s * s - 4 * k10 * k21)
    return (s - r) / 2, (s + r) / 2

# ---------------------------------------------------------------- parameters and sampling times
def draw_parameters(family, rng):
    """Simulation parameters (h, L, clearance in L/h): returns (params, terminal half-life in h, early time scale in h)."""
    if family.startswith("pk2"):
        while True:
            vc, vp = sig(rng.uniform(8, 40)), sig(rng.uniform(15, 70))
            q, cl = sig(rng.uniform(3, 15)), sig(rng.uniform(2, 9))
            beta, alpha = beta_alpha(cl, vc, q, vp)
            th = math.log(2) / beta
            if 4 <= th <= 20 and alpha > 4 * beta: break
        params = {"cl": cl, "vc": vc, "q": q, "vp": vp}
        early = math.log(2) / alpha
    else:
        th = rng.uniform(2.5, 14)
        v = sig(rng.uniform(15, 150)); cl = sig(math.log(2) / th * v)
        params = {"cl": cl, "v": v}
        th = math.log(2) / (cl / v); early = th / 2
    base = family.replace("pk2_", "")
    if base.startswith("oral_1"): params["ka"] = sig(max(0.7, rng.uniform(3, 6) * math.log(2) / th), 2)
    if base == "oral_1_lag": params["tlag"] = sig(rng.choice([0.25, 0.5, 0.75, 1.0]), 2)
    if base == "oral_0": params["dur"] = sig(rng.choice([1.0, 1.5, 2.0, 3.0]), 2)
    if base == "iv_infusion": params["dur"] = sig(rng.choice([0.5, 1.0, 1.5, 2.0]), 2)
    return params, th, early

def sample_times(family, params, th, early, n, tscale, blq):
    """The sampling times in the CSV time unit, 2 significant digits, 8-12 of them: geometric from the
    early phase to 5 terminal half-lives (7 when BLQ values are wanted), plus a leading 0 for oral and
    infusion profiles, plus the end of the infusion."""
    t_end = (7 if blq else 5) * th
    base = family.replace("pk2_", "")
    if base.startswith("oral_1"): first = 0.1 / params["ka"] + params.get("tlag", 0) / 2
    elif base == "oral_0": first = params["dur"] / 4
    elif base == "iv_infusion": first = params["dur"] / 3
    else: first = early / 2
    first = max(first, t_end / 200)
    lead0 = base.startswith("oral") or base == "iv_infusion"
    m = n - (1 if lead0 else 0)
    ratio = (t_end / first) ** (1 / (m - 1))
    ts = [first * ratio ** i for i in range(m)]
    if base == "iv_infusion": ts[min(range(m), key=lambda i: abs(ts[i] - params["dur"]))] = params["dur"]
    out = sorted({sig(t * tscale, 2) for t in ts} | ({0.0} if lead0 else set()))
    return out

# ---------------------------------------------------------------- building one exercise
def route_of(family, params, tscale):
    if family in ("iv_bolus", "pk2_iv_bolus"): return "iv_bolus"
    if family == "iv_infusion": return {"iv_infusion": {"duration": sig(params["dur"] * tscale, 3)}}
    return "extravascular"

def build(index, call, plan_row):
    """The simulated part of an exercise (needs the engine for model_simulate): (meta without ground truth, CSV text)."""
    family, model, dose_unit, conc_unit, time_unit, blq = plan_row
    rng = random.Random(SEED * 100 + index)
    params, th, early = draw_parameters(family, rng)
    dose = rng.choice(DOSES[dose_unit]); tscale = TIME_SCALE[time_unit]
    n = rng.randint(8, 12); n = max(n, 11) if blq else n; cv = rng.choice([0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
    times = sample_times(family, params, th, early, n, tscale, blq)
    ok, text = call("model_simulate", {"model": model, "dose": dose, "params": params,
                                       "times": [t / tscale for t in times]})
    if not ok: raise RuntimeError(f"model_simulate failed for exercise {index}: {text}")
    clean = json.loads(text)["conc"]                     # dose unit / L
    factor = CONC_FACTOR[(dose_unit, conc_unit)]
    noisy = []
    for c in clean:
        z = max(-CLIP_SD, min(CLIP_SD, rng.gauss(0, 1)))
        noisy.append(c * factor * (1 + cv * z) if c > 0 else 0.0)
    lloq, n_blq = None, 0
    if blq:
        lloq = sig(0.03 * max(noisy), 2)
        for i, c in enumerate(noisy):
            if i > 0 and c < lloq: noisy[i] = 0.0; n_blq += 1
        if n_blq < 1: raise RuntimeError(f"exercise {index}: no BLQ value was produced")
    fmt = lambda x: f"{x:.4g}"
    rows = [f"{fmt(t)},{fmt(c)}" for t, c in zip(times, noisy)]
    if any("e" in r for r in rows): raise RuntimeError(f"exercise {index}: exponent in the CSV")
    csv = f"time ({time_unit}),conc ({conc_unit})\n" + "\n".join(rows) + "\n"
    meta = {
        "id": f"ex{index:02d}_{family}", "index": index, "family": family, "model": model,
        "route": route_of(family, params, tscale), "dose": {"amount": dose, "unit": dose_unit},
        "units": {"time": time_unit, "conc": conc_unit}, "n_points": len(times),
        "noise": {"type": "proportional", "cv": cv, "distribution": "gaussian, clipped at +-2 sd",
                  "seed": SEED * 100 + index},
        "blq": None if lloq is None else {"lloq": lloq, "unit": conc_unit, "n_blq": n_blq, "written_as": 0},
        "simulation": {"parameters": params,
                       "parameter_units": "times and rates in h, volumes in L, clearances in L/h, dose in the dose unit",
                       "time_scale_to_csv": tscale, "conc_factor_to_csv": factor,
                       "terminal_half_life_h": th},
    }
    return meta, csv

def tool_arguments(meta, csv, units=True):
    """The exact tool arguments of the oracle (and of a correct agent): (data_import arguments, nca_run arguments of a method).
    units=False: the dose amount alone, no options.units (CL and V in dose unit/...), the convention of decision/exercises/."""
    cols = [{"name": "time", "unit": meta["units"]["time"]}, {"name": "conc", "unit": meta["units"]["conc"]}]
    imp = {"name": meta["id"], "csv": csv, "columns": cols}
    # options.units as the agent's client fills them from the worksheet and the dose unit (T-059): CL and V in L/time and L.
    units = units and apothicaire.nca_units({"time": meta["units"]["time"], "conc": meta["units"]["conc"]}, meta["dose"]["unit"])
    nca = lambda method: {"dose": meta["dose"]["amount"], "route": meta["route"],
                          "options": {"auc_method": method, **({"units": units} if units else {})}}
    return imp, nca

def run_oracle(call, meta, csv, methods=METHODS, units=True):
    """Ground truth NCA: data_import + nca_run on the CSV, with the units the agent's client sends. Each parameter carries
    the unit label the agent is shown."""
    imp, nca = tool_arguments(meta, csv, units=units)
    ok, text = call("data_import", imp)
    if not ok: raise RuntimeError(f"data_import failed for {meta['id']}: {text}")
    ws = json.loads(text)["worksheet"]
    roles = {c["role"]: c.get("unit") for c in ws["columns"]}
    with_units = units
    units = {"time": roles.get("time"), "conc": roles.get("concentration"), "dose": roles.get("dose"),
             "derived": ws["derived_units"]}
    sent = nca(METHODS[0])["options"].get("units")
    if with_units and sent != apothicaire.nca_units(units, meta["dose"]["unit"]):
        raise RuntimeError(f"{meta['id']}: the oracle's options.units differ from what the agent's client would send")
    out = {}
    for method in methods:
        ok, text = call("nca_run", {"worksheet": ws["id"], **nca(method)})
        if not ok: raise RuntimeError(f"nca_run failed for {meta['id']}: {text}")
        subj = json.loads(text)["result"]["subjects"][0]
        if "ok" not in subj["outcome"]: raise RuntimeError(f"{meta['id']}: NCA error {subj['outcome']}")
        okk = subj["outcome"]["ok"]; params, nc = {}, {}
        if not any(p["name"] == "half.life" and "value" in p["value"] for p in okk["parameters"]):
            raise RuntimeError(f"{meta['id']}: Caladrius cannot compute the half-life; change the sampling")
        for p in okk["parameters"]:
            v = p["value"]
            if "value" in v:                       # the engine's unit when it reports one, as the agent's digest shows it
                unit = p["unit"] if p.get("unit") is not None else apothicaire.param_unit(p["name"], units)
                params[p["name"]] = {"value": v["value"], "unit": unit}
            else: nc[p["name"]] = v["not_calculated"]
        sel = [c for c in okk["lambda_z_candidates"] if c.get("selected")]
        out[method] = {"nca_run_arguments": nca(method), "parameters": params, "not_calculated": nc,
                       "not_calculated_messages": subj.get("not_calculated_messages", {}),
                       "flags": okk["flags"], "flag_messages": subj.get("flag_messages", []),
                       "lambda_z_regression": sel[0] if sel else None}
    return {"data_import_columns": imp["columns"], "worksheet_derived_units": ws["derived_units"],
            "worksheet_unit_warnings": ws.get("unit_warnings", []), "nca": out}

def generate(out_dir=OUT, mcp_bin=None):
    """Writes the 25 exercises into out_dir (emptied first). Returns the ids."""
    client = apothicaire.MCPClient([mcp_bin or apothicaire.MCP_BIN])
    if os.path.isdir(out_dir): shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    ids = []
    try:
        for i, row in enumerate(PLAN, start=1):
            meta, csv = build(i, client.call, row)
            truth = run_oracle(client.call, meta, csv)
            meta["ground_truth"] = {**truth, "fit_parameters": meta["simulation"]["parameters"]}
            d = os.path.join(out_dir, meta["id"]); os.makedirs(d)
            with open(os.path.join(d, "data.csv"), "w", encoding="utf-8", newline="\n") as f: f.write(csv)
            with open(os.path.join(d, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1); f.write("\n")
            ids.append(meta["id"])
    finally:
        client.close()
    return ids

def load(ex_dir):
    """(meta, CSV text) of a generated exercise folder."""
    with open(os.path.join(ex_dir, "meta.json"), encoding="utf-8") as f: meta = json.load(f)
    with open(os.path.join(ex_dir, "data.csv"), encoding="utf-8") as f: csv = f.read()
    return meta, csv

def list_exercises(root=OUT):
    return [os.path.join(root, d) for d in sorted(os.listdir(root)) if os.path.isfile(os.path.join(root, d, "meta.json"))]

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUT
    print(f"wrote {len(generate(out))} exercises to {out}")
