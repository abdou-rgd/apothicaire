# Apothicaire v0

Apothicaire is a pharmacokinetics (PK) assistant that runs entirely on one consumer PC, with nothing sent to the cloud. You give it a table of drug concentrations over time and ask questions in French or English: the half-life, the clearance, how two ways of computing the area under the curve differ.

**It never computes a number itself.** A language model reads the request, calls the [Caladrius](https://github.com/abdou-rgd/caladrius) engine, and explains what the engine returned. A number may reach the user only if Caladrius computed it or the user typed it, and a deterministic gate checks every final answer.

It is a prototype and an experiment. It is not a product and not a replacement for anything. It must never be used for a real patient or for a regulatory decision. The exercises it is tested on are synthetic, simulated by Caladrius, not from patients, and the results are counts with their limits stated in [docs/benchmark.md](docs/benchmark.md).

## What runs where

- **Model.** Bonsai 2 27B, a ternary model from PrismML, served locally by `llama-server` (`llama.cpp`) on `http://127.0.0.1:18435`. The pinned versions are in [docs/runtime.md](docs/runtime.md).
- **Memory.** [OptChat](https://github.com/abdou-rgd/optchat), an idea by Victor Taelin, keeps the whole chat on disk and shows the model recent messages verbatim and older ones merged into summary lines; nothing is deleted. `apothicaire.py` imports `../optchat/optchat.py` unchanged.
- **Numbers.** Caladrius, a calculation engine in Rust, reached over the Model Context Protocol (MCP) by `caladrius-mcp` on stdio: import a table, run a non-compartmental analysis, read a result, export a table, compare two analyses.
- **Check.** `gate.py`, plain Python with no model, and a benchmark in `bench/`.

The code is written by AI coding agents (Claude Code, and a DeepSeek agent as a second contributor) under a written contract, with a task board and a human who decides what is published. The author is Abdallah (abdou-rgd on GitHub); what went wrong along the way is in [docs/history.md](docs/history.md).

**Sources, tools and credits.** The engine's own sources are in `ATTRIBUTION.md` of the Caladrius repository; the short version for this repository:

- Model and runtime: Bonsai 2 27B and the PrismML fork of `llama.cpp` (PrismML); `llama.cpp` and `ggml` (Georgi Gerganov and contributors).
- Memory: the OptChat gist by Victor Taelin.
- Calculation: Caladrius, reached through the Model Context Protocol (MCP), the open protocol for connecting tools to models.
- Candidates and next step: Underdog Saluki 27B (Conway Research), a model to compare; the `d1` decision models (Liquid AI) and the decision-model recipe (Unsloth).
- The agents that wrote the code: Claude Code (Anthropic) and the DeepSeek Harness `dsh`. The agent itself is Python.
- No data from the commercial reference software is used here; the exercises are synthetic.

## Run

Apothicaire needs the sibling checkouts `../caladrius` and `../optchat` next to this repository, and Python with `httpx`. The model server needs a graphics card; the tests do not.

```bash
pip install httpx==0.28.1
# 1. the engine (once)
(cd ../caladrius && cargo build --release -p caladrius-mcp --target-dir target/agent-apothicaire)
# 2. the model server (upstream llama.cpp b11700, Bonsai 2 27B Q2_0, http://127.0.0.1:18435)
bash ../optchat/start_servers_upstream.sh && curl http://127.0.0.1:18435/health
# 3. the agent
python apothicaire.py chat            # interactive, memory in data/
python apothicaire.py tools           # exposed tools and static prompt size
python run_exo1.py                    # the demo -> runs/<date>-exo1.md
# 4. stop the server (PowerShell; taskkill does nothing under Git Bash)
powershell -Command "Stop-Process -Name llama-server -Force"
```

Environment: `APOTHICAIRE_MCP` (path of the `caladrius-mcp` binary, default `../caladrius/target/agent-apothicaire/release/caladrius-mcp.exe`), `APOTHICAIRE_DATA` (memory folder), `OPTCHAT_URL`. Python 3.12 + httpx only. Tests use `unittest` (pytest is not installed).

The paths in the server script point to the author's PC. The pinned runtimes, the full commands and the benchmark commands are in [docs/runtime.md](docs/runtime.md).

## Gates

Every final answer goes through a deterministic number gate. It flags any number that is not found in a tool result or in the user's own message; the model is asked once to regenerate, and if a flagged number remains, a badge listing it is appended to the answer.

- **Gate v1** (`gate.py`) is the default and the demo gate.
- **Gate v2** (`gate_v2.py`, typed rendering, specified in [GATE_V2.md](GATE_V2.md)) runs only with `APOTHICAIRE_GATE=v2`. Gate v3 (`gate_v3.py`, `APOTHICAIRE_GATE=v3`) is exploratory. The rule, its known limits and the results are in [docs/gates.md](docs/gates.md).

## Tests

```bash
python -m unittest discover -s tests     # unittest only, no pytest
```

CI (`.github/workflows/ci.yml`) runs them on every pull request and push to main, with `optchat` and `caladrius` checked out next to this repository and `caladrius-mcp` built from source. The engine tests skip without the binary, many modules fail to import without `../optchat`, and the tests that need `llama-server` or the decision datasets skip elsewhere. What each file covers: [docs/tests.md](docs/tests.md).

## Where to read more

- [docs/benchmark.md](docs/benchmark.md): the benchmark and demo results, their history and their limits.
- [docs/gates.md](docs/gates.md) and [GATE_V2.md](GATE_V2.md): the number gate and the specification of gate v2.
- [docs/runtime.md](docs/runtime.md): the pinned runtimes and the full run commands.
- [docs/design.md](docs/design.md): the files of this repository and the design choices.
- [docs/tests.md](docs/tests.md), [docs/history.md](docs/history.md), [docs/background.md](docs/background.md): the tests, the known problems with their dated fixes, the longer introduction.
- [bench/](bench/): the benchmark code and runs, and [bench/FROZEN_SET.md](bench/FROZEN_SET.md), which governs the frozen set.
- [decision/](decision/): the decision-model spike ([PLAN.md](decision/PLAN.md), [README.md](decision/README.md)).
- [Caladrius](https://github.com/abdou-rgd/caladrius) and [OptChat](https://github.com/abdou-rgd/optchat): the engine and the memory.

## License

Apothicaire is licensed under either of the [MIT license](LICENSE-MIT) or the [Apache License, Version 2.0](LICENSE-APACHE), at your option, like Caladrius.

This covers the code of this repository only. It does not cover:
- the `optchat` memory module, imported from a sibling folder: its own repository, <https://github.com/abdou-rgd/optchat>, MIT OR Apache-2.0;
- the model weights and inference builds the scripts download or call, each under its own terms; the Liquid AI `d1` models, used only in the zero-shot baseline of the decision spike, are described in [docs/background.md](docs/background.md).
