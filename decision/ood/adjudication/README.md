# Adjudication of the 74 out-of-distribution requests

`decision/ood/gold.jsonl` holds the gold decisions of the 74 requests that the reviewer dsh wrote in `decision/ood/requests.jsonl`. dsh gave a first gold; this folder records how it was checked, so that the figure measured on these requests is not the opinion of one author, and not of a model grading a model.

## How the gold was settled (2026-10-21)

1. **Two blind adjudications.** Gemini 4 Argon and Astra6 each received `prompt-argon-astra.md`: the definitions of the 20 closed questions (`analysis`, `route`, `auc_method`, `dose_has_unit`, `is_not_available`, `compare_pair` and 14 `asked_<parameter>` questions, folded into one `asked` list), and the 74 requests as the decision model sees them (the user's message, the table header and first five rows, the notes, the analyses already in the project). They did not see dsh's answers or his tags. Their raw answers are `argon.jsonl` and `astra.jsonl`, as pasted by Abdallah.
2. **Field-by-field comparison.** A field is settled when dsh, Argon and Astra give the same answer. This held for all 7 fields of 47 requests. The other 27 requests carry 47 disputed questions out of 1,480.
3. **Human arbitration.** Abdallah approved a proposal that settles the 27 requests through seven decisions, each applying to a group of requests (the conventions below). `arbitrations.jsonl` lists each disputed field and the source whose answer was kept (`A` is Argon, `B` is Astra). Each line of `gold.jsonl` has an `adjudication` object naming the fields that were arbitrated, so the origin of every answer can be traced.

| agreement | questions identical out of 1,480 |
|---|---|
| Argon and Astra | 1,472 |
| Argon and dsh | 1,434 |
| Astra and dsh | 1,440 |

## Conventions the gold follows

The prompt applies the schema of `decision/make_dataset.py`, not dsh's own conventions. Where they differ, the gold takes the schema:

- `auc_method` is `not_applicable` when the request reads an existing result, refuses, or fits: no NCA runs.
- Out-of-scope requests (bioequivalence, population models, repeated doses, urine data) and parameters outside the 14 (Vss, ka) are `analysis = not_supported`, with `is_not_available = false`.
- The route is the one the user wrote, never one read from the data: `unknown` when the text is silent.
- `mcg` and `g` are dose units, so `dose_has_unit` is true for them.
- With fewer than two analyses in the project, `compare_pair` is `none_available`.
- A pair `a+b` takes the first analysis named as the reference.
- A comparison that says "the AUC" without more asks for `auclast`.

`REVIEW.md` records dsh's own conventions and the lines he calls debatable.

## Limits

- Two models and the project's author adjudicated the gold; no external pharmacometrician did. Ambiguous lines (ood-013, 014, 030, 039, 058, 071, 072 among them) are decisions, not discoveries.
- The models see only what the decision model sees, so a request that depends on the data beyond the first five rows is not judged on it.
- `argon.jsonl` and `astra.jsonl` were re-typed from chat messages. The schema check passes on all 74 lines of each; a typing slip is unlikely but not excluded.
- The merge script, its tests and the prompt generator live in the project Library, not in this repository.

## Use

Do not run the trained model on these 74 requests, or show any prediction on them, before the frozen run of `bench/FROZEN_SET.md` has been done. Once it has, `python decision/eval_ood.py --requests decision/ood/gold.jsonl` reads this file in place of `requests.jsonl`.
