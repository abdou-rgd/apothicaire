# Gate v2: typed rendering

Status: implemented behind a flag (`APOTHICAIRE_GATE=v2`, default `v1`). First in-sample measurement on 2026-10-17 (`bench/runs/2026-10-17-gate-v2/`, 27B PTQ1_0, 25 exercises): 182/200 turns correct (v1: 195/200), 51/842 quantities shown as markers (6.1 %, all visible), 0 invalid tool calls, 13.7 s per turn (v1: 10.4). 12 of the 13 lost turns are compare answers that cite the difference and percentage from `analysis_compare` but no longer restate the linear AUC the scoring rule asks for; the rest are the false positives below. Markers by cause: 25 bare numbers absent from the user's message (21 of them the 20 % extrapolation threshold), 16 invented paths (`lambda_z_regression.adj_r_squared` and the like: the values exist under `lambda_z_candidates[selected]` but the reference grammar cannot name the selected candidate), 5 units typed after a reference, 3 `analyse 2, {{ref}}` (rule 6 false positive), 2 `demi-vies` (plural escapes the half-life exemption). Not yet measured on the frozen test set. Open before making v2 the default: rule 6 punctuation, the plural exemption, reference aliases for the selected λz candidate and the thresholds, and a decision on domain constants (closed list of named conventions rendered by the client, or keep the marker).
Code: `gate_v2.py` (pure Python, no dependency, no model), wiring in `apothicaire.py`, tests in `tests/test_gate_v2.py`
and `tests/test_agent_gate_v2.py`.

## Why

Gate v1 (`gate.py`) lets the model write numbers and checks afterwards that every number is in a tool result or in the
user's message. The audit of 2026-10-14 probed it with 15 adversarial sentences and found it blind to: a right number on
the wrong parameter, a changed unit, an inverted sign, numbers spelled in words, small integers (0-20) and years used as
exemptions, and 2-significant-digit coincidences with one of the ~100 numbers of a tool result. All of these are numbers
that *exist* somewhere in the sources; set membership cannot see what they are attached to.

Gate v2 changes who writes the number. The model writes a typed reference; a deterministic renderer replaces it with
the value and the unit read from the `structuredContent` of the MCP tool call, after checking the path against the tool's
`outputSchema` (from `tools/list`). The model never types a tool number, so a tool number cannot be wrong by construction.
What is left to the model is the *selection* (which call, which parameter, which field), and that is measurable.

## Reference syntax

A reference is `{{REF.PATH}}`: two braces, the `ref` written at the top of the tool result as the model sees it
(`"ref":"call_3"`, numbered over the whole chat memory), a dot, a path. Spaces inside the braces are ignored; `call3`,
`call-3` and `call 3` are read as `call_3`. Parameter names keep their PKNCA dots (`aucinf.obs`, `half.life`).

| the model writes | what is rendered |
|---|---|
| `{{call_3.cmax}}` | the parameter `cmax` of the only subject of the analysis of call 3, value at 6 significant digits + unit |
| `{{call_3.subject=2.cmax}}` | the same for subject `2` of a multi-subject analysis (each subject of the digest shows its own `ref`) |
| `{{call_3.aucinf.obs}}`, `{{call_3.lambda.z.n.points}}` | any computed PKNCA parameter (a `parameters.` prefix or a `.value` suffix is accepted and ignored) |
| `{{call_3.dose}}` | the dose of the subject, with the dose unit when the worksheet has one |
| `{{call_5.auclast.difference}}` | from `analysis_compare`: `b - a` with its unit; also `.percent` (relative difference, `%`), `.ratio`, `.a`, `.b` |
| `{{call_1.rows}}`, `{{call_1.subjects}}` | from `data_import`: fields of the worksheet (`worksheet.` prefix optional) |
| `{{call_3.spec.options.quality.max_extrapolated_percent}}` | any scalar of the `structuredContent` by its JSON path (`[i]` for lists); rendered without unit |

The renderer, not the model, chooses the display: 6 significant digits (the same rule as the digest, `numtext.value_text`),
decimal point by default, decimal comma when the chat language is French (`cfg["digest_lang"]`), the unit after a space.
A string field (a route, a label) is rendered as is; a list of scalars is joined by commas.

## Resolution rules (fail-closed)

Every reference must resolve, and everything else that looks like a quantity must be covered by the user's message.
A violation never passes through silently: the offending span is replaced by a visible marker (`⟦unresolved {{...}}⟧`,
`⟦unverified 12,5 mg/L⟧`, `⟦rejected: unit next to a reference: ...⟧`) and a badge lists the problems. In the agent, one
regeneration with a reminder is tried first (same loop as v1: reminder appended at the end of the messages, the better of
the two answers kept, the static prefix untouched).

1. **Unknown ref** (`call_9` when there is no ninth call, or the call failed and has no `structuredContent`): rejected.
2. **Wrong path**: a parameter name that is not in the analysis, a field of `analysis_compare` that is not one of
   `a b difference percent ratio`, a JSON path that leads nowhere or to an object: rejected, with the closest parameter
   name as a hint in the reminder.
3. **Not calculated / not comparable**: a parameter the engine did not compute (the result carries a reason, not a
   value) is rejected; the model must say that Caladrius did not return it.
4. **Schema check**: the canonical JSON path of the resolved value is walked through the tool's `outputSchema`
   (`$ref`/`$defs`, `oneOf`/`anyOf`, `properties`, `additionalProperties`, `items`). A path the schema forbids, or a leaf
   whose declared type disagrees with the value found, is rejected. A schema without property constraints
   (`analysis_compare` publishes `{"type":"object"}`) constrains nothing and the value is accepted on the data alone.
5. **Several subjects, no `subject=`**: rejected (ambiguous selection).
6. **Nothing next to a reference**: a digit, a unit (the closed unit table of gate v1 plus unit words such as
   `heures`, `litres`, `mg`), a sign, or an arithmetic operator (`× * / ^ +`, `-` or `+` with an operand, `x` between two
   operands) glued to or one space away from a reference is rejected. The renderer prints the unit and the sign; the model
   writing them is the only way it could change them. `=` and `:` are allowed ("Cmax = {{call_3.cmax}}").
7. **Bare numbers**: every number written in digits (extracted by gate v1's tokeniser) must equal, as an exact value, a
   number of the user's messages (CSV included; decimal comma and point are the same number; the sign is ignored as in
   v1). Tool results are NOT a source any more: a tool number typed by the model is rejected even if it is right.
   No rounding match: `7,0` does not match a user `6.98`.
8. **Exemptions**, counted apart and never rendered as values: list markers (`1.`, `2)`), `#17` message references,
   label numbers (`sujet 2`, `étape 3`, two digits at most), ISO dates, the `1` of `1/h`, a bare `10^k`, and
   **counts**: an integer 0-20 without unit, decimal or `%`, in digits or in words (`deux analyses`, `3 sujets`).
   A count is NOT exempt when it follows a PK label with a connector (`Cmax est de 10`, `la clairance : 5`,
   `half-life of 7`): that is a quantity and is rejected. Years are not exempt in v2.
9. **Numbers in words**: a numeral word followed by a unit word (`deux litres`, `trois heures`, `cinq pour cent`),
   a compound numeral (`trente-deux`, `deux cents`, `twenty five`), a numeral above twenty (`cent`, `mille`,
   `million`), a decimal in words (`deux virgule cinq`) and a multiple or fraction (`double`, `deux fois`, `moitié`,
   `demi` outside `demi-vie`, `tiers`, `quart`, `twice`, `half` outside `half-life`) are rejected.
   `un`, `une`, `one`, `a` are never read as numbers (articles).
10. **Malformed reference** (`{call_3.cmax}`, `{{call_3.cmax}`, `{{cmax}}` without a ref): rejected.

## What is now impossible by construction

| audit blind spot | v1 | v2 |
|---|---|---|
| right number, wrong parameter (`aucall` quoted as AUC(0-tlast)) | invisible: the number is in the tool result | the number is never typed; the reference names the parameter, so the rendered label is the selected parameter's. A wrong *selection* is still possible (`{{call_3.aucall}}` written where `auclast` was asked) but it is now a visible token in the transcript, scored by the oracle check against the asked parameter, not a number to be guessed at |
| unit changed (`mg/L` written as `ng/mL`) | invisible | impossible: the unit comes from the result (`unit` field or the worksheet units of the analysis); a unit written next to a reference is rejected (rule 6) |
| sign inverted (`-1.69` written as `1.69`) | invisible (sign ignored) | impossible for tool values: the renderer prints the sign; a sign written next to a reference is rejected |
| rounding chosen by the model (`2 128 760,0` as 8 digits) | passes when it rounds right | impossible: 6 significant digits, always |
| 2-digit coincidence with one of ~100 tool numbers (`−1,00 %` matching a tool `1.00`) | passes | tool numbers are not a source at all; the only coincidence left is with the user's own numbers, at exact value (no rounding), which is a far smaller and user-visible set |
| year exemption (`1900-2100`) as a channel | passes | no year exemption |
| small integer exemption (`Cmax est de 10`) | passes | rejected after a PK label; a bare count (`3 sujets`) stays exempt, see below |
| number spelled in words (`deux litres par heure`) | passes (no number seen) | rejected when followed by a unit word, compound, above twenty, decimal in words, or a multiple/fraction |
| converted value (`CL/F × dose × 10³`) | caught by set membership (the main v1 catch) | impossible to write: the result would be a bare number; arithmetic next to a reference is rejected |
| computed difference / percent / ratio | caught | impossible to write as a number; `{{call_5.x.difference}}` must come from `analysis_compare` |
| wrong AUC method / wrong options (ex07 `start: zero`) | invisible | still invisible to the gate: the reference points at a real analysis run with the wrong options. This is a tool-argument error, checked by the bench's tool-argument audit, not by any number gate |

## What remains (and how to measure it)

- **Selection errors.** The model can cite the wrong call (`call_2` for `call_3`, the linear analysis for the
  lin-up/log-down one), the wrong parameter (`aucall` for `auclast`, `cl.obs` for `cl.pred`), the wrong subject, the
  wrong compare field (`.ratio` for `.percent`). Every such error is now a reference token in the transcript, so it can
  be read and classified without guessing which number the model meant. The bench's oracle check (`bench/score.py`,
  `oracle_turn`) already scores "the number after the label is the one asked for"; on a v2 run it scores the rendered
  answer, and the raw answer (`first_answer` / the memory log) gives the reference that produced it.
- **Counts.** An unlabelled integer 0-20 (`10`, `dix`) is exempt as a count. The gate cannot tell `10 sujets` from a
  Cmax of 10 written with no label at all; the PK-label rule only covers the labelled case. Not a tool-number leak
  (the token is not matched against any tool number), but a channel for an invented small quantity.
- **User numbers.** A number of the user's message can be quoted anywhere, with any label, sign ignored. A user dose of
  `320` written as `Cmax = 320` passes. The oracle check sees it; the gate does not.
- **Free text.** Flags, quality judgements, explanations and the parameter *names* are the model's words, unchecked.
- **Powers of ten and symbols.** A bare `10^3` not adjacent to a reference is still exempt (v1 rule); `{{ref}} 10^3`
  written without an operator passes as two tokens. No number is invented, but the sentence can suggest a conversion.
- **Rendering vs. memory.** The chat memory stores the model's raw answer (references), the user sees the rendered one.
  Summaries of the memory therefore contain references; `zoom` shows them unrendered.

**Next measurement, on the frozen test set** (`agent/decision/PLAN.md`: 25 new exercises × phrasings, adjudicated
before any prediction is seen), v1 and v2 on the same exercises, same model, same sampling:

1. Gate counts as today (`numbers_unverified / numbers_total` before and after the regeneration), reported separately
   for references (`references_unresolved / references_total`) and for bare numbers.
2. **Selection error rate**: per turn that expects a parameter, whether the reference cited names the asked parameter
   (`auclast` for AUC(0-tlast), the compare `.difference` and `.percent` of the asked pair), the asked call (the analysis
   with the asked AUC method) and the asked subject. Read from the raw answer's references, not from the numbers.
   This is the number that v2 exists to make measurable; v1 cannot produce it.
3. **Regeneration rate and badge rate**: how often the 27B fails to write a resolvable reference at first (syntax
   errors, wrong parameter names) and how often the reminder fixes it. If the 27B cannot learn the syntax from the
   prompt, v2 is not viable at this size and that is a result.
4. **Prompt cost**: static prefix tokens (budget 2.5k, test `TestStaticPrefixBudget`) and prompt tokens per turn
   (the `ref` fields and the reminders add tokens to the dynamic part).
5. **Oracle check** on the rendered answers, same rules as `bench/score.py`, so v1 and v2 share one correctness figure.
