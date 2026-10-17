#!/usr/bin/env python
"""
Apothicaire v0 -- a local DMPK agent: Bonsai 2 27B (llama.cpp) + OptChat memory + Caladrius MCP tools.

The model never computes pharmacokinetic numbers: it imports the data and calls Caladrius
(caladrius-mcp, spoken over stdio as JSON-RPC 2.0 lines), then explains the results.

Built on ../optchat/optchat.py (imported, not copied): its Agent keeps the endless-chat memory
(log + summary tree + view); we add the MCP tools next to zoom/read_message.

Usage:
  python apothicaire.py chat               interactive chat (memory in agent/data/)
  python apothicaire.py say "message"      one turn
  python apothicaire.py tools              print the exposed tools and the static prompt size
Environment: APOTHICAIRE_MCP (path of caladrius-mcp), APOTHICAIRE_DATA (memory folder),
OPTCHAT_URL (llama-server, default http://127.0.0.1:18435), APOTHICAIRE_GATE (v1, the default: the number gate of
gate.py; v2: the typed rendering of gate_v2.py, see GATE_V2.md).
"""
import json, os, subprocess, sys, threading, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICINA = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(OFFICINA, "optchat"))
import optchat  # noqa: E402
sys.path.insert(0, HERE)
import gate, gate_v2  # noqa: E402
from numtext import value_text  # noqa: E402

optchat.CFG["data_dir"] = os.environ.get("APOTHICAIRE_DATA", os.path.join(HERE, "data"))

MCP_BIN = os.environ.get("APOTHICAIRE_MCP", os.path.join(
    OFFICINA, "caladrius", "target", "agent-apothicaire", "release",
    "caladrius-mcp.exe" if os.name == "nt" else "caladrius-mcp"))

# Tools exposed to the model (the 12k-token context cannot hold the 18 schemas).
EXPOSED = ["data_import", "nca_run", "analysis_get", "export_table", "analysis_compare"]
# nca_run options kept in the schema shown to the model (the full schema is ~1k tokens; the
# server still accepts every option, they are only hidden from the prompt).
NCA_OPTIONS_KEPT = ["auc_method", "start", "lambda_z", "quality"]

SYSTEM_ADDITION = """

You are Apothicaire, a DMPK assistant. Never compute pharmacokinetic numbers yourself: import the data and call Caladrius tools, then explain the results in the user's language, with units, and mention quality flags.
Caladrius workflow: data_import (CSV text in `csv`; give the units the user states in `columns`, e.g. {"name":"time","unit":"h"}) returns a worksheet id; nca_run(worksheet, dose, route, options) returns an analysis id and the parameters by PKNCA name; to redo an analysis with other options call nca_run again. Worksheets and analyses persist during the chat: reuse their ids, do not import the same data twice. NCA parameters come with their unit (aucpext.* are percentages); when the dose unit is unknown to Caladrius, CL and V are in dose unit/(...). Quote tool values verbatim and never convert units (no mg to ug, no h to min, no L/h from dose unit/...); if a unit is missing, say so. You may round a value, saying so. Never state a value that no tool returned. Differences, percentages and ratios between two results come from analysis_compare (b minus a, per parameter, with units), never from you."""

# Gate v2 (typed rendering, GATE_V2.md): the model cites tool values by reference, the client prints them.
SYSTEM_ADDITION_V2 = """

You are Apothicaire, a DMPK assistant. Never compute PK numbers yourself: import the data, call Caladrius tools, then explain the results in the user's language and mention quality flags.
Caladrius workflow: data_import (CSV text in `csv`; give the units the user states in `columns`, e.g. {"name":"time","unit":"h"}) returns a worksheet id; nca_run(worksheet, dose, route, options) returns an analysis id and the parameters by PKNCA name; rerun nca_run for other options. Worksheets and analyses persist: reuse their ids, never import data twice. Differences, percentages and ratios between two results come from analysis_compare (b minus a), never from you.
Numbers: never type a tool value, not even rounded. Cite it as {{ref.name}} ("ref" of the tool result); the client prints value and unit. E.g. {{call_3.cmax}}; subject 2: {{call_3.subject=2.cmax}}; analysis_compare: {{call_5.auclast.difference}}, .percent, .ratio, .a, .b; λz regression: {{call_3.lambda_z.adj_r_squared}}, .r_squared, .n_points; thresholds: {{call_3.thresholds.max_extrapolated_percent}} (no analysis: {{convention.max_extrapolated_percent}}). Write no unit, sign, digit or arithmetic next to a reference; the only digits you may type are the user's. If a value is missing, say Caladrius did not return it."""

_ADDITIONS = (SYSTEM_ADDITION, SYSTEM_ADDITION_V2)

def install_prompt(addition):
    """optchat.SYSTEM_PROMPT = the base prompt + one addition (whichever was installed before is removed first)."""
    base = optchat.SYSTEM_PROMPT
    for a in _ADDITIONS: base = base.replace(a, "")
    optchat.SYSTEM_PROMPT = base + addition

def gate_version_of(value=None):
    v = (value or os.environ.get("APOTHICAIRE_GATE") or "v1").strip().lower()
    if v not in ("v1", "v2"): raise ValueError(f"APOTHICAIRE_GATE must be v1 or v2, not {value!r}")
    return v

# ---------------------------------------------------------------- MCP stdio client
class MCPError(Exception): pass

class MCPClient:
    """Minimal MCP client over stdio: one JSON-RPC 2.0 message per line."""
    def __init__(self, cmd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  encoding="utf-8", bufsize=1)
        self._id = 0; self._lock = threading.Lock()
        init = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "apothicaire", "version": "0"}})
        self.server_info = init.get("serverInfo", {}); self.instructions = init.get("instructions", "")
        self.notify("notifications/initialized")
        self.tools = {t["name"]: t for t in self.request("tools/list").get("tools", [])}

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n"); self.p.stdin.flush()

    def notify(self, method, params=None):
        with self._lock: self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def request(self, method, params=None):
        with self._lock:
            self._id += 1; rid = self._id
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
            while True:
                line = self.p.stdout.readline()
                if not line: raise MCPError("caladrius-mcp closed its output")
                msg = json.loads(line)
                if msg.get("id") != rid: continue            # notifications or stray answers
                if "error" in msg: raise MCPError(f"{msg['error'].get('code')}: {msg['error'].get('message')}")
                return msg["result"]

    def call_full(self, name, args):
        """Returns (ok, text, structuredContent or None). A tool error (isError) is returned as text, not raised."""
        res = self.request("tools/call", {"name": name, "arguments": args})
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return (not res.get("isError", False)), text, res.get("structuredContent")

    def call(self, name, args):
        """Returns (ok, text)."""
        ok, text, _ = self.call_full(name, args)
        return ok, text

    def output_schemas(self):
        """tool name -> outputSchema, for the tools that publish one (gate v2 checks the cited paths against it)."""
        return {n: t["outputSchema"] for n, t in self.tools.items() if isinstance(t.get("outputSchema"), dict)}

    def close(self):
        try: self.p.stdin.close(); self.p.wait(timeout=5)
        except Exception: self.p.kill()

# ---------------------------------------------------------------- schema -> OpenAI function
def _inline(schema, defs):
    """Resolve $ref against $defs, drop $schema/title, so small models see plain nested schemas."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            target = defs[schema["$ref"].split("/")[-1]]
            merged = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
            return _inline(merged, defs)
        return {k: _inline(v, defs) for k, v in schema.items() if k not in ("$defs", "$schema", "title")}
    if isinstance(schema, list): return [_inline(x, defs) for x in schema]
    return schema

def to_openai(tool):
    s = tool["inputSchema"]; params = _inline(s, s.get("$defs", {}))
    desc = tool.get("description", "").replace(f" Command `{tool['name'].replace('_', '.', 1)}`.", "")
    if tool["name"] == "nca_run":
        opts = params["properties"]["options"]
        opts["properties"] = {k: v for k, v in opts["properties"].items() if k in NCA_OPTIONS_KEPT}
        opts["description"] = ("NCA conventions, all optional. auc_method: linear = linear trapezoids, "
                               "lin_up_log_down = linear-up/log-down. Other options (blq, missing...) exist but are not shown.")
        params["properties"]["route"] = {"type": "string", "enum": ["extravascular", "iv_bolus", "iv_infusion"],
                                         "description": "oral = extravascular; infusion = iv_infusion with infusion_duration"}
        params["properties"]["infusion_duration"] = {"type": "number", "description": "Only with route iv_infusion: duration of the infusion in the time unit of the data (2 h -> 2)."}
        params["properties"]["dose"] = {"type": "number", "description": "Dose amount in the unit the user gives (10 mg -> 10)."}
        params["properties"]["subject"] = {"description": "One subject label; omit for all subjects."}
    if tool["name"] == "analysis_compare":
        desc = ("Differences, relative differences in percent and ratios (b minus a) of the parameters two analyses of one "
                "subject share, computed by Caladrius with their units. Use it for any comparison of two results.")
        params["properties"]["a"] = {"type": "integer", "description": "Analysis id of the reference result (from nca_run)."}
        params["properties"]["b"] = {"type": "integer", "description": "Analysis id of the other result."}
        params["properties"]["parameters"] = {"type": "array", "items": {"type": "string"},
                                              "description": "PKNCA names to compare, e.g. [\"auclast\"]; omit for all shared."}
    if tool["name"] == "data_import":
        params["properties"].pop("decimal_comma", None); params["properties"].pop("delimiter", None)
    return {"type": "function", "function": {"name": tool["name"], "description": desc, "parameters": params}}

# ---------------------------------------------------------------- result digest for the model
def _sig(x, n=6):
    """Round to n significant digits (a display choice made by the client, not a computation)."""
    return float(f"{x:.{n}g}") if isinstance(x, float) else x

def _shown(x):
    """The text of a digest value: the 6 significant digits, without the ".0" Python prints after an integral float
    ("2128760", not "2128760.0", which would claim 8 digits). Same rule as the decision harness (numtext.value_text)."""
    return "0" if x == 0 else value_text(_sig(x))        # "0", never "-0" or "0.0"

def param_unit(name, u):
    """Unit label of a PKNCA parameter from the worksheet's units (u: time, conc, dose, derived).
    Labels only: no value is converted. Unknown units are written as such, never guessed."""
    t = u.get("time") or "time unit"; c = u.get("conc") or "conc unit"; d = u.get("dose")
    der = u.get("derived", {})
    if name.endswith(".dn"):
        base = param_unit(name[:-3], u); return f"{base}/(dose unit)" if base else "per dose unit"
    if "pext" in name or "pbext" in name: return "%"
    if name in ("r.squared", "adj.r.squared", "span.ratio", "lambda.z.n.points"): return ""
    if name == "lambda.z": return der.get("lambda_z", f"1/{t}")
    if name.startswith("aumc"): return der.get("aumc", f"{t}^2*{c}")
    if name.startswith("auc"): return der.get("auc", f"{t}*{c}")
    if name.startswith(("cmax", "clast", "c0")): return c
    if name.startswith(("tmax", "tlast", "tfirst", "tlag", "half.life", "lambda.z.time", "mrt")): return t
    if name.startswith("cl."): return der.get("cl", f"{d or 'dose unit'}/({t}*{c})")
    if name.startswith(("vz.", "vss.")): return der.get("v", f"{d or 'dose unit'}/({c})")
    return "?"

def digest_analysis(d, units=None):
    """An NCA analysis (nca_run / analysis_get answer) is ~7 kB of JSON (all lambda_z candidates,
    the profile, ~60 parameters): too much for a 12k context. The model gets the same values,
    reorganised: computed parameters as name -> value (6 significant digits), the names of the
    parameters not calculated with their reason, the selected lambda_z regression, the options
    and quality thresholds used, flags. The full text is kept in the tool log."""
    res, spec = d.get("result") or {}, d.get("spec") or {}
    opts = spec.get("options", {})
    out = {"analysis": d.get("id"), "label": d.get("label"), "status": (d.get("status") or {}).get("state"),
           "options_used": {"auc_method": opts.get("auc_method"), "lambda_z": opts.get("lambda_z"),
                            "quality_thresholds": opts.get("quality"),
                            "blq": opts.get("blq"), "missing": opts.get("missing"),
                            "negative": opts.get("negative"), "start": opts.get("start")},
           "subjects": []}
    u = units or {}
    out["unit_warnings"] = u.get("warnings", [])
    out["dose_unit"] = u.get("dose") or "unknown to Caladrius (no dose column): CL and V are in dose unit/..."
    for s in res.get("subjects", []):
        o = {"subject": s.get("subject"), "dose": s.get("dose"), "route": s.get("route")}
        oc = s.get("outcome", {})
        if "ok" in oc:
            ok = oc["ok"]; vals, nc = {}, {}
            for p in ok.get("parameters", []):
                v = p.get("value", {})
                if "value" in v:
                    un = param_unit(p["name"], u)
                    vals[p["name"]] = f"{_shown(v['value'])} {un}".strip() if un else _sig(v["value"])
                else: nc.setdefault(str(v.get("not_calculated")), []).append(p["name"])
            o["flags"] = ok.get("flags", [])
            o["flag_messages"] = s.get("flag_messages", [])
            o["parameters"] = vals
            o["not_calculated"] = nc
            # the engine's wording per not-calculated parameter, grouped by identical text (one line per
            # distinct message instead of ~20 repeated ones)
            ncm = {}
            for pname, msg in (s.get("not_calculated_messages") or {}).items(): ncm.setdefault(msg, []).append(pname)
            o["not_calculated_messages"] = ncm
            sel = [c for c in ok.get("lambda_z_candidates", []) if c.get("selected")]
            if sel: o["lambda_z_regression"] = {k: _sig(v) for k, v in sel[0].items() if k not in ("selected", "valid")}
            if ok.get("removed"): o["removed_points"] = ok["removed"]
        else:
            o["outcome"] = oc
        out["subjects"].append(o)
    return out

def digest_compare(d, units=None):
    """An `analysis_compare` answer (one row per shared parameter: a, b, unit_a, unit_b, difference, difference_unit,
    relative_percent, ratio, not_comparable) as one line per parameter in the "value unit" style of the NCA digest, 6
    significant digits, nothing computed or converted here. A row with neither value (both missing) carries only a reason:
    those are grouped under their reason like the NCA digest does for not-calculated parameters.
    Units: the engine's own when it reports them; when it reports none (an NCA run whose options carry no units, which is
    what nca_run called through this client does) the unit is labelled from the worksheet like in the NCA digest, but only
    when both analyses come from the same worksheet (`units[("analysis", id)]` -> worksheet id, filled by render_tool_result).
    No value is converted."""
    label = _compare_labels(d, units)
    def val(x, unit=None):
        if x is None: return None
        return f"{_shown(x)} {unit}".strip() if unit else _shown(x)
    info = lambda s: {"analysis": s.get("analysis"), "label": s.get("label"), "status": s.get("status")}
    out = {"a": info(d.get("a") or {}), "b": info(d.get("b") or {}), "subject": (d.get("a") or {}).get("subject"),
           "parameters": {}, "not_comparable": {}}
    for r in d.get("rows", []):
        if r.get("a") is None and r.get("b") is None:
            out["not_comparable"].setdefault(r.get("not_comparable") or "no value", []).append(r.get("parameter"))
            continue
        pn = r.get("parameter"); ua, ub = label(pn, r.get("unit_a")), label(pn, r.get("unit_b"))
        parts = [f"a {val(r.get('a'), ua)}" if r.get("a") is not None else "a none",
                 f"b {val(r.get('b'), ub)}" if r.get("b") is not None else "b none"]
        if r.get("difference") is not None: parts.append(f"difference {val(r['difference'], r.get('difference_unit') or (ua if ua == ub else None))}")
        if r.get("relative_percent") is not None: parts.append(f"percent {val(r['relative_percent'], '%')}")
        if r.get("ratio") is not None: parts.append(f"ratio {val(r['ratio'])}")
        if r.get("not_comparable"): parts.append(f"not comparable: {r['not_comparable']}")
        out["parameters"][r.get("parameter")] = " | ".join(parts)
    return out

def _compare_labels(d, units):
    """Unit labeller of an analysis_compare answer: the engine's unit when it reports one, else the worksheet's label
    when both analyses come from the same worksheet (`units[("analysis", id)]` -> worksheet id), else None."""
    ids = [(d.get(k) or {}).get("analysis") for k in ("a", "b")]
    wsids = [(units or {}).get(("analysis", i)) for i in ids]
    wu = (units or {}).get(wsids[0]) if wsids[0] is not None and wsids[0] == wsids[1] else None
    def label(name, unit):
        if unit is not None or wu is None: return unit
        u = param_unit(name, wu); return None if u == "?" else u
    return label

def ref_record(ref, name, structured, units):
    """The record gate v2 resolves a reference against: the structuredContent of the call as the server sent it, plus the
    unit labels the client computes for it (the same labels as the digest shows; nothing converted). Built after
    render_tool_result has remembered the worksheet's units."""
    rec = {"ref": ref, "name": name, "structured": structured, "units": {}}
    d = structured
    if isinstance(d, dict) and d.get("kind") == "nca" and isinstance(d.get("result"), dict):
        u = units.get((d.get("spec") or {}).get("worksheet")) or {}
        pu = {}
        for s in d["result"].get("subjects") or []:
            for p in ((s.get("outcome") or {}).get("ok") or {}).get("parameters") or []:
                un = p.get("unit") or param_unit(p["name"], u)
                pu[p["name"]] = "" if un == "?" else un
        rec["units"] = {"dose": u.get("dose") or "", "parameters": pu}
    elif isinstance(d, dict) and isinstance(d.get("rows"), list) and "a" in d and "b" in d:
        label = _compare_labels(d, units); rows = {}
        for r in d["rows"]:
            pn = r.get("parameter"); ua, ub = label(pn, r.get("unit_a")), label(pn, r.get("unit_b"))
            rows[pn] = {"a": ua or "", "b": ub or "", "difference": r.get("difference_unit") or (ua if ua == ub else None) or "",
                        "relative_percent": "%", "ratio": ""}
        rec["units"] = {"rows": rows}
    return rec

def render_tool_result(name, ok, text, units, ref=None):
    """What the model is shown for an MCP answer. `units` (worksheet id -> units, updated in place)
    remembers the units a worksheet reported; an NCA analysis is digested with the units of its
    worksheet; any other answer is the compact JSON of the same content. With `ref` (gate v2) the JSON
    starts with "ref": the handle the model cites, and each subject of a multi-subject analysis has its own."""
    if not ok: return text
    try:
        d = json.loads(text)
        ws = d.get("worksheet") if isinstance(d, dict) else None
        if isinstance(ws, dict) and "derived_units" in ws:          # remember units per worksheet
            roles = {col.get("role"): col.get("unit") for col in ws.get("columns", [])}
            units[ws.get("id")] = {"time": roles.get("time"), "conc": roles.get("concentration"),
                                   "dose": roles.get("dose"), "derived": ws["derived_units"],
                                   "warnings": ws.get("unit_warnings", [])}
        if name == "analysis_compare" and isinstance(d, dict) and isinstance(d.get("rows"), list):
            d = digest_compare(d, units)
        elif isinstance(d, dict) and d.get("kind") == "nca" and "result" in d:
            wid = (d.get("spec") or {}).get("worksheet")
            units[("analysis", d.get("id"))] = wid                  # lets analysis_compare label units
            d = digest_analysis(d, units.get(wid))
            if ref and len(d.get("subjects") or []) > 1:
                d["subjects"] = [{"ref": f"{ref}.subject={s.get('subject')}", **s} for s in d["subjects"]]
        if ref and isinstance(d, dict): d = {"ref": ref, **d}
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return text

# ---------------------------------------------------------------- number gate
def gate_context(log, mcp_tool_names):
    """What an answer may quote: the results of the Caladrius tools and the user's messages of the whole
    chat log. Not the assistant's own messages, not zoom / read_message results (they restate old
    messages and summaries and could launder a wrong number)."""
    tools = [m["content"] for m in log if m["role"] == "tool_result" and m.get("name") in mcp_tool_names]
    users = [m["content"] for m in log if m["role"] == "user"]
    return tools, users

def _counts(g):
    c = {"numbers_total": g["numbers_total"], "numbers_unverified": g["numbers_unverified"],
         "numbers_exempt": g["numbers_exempt"]}
    if "references_total" in g:                                       # gate v2
        c["references_total"] = g["references_total"]; c["references_unresolved"] = g["references_unresolved"]
    return c

# ---------------------------------------------------------------- agent
class Apothicaire(optchat.Agent):
    def __init__(self, cfg=optchat.CFG, mcp_bin=MCP_BIN, gate_version=None):
        self.gate_version = gate_version_of(gate_version)             # "v1" (gate.py) or "v2" (gate_v2.py), APOTHICAIRE_GATE
        self.mcp = MCPClient([mcp_bin])
        self.mcp_tools = [to_openai(self.mcp.tools[n]) for n in EXPOSED if n in self.mcp.tools]
        # optchat reads these module globals at call time (in turn() and build_messages())
        optchat.TOOLS = optchat.TOOLS[:2] + self.mcp_tools
        install_prompt(SYSTEM_ADDITION_V2 if self.gate_version == "v2" else SYSTEM_ADDITION)
        self.tool_log = []           # every MCP call of the session: turn, name, args, ok, text, shown
        self.units = {}              # worksheet id -> derived units reported by Caladrius
        self.gate_log = []           # one record per turn: the gate's counts and findings
        self._gate_rec = None
        self.refs = {}               # gate v2: ref ("call_3") -> record (structuredContent + unit labels), persisted in refs.jsonl
        self.schemas = self.mcp.output_schemas() if self.gate_version == "v2" else {}
        self.decimal_mark = "," if str(cfg.get("digest_lang", "")).lower().startswith("fr") else "."
        super().__init__(cfg)
        if self.gate_version == "v2": self._load_refs()

    # -- gate v2: the citable results of the whole chat memory survive a restart
    def _refs_path(self): return os.path.join(self.cfg["data_dir"], "refs.jsonl")

    def _load_refs(self):
        try:
            with open(self._refs_path(), encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line); self.refs[rec["ref"]] = rec
        except OSError: pass

    def _remember_ref(self, rec):
        self.refs[rec["ref"]] = rec
        try:
            with open(self._refs_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError: pass

    def _tool(self, name, args):
        if name not in self.mcp.tools: return super()._tool(name, args)
        args = dict(args) if isinstance(args, dict) else {}
        if name == "data_import" and "path" in args and "csv" not in args:   # convenience: a file path
            try:
                with open(args.pop("path"), encoding="utf-8") as f: args["csv"] = f.read()
            except OSError as e: return f"tool error: cannot read file: {e}"
        if name == "nca_run":
            err = self._nca_route(args)
            if err: return err
        try: ok, text, structured = self.mcp.call_full(name, args)
        except MCPError as e: ok, text, structured = False, f"mcp error: {e}", None
        ref = None
        if self.gate_version == "v2" and ok and structured is not None:    # a citable result gets the next ref
            ref = f"call_{len(self.refs) + 1}"
        shown = render_tool_result(name, ok, text, self.units, ref=ref)
        if ref: self._remember_ref(ref_record(ref, name, structured, self.units))
        self.tool_log.append({"turn": len(self.turn_stats), "name": name, "args": args, "ok": ok,
                              "text": text, "shown": shown, "ref": ref})
        return shown if ok else f"TOOL ERROR: {text}"

    @staticmethod
    def _nca_route(args):
        """The server's infusion route is an object, {"iv_infusion": {"duration": d}}, which the 27B cannot write as a
        tool argument (it sends a string). The model sees route = "iv_infusion" plus infusion_duration; this builds the
        object. A route sent as a JSON string is parsed. Returns a TOOL ERROR text, or None when the arguments are fine."""
        dur = args.pop("infusion_duration", None); route = args.get("route")
        if isinstance(route, str) and route.strip().startswith("{"):
            try: route = args["route"] = json.loads(route)
            except ValueError: return "TOOL ERROR: route is not valid JSON"
        if route == "iv_infusion":
            if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur <= 0:
                return "TOOL ERROR: route iv_infusion needs infusion_duration, a positive number in the time unit of the data"
            args["route"] = {"iv_infusion": {"duration": dur}}
        return None

    # -- number gate: every final answer is checked against the tool results and the user's messages
    def _chat_call(self, msgs, tools=None):
        m = super()._chat_call(msgs, tools)
        if m.get("tool_calls"): return m                      # a tool round, not an answer
        draft = (m.get("content") or "").strip()
        tool_texts, users = gate_context(self.store.log, self.mcp.tools)
        if self.gate_version == "v2":
            # typed rendering: the sources are the user's messages only; tool values are cited and rendered
            allowed = gate_v2.user_numbers(users)
            run = lambda text: gate_v2.check(text, self.refs, schemas=self.schemas, decimal_mark=self.decimal_mark, allowed=allowed)
            remind = lambda findings: gate_v2.reminder(findings, self.refs)
        else:
            allowed = gate.allowed_numbers(tool_texts, users)
            run = lambda text: gate.check(text, allowed=allowed)
            remind = gate.reminder
        g1 = run(draft)
        rec = {"version": self.gate_version, "before": _counts(g1), "after": _counts(g1), "regenerated": False, "kept": "first",
               "findings": g1["findings"]}
        if "rendered" in g1: rec["rendered"] = g1["rendered"]
        if g1["findings"]:
            # one regeneration. The reminder is appended at the END of the messages (the system prompt and
            # the tool definitions, hence the cached prefix, are untouched) and is not stored in the memory.
            first_last = dict(self.llm.last)
            msgs2 = list(msgs) + [{"role": "assistant", "content": draft},
                                  {"role": "user", "content": remind(g1["findings"])}]
            try:
                m2 = self.llm.chat(msgs2, slot=0, tools=None, max_tokens=self.cfg["agent_max_tokens"],
                                   think=self.cfg["agent_think"])
                regen_stats = dict(self.llm.last)
                new = (m2.get("content") or "").strip()
            except optchat.LLMError as e:
                regen_stats, new = {"error": str(e)}, ""
            self.llm.last = first_last                        # turn() reads the stats of the first call
            rec.update(regenerated=True, first_answer=draft, first_findings=g1["findings"], regen_stats=regen_stats)
            if new:
                g2 = run(new)
                rec["after_regeneration"] = _counts(g2)
                if g2["numbers_unverified"] <= g1["numbers_unverified"]:   # keep the better of the two
                    rec.update(kept="regenerated", after=_counts(g2), findings=g2["findings"])
                    if "rendered" in g2: rec["rendered"] = g2["rendered"]
                    m = {**m, "content": new}
        self._gate_rec = rec
        return m

    def turn(self, user_text, verbose=True):
        self._gate_rec = None
        ans, stat = super().turn(user_text, verbose)
        rec = self._gate_rec
        if rec is not None:
            stat["gate"] = rec
            self.gate_log.append({"turn": len(self.turn_stats), **rec})
            self._append_gate_jsonl(self.gate_log[-1])
            if rec.get("version") == "v2" and "rendered" in rec:
                ans = rec["rendered"]                         # the memory keeps the references; the user sees the values
                if rec["findings"]: ans = ans + "\n\n" + gate_v2.badge(rec["findings"])
            elif rec["findings"]:                             # shown, not stored in the memory
                ans = ans + "\n\n" + gate.badge(rec["findings"])
        return ans, stat

    def _append_gate_jsonl(self, record):
        try:
            with open(os.path.join(self.cfg["data_dir"], "gate.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError: pass

    def close(self):
        try: super().close()
        finally: self.mcp.close()

def static_prefix_tokens(ag):
    """Prompt tokens of the system prompt + tool definitions + a one-word user message (slot 1)."""
    ag.llm.chat([{"role": "system", "content": optchat.SYSTEM_PROMPT}, {"role": "user", "content": "ok"}],
                slot=1, tools=optchat.TOOLS, max_tokens=1)
    return ag.llm.last["prompt_tokens"]

# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("chat"); p = sp.add_parser("say"); p.add_argument("text"); sp.add_parser("tools")
    a = ap.parse_args(); optchat._utf8_stdout()
    ag = Apothicaire()
    try:
        if a.cmd == "tools":
            for t in optchat.TOOLS: print(t["function"]["name"], len(json.dumps(t)), "chars")
            print("static prefix:", static_prefix_tokens(ag), "tokens")
        elif a.cmd == "say":
            ans, s = ag.turn(a.text); print(ans); print(json.dumps(s))
        else:
            while True:
                try: q = input("\nvous> ").strip()
                except EOFError: break
                if not q: break
                ans, s = ag.turn(q)
                print(f"\napothicaire> {ans}\n   · {s['wall_s']}s, prompt {s['prompt_tokens']} tok, {s['rounds']} round(s)")
    except KeyboardInterrupt: pass
    finally: ag.close()

if __name__ == "__main__":
    main()
