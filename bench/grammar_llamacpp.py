#!/usr/bin/env python
"""Does llama.cpp b11700 read the grammar of gate v3 the way gate_v3.Machine and tests/gbnf_reader.py do? A check on the library
itself, on the CPU: no llama-server, no GPU, no weights.

bench/grammar_offline.py runs the rules of a grammar on two readers written here (the stack engine `gate_v3.Machine`, which mirrors
src/llama-grammar.cpp, and the Earley recogniser of tests/gbnf_reader.py). Neither is llama.cpp. This script puts the printed text,
`Grammar.gbnf`, to the real thing: llama.dll of the upstream b11700 release (C:\\Users\\abdou\\llama-upstream\\bin), called through
ctypes, with the vocabulary of the 27B (the GGUF is opened vocab-only: `vocab_only` is set, no tensor is read, no backend is
loaded, so nothing can reach the GPU). For each text:

  1. `llama_sampler_init_grammar(vocab, gbnf, "root")` - the call the server makes for a user grammar (common/sampling.cpp, not
     lazy, not prefilled) - must parse the text (NULL if it does not: "failed to parse grammar" on the server);
  2. the text is tokenised with the model's tokenizer and walked token by token the way the server samples: a token is allowed
     when `llama_sampler_apply` on a candidate list of that one token leaves its logit finite (the check the server makes on the
     token it has drawn), then `llama_sampler_accept`. The text is ALIVE when every token is allowed, and ACCEPTED when, after the
     last token, an end-of-generation token is allowed too (llama.cpp lets the model stop only where the grammar can end).

These verdicts are compared with `gate_v3.conformance(grammar, text)` (Machine): the same `alive`, the same `accepted`, and, when
the text is refused, the first refused character of Machine lies in the first token llama.cpp refuses. The texts are the final
answers and the first drafts of the stored gate v2 development runs (the grammar of each turn is built as bench/grammar_offline.py
builds it) and mutations of those finals (a digit run, a unit, a sign after a reference, a wrong path, a cut reference, digits and
letters of other scripts, 2- to 4-byte characters), the cases where a difference between the readers would show.

It also times the call the server makes when the token it drew is refused: the grammar applied to the whole vocabulary (248 320
candidates), in the initial state and after some prefixes, on this CPU.

  python bench/grammar_llamacpp.py [--runs DIR] [--limit N] [--json]

needs llama.dll (LLAMA_UPSTREAM_BIN, default C:\\Users\\abdou\\llama-upstream\\bin) and a GGUF for its vocabulary (LLAMA_VOCAB_GGUF,
default the 27B in %LOCALAPPDATA%\\hermes\\models); `available()` says whether they are there. About 2 minutes on the full runs.
"""
import argparse, collections, ctypes, json, os, random, statistics, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
if AGENT not in sys.path: sys.path.insert(0, AGENT)
import gate_v3  # noqa: E402
from bench import grammar_offline as go  # noqa: E402

DLL_DIR = os.environ.get("LLAMA_UPSTREAM_BIN", r"C:\Users\abdou\llama-upstream\bin")
GGUF = os.environ.get("LLAMA_VOCAB_GGUF", os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "models", "Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf"))


def available():
    """True when llama.dll of b11700 and a GGUF to take the vocabulary from are on this machine (Windows only)."""
    return os.name == "nt" and os.path.exists(os.path.join(DLL_DIR, "llama.dll")) and os.path.exists(GGUF)


# ---------------------------------------------------------------- llama.h of b11700, the parts used
class _ModelParams(ctypes.Structure):
    """struct llama_model_params, 80 bytes on x64: pointers at 0, 8, 40, 48, 56, 64, 32-bit fields at 16-32, six bools from 72
    (vocab_only first). Only the default values and the bool at offset 72 are touched."""
    _fields_ = [("raw", ctypes.c_ubyte * 80)]
VOCAB_ONLY = 72


class _TokenData(ctypes.Structure):
    _fields_ = [("id", ctypes.c_int32), ("logit", ctypes.c_float), ("p", ctypes.c_float)]


class _TokenDataArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(_TokenData)), ("size", ctypes.c_size_t), ("selected", ctypes.c_int64), ("sorted", ctypes.c_bool)]


_LOG = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
assert ctypes.sizeof(_ModelParams) == 80 and ctypes.sizeof(_TokenData) == 12 and ctypes.sizeof(_TokenDataArray) == 32


class LlamaCpp:
    """The vocabulary of a GGUF and the grammar sampler of llama.dll."""

    def __init__(self, dll_dir=DLL_DIR, gguf=GGUF):
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")                 # belt and braces: no backend is loaded anyway
        os.add_dll_directory(dll_dir)
        L = self.lib = ctypes.CDLL(os.path.join(dll_dir, "llama.dll"))
        vp, ip, cp = ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p
        L.llama_model_default_params.restype = _ModelParams
        L.llama_model_load_from_file.restype, L.llama_model_load_from_file.argtypes = vp, [cp, _ModelParams]
        L.llama_model_free.argtypes = [vp]
        L.llama_model_get_vocab.restype, L.llama_model_get_vocab.argtypes = vp, [vp]
        L.llama_vocab_n_tokens.restype, L.llama_vocab_n_tokens.argtypes = ip, [vp]
        L.llama_vocab_eot.restype, L.llama_vocab_eot.argtypes = ip, [vp]
        L.llama_vocab_is_eog.restype, L.llama_vocab_is_eog.argtypes = ctypes.c_bool, [vp, ip]
        L.llama_tokenize.restype, L.llama_tokenize.argtypes = ip, [vp, cp, ip, ctypes.POINTER(ip), ip, ctypes.c_bool, ctypes.c_bool]
        L.llama_token_to_piece.restype, L.llama_token_to_piece.argtypes = ip, [vp, ip, ctypes.c_char_p, ip, ip, ctypes.c_bool]
        L.llama_sampler_init_grammar.restype, L.llama_sampler_init_grammar.argtypes = vp, [vp, cp, cp]
        L.llama_sampler_clone.restype, L.llama_sampler_clone.argtypes = vp, [vp]
        L.llama_sampler_apply.argtypes = [vp, ctypes.POINTER(_TokenDataArray)]
        L.llama_sampler_accept.argtypes = [vp, ip]
        L.llama_sampler_free.argtypes = [vp]
        self.messages = []                                                   # the warnings and errors llama.cpp logs
        def log(level, text, _):
            if level in (3, 4): self.messages.append(text.decode("utf-8", "replace").rstrip())
        self._log = _LOG(log)                                                # kept: the callback must outlive the calls
        L.llama_log_set(self._log, None)
        params = L.llama_model_default_params()
        params.raw[VOCAB_ONLY] = 1
        self.model = L.llama_model_load_from_file(gguf.encode("utf-8"), params)
        if not self.model: raise RuntimeError(f"llama.cpp could not open the vocabulary of {gguf}: {self.messages[-3:]}")
        self.vocab = L.llama_model_get_vocab(self.model)
        self.n_vocab, self.eot = L.llama_vocab_n_tokens(self.vocab), L.llama_vocab_eot(self.vocab)
        assert L.llama_vocab_is_eog(self.vocab, self.eot)
        self._pieces = {}
        self.walked_s = self.walked_tokens = 0                                 # time spent in `walk` (tokenizer included) and tokens walked

    def close(self):
        if self.model: self.lib.llama_model_free(self.model); self.model = None

    def identity(self):
        """Which library and vocabulary this is (sha256 of llama.dll, size of the GGUF, vocabulary size)."""
        import hashlib
        path = os.path.join(DLL_DIR, "llama.dll")
        with open(path, "rb") as f: digest = hashlib.sha256(f.read()).hexdigest()
        return {"llama.dll": digest, "bytes": os.path.getsize(path), "gguf": os.path.basename(GGUF), "n_vocab": self.n_vocab, "eot": self.eot}

    # -- the tokenizer
    def tokenize(self, text):
        raw = text.encode("utf-8")
        n = len(raw) + 8
        buf = (ctypes.c_int32 * n)()
        k = self.lib.llama_tokenize(self.vocab, raw, len(raw), buf, n, False, False)
        if k < 0:
            n = -k; buf = (ctypes.c_int32 * n)()
            k = self.lib.llama_tokenize(self.vocab, raw, len(raw), buf, n, False, False)
        return list(buf[:k])

    def piece(self, token):
        p = self._pieces.get(token)
        if p is None:
            buf = ctypes.create_string_buffer(256)
            k = self.lib.llama_token_to_piece(self.vocab, token, buf, 256, 0, False)
            p = self._pieces[token] = buf.raw[:max(k, 0)]
        return p

    # -- the grammar sampler
    def grammar(self, gbnf):
        """A grammar sampler for `gbnf` (rule "root"), or None when llama.cpp does not parse the text. The parser reports its errors
        on stderr (not through the log callback): they are caught there and kept in `self.messages`."""
        del self.messages[:]
        with tempfile.TemporaryFile("w+b") as tmp:
            saved = os.dup(2); os.dup2(tmp.fileno(), 2)
            try: smpl = self.lib.llama_sampler_init_grammar(self.vocab, gbnf.encode("utf-8"), b"root")
            finally: os.dup2(saved, 2); os.close(saved)
            tmp.seek(0); err = tmp.read().decode("utf-8", "replace").strip()
        if err: self.messages.append(err)
        return smpl or None

    def free(self, sampler): self.lib.llama_sampler_free(sampler)

    def allows(self, sampler, token):
        """The check the server makes on the token it has drawn: the grammar applied to a candidate list of that token alone."""
        cand = (_TokenData * 1)(_TokenData(token, 0.0, 0.0))
        arr = _TokenDataArray(cand, 1, -1, False)
        self.lib.llama_sampler_apply(sampler, ctypes.byref(arr))
        return cand[0].logit != float("-inf")

    def walk(self, pristine, text):
        """The verdict of llama.cpp on `text`, from a copy of the grammar sampler `pristine` (still in its initial state):
        {"alive", "accepted", "tokens", "refused_token", "refused_bytes": (first byte, end) of the first refused token}.
        {"faithful": False} when the pieces of the tokens do not add up to the text (then it is not compared)."""
        t0 = time.perf_counter()
        tokens = self.tokenize(text)
        if b"".join(self.piece(t) for t in tokens) != text.encode("utf-8"): return {"faithful": False, "tokens": len(tokens)}
        s = self.lib.llama_sampler_clone(pristine)
        try:
            off = 0
            for i, t in enumerate(tokens):
                p = self.piece(t)
                if not self.allows(s, t): return {"faithful": True, "alive": False, "accepted": False, "tokens": len(tokens), "refused_token": i, "refused_bytes": (off, off + len(p))}
                self.lib.llama_sampler_accept(s, t)
                off += len(p)
            return {"faithful": True, "alive": True, "accepted": self.allows(s, self.eot), "tokens": len(tokens), "refused_token": None, "refused_bytes": None}
        finally:
            self.lib.llama_sampler_free(s)
            self.walked_s += time.perf_counter() - t0; self.walked_tokens += len(tokens)

    def full_vocab_ms(self, pristine, prefix="", repeat=5):
        """Milliseconds to apply the grammar, after `prefix`, to the whole vocabulary (what the server does when the token it drew
        is refused), and how many of the candidates are left."""
        s = self.lib.llama_sampler_clone(pristine)
        try:
            for t in self.tokenize(prefix): self.lib.llama_sampler_accept(s, t)
            times = []
            for _ in range(repeat):
                cand = (_TokenData * self.n_vocab)()
                for i in range(self.n_vocab): cand[i].id = i
                arr = _TokenDataArray(cand, self.n_vocab, -1, False)
                t0 = time.perf_counter()
                self.lib.llama_sampler_apply(s, ctypes.byref(arr))
                times.append((time.perf_counter() - t0) * 1000)
            left = sum(1 for i in range(self.n_vocab) if cand[i].logit != float("-inf"))
            return statistics.median(times), left
        finally: self.lib.llama_sampler_free(s)


# ---------------------------------------------------------------- the comparison
def byte_offset(text, char_index): return len(text[:char_index].encode("utf-8"))

def compare(ll, pristine, grammar, text):
    """One text, both readers. Returns None when llama.cpp's tokenizer does not round-trip it, else a record: Machine's verdict
    (`conformance`), llama.cpp's, whether `alive` and `accepted` agree and, for a refused text, whether Machine's first refused
    character lies in llama.cpp's first refused token."""
    v = ll.walk(pristine, text)
    if not v["faithful"]: return None
    c = gate_v3.conformance(grammar, text, "stop")
    rec = {"alive": c["alive"], "accepted": c["accepted"], "llama_alive": v["alive"], "llama_accepted": v["accepted"], "tokens": v["tokens"],
           "same_alive": c["alive"] == v["alive"], "same_accepted": c["accepted"] == v["accepted"], "same_place": None}
    if not c["alive"] and not v["alive"]:
        # llama.cpp refuses a token, not a character. A token that ends in the middle of a multi-byte character is allowed while some
        # character of the class still begins like that (llama_grammar_match_partial_char), so the refusal can come with the token
        # that holds the last bytes of the character Machine refuses: the two places agree when the token overlaps the character.
        a, b = v["refused_bytes"]
        c0, c1 = byte_offset(text, c["refused_at"]), byte_offset(text, c["refused_at"] + 1)
        rec["same_place"] = a < c1 and c0 < b
    rec["agree"] = rec["same_alive"] and rec["same_accepted"] and rec["same_place"] is not False
    return rec

MUTATIONS = ("digits", "unit", "sign", "wrong path", "cut reference", "other digits", "other letters")
_OTHER_DIGITS = ("\uff11\uff12", "\u0663", "\u00b2", "\u00bd", "\u2155", "\u0967")            # fullwidth 12, Arabic-Indic 3, superscript 2, 1/2, 1/5, Devanagari 1
_OTHER_LETTERS = ("\u00e9", "\u00b5", "\u2192", "\u4e2d\u6587", "\U0001f600", "\u0394", "\u00e0\u00e8\u00ec")   # e acute, micro, arrow, CJK, emoji (4 bytes), Delta, accents

def mutate(text, kind, rng):
    """`text` with one change of the family `kind` at a place picked by `rng`; None when the family has no place in `text`."""
    refs = [i for i in range(len(text)) if text.startswith("{{call_", i)]
    ends = [text.index("}}", i) + 2 for i in refs if "}}" in text[i:]]
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if kind in ("unit", "sign", "wrong path", "cut reference", "digits") and not ends: return None
    if kind == "digits": i = rng.choice(spaces or [0]); return text[:i] + " 12" + text[i:]
    if kind == "unit": e = rng.choice(ends); return text[:e] + rng.choice([" mg", " h", " ng/mL", " %"]) + text[e:]
    if kind == "sign": e = rng.choice(ends); return text[:e] + rng.choice(["+", " -", "x", "/"]) + text[e:]
    if kind == "wrong path":
        e = rng.choice(ends); s = text.rindex("{{", 0, e)
        return text[:e - 2] + "_x" + text[e - 2:] if "." in text[s:e] else None
    if kind == "cut reference": e = rng.choice(ends); s = text.rindex("{{", 0, e); return text[:rng.randrange(s + 2, e)]
    if kind == "other digits": i = rng.choice(spaces or [0]); return text[:i] + " " + rng.choice(_OTHER_DIGITS) + text[i:]
    if kind == "other letters": i = rng.choice(spaces or [0]); return text[:i] + " " + rng.choice(_OTHER_LETTERS) + text[i:]
    raise ValueError(kind)

def run(ll, turns, limit=None, seed=1, mutations_per_family=1, timing=True):
    """The full comparison on the turns of `go.load_turns`. Returns plain data (see `markdown`)."""
    rng = random.Random(seed)
    out = {"turns": 0, "grammars": 0, "parse_failures": [], "finals": [], "drafts": [], "mutated": {k: [] for k in MUTATIONS}, "untokenizable": 0,
           "disagreements": [], "sizes": [], "timing": [], "parse_ms": [], "n_vocab": ll.n_vocab, "dll": ll.identity(), "draft_spans": [], "regen_wall_s": []}
    for T in turns[:limit]:
        g = T["gate"]
        is_clean, draft = not g.get("findings"), g.get("first_answer") if g.get("regenerated") else None
        if not is_clean and not draft: continue
        gr = gate_v3.build(T["calls"], T["users"], None)
        out["turns"] += 1; out["sizes"].append(gr.stats["bytes"])
        t0 = time.perf_counter(); pristine = ll.grammar(gr.gbnf); out["parse_ms"].append((time.perf_counter() - t0) * 1000)
        who = f"seed {T['seed']} {T['exercise']} turn {T['turn']}"
        if pristine is None:
            out["parse_failures"].append({"who": who, "log": list(ll.messages)}); continue
        out["grammars"] += 1
        try:
            def note(bucket, text, what):
                r = compare(ll, pristine, gr, text)
                if r is None: out["untokenizable"] += 1; return
                bucket.append(r)
                if not r["agree"]: out["disagreements"].append({"who": who, "what": what, "text": text[:2000], **r})
            if is_clean:
                note(out["finals"], T["final"], "final")
                for kind in MUTATIONS:
                    for _ in range(mutations_per_family):
                        m = mutate(T["final"], kind, rng)
                        if m is not None: note(out["mutated"][kind], m, "mutation: " + kind)
            if draft:
                note(out["drafts"], draft, "draft")
                out["draft_spans"].append(len(gr.scan(draft)))                  # each refused span is at least one drawn token the server has to reject
                wall = (g.get("regen_stats") or {}).get("wall_s")
                if wall: out["regen_wall_s"].append(wall)
        finally: ll.free(pristine)
    out["walk"] = {"seconds": round(ll.walked_s, 1), "tokens": ll.walked_tokens}
    if timing and turns:
        T = max((t for t in turns if not t["gate"].get("findings")), key=lambda t: len(t["calls"]))
        gr = gate_v3.build(T["calls"], T["users"], None); p = ll.grammar(gr.gbnf)
        try:
            for label, prefix in (("start of an answer", ""), ("after 'La valeur est '", "La valeur est "), ("inside a reference", "Le {{call_"), ("after a reference", "Le Cmax vaut {{call_2.cmax}}")):
                ms, left = ll.full_vocab_ms(p, prefix)
                out["timing"].append({"state": label, "ms": round(ms, 1), "left": left})
            out["timing_grammar"] = {"rules": gr.stats["rules"], "bytes": gr.stats["bytes"]}
        finally: ll.free(p)
    return out

def tally(res):
    def count(rs):
        return {"texts": len(rs), "agree": sum(r["agree"] for r in rs), "alive": sum(r["llama_alive"] for r in rs), "accepted": sum(r["llama_accepted"] for r in rs),
                "refused_places_agree": sum(1 for r in rs if r["same_place"] is True), "refused_places": sum(1 for r in rs if r["same_place"] is not None)}
    t = {"finals": count(res["finals"]), "drafts": count(res["drafts"]), "mutated": {k: count(v) for k, v in res["mutated"].items()}}
    allr = res["finals"] + res["drafts"] + [r for v in res["mutated"].values() for r in v]
    t["all"] = count(allr); t["tokens"] = sum(r["tokens"] for r in allr)
    return t

def markdown(res, runs):
    t = tally(res)
    a = t["all"]
    d = res["dll"]
    out = ["# Gate v3 grammar against llama.cpp b11700 itself (llama.dll, vocabulary only, CPU)", "",
           f"Library: llama.dll of the upstream b11700 release, sha256 `{d['llama.dll'][:16]}...` ({d['bytes']} bytes); vocabulary of `{d['gguf']}` ({d['n_vocab']} tokens), vocab-only, no backend loaded.", "",
           f"Runs: `{runs}`. {res['turns']} turns, one grammar each (median {int(statistics.median(res['sizes'])) / 1000:.1f} KB, largest {max(res['sizes']) / 1000:.1f} KB); "
           f"`llama_sampler_init_grammar` parsed {res['grammars']} of {res['turns']} (median {statistics.median(res['parse_ms']):.1f} ms to parse). "
           f"{a['texts']} texts, {t['tokens']} tokens walked ({res['untokenizable']} texts skipped: the tokenizer's pieces do not add up to the text).", "",
           "| texts | compared | llama.cpp = Machine on alive, accepted and the place | llama.cpp alive | llama.cpp accepted | refused texts with the same place |", "|---|---|---|---|---|---|"]
    rows = [("final answers gate v2 passed", t["finals"]), ("first drafts with findings", t["drafts"])] + [(f"mutations: {k}", v) for k, v in t["mutated"].items()] + [("**all**", a)]
    for name, c in rows: out.append(f"| {name} | {c['texts']} | {c['agree']} | {c['alive']} | {c['accepted']} | {c['refused_places_agree']} / {c['refused_places']} |")
    out += ["", f"Disagreements: {len(res['disagreements'])}." + ("" if not res["disagreements"] else " First ones:")]
    for d in res["disagreements"][:5]: out.append(f"- {d['who']}, {d['what']}: Machine alive={d['alive']} accepted={d['accepted']}, llama.cpp alive={d['llama_alive']} accepted={d['llama_accepted']}, same place {d['same_place']}: `{d['text'][:120]!r}`")
    if res["parse_failures"]: out += ["", "Grammars llama.cpp did not parse:"] + [f"- {f['who']}: {f['log'][-2:]}" for f in res["parse_failures"][:5]]
    if res["timing"]:
        g = res["timing_grammar"]
        out += ["", f"Cost of the call the server makes when the token it drew is refused (the grammar applied to all {res['n_vocab']} candidates), on this CPU, "
                    f"for the largest-reference turn ({g['rules']} rules, {g['bytes'] / 1000:.1f} KB), median of 5:", "", "| state | ms | candidates left |", "|---|---|---|"]
        for r in res["timing"]: out.append(f"| {r['state']} | {r['ms']} | {r['left']} |")
        prose = statistics.median(r["ms"] for r in res["timing"] if r["left"] > 1000)
        sp = res["draft_spans"]
        if sp:
            out += ["", f"Expected cost of the regeneration. The server draws a token, checks it alone against the grammar, and only if it is refused applies the grammar "
                        f"to the whole vocabulary and draws again. If the model wrote again what it wrote in its first draft, each refused span of that draft would cost one such "
                        f"call: the {len(sp)} stored first drafts have {statistics.mean(sp):.1f} refused spans on average (median {statistics.median(sp):g}, 90th percentile "
                        f"{sorted(sp)[int(0.9 * len(sp))]}, largest {max(sp)}), so about {statistics.mean(sp) * prose / 1000:.1f} s of grammar work per regeneration at {prose:.0f} ms "
                        f"a call" + (f", on top of the {statistics.median(res['regen_wall_s']):.1f} s median of the stored gate v2 regeneration call" if res["regen_wall_s"] else "") + ". "
                        f"The check of a drawn token that is allowed is cheap: the walk of the {res['walk']['tokens']} tokens above (tokenizer and clone of the sampler included) took {res['walk']['seconds']} s, "
                        f"{1e6 * res['walk']['seconds'] / max(res['walk']['tokens'], 1):.0f} microseconds a token."]
    return "\n".join(out) + "\n"

def main(argv=None):
    ap = argparse.ArgumentParser(description="The gate v3 grammar against llama.cpp b11700 (llama.dll, vocabulary only, CPU).")
    ap.add_argument("--runs", default=go.RUNS, help="stored gate v2 runs (default bench/runs/decision/v2)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N turns")
    ap.add_argument("--mutations", type=int, default=1, help="mutations per family per final answer (default 1)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    if not available(): print(f"llama.dll ({DLL_DIR}) or the GGUF ({GGUF}) is not here", file=sys.stderr); return 2
    ll = LlamaCpp()
    try:
        res = run(ll, go.load_turns(args.runs), limit=args.limit, seed=args.seed, mutations_per_family=args.mutations)
    finally: ll.close()
    if args.json: json.dump(res, sys.stdout, ensure_ascii=False, indent=1, default=str)
    else: print(markdown(res, args.runs))
    return 1 if res["disagreements"] or res["parse_failures"] else 0

if __name__ == "__main__":
    sys.exit(main())
