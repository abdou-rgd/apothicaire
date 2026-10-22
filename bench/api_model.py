"""A hosted model behind the agent's client: optchat.LLM's interface on the Anthropic Messages API (the frontier API arm,
bench/FRONTIER_ARM.md).

The agent, its prompts, its five exposed Caladrius tools, OptChat's memory and compaction, the gate and the rubric stay as they are;
only the model call changes. `AnthropicLLM.chat` takes the OpenAI-shaped messages and tools that optchat builds for llama-server and
returns the OpenAI-shaped message optchat reads (`content`, `tool_calls`), with the same `last` statistics, so `run_bench.run_exercise`
runs it exactly as it runs the stub model (`llm=`).

What cannot be the same as on llama-server, and is declared in FRONTIER_ARM.md §2:

- **Sampling.** The Messages API takes no temperature, top-p or seed: the provider's sampling is used, the `--seeds` of the runner
  only label the repetitions, and no replay is claimed.
- **Thinking.** Claude Sonnet 5.5 runs with thinking off (`between_tools`, the lowest setting); Claude Opus 5.5 cannot turn it off
  and runs adaptive thinking at the declared effort, with `THINKING_HEADROOM` tokens added to `max_tokens` so the thinking does
  not eat the answer's 1,200. Thinking blocks are sent back only inside the current tool loop (after the last user message), where
  the history is append-only; earlier turns are rebuilt without them, as they are for the 27B. Removing blocks from the front of
  the history is allowed; OptChat's compaction rewrites the front between turns, never inside a tool loop.
- **A round without tools.** optchat sends no tools on its last allowed round and on the gate's regeneration; the API refuses a
  history with tool calls and no tool definitions, so the tools of the turn are sent with `tool_choice: none` (the model sees them
  and cannot call them).
- **Compaction's grammar.** The JSON schema of the summary lines goes to structured outputs without `minItems`/`maxItems`, which the
  API does not take; optchat already checks the number of lines it gets back.
- **No fallback model.** A refusal is a failed call (`LLMError`, so the turn is an ERROR and counts), never a silent switch to
  another model: the arm measures one model.

The key is read from APOTHICAIRE_API_KEY, else ANTHROPIC_API_KEY, and never written anywhere (a cloud environment may reserve the
ANTHROPIC_* names for its own session, hence the first name). The endpoint is https://api.anthropic.com unless
APOTHICAIRE_API_BASE_URL says otherwise: ANTHROPIC_BASE_URL is ignored on purpose, a cloud coding session sets it for its own use.
"""
import json, os, re, time

import optchat

BASE_URL = "https://api.anthropic.com"
THINKING_HEADROOM = 8000
# USD per million tokens: input, output, cache read; a 5-minute cache write is 1.25 x input (Anthropic price list, 2026-10-06)
PRICES = {"claude-sonnet-5-5": (2.00, 10.00, 0.20), "claude-opus-5-5": (4.00, 20.00, 0.20), "claude-haiku-5-5": (0.10, 0.50, 0.01)}
# declared configuration per model (FRONTIER_ARM.md §2): thinking off where the model allows it, the effort of its row otherwise
DEFAULTS = {"claude-sonnet-5-5": ("between_tools", "high"), "claude-opus-5-5": ("adaptive", "medium")}
_ID = re.compile(r"[^a-zA-Z0-9_-]")

def _get(b, k, default=None): return b.get(k, default) if isinstance(b, dict) else getattr(b, k, default)

def cost_usd(model, usage):
    """Cost of a usage dict (input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens); None if unpriced."""
    p = PRICES.get(model)
    if p is None: return None
    i, o, cr = p
    return (usage.get("input_tokens", 0) * i + usage.get("cache_creation_input_tokens", 0) * i * 1.25
            + usage.get("cache_read_input_tokens", 0) * cr + usage.get("output_tokens", 0) * o) / 1e6

def to_tools(tools):
    """OpenAI function tools (optchat.TOOLS, apothicaire.to_openai) to Messages API tools, same names, descriptions and schemas."""
    out = []
    for t in tools or []:
        f = t.get("function", t)
        out.append({"name": f["name"], "description": f.get("description", ""),
                    "input_schema": f.get("parameters") or {"type": "object", "properties": {}}})
    return out

def _strip_array_bounds(schema):
    if isinstance(schema, dict):
        return {k: _strip_array_bounds(v) for k, v in schema.items() if k not in ("minItems", "maxItems")}
    if isinstance(schema, list): return [_strip_array_bounds(v) for v in schema]
    return schema

def _args(s):
    try: a = json.loads(s) if isinstance(s, str) else s
    except ValueError: a = None
    return a if isinstance(a, dict) else {}

def to_messages(msgs, replay=None):
    """(system, messages) for the Messages API from optchat's OpenAI-shaped messages.

    `replay` maps the id of a tool call to the content blocks of the response that made it (thinking included); an assistant
    message after the last user message whose calls are found there is sent back as those blocks. Every other assistant message
    is rebuilt from its text and calls. Tool results become tool_result blocks in a user message; a result whose call is not in
    the assistant message just before it (the call was summarised away) and a call whose result is not just after it become
    plain text, so the transcript the model reads stays the one optchat built."""
    replay = replay or {}
    system = []
    k = 0
    while k < len(msgs) and msgs[k]["role"] == "system": system.append(msgs[k]["content"] or ""); k += 1
    last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user"), default=-1)
    turns = []                                                   # [role, blocks]
    def add(role, blocks):
        if turns and turns[-1][0] == role: turns[-1][1].extend(blocks)
        else: turns.append([role, list(blocks)])
    for i in range(k, len(msgs)):
        m = msgs[i]; role, c = m["role"], m.get("content") or ""
        if role == "assistant":
            tcs = m.get("tool_calls") or []
            cached = replay.get(tcs[0]["id"]) if tcs and i > last_user else None
            if cached is not None and [_get(b, "id") for b in cached if _get(b, "type") == "tool_use"] == [t["id"] for t in tcs]:
                add("assistant", cached); continue
            blocks = [{"type": "text", "text": c}] if c.strip() else []
            blocks += [{"type": "tool_use", "id": _ID.sub("_", t["id"] or f"call{i}_{j}"), "name": t["function"]["name"],
                        "input": _args(t["function"].get("arguments"))} for j, t in enumerate(tcs)]
            add("assistant", blocks)
        elif role == "tool":
            add("user", [{"type": "tool_result", "tool_use_id": _ID.sub("_", m.get("tool_call_id") or ""), "content": c or "(empty)"}])
        else:
            add("user", [{"type": "text", "text": (f"[{role}] " if role != "user" else "") + (c if c.strip() else "(empty)")}])
    # pair every tool_use with the tool_result just after it; anything unpaired is shown as text
    for n, (role, blocks) in enumerate(turns):
        if role == "assistant":
            nxt = turns[n + 1][1] if n + 1 < len(turns) and turns[n + 1][0] == "user" else []
            answered = {_get(b, "tool_use_id") for b in nxt if _get(b, "type") == "tool_result"}
            turns[n][1] = [b if _get(b, "type") != "tool_use" or _get(b, "id") in answered else
                           {"type": "text", "text": f"call {_get(b, 'name')}({json.dumps(_get(b, 'input'), ensure_ascii=False)})"}
                           for b in blocks]
        else:
            prev = turns[n - 1][1] if n and turns[n - 1][0] == "assistant" else []
            asked = {_get(b, "id") for b in prev if _get(b, "type") == "tool_use"}
            res = [b for b in blocks if _get(b, "type") == "tool_result" and b["tool_use_id"] in asked]
            rest = [b if _get(b, "type") != "tool_result" or b["tool_use_id"] in asked else
                    {"type": "text", "text": f"[tool result {b['tool_use_id']}] {b['content']}"} for b in blocks]
            turns[n][1] = res + [b for b in rest if not (_get(b, "type") == "tool_result")]
    for t in turns:
        if not t[1]: t[1] = [{"type": "text", "text": "(empty)"}]
    if turns and turns[0][0] == "assistant": turns.insert(0, ["user", [{"type": "text", "text": "(conversation continues)"}]])
    return "\n\n".join(system), [{"role": r, "content": b} for r, b in turns]

class AnthropicLLM:
    """Drop-in for optchat.LLM: chat(messages, slot, tools, max_tokens, think, temperature, response_format) -> message dict,
    `last` with the statistics turn() reads, plus `usage` (tokens and cost over every call of the run) and `refusals`."""

    def __init__(self, model, thinking=None, effort=None, client=None, api_key_env=("APOTHICAIRE_API_KEY", "ANTHROPIC_API_KEY"),
                 max_retries=8, timeout=600.0):
        self.model = model
        d = DEFAULTS.get(model, ("adaptive", "medium"))
        self.thinking, self.effort = thinking or d[0], effort or d[1]
        if client is None:
            key = next((os.environ[v] for v in api_key_env if os.environ.get(v)), None)
            if not key: raise SystemExit(f"{' or '.join(api_key_env)} is not set: the frontier API arm needs a key (FRONTIER_ARM.md §7)")
            import anthropic
            client = anthropic.Anthropic(api_key=key, base_url=os.environ.get("APOTHICAIRE_API_BASE_URL", BASE_URL),
                                         max_retries=max_retries, timeout=timeout)
        self.client = client
        self.total_slots = 1
        self.last = {}
        self.tools = None                     # the tools of the last call that had some: sent with tool_choice none when needed
        self.replay = {}                      # first tool call id -> content blocks of the response that made it
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0, "cost_usd": 0.0, "wall_s": 0.0, "served_by": []}
        self.refusals = []

    def label(self):
        return (f"{self.model} on the Anthropic Messages API, thinking {self.thinking}, effort {self.effort}, "
                "provider sampling (no temperature, no seed)")

    def config(self):
        return {"provider": "anthropic", "model": self.model, "thinking": self.thinking, "effort": self.effort,
                "thinking_headroom": THINKING_HEADROOM if self.thinking == "adaptive" else 0, "prompt_caching": "automatic",
                "fallback_model": None}

    def request(self, messages, tools=None, max_tokens=512, response_format=None):
        """The keyword arguments of messages.create for one optchat call."""
        system, msgs = to_messages(messages, self.replay)
        if tools: self.tools = to_tools(tools)
        p = {"model": self.model, "max_tokens": max_tokens + (THINKING_HEADROOM if self.thinking == "adaptive" else 0),
             "messages": msgs, "cache_control": {"type": "ephemeral"}, "thinking": {"type": self.thinking},
             "output_config": {"effort": self.effort}}
        if system: p["system"] = system
        has_calls = any(_get(b, "type") in ("tool_use", "tool_result") for m in msgs for b in m["content"])
        if tools: p["tools"], p["tool_choice"] = self.tools, {"type": "auto"}
        elif has_calls and self.tools: p["tools"], p["tool_choice"] = self.tools, {"type": "none"}
        if response_format:
            schema = (response_format.get("json_schema") or {}).get("schema") or response_format.get("schema")
            p["output_config"]["format"] = {"type": "json_schema", "schema": _strip_array_bounds(schema)}
        return p

    def chat(self, messages, slot=0, tools=None, max_tokens=512, think=False, temperature=0.3, response_format=None):
        p = self.request(messages, tools, max_tokens, response_format)
        t0 = time.time()
        try:
            r = self.client.messages.create(**p)
        except Exception as e:                # the SDK has already retried 429, 5xx and connection errors
            code = getattr(e, "status_code", None)
            if code is not None: raise optchat.LLMError(f"HTTP {code}: {str(e)[:300]}") from e
            raise optchat.LLMError(f"transport: {type(e).__name__}: {e}") from e
        wall = time.time() - t0
        u = _get(r, "usage")
        us = {k: int(_get(u, k, 0) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
        cost = cost_usd(self.model, us)
        self.usage["calls"] += 1; self.usage["wall_s"] = round(self.usage["wall_s"] + wall, 2)
        for k, v in us.items(): self.usage[k] += v
        if cost is not None: self.usage["cost_usd"] = round(self.usage["cost_usd"] + cost, 6)
        served = _get(r, "model")                 # the model the API says answered, recorded since an id can be re-pointed
        if served and served not in self.usage["served_by"]: self.usage["served_by"].append(served)
        stop = _get(r, "stop_reason")
        self.last = {"wall_s": round(wall, 2), "prompt_tokens": us["input_tokens"] + us["cache_creation_input_tokens"] + us["cache_read_input_tokens"],
                     "completion_tokens": us["output_tokens"], "prompt_eval_n": us["input_tokens"] + us["cache_creation_input_tokens"],
                     "cache_n": us["cache_read_input_tokens"], "prompt_ms": None, "predicted_ms": None, "gen_tps": None,
                     "finish_reason": {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length"}.get(stop, stop),
                     "cost_usd": cost}
        if stop == "refusal":
            sd = _get(r, "stop_details")
            self.refusals.append({"category": _get(sd, "category"), "explanation": _get(sd, "explanation")})
            raise optchat.LLMError(f"refusal: {_get(sd, 'category')}")
        content = list(_get(r, "content") or [])
        text = "".join(_get(b, "text") or "" for b in content if _get(b, "type") == "text")
        calls = [{"id": _get(b, "id"), "type": "function",
                  "function": {"name": _get(b, "name"), "arguments": json.dumps(_get(b, "input") or {}, ensure_ascii=False)}}
                 for b in content if _get(b, "type") == "tool_use"]
        m = {"role": "assistant", "content": text}
        if calls:
            m["tool_calls"] = calls; self.replay[calls[0]["id"]] = content
        return m
