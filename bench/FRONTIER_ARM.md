# The same agent on a frontier model: the frontier API arm of the frozen set (pre-registration draft, 2026-10-22)

Status: draft, written before any hosted model has answered any exercise, development or frozen. It becomes binding with the system
freeze of [`FROZEN_SET.md`](FROZEN_SET.md) §9, and nothing in it changes after that except through dated entries in
`bench/frozen/LEDGER.md`. It adds configurations; it changes nothing in the demo-gate decision of §8, in C1, in C2 or in the
decider-only arm of [`NO_LM_ARM.md`](NO_LM_ARM.md).

## 1. Question

Abdou's question (2026-10-22): how far behind a frontier model is the local 27B, when both sit in the same agent? The intended
reading is not "which model is cleverer". In Apothicaire the numbers come from Caladrius and the gate checks every final answer;
the model picks the tool, fills its arguments and writes the sentence around the engine's values. If a much larger model passes about
as many exercises, the task has been fitted to a small local model, which is the design's claim. If it passes many more, the gap is in
routing and wording, and the outcomes by turn kind say where.

> **F.** On the eight turn kinds of the frozen set, the agent with gate v1 on a hosted frontier model passes at most 5 more
> exercises than C1 (the 27B with the gate of §8), under the same rubric, on the same exercises, wordings and seed labels.

The figure is read as a triplet, always shown together:

| Configuration | Answer path | What it says |
|---|---|---|
| `nolm` | decision model, deterministic harness, Caladrius, templates (NO_LM_ARM.md) | how far a path with no language model goes |
| C1 | the 27B on the PC, gate v1 | the system as shipped: local, offline, synthetic or private data never leave the machine |
| `v1+<model>` | the same agent, prompts, tools and gate, on a hosted model | what a frontier model adds on this task |

## 2. The arm

`bench/api_model.py` puts the Anthropic Messages API behind the client optchat already uses (`optchat.LLM`'s interface), so
`bench/run_frozen.py run --api-model <id>` runs the unchanged agent and stores the run as configuration `<gate>+<id>`
(`v1+claude-sonnet-5-5`). The analysis reads it next to the other configurations.

| Part | Same as C1 | Different, and why |
|---|---|---|
| system prompt, the five exposed Caladrius tools and their schemas, tool-call refusals and caps | yes | |
| OptChat memory: log, digest, view, compaction settings (`optchat.CFG`), `max_tool_rounds` 8 | yes | |
| gate v1, its one regeneration, the rubric of §6.2, the analysis of §11 | yes | |
| answer budget: `max_tokens` 1,200 | yes | Claude Opus 5.5 cannot turn thinking off; it gets 8,000 tokens more for its thinking so the answer keeps its 1,200 |
| sampling | no | the API takes no temperature, top-p or seed: provider sampling; seeds 1 to 3 only label the three repetitions |
| thinking | off where the model allows it | Sonnet 5.5: `between_tools` (its lowest setting); Opus 5.5: adaptive at its declared effort |
| a round without tools (the last allowed round, the regeneration) | same effect | the API refuses a history with tool calls and no tool definitions, so the tools are sent with `tool_choice: none` |
| compaction's grammar | same effect | the JSON schema goes to structured outputs without `minItems`/`maxItems`; optchat already checks the number of lines |
| thinking blocks | not applicable | sent back only inside the current tool loop; earlier turns are rebuilt from text and calls, as the 27B sees them |
| refusals | not applicable | a refusal is a failed call (the turn is ERROR and counts); no fallback model, so the arm measures one model |
| prompt caching | not applicable | automatic caching on the Messages API; it changes the cost, not the answers |

Declared models, in the order they run:

| Model | id | Thinking | Effort | Price per million tokens (input / output / cache read) |
|---|---|---|---|---|
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | off (`between_tools`) | high (the highest `between_tools` accepts) | 2.00 / 10.00 / 0.20 USD |
| Claude Opus 5.5 | `claude-opus-5-5` | adaptive (cannot be off) | medium (the model's default) | 4.00 / 20.00 / 0.20 USD |

A cache write costs 1.25 times the input price. The run records, per seed, the declared row, the model the API says answered
(`served_by`), the token counts, the cost and every refusal in `api_usage.json`.

No prompt, tool description, cap or harness rule is changed for this arm, now or later. A configuration tuned for a hosted model would
be a new arm, declared in a dated amendment before it runs.

## 3. Development tier: the exploratory figure

The development set (25 exercises, wordings of `scripts.py`, seeds 1 to 3) runs first, in a cloud session, without any frozen file.

- **It is in-sample for the 27B.** The prompts, the gate and the caps were tuned on these exercises with the 27B; nothing was tuned
  for a hosted model. The comparison therefore leans towards the 27B, and every figure from it is labelled "development set,
  in-sample for the 27B, exploratory".
- **Reference:** the v1 runs of the gate decision, `bench/runs/decision/v1/` (583 / 600 turns CORRECT, 14 / 25 exercises passed on
  all three seeds, 3 / 25 with an unverifiable quantity shown), read by the same analysis (`--with bench/runs/decision:v1`), never
  re-run or rewritten.
- **Order:** Claude Sonnet 5.5 first. Claude Opus 5.5 runs only if Sonnet passes at most 3 more development exercises than v1
  (strict rule): a small gap is where a larger model could still change the reading; a large one is already the answer.
- **What the slide may say**, in this form and no other: "Development set, 25 exercises x 3 runs, in-sample for the 27B: the local
  27B passes A / 25 exercises (P % of turns correct), Claude Sonnet 5.5 passes B / 25 (Q %), the decider-only arm C / 25." The gap
  is given in exercises (B − A) and in percentage points of correct turns (Q − P), never as a ratio of pass rates, and never without
  the denominators. The cost of the run is given next to it.

## 4. Frozen tiers: the real figure

- **Demo tier (40 exercises).** After C1 and C2 on every seed and after `nolm` (FROZEN_SET.md §10.2), with the same wordings file
  and wording seed. Like every configuration other than C1, it is descriptive in this tier; the reading of §5 is written in
  `bench/frozen/demo/RESULTS.md` under its own heading. This is the figure that replaces the development one once it exists. The
  frozen wordings are sent to the provider at run time, as they are sent to the 27B; they are never sent before the run.
- **PAGE tier.** The declared comparison: the frontier arm against C1 with the paired test of §11.3, under the reading of §5, after a
  dated amendment fixing the model ids and settings of §2 before the run.

## 5. Reading, decided before any result

Let p(X) be the number of exercises configuration X passes under the strict rule (all 8 turns CORRECT on every seed), on the same
exercises.

| Result | Reading |
|---|---|
| p(F) − p(C1) ≤ 5 and p(C1) − p(F) ≤ 5 | **no difference detected** (fewer than 6 discordant exercises cannot reach p < 0.05, §11.3): F holds; the 27B is not detectably behind on these eight kinds |
| p(F) ≥ p(C1) + 6, the discordant exercises all going to F | **the 27B is behind**: F fails; the outcomes by turn kind say whether the gap is in routing (tool calls), reading (values on the wrong parameter) or wording (verdicts) |
| p(C1) ≥ p(F) + 6, the discordant exercises all going to C1 | **the harness is fitted to the 27B**: a statement about the prompts and caps, not about the models |
| a gap of 6 or more with discordant exercises in both directions | the exact McNemar p decides between "no difference detected" (p ≥ 0.05) and the row of the larger side |

Endpoint 2 (exercises with an unverifiable quantity shown) is printed next to it for every configuration of the triplet. Whatever the
reading, the demo shows the 27B with C1's gate: this arm is a comparison, not a candidate.

## 6. What this arm does not measure

First, the hosted model is not tested at its best: it runs a prompt written for a 27B, without thinking where that can be turned off,
and with a 1,200-token answer budget. A lower score says "in this agent", not "this model is worse". Second, the provider's sampling
has no seed, so the three repetitions are not replayable and the replay check of §10.1 does not apply; the model behind an id can also
change, which `served_by` and the run date record but cannot prevent. Third, time per turn and cost compare a local GPU with a data
centre and are descriptive only. Fourth, the 27B's main property here, that data never leave the machine, is not something a benchmark
scores; the arm only runs synthetic exercises and is never run on real data.

## 7. Running

The key is an environment variable, `ANTHROPIC_API_KEY`, set as a secret of the environment that runs the arm (a cloud session or
the PC), never written in a file, a commit, a log or a chat. The client reads it, sends it only to `https://api.anthropic.com` (or
`APOTHICAIRE_API_BASE_URL`), and ignores `ANTHROPIC_BASE_URL`, which a cloud coding session sets for its own use. No GPU and no
llama-server are needed; the caladrius-mcp binary is.

```bash
# development tier, exploratory (§3): Sonnet first, then Opus if the rule of §3 says so
python bench/run_frozen.py run --tier dev --gate v1 --seeds 1,2,3 --api-model claude-sonnet-5-5 --out bench/runs/frontier-dev-<date>
python bench/run_frozen.py run --tier dev --gate v1 --seeds 1,2,3 --api-model claude-opus-5-5 --out bench/runs/frontier-dev-<date>
python bench/run_frozen.py analyse --tier dev --out bench/runs/frontier-dev-<date> --with bench/runs/decision:v1 --c1 v1 --c2 v1+claude-sonnet-5-5

# demo tier (§4), after C1, C2 and nolm: the output joins them under bench/frozen/demo/runs/
python bench/run_frozen.py run --tier demo --gate v1 --seeds 1,2,3 --api-model claude-sonnet-5-5 --wordings bench/frozen/demo/wordings.json --wording-seed <N>
python bench/run_frozen.py analyse --tier demo --c1 <C1> --c2 <C2>
```

Size, from the v1 development runs: 600 turns, about 1,030 model calls plus compaction, a first prompt of about 3,000 tokens and
5,100 tokens per call at the median (counted by the 27B's tokenizer; Claude's may count more). Upper bounds without any cache hit:
about 15 USD for Claude Sonnet 5.5 and 35 USD for Claude Opus 5.5 per three-seed run; prompt caching should bring both well below.
The measured cost is in `api_usage.json`, and the console prints it after each exercise.
