# Apothicaire: notes for Claude Code

The local DMPK assistant: Bonsai 2 27B on llama.cpp, OptChat memory, Caladrius reached as MCP tools.
The model never computes a pharmacokinetic number; Caladrius is the only source of numbers and a gate
checks every final answer.

- **Gates.** `gate.py` (v1) is the default and the demo gate. `gate_v2.py` (typed rendering,
  `GATE_V2.md`) runs only with `APOTHICAIRE_GATE=v2`. `--gate nolm` in `bench/run_frozen.py` is the
  decider-only arm (`bench/NO_LM_ARM.md`). `gate_v3.py` (gate v2 plus a GBNF grammar on the one
  regeneration, `bench/GRAMMAR_ARM.md`) runs only with `APOTHICAIRE_GATE=v3` and `--gate v3` in
  `bench/run_frozen.py`: exploratory, development tier only.
- **Siblings.** `apothicaire.py` imports `../optchat/optchat.py` unchanged and starts
  `../caladrius/target/agent-apothicaire/release/caladrius-mcp`. Both checkouts must sit next to this
  one. On the PC this repository is the folder `agent/`.

Tests, as CI runs them (`.github/workflows/ci.yml`):

```sh
pip install httpx==0.28.1
(cd ../caladrius && cargo build --release -p caladrius-mcp --target-dir target/agent-apothicaire)
python -m unittest discover -s tests     # unittest only, no pytest
git diff --exit-code                     # the tests leave tracked files unchanged
```

Without the binary the engine tests skip silently; without `../optchat` many modules fail to import.
Tests that need `llama-server`, the decision datasets or `datasets` skip outside the PC.

- **Cloud or PC.** `llama-server`, benchmark runs and Unsloth training happen only on the PC
  (llama.cpp b11700, 27B Q2_0, port 18435; for `.venv-unsloth`, `HF_HOME`, `TMP` and `TEMP` under
  `agent/`). Elsewhere, prepare the command and say so. Run outputs in `bench/runs/` and
  `decision/runs/` are never written by hand.
- **Frozen set.** `bench/FROZEN_SET.md` governs it; thresholds are fixed before any run and every event
  goes into `bench/frozen/LEDGER.md`. `bench/frozen/*/wordings.json` is git-ignored and written by a
  human: never open, generate or commit it. No trained-model prediction on the 74 requests of
  `decision/ood/gold.jsonl` before the frozen run (`FROZEN_SET.md`).
- **README.** It states no figure that a run can change (no count, ratio or percentage): each figure lives
  in its owner file under `docs/` (or `bench/`, `decision/`) and the README links to it (caladrius T-124).
