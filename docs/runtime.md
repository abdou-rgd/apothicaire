# Runtime and run commands

The pinned runtimes (demo runtime, PrismML fork block, engine block) that the figures of benchmark.md were measured with, and the full run commands, moved unchanged from the former README.

## What runs where

The first working version of Apothicaire, the DMPK agent of Officina: **Bonsai 2 27B** (local llama.cpp: the PrismML fork for the first runs, upstream b11700 from the run of 2026-10-17 on and for the demo, see "Pinned versions") + the **OptChat** endless-chat memory (`../optchat/optchat.py`, imported unchanged) + the **Caladrius** engine reached as MCP tools (`caladrius-mcp` over stdio). The model never computes pharmacokinetic numbers: it imports the data, calls Caladrius, and explains the results. Everything runs on the local RTX 3060. Since 2026-10-09 every final answer goes through a deterministic number gate ([gates.md](gates.md)).

## Pinned versions (what the numbers of [benchmark.md](benchmark.md) were measured with)

**Demo runtime** (as of 2026-10-21, entry of that date in `bench/frozen/LEDGER.md`; first upstream run 2026-10-17, `bench/runs/2026-10-17-27b-upstream/NOTE.md`):

- **llama.cpp**: upstream b11700 (23f7aabc1), CUDA 12.4 build, no PrismML fork. Started by `bash ../optchat/start_servers_upstream.sh` (port 18435; its two paths point to the author's PC).
- **Model**: Bonsai 2 27B in the Q2_0 packing, `Ternary-Bonsai-2-27B-Q2_0-prism-fork-required.gguf` (file name as on disk; "prism-fork-required" in it is outdated), 7 626 008 928 bytes.
- **Server flags**: those of the fork block below plus `--reasoning-budget 4096`. The ledger runs use temperature 0.3, thinking off.

**PrismML fork block: the runtime of the runs of 2026-10-08 to 2026-10-18 reported in [benchmark.md](benchmark.md) (demo runs, 2026-10-09, 2026-10-09b, gate v2 on 2026-10-17 and 2026-10-18), except the upstream runs of 2026-10-17; `../optchat/start_servers.sh` is kept only to reproduce them.**

- **llama.cpp**: the PrismML fork, CUDA build, `C:\Users\abdou\mitsuba\llama\llama-server.exe`; `llama-server --version` prints `version: 0.2.0-dev (build 10743, commit adfffbe41)`, built with MSVC 19.44.35229.0 for Windows AMD64.
- **Model**: `Ternary-Bonsai-2-27B-PTQ1_0.gguf` (file name as on disk; format `PTQ1_0`), 5 946 648 928 bytes, SHA-256 `53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3`.
- **Server flags** (`../optchat/start_servers.sh`): `-c 24576 -np 2 -ngl 99 --jinja -fa on -ctk q8_0 -ctv q8_0 --slots --metrics` (2 slots of 12 288 tokens; slot 0 chat, slot 1 compaction). Sampling: temperature 0.3, no fixed seed, so two runs of the same script differ.

**Engine, both runtimes.**

- **Engine**: `caladrius-mcp` 0.1.0; the engine registry holds 25 commands as of 2026-10-29 (the golden `tests/golden/tools_list.json` of 2026-10-09 lists 21 tools); the golden files were regenerated on 2026-10-09 from Caladrius commit `be3625e` (`tests/golden/*.json` store it; the working tree had uncommitted UI changes of another agent, no engine change; the only differences with the earlier goldens are the commit and the engine's newer `tools/list`).

## Run

```bash
# 1. the engine (once; absolute target dir)
cd ../caladrius && CARGO_TARGET_DIR=C:/Users/abdou/apothicaire/caladrius/target/agent-apothicaire cargo build --release -p caladrius-mcp
# 2. the model server (Bonsai 2 27B Q2_0 on upstream llama.cpp b11700, 2 slots of 12k tokens, http://127.0.0.1:18435; ~15 s)
bash ../optchat/start_servers_upstream.sh && curl http://127.0.0.1:18435/health
# 3. the agent
python apothicaire.py chat            # interactive, memory in data/
python apothicaire.py tools           # exposed tools and static prompt size
python run_exo1.py                    # the demo -> runs/<date>-exo1.md
# 4. stop the server (PowerShell; taskkill does nothing under Git Bash)
powershell -Command "Stop-Process -Name llama-server -Force"
# the benchmark (model server needed; ~3 min per exercise)
python bench/make_exercises.py        # regenerates bench/exercises/ (deterministic; needs the built caladrius-mcp)
python bench/run_bench.py --date 2026-10-09 [--first 10] [--resume]   # -> bench/runs/<date>/report.md
python bench/run_bench.py --date 2026-10-09 --rescore            # scores + oracle check of the stored answers, no model (then report.md / report.json)
python bench/run_bench.py --date 2026-10-09 --tool-arg-audit      # every nca_run / data_import call whose arguments differ from the script's intent
# tests (no model server needed; test_agent_gate.py needs the built caladrius-mcp and is skipped without it)
python -m unittest discover -s tests
```
