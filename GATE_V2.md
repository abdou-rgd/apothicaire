# Gate v2: typed rendering

Status: implemented behind a flag (`APOTHICAIRE_GATE=v2`, default `v1`). First in-sample measurement on 2026-10-17 (`bench/runs/2026-10-17-gate-v2/`, 27B PTQ1_0, 25 exercises): 182/200 turns correct (v1: 195/200), 51/842 quantities shown as markers (6.1 %, all visible), 0 invalid tool calls, 13.7 s per turn (v1: 10.4). 12 of the 13 lost turns are compare answers that cite the difference and percentage from `analysis_compare` but no longer restate the linear AUC the scoring rule asks for; the rest are the false positives below. Markers by cause: 25 bare numbers absent from the user's message (21 of them the 20 % extrapolation threshold), 16 invented paths (`lambda_z_regression.adj_r_squared` and the like: the values exist under `lambda_z_candidates[selected]` but the reference grammar cannot name the selected candidate), 5 units typed after a reference, 3 `analyse 2, {{ref}}` (rule 6 false positive), 2 `demi-vies` (plural escapes the half-life exemption). Not yet measured on the frozen test set. Fixed after that run (commit 201e782 and the aliases below): rule 6 punctuation, the plural exemption, the aliases `lambda_z.<field>` (selected λz candidate) and `thresholds.<name>` (quality thresholds), named in the v2 system addition (prefix proxy count 2 499 of the 2 500 budget, `TestStaticPrefixBudget`). Domain constants decided by Abdou on 2026-10-17: a closed list of named conventions rendered by the client (`{{convention.<name>}}`, section "Named conventions"); a bare `20 %` typed by the model stays rejected, the reminder names the reference to write.
Second in-sample measurement on 2026-10-17, after the aliases and the conventions (`bench/runs/2026-10-18-gate-v2b/`, commits d08dc28 and 20aeb09, same model, same 25 exercises): 183/200 turns correct (v1 run 2026-10-09b: 195/200; first v2 run: 182/200), 17/874 quantities shown as markers (1.9 %, all visible; first run 51/842 = 6.1 %), 0 invalid tool calls, 48 regenerations (was 62), 9 turns shown with a badge (was 36), 13.9 s per turn (first run 13.7, v1 10.4), static prefix 2 500 tokens exactly (v1 2 434). Markers by cause: 15 units typed after a reference (11 `h` after `lambda_z.time_first` / `time_last`, 2 `%` after `thresholds.max_extrapolated_percent`, 1 `%` after `aucpext.obs`, 1 `min` after `time_last`), 1 `+` between two references; 0 invented paths (was 16), 0 bare domain constants (was 25), 0 rule-6 or plural false positives (was 5). Aliases written by the model: `thresholds.*` 44 times, `lambda_z.*` 31, `{{convention.*}}` once. Lost turns: 13 compare (10 do not restate the linear AUC(0-tlast) the scoring rule asks for, 3 the lin-up/log-down one; the engine's difference and percentage are cited) and 4 recall (unit missing; v1 lost 3 recall and 2 compare turns). Decision rule (v2 default only if at least as correct as v1 where no marker is shown): on the 191 marker-free turns v2 is correct on 174 and v1 on 186 of the same turns, so v2 does **not** become the default yet. The gap is the compare phrasing, not the number channel: the oracle check is 157/175 in both v2 runs, and the number channel is now closed to within the units-after-a-reference habit (rule 6), the last cause left.
**Closed typed renderer (2026-10-19, cards T-054 to T-058, red-team triage rows RT-A1, RT-A9, RT-A6, RT-A2, RT-A10).** The five
red-team reports of 2026-10-17/19 found that the renderer printed value and unit only (a wrong parameter of the same unit read
as verified), that any JSON path of a result was citable (a model-written analysis name "Cmax = 999 mg/L" rendered as a
result; a raw path rendered without unit; a non-selected λz candidate was citable), that a contradictory unit passed unless it
was glued after the reference, and that a sign outside bold, signs and multipliers in words, English numerals and Unicode
numerals were not seen. The renderer now prints a closed typed assertion (section "Typed assertion"), accepts only the
quantities of closed tables (rule 12), rejects a contradictory unit in the clause or the table column (rule 11) and reads
signs through Markdown emphasis, signs and multipliers in words and Unicode numerals (rules 6, 9, 13). The probes are mutation
tests in `tests/test_gate_v2.py` (`TestRedTeamMutations`). **The two measurements above predate this change**; the next one
runs on the frozen set.
Code: `gate_v2.py` (pure Python, no dependency, no model), wiring in `apothicaire.py`, tests in `tests/test_gate_v2.py`
and `tests/test_agent_gate_v2.py`.

## Why

Gate v1 (`gate.py`) lets the model write numbers and checks afterwards that every number is in a tool result or in the
user's message. The audit of 2026-10-14 probed it with 15 adversarial sentences and found it blind to: a right number on
the wrong parameter, a changed unit, an inverted sign, numbers spelled in words, small integers (0-20) and years used as
exemptions, and 2-significant-digit coincidences with one of the ~100 numbers of a tool result. All of these are numbers
that *exist* somewhere in the sources; set membership cannot see what they are attached to.

Gate v2 changes who writes the number. The model writes a typed reference; a deterministic renderer replaces it with
the engine's value, its sign, its unit and the name of the quantity, read from the `structuredContent` of the MCP tool call
after checking the path against the tool's `outputSchema` (from `tools/list`). The model never types a tool number, so the
digits, the sign and the unit printed next to a reference are the engine's. What is left to the model is the *selection*
(which call, which parameter, which field) and the words around the reference, and the rendered name makes a wrong selection
visible to the reader.

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
| `{{call_3.lambda_z.adj_r_squared}}` | **alias**: a field of the *selected* λz regression candidate (`outcome.ok.lambda_z_candidates[j]` with `selected: true`); also `.r_squared`, `.n_points`, `.time_first`, `.time_last` (time unit), `.lambda_z` (its unit), `.intercept`; `subject=L.lambda_z.…` for several subjects. Fail-closed when no candidate is selected (or several are): the model must say Caladrius did not retain one |
| `{{call_3.thresholds.max_extrapolated_percent}}` | **alias**: a quality threshold echoed by the result (`spec.options.quality.<name>`), `%` for the `*_percent` ones, nothing for the others; rejected when the result carries no thresholds |
| `{{convention.max_extrapolated_percent}}` | **named convention**: a domain constant from the closed table below, rendered with its unit; when a citable analysis echoes the threshold, that value is rendered instead (see "Named conventions") |

Nothing else is citable (rule 12, since 2026-10-19): no raw JSON path (`{{call_3.spec.options.quality.max_extrapolated_percent}}`,
`{{call_3.result.subjects[0].outcome.ok.parameters[0].value.value}}`, `{{call_3.outcome.ok.lambda_z_candidates[1].lambda_z}}`),
no text field (`name`, `label`, `route`, `subject`, `status`), nothing from `data_import` (the worksheet description is the
user's and the model's, not a computed quantity) and nothing from the other tools. The same values are cited by their typed
names (`thresholds.<name>`, `lambda_z.<field>`, the parameter) or said in words.

Aliases exist because the plain path syntax cannot name "the selected candidate" (its index varies) and the model should
not have to know where the options are echoed. The digest's own labels (`lambda_z_regression.adj_r_squared`,
`options_used.quality_thresholds.max_extrapolated_percent`, `lambda.z_regression.r.squared`) are **not** paths: they are
rejected (rule 2) with the alias as the closest name in the reminder (`closest: lambda_z.adj_r_squared`). The five
PKNCA parameters `adj.r.squared`, `r.squared`, `lambda.z.n.points`, `lambda.z.time.first`, `lambda.z.time.last` keep
resolving as before and carry the same values as the selected candidate; the alias is the second name, not a second value.

## Typed assertion

The renderer, not the model, writes everything about the quantity: 6 significant digits (the same rule as the digest,
`numtext.value_text`), the engine's sign, decimal point by default, decimal comma when the chat language is French
(`cfg["digest_lang"]`), the unit after a space, then the name of the quantity in brackets, and the subject when the analysis
has several:

| the model writes | the user reads |
|---|---|
| `AUC(0-tlast) = {{call_3.auclast}}` | `AUC(0-tlast) = 98.7654 h*ng/mL [AUClast]` |
| `AUC(0-tlast) = {{call_3.aucinf.obs}}` (a selection error) | `AUC(0-tlast) = 123.457 h*ng/mL [AUCinf,obs]`: the mismatch is on the page |
| `{{call_3.subject=2.cmax}}` | `9.25 ng/mL [Cmax, subject 2]` |
| `{{call_5.auclast.difference}}`, `.percent`, `.ratio` | `-1.75309 h*ng/mL [AUClast, b−a]`, `-1.775 % [AUClast, (b−a)/a]`, `0.98225 [AUClast, b/a]` |
| `{{call_3.lambda_z.adj_r_squared}}` | `0.99876 [adjusted R² of λz]` |
| `{{call_3.thresholds.max_extrapolated_percent}}`, `{{convention.max_extrapolated_percent}}` | `20 % [threshold: max AUC%extrap]`, `20 % [convention: max AUC%extrap]` |

The names come from closed tables in `gate_v2.py`: `PARAMETERS` (the 61 PKNCA names Caladrius returns, from
`caladrius-nca/src/units.rs` and the goldens, `.dn` included), the λz fields, the compare fields and `CONVENTIONS`. A
parameter the engine returns that the table does not name is not renderable (fail-closed) until it is added. Only finite
numbers are rendered: `render_value` refuses a string, a boolean, a list or a NaN. `check` also returns the assertions it
rendered (`assertions`: ref, analysis id, subject, quantity, printed name, value, unit, canonical path), which is what the
selection-error measurement reads. The chat memory keeps the references; the bracketed name exists only in the rendered text.

## Named conventions

Decision of Abdou, 2026-10-17: the domain constants a DMPK answer quotes (the 20 % limit on the extrapolated share of
AUCinf, the 0.9 adjusted R²) are never typed by the model. They are a **closed table** in `gate_v2.py` (`CONVENTIONS`,
a module-level dict, nothing configurable at runtime); the model writes `{{convention.<name>}}` and the renderer prints
the value and the unit. The table holds only conventions with a citable source and the values are the engine's own
defaults (`caladrius-nca/src/options.rs`, `QualityThresholds::default`; spec rule NCA-LZ-12b, which records them as
PKNCA's conventions): if the engine's value ever differed from a textbook one, the engine would win and the source
column would say so.

| name | value | unit | source |
|---|---|---|---|
| `max_extrapolated_percent` | 20 | % | PKNCA exclusion helper `max.aucinf.pext` (20 %): the usual upper limit on the share of AUCinf that is extrapolated; Caladrius default `quality.max_extrapolated_percent` |
| `min_adj_r_squared` | 0.9 | | PKNCA exclusion helper `min.hl.r.squared` (0.9) on the adjusted R² of the terminal regression; Caladrius default `quality.min_adj_r_squared` |
| `min_span_ratio` | 2 | | PKNCA exclusion helper `min.span.ratio` (2): the regression window must span at least two half-lives; Caladrius default `quality.min_span_ratio` |
| `min_points` | 3 | | PKNCA `min.hl.points` (3): fewest points in a terminal regression; Caladrius defaults `quality.min_points` and `lambda_z.min_points` |

**Precedence.** A convention is a fallback, never a shadow: when a citable analysis of the chat echoes the threshold
(`spec.options.quality.<name>`, the `thresholds.<name>` alias), `{{convention.<name>}}` resolves to **that** value, with
the analysis's path, so a threshold the user changed (`max_extrapolated_percent: 25`) is rendered as 25 %, not 20 %.
When two analyses carry different values the convention is ambiguous and rejected; the hint names the
`{{call_N.thresholds.<name>}}` references to choose from. The table is used only when no analysis carries the threshold
(a question asked before any analysis, or a result without options). The reminder prefers the `thresholds.` alias for
the same reason. An unknown convention name is rejected like an unknown path, with the closest name as a hint. A bare
`20 %` typed by the model stays rejected (rule 7); the finding's hint and the reminder name the reference to write
(`{{call_N.thresholds.max_extrapolated_percent}}` when an analysis echoes it, else `{{convention.max_extrapolated_percent}}`).
Not in the table: PKNCA's λz tolerance `adj_r_squared_factor` (1e-4), an algorithm parameter rather than a quoted
constant; it is citable by plain path (`{{call_3.spec.options.lambda_z.adj_r_squared_factor}}`).

## Resolution rules (fail-closed)

Every reference must resolve, and everything else that looks like a quantity must be covered by the user's message.
A violation never passes through silently: the offending span is replaced by a visible marker (`⟦unresolved {{...}}⟧`,
`⟦unverified 12,5 mg/L⟧`, `⟦rejected: unit next to a reference: ...⟧`) and a badge lists the problems. In the agent, one
regeneration with a reminder is tried first (same loop as v1: reminder appended at the end of the messages, the better of
the two answers kept, the static prefix untouched).

1. **Unknown ref** (`call_9` when there is no ninth call, or the call failed and has no `structuredContent`): rejected.
2. **Wrong path**: a parameter name that is not in the analysis, a field of `analysis_compare` that is not one of
   `a b difference percent ratio`, a name that is neither a parameter nor an alias (a raw JSON path is rule 12): rejected, with the closest parameter
   name as a hint in the reminder (for the digest's labels `lambda_z_regression.x` and `options_used.quality_thresholds.x`
   the hint is the alias, `lambda_z.x` or `thresholds.x`; the reminder also lists the aliases of the last analysis).
3. **Not calculated / not comparable**: a parameter the engine did not compute (the result carries a reason, not a
   value) is rejected; the model must say that Caladrius did not return it.
4. **Schema check**: the canonical JSON path of the resolved value is walked through the tool's `outputSchema`
   (`$ref`/`$defs`, `oneOf`/`anyOf`, `properties`, `additionalProperties`, `items`). A path the schema forbids, or a leaf
   whose declared type disagrees with the value found, is rejected. A schema without property constraints
   (`analysis_compare` publishes `{"type":"object"}`) constrains nothing and the value is accepted on the data alone.
   An alias is checked on its canonical path (`result.subjects[i].outcome.ok.lambda_z_candidates[j].<field>`,
   `spec.options.quality.<name>`), never on the alias text.
5. **Several subjects, no `subject=`**: rejected (ambiguous selection).
6. **Nothing next to a reference**: a digit, a unit (the closed unit table of gate v1 plus unit words such as
   `heures`, `litres`, `mg`), a sign, or an arithmetic operator (`× * / ^ +`, `-` or `+` with an operand, `x` between two
   operands) glued to or one space away from a reference is rejected. The renderer prints the unit and the sign; the model
   writing them is the only way it could change them. `=` and `:` are allowed ("Cmax = {{call_3.cmax}}"). Markdown emphasis
   glued to the reference (`**`, `*`, `_`, `` ` ``, `~~`) is looked through: `-**{{call_3.cmax}}**` and `**-{{call_3.cmax}}**`
   are a sign, `*{{call_3.cmax}}*` is italic. A `-` after `=`, `:`, `(` or `|`, even spaced, is a sign; `- `, `* `, `+ ` at the
   start of a line are list items. A sign in words right before a reference (`negative`, `négative de`, `minus`, `moins`) is
   rejected; `moins de {{…}}` (less than) is a comparison and passes.
7. **Bare numbers**: every number written in digits (extracted by gate v1's tokeniser) must equal, as an exact value, a
   number of the user's messages (CSV included; decimal comma and point are the same number; the sign is ignored as in
   v1). Tool results are NOT a source any more: a tool number typed by the model is rejected even if it is right.
   No rounding match: `7,0` does not match a user `6.98`. A typed domain constant (`20 %`, `0,9`) is rejected like any
   other; its finding carries the reference to write instead (see "Named conventions").
8. **Exemptions**, counted apart and never rendered as values: list markers (`1.`, `2)`), `#17` message references,
   label numbers (`sujet 2`, `étape 3`, two digits at most), ISO dates, the `1` of `1/h`, a bare `10^k`, and
   **counts**: an integer 0-20 without unit, decimal or `%`, in digits or in words (`deux analyses`, `3 sujets`).
   A count is NOT exempt when it follows a PK label with a connector (`Cmax est de 10`, `la clairance : 5`,
   `half-life of 7`): that is a quantity and is rejected. Years are not exempt in v2.
9. **Numbers in words**: a numeral word followed by a unit word, spaced or hyphenated (`deux litres`, `trois heures`,
   `cinq pour cent`, `eleven-hour`), a compound numeral (`trente-deux`, `deux cents`, `twenty five`), a numeral above twenty
   (`cent`, `mille`, `million`, `dozen`), a decimal in words (`deux virgule cinq`) and a multiple or fraction (`double`,
   `deux fois`, `moitié`, `demi` outside `demi-vie`, `tiers`, `quart`, `twice`, `thrice`, `half` outside `half-life`,
   `quadruple`, `tenfold`, `hundredfold`, `two thirds`, `one third of`, `un cinquième de`) are rejected. `un`, `une`, `one`
   are articles, except right before a unit word (`one hour`, `une heure`; `une fois` stays an article). A small integer
   followed by a multiplier (`10-fold`, `3 fois`, `2 times`, `2 x`) is not a count.
10. **Malformed reference** (`{call_3.cmax}`, `{{call_3.cmax}`, `{{cmax}}` without a ref): rejected.
11. **Contradictory unit** (since 2026-10-19): a unit the model wrote in the reference's clause (from the previous `;`,
   sentence end or line end to the next; a comma does not end it) that has the dimension of the rendered unit but another
   scale rejects the reference: "La Cmax en mg/L vaut {{call_2.cmax}}", "Cmax (µg/mL) : {{call_2.cmax}}",
   "{{call_2.tmax}}, en minutes". In a Markdown table the clause is the cell, the row's first cell, the cell before it and
   the column header, plus any cell of the row that is a unit alone (`| Cmax | {{…}} | mg/L |`). A written unit counts after a
   number, alone in parentheses or brackets, or after `en`, `in`, `unit:`, `exprimée en`. Dimensions and scales come from a
   closed unit reader (mass, volume, time, amount, %; SI prefixes; `*`, `·`, `.`, `/`, parentheses, exponents), so `µg/L`
   next to an `ng/mL` value and `h·ng/mL` next to `h*ng/mL` are the same unit and pass, and a unit of another dimension (a
   time in the same sentence as a concentration) is not judged. When the engine's unit carries `dose unit`, any written unit
   of that dimension (`L/h` for a clearance) is a conversion the engine did not make and is rejected.
12. **Only typed quantities** (since 2026-10-19): a reference to a raw JSON path, a text or boolean field, a non-selected λz
   candidate, a `data_import` field or another tool's result is an `untyped_reference` finding, never rendered, counted in
   `references_untyped` and not in `references_total` (which counts the typed namespace: parameters, dose, aliases,
   conventions, compare fields, including the misspelt ones).
13. **Unicode numerals** (since 2026-10-19): a run of non-ASCII numeric characters (Unicode categories No and Nl: `½`, `⁹⁹⁹`,
   `①`, `Ⅻ`; what NFKC would turn into digits) is rejected, except an exponent or index of at most three characters glued to
   a label or a unit (`R²`, `h⁻¹`, `AUC₀₋∞`), `10⁻³`, and `t½`. Decimal digits of other scripts (`１２`) are read by the
   tokeniser and checked as numbers.

## What the renderer guarantees, and what it does not

What is guaranteed is narrow and checkable: the digits, the sign, the unit and the bracketed name printed in place of a
reference are the engine's, for a quantity of the closed tables. What the model writes around the reference is checked by the
rules above, which are pattern rules: they close the channels found by the audit and the red team, not every possible
phrasing (see "What remains").

| audit blind spot | v1 | v2 |
|---|---|---|
| right number, wrong parameter (`aucall` quoted as AUC(0-tlast)) | invisible: the number is in the tool result | the number is never typed and the renderer prints the cited parameter's name next to it (`[AUCall]`). A wrong *selection* is still possible (`{{call_3.aucall}}` written where `auclast` was asked) but the reader sees it, and the oracle check scores it against the asked parameter |
| unit changed (`mg/L` written as `ng/mL`) | invisible | the printed unit is the engine's (`unit` field or the worksheet units of the analysis); a unit written next to a reference is rejected (rule 6), and so is a contradictory unit elsewhere in the clause or the table column (rule 11). A unit written in a form the closed unit reader does not know is not judged |
| sign inverted (`-1.69` written as `1.69`) | invisible (sign ignored) | the renderer prints the engine's sign; a sign written next to a reference, through emphasis or in words, is rejected (rule 6) |
| rounding chosen by the model (`2 128 760,0` as 8 digits) | passes when it rounds right | the renderer always prints 6 significant digits |
| model-written text rendered as a result (analysis named "Cmax = 999 mg/L") | not applicable | text fields are not citable (rule 12) |
| 2-digit coincidence with one of ~100 tool numbers (`−1,00 %` matching a tool `1.00`) | passes | tool numbers are not a source at all; the only coincidence left is with the user's own numbers, at exact value (no rounding), which is a far smaller and user-visible set |
| year exemption (`1900-2100`) as a channel | passes | no year exemption |
| small integer exemption (`Cmax est de 10`) | passes | rejected after a PK label; a bare count (`3 sujets`) stays exempt, see below |
| number spelled in words (`deux litres par heure`) | passes (no number seen) | rejected when followed by a unit word, compound, above twenty, decimal in words, or a multiple/fraction |
| converted value (`CL/F × dose × 10³`) | caught by set membership (the main v1 catch) | a converted value would be a bare number (rule 7); arithmetic next to a reference is rejected |
| computed difference / percent / ratio | caught | a computed value would be a bare number; `{{call_5.x.difference}}` must come from `analysis_compare` |
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
- **Free text.** Flags, quality judgements, explanations and the labels the model writes before a reference are its words,
  unchecked; the bracketed name is the only label the renderer vouches for.
- **Thresholds where a result is asked** (red-team RT-A3). `La fraction extrapolée est {{convention.max_extrapolated_percent}}`
  renders "20 % [convention: max AUC%extrap]": the bracket shows it, nothing rejects it.
- **Phrasings outside the patterns.** An article before a unit word other than `one`/`un`/`une` (`an hour`), a sign word
  separated from the reference by other words (`a negative value of {{…}}`), a unit spelled in a form the closed unit reader
  does not know: not seen. Each rule is a closed list, extended when a run or a review finds a miss.
- **Stale results** (red-team RT-C3, RT-C9). A reference renders the snapshot of its call; an analysis the engine has since
  marked stale, or a reference reloaded after a restart, is rendered without warning.
- **Known false positives left.** `| t1/2 (h) | {{…}} |` marks the `2` of the label, `double-blind` is read as a multiple
  (red-team RT-A7); unchanged by the closed renderer.
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
