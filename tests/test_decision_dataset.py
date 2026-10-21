"""Tests of the decision-model dataset v2 (decision/make_dataset.py, decision/wordings.json): the typed-decisions row schema, the
wordings file (pools, families, declared intents, no near duplicate of the reviewer's frozen requests), the gold answers (inside the
declared options, consistent with the truth of the exercises and with the wording's declared intent, recomputed here independently of
the generator's tables), the two splits (by exercise and by wording), the class coverage of every file, the README blocks,
determinism. No engine and no model needed, except for the optional byte-identity check of decision/exercises/ (skipped when
caladrius-mcp is not built).
"""
import collections, filecmp, json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT); sys.path.insert(0, os.path.join(AGENT, "decision"))
import apothicaire  # noqa: E402
import make_dataset as md  # noqa: E402
from bench import make_exercises as mk, scripts  # noqa: E402

FIELDS = ["id", "workflow", "split", "state", "questions", "gold", "factors", "label_agreement", "n_questions"]
TYPES = {"choice", "noul", "score"}
TRAIN, HE, HW, HB, BENCH = md.FILES

_CACHE = {}
def data():
    if "data" not in _CACHE: _CACHE["data"] = md.build()
    return _CACHE["data"]

def by_file():
    return dict(zip(md.FILES, data()))

def metas():
    if "metas" not in _CACHE: _CACHE["metas"] = {m["id"]: m for m, _, _ in md.load_exercises()}
    return _CACHE["metas"]

def parsed(rows):
    for r in rows:
        yield r, json.loads(r["state"]), json.loads(r["questions"]), json.loads(r["gold"]), json.loads(r["factors"])

def all_rows():
    return [x for rows in data() for x in rows]

def options_of(q):
    """The declared answers of a question."""
    if q["type"] == "choice": return set(q["criteria"])
    if q["type"] == "noul": return {"false", "true"}
    return {str(i) for i in range(len(q["criteria"]))}

def not_calculated(meta):
    return {k for k in ("c0", "tlag") if k in meta["ground_truth"]["nca"]["linear"]["not_calculated"]}

def written_dose(meta, fill, factor=1):
    """The dose as the rows must write it, recomputed here (not md.dose_text)."""
    a, u = meta["dose"]["amount"] * factor, meta["dose"]["unit"]
    fr = lambda x: f"{x:g}".replace(".", ",")
    return {"unit": f"{fr(a)} {'µg' if u == 'ug' else 'mg'}", "no_unit": fr(a),
            "other_unit": (f"{fr(a / 1000)} g" if a >= 100 else f"{fr(a * 1000)} µg") if u == "mg" else f"{fr(a / 1000)} mg"}[fill]


class TestRows(unittest.TestCase):
    def test_row_schema(self):
        te_ids = set()
        for name, rows in by_file().items():
            ids = set()
            for r, state, qs, gold, factors in parsed(rows):
                assert list(r) == FIELDS
                assert all(isinstance(r[k], str) for k in FIELDS if k != "n_questions") and isinstance(r["n_questions"], int)
                assert r["id"] not in ids; ids.add(r["id"])
                split = {TRAIN: "train", BENCH: "bench"}.get(name, "test")
                assert r["split"] == split and r["id"].startswith({"train": "tr_", "test": "te_", "bench": "be_"}[split])
                if split == "test": assert r["id"] not in te_ids; te_ids.add(r["id"])         # unique over the three held-out files
                assert r["n_questions"] == len(qs) == len(gold) == 6 + len(md.PARAMETERS) and set(qs) == set(gold) == set(json.loads(r["label_agreement"]))
                assert set(state) == {"analyses", "data", "notes", "request", "user_dose_sentence"}
                assert set(state["data"]) == {"header", "first_rows", "n_rows", "n_subjects"}
                assert state["data"]["header"].startswith("time (") and "conc (" in state["data"]["header"]
                assert state["data"]["n_rows"] >= len(state["data"]["first_rows"]) > 0
                assert state["request"].strip() and state["user_dose_sentence"].strip()
                assert "{" not in state["request"] + state["user_dose_sentence"] + "".join(state["notes"]), r["id"]   # every slot filled
                for q_name, q in qs.items():
                    assert q["type"] in TYPES and isinstance(q["instructions"], str) and q["instructions"]
                    if q["type"] == "choice": assert len(q["criteria"]) >= 2 and all(isinstance(v, str) for v in q["criteria"].values())
                    if q["type"] == "noul": assert q["criteria"].keys() == {"false", "true"}
                    g = gold[q_name]
                    assert g["type"] == q["type"] and set(g["probabilities"]) == options_of(q)
                    assert abs(sum(g["probabilities"].values()) - 1) < 1e-9 and 0 <= g["confidence"] <= 1
                    if q["type"] == "noul": assert g["noul"] == g["probabilities"]["true"]
                assert factors["file"] == name and set(factors) >= {"exercise", "kind", "bench", "route", "wording_id", "wording_family"}

    def test_files_on_disk_are_current(self):
        for name, rows in by_file().items():
            path = os.path.join(md.OUT, f"{name}.jsonl")
            if not os.path.exists(path): continue                              # decision/data/ is git-ignored: checked when present
            with open(path, encoding="utf-8") as f: disk = [json.loads(l) for l in f]
            assert disk == rows, f"{path} is stale: run python decision/make_dataset.py"

    def test_deterministic(self):
        assert md.build() == data()
        assert md.split_wordings() == (md.HALVES, md.HALVES_ATTEMPT)

    def test_row_counts(self):
        n = {name: len(rows) for name, rows in by_file().items()}
        per_ex = sum(1 for k in md.KINDS if k in scripts.KINDS) + sum(md.PARAPHRASES.values())          # 8 scripted + paraphrases
        assert n[TRAIN] == 55 * per_ex and n[HE] == 20 * per_ex and n[BENCH] == 25 * per_ex
        assert n[HW] == 55 * len(md.KINDS)                                                                # one held-out wording per kind
        assert 20 * len(md.KINDS) < n[HB] <= 20 * len(md.KINDS) * 2
        assert n[TRAIN] >= 2500


class TestGold(unittest.TestCase):
    def test_every_gold_is_a_declared_option(self):
        for r, state, qs, gold, factors in parsed(all_rows()):
            for name, q in qs.items():
                assert gold[name]["label"] in options_of(q), (r["id"], name, gold[name]["label"])
                assert gold[name]["probabilities"][gold[name]["label"]] == 1.0
            ids = sorted(a["id"] for a in state["analyses"])
            pairs = {f"{a}+{b}" for a in ids for b in ids if a != b}                     # directed: both orders are offered
            assert set(qs["compare_pair"]["criteria"]) == {"not_applicable"} | (pairs or {"none_available"})

    def test_gold_from_the_truth_and_the_declared_intent(self):
        """Every label recomputed from meta.json, the kind and the wording of wordings.json (not from the generator's tables)."""
        analysis = {"import_nca": "nca", "nca_oneline": "nca", "compare": "compare", "compare_directed": "compare", "fit_pk1": "fit_pk1",
                    "fit_pk2": "fit_pk2", "simulate": "simulate", "not_supported": "not_supported"}
        for r, state, qs, gold, f in parsed(all_rows()):
            meta = metas()[f["exercise"]]; kind = f["kind"]; label = lambda q: gold[q]["label"]
            route = scripts.kind_of(meta)
            w = None if f["scripted_wording"] else md.WORDING_BY_ID[f["wording_id"]]
            assert f["wording_family"] == ("scripted" if w is None else w["family"])
            assert label("analysis") == analysis.get(kind, "none_needed"), r["id"]
            # route: the exercise's, unless the user's text gives none (introduction without route phrase, one line declared silent)
            if w is not None and w.get("oneline"):
                assert f["layout"] == "oneline" and state["user_dose_sentence"] == state["request"]
                silent = w["route"] == "none"
                if w["route"] in md.CONCRETE_ROUTES: assert w["route"] == route
                assert (f["route_phrase_id"] is not None) == (w["route"] == "slot")
            else:
                silent = f["route_phrase_id"] is None and w is not None
                assert (f["intro_id"] is None) == (w is None)
            if f["route_phrase_id"]:
                rp = md.WORDING_BY_ID[f["route_phrase_id"]]
                assert rp["id"].startswith(f"route_{route}.")
                assert rp["text"].format(d=scripts.fr(meta["route"]["iv_infusion"]["duration"]) if route == "iv_infusion" else "",
                                         t=meta["units"]["time"]) in state["user_dose_sentence"]
            assert label("route") == ("unknown" if silent else route), r["id"]
            if kind == "not_available": assert label("route") == route                  # the route decides the answer there
            # dose: written with its unit, in another unit, without a unit, or not at all (declared by the one-line wording)
            fill = f["dose_fill"]
            if w is None: assert fill == "unit"
            if w is not None and w.get("oneline") and w["dose"] == "none": assert fill == "none"
            assert label("dose_has_unit") == ("true" if fill in ("unit", "other_unit") else "false"), r["id"]
            if fill != "none":
                assert written_dose(meta, fill) in state["user_dose_sentence"], (r["id"], fill, state["user_dose_sentence"])
                if w is not None and "{wrong_dose}" in w["text"]:
                    s = state["user_dose_sentence"]
                    assert s.index(written_dose(meta, fill, 10)) < s.rindex(written_dose(meta, fill))   # said wrongly first, corrected after
            # AUC method: the NCA kinds take the declared method (scripted: linear), the compare turn re-runs lin-up/log-down
            if kind in ("import_nca", "nca_oneline"): assert label("auc_method") == ("linear" if w is None else w["auc_method"])
            else: assert label("auc_method") == ("lin_up_log_down" if kind == "compare" else "not_applicable"), r["id"]
            # compare pair: the re-run compares the new analysis with the linear one; a directed compare names the reference first
            if kind == "compare": assert label("compare_pair") == "2+3"
            elif kind == "compare_directed":
                a, b = (int(x) for x in label("compare_pair").split("+"))
                assert {a, b} == {2, 3} and a == f["compare_reference"]
                cl, vz = ("CL/F", "Vz/F") if route == "oral" else ("CL", "Vz")
                m = {2: "linéaire", 3: "lin-up/log-down"}
                assert w["text"].format(ref=a, other=b, ref_method=m[a], other_method=m[b], cl=cl, vz=vz) == state["request"]
            else: assert label("compare_pair") == "not_applicable"
            # parameters asked: the wording's declared list (scripted: the benchmark's)
            asked = [k for k in md.PARAMETERS if label(f"asked_{k}") == "true"]
            assert set(asked) == set(f["parameters_asked"]) and (w is None or set(asked) == set(w["asked"])), r["id"]
            # the state's analyses
            assert state["data"]["header"] == f"time ({meta['units']['time']}),conc ({meta['units']['conc']})"
            assert (state["analyses"] == []) == f["first_turn"]
            if kind in ("import_nca", "nca_oneline"): assert f["first_turn"]
            if kind in ("compare", "compare_directed"): assert [a["id"] for a in state["analyses"]] == [2, 3]
            assert bool(meta.get("blq")) == bool(state["notes"])

    def test_is_not_available_exactly_for_the_not_available_kind(self):
        n_true = 0
        for r, state, qs, gold, f in parsed(all_rows()):
            flag = gold["is_not_available"]["label"] == "true"
            assert flag == (f["kind"] == "not_available"), r["id"]
            # independent of the kind table: the parameters asked include one Caladrius did not compute for this route
            assert flag == bool(set(f["parameters_asked"]) & not_calculated(metas()[f["exercise"]])), r["id"]
            n_true += flag
        assert n_true > 0

    def test_route_of_not_calculated_parameters(self):
        """md.NC_OF_ROUTE (used to draw the wording split) agrees with meta.json for every exercise."""
        for m in metas().values(): assert not_calculated(m) == md.NC_OF_ROUTE[scripts.kind_of(m)], m["id"]

    def test_labels_are_not_a_pattern_over_the_text(self):
        """The cases a pattern over the sentence gets wrong are labelled from the intent: an implied route (comprimé, gélule, injectés
        dans la veine, perfusé), a dose in g or mcg-free µg conversions, a corrected dose, a negated or corrected parameter."""
        route_re = {"oral": r"orale?\b|per os", "iv_bolus": r"bolus|injection intraveineuse rapide", "iv_infusion": r"perfusion"}
        unit_re = r"\d\s*(?:mg|µg|μg|ug)\b"
        implied = grams = negated = 0
        for r, state, qs, gold, f in parsed(all_rows()):
            s = state["user_dose_sentence"]; route = gold["route"]["label"]
            if route != "unknown" and not re.search(route_re[route], s): implied += 1
            if gold["dose_has_unit"]["label"] == "true" and not re.search(unit_re, s): grams += 1
            if f["wording_family"] in ("negation", "correction-in-sentence") and f["parameters_asked"]: negated += 1
        assert implied > 50 and grams > 50 and negated > 100, (implied, grams, negated)

    def test_new_options_have_rows(self):
        """not_supported, the reversed pair 3+2, route unknown and dose without unit: rows in train and in each held-out file."""
        for name in (TRAIN,) + md.HELDOUT_FILES:
            h = collections.defaultdict(collections.Counter)
            for r, state, qs, gold, f in parsed(by_file()[name]):
                for q in ("analysis", "compare_pair", "route", "dose_has_unit"): h[q][gold[q]["label"]] += 1
            assert h["analysis"]["not_supported"] and h["compare_pair"]["3+2"] and h["compare_pair"]["2+3"], name
            assert h["route"]["unknown"] and h["dose_has_unit"]["false"], name

    def test_not_supported_rows(self):
        n = 0
        for r, state, qs, gold, f in parsed(all_rows()):
            if gold["analysis"]["label"] != "not_supported": continue
            n += 1
            assert f["kind"] == "not_supported" and f["parameters_asked"] == []
            assert all(gold[f"asked_{k}"]["label"] == "false" for k in md.PARAMETERS)
            assert gold["is_not_available"]["label"] == "false" and gold["compare_pair"]["label"] == "not_applicable"
            assert gold["auc_method"]["label"] == "not_applicable"
        assert n > 0

    def test_one_noul_question_per_parameter(self):
        """`asked_<key>`: one noul per parameter, a boolean gold, no several / none."""
        keys = ["cmax", "tmax", "c0", "auclast", "aucinf", "lambda_z", "half_life", "cl", "vz", "mrt", "aucpext", "lambda_z_points", "adj_r2", "tlag"]
        assert list(md.PARAMETERS) == keys
        qs = md.questions_for([2, 3])
        assert "parameter_asked" not in qs and [q for q in qs if q.startswith("asked_")] == [f"asked_{k}" for k in keys]
        for r, state, qs, gold, f in parsed(all_rows()):
            asked = []
            for k in keys:
                q, g = qs[f"asked_{k}"], gold[f"asked_{k}"]
                assert q["type"] == "noul" and q["criteria"] == md.TF and g["type"] == "noul"
                assert g["label"] in ("true", "false") and g["noul"] in (0.0, 1.0) and g["noul"] == (g["label"] == "true")
                if g["label"] == "true": asked.append(k)
            kind = f["kind"]
            if kind in ("import_nca", "nca_oneline", "cmax_tmax", "clearance_volume", "half_life", "lambda_z_regression", "compare", "nca_other", "not_available"):
                assert asked, r["id"]
            if kind in ("recall", "fit_pk1", "fit_pk2", "simulate", "not_supported"): assert asked == [], r["id"]
            nc = not_calculated(metas()[f["exercise"]])
            if kind == "not_available": assert set(asked) & nc, r["id"]
            else: assert not set(asked) & nc, r["id"]                 # no other turn asks for what the route does not give
            if kind == "import_nca" and f["scripted_wording"]:
                assert asked == [k for k in keys if k in ("cmax", "tmax", "auclast", "aucinf", "lambda_z", "half_life", "cl", "vz", "mrt")]
            if kind == "compare" and f["scripted_wording"]: assert asked == ["auclast"]

    def test_compare_pairs_are_directed(self):
        crit = md.questions_for([2, 3])["compare_pair"]["criteria"]
        assert set(crit) == {"not_applicable", "2+3", "3+2"}
        assert "analysis 2 as the reference" in crit["2+3"] and "analysis 3 as the reference" in crit["3+2"]
        assert set(md.questions_for([2])["compare_pair"]["criteria"]) == {"not_applicable", "none_available"}
        assert len(md.questions_for([2, 3, 4])["compare_pair"]["criteria"]) == 1 + 6
        assert "not_supported" in md.questions_for([2])["analysis"]["criteria"]

    def test_scripted_rows_are_the_benchmark_wording(self):
        n = 0
        for r, state, qs, gold, f in parsed(all_rows()):
            if not f["scripted_wording"]: continue
            assert f["file"] in (TRAIN, HE, BENCH)
            meta = metas()[f["exercise"]]
            with open(os.path.join(md.BENCH_DIR if f["bench"] else md.EXTRA_DIR, meta["id"], "data.csv"), encoding="utf-8") as fh: csv = fh.read()
            turns = {t["kind"]: t for t in scripts.build_script(meta, csv)}
            t1 = turns["import_nca"]["question"].split(chr(10))
            assert f["kind"] in scripts.KINDS and state["user_dose_sentence"] == t1[0]
            assert state["request"] == (t1[-1] if f["kind"] == "import_nca" else turns[f["kind"]]["question"])
            n += 1
        assert n == 8 * 100

    def test_distinct_wordings_per_exercise_kind_and_file(self):
        seen = collections.defaultdict(list)
        for r, state, qs, gold, f in parsed(all_rows()):
            seen[(f["file"], f["exercise"], f["kind"])].append(f["wording_id"])
        for key, ws in seen.items():
            assert len(set(ws)) == len(ws), key


class TestWordings(unittest.TestCase):
    def test_pools_and_families(self):
        for kind in md.KINDS: assert len(md.WORDINGS[kind]) >= 12, kind               # at least 12 wordings per turn kind
        for kind in md.SLOT_KINDS: assert len(md.WORDINGS[kind]) >= 5, kind
        fam = collections.Counter(x["family"] for x in md.WORDING_BY_ID.values())
        assert set(fam) == set(md.FAMILIES) and min(fam.values()) >= 2
        for f in ("formal", "colloquial", "abbreviated", "implicit-route", "unit-in-text", "multi-parameter", "negation",
                  "correction-in-sentence", "out-of-scope", "directed-compare", "follow-up", "no-dose"):
            assert f in md.FAMILIES, f
        for x in md.WORDING_BY_ID.values():
            if x["family"] != "abbreviated":
                assert re.search(r"[éèàêçù']|\b(?:le|la|les|de|des|du|un|une|est|et|ou|moi|je|ai|en|par|sur)\b", x["text"], re.I), x["id"]

    def test_required_phenomena_are_written(self):
        texts = {x["id"]: x["text"] for x in md.WORDING_BY_ID.values()}
        has = lambda pattern, kinds=None: [i for i, t in texts.items() if re.search(pattern, t) and (kinds is None or i.split(".")[0] in kinds)]
        for abbr in (r"t1/2", r"AUC0-t\b", r"AUC0-inf", r"Cl/F", r"\bVd\b", r"λz"): assert has(abbr), abbr
        assert has(r"\bpas (?:la|le|l'|besoin)", md.KINDS) and has(r"pardon|non,|euh non|enfin non", md.KINDS)
        assert has(r"comprimé|gélule") and has(r"perfusé") and has(r"injecté")
        assert has(r"\{wrong_dose\}")
        assert has(r"bioéquivalen", ["not_supported"]) and has(r"population", ["not_supported"]) and has(r"[Ee]xplique", ["not_supported"])
        assert has(r"graphique|courbe", ["not_supported"])
        assert sum(len(x["asked"]) >= 3 for k in md.KINDS for x in md.WORDINGS[k]) >= 12
        assert sum(x["family"] == "follow-up" for x in md.WORDING_BY_ID.values()) >= 10
        ones = [x for k in md.KINDS for x in md.WORDINGS[k] if x.get("oneline")]
        assert {x["dose"] for x in ones} == {"slot", "none"} and {x["route"] for x in ones} == {"slot", "none", *md.CONCRETE_ROUTES}

    def test_validation_rejects_a_malformed_file(self):
        with open(md.WORDINGS_FILE, encoding="utf-8") as f: good = json.load(f)
        md.validate_wordings(good)
        def broken(edit):
            w = json.loads(json.dumps(good)); edit(w)
            with self.assertRaises(AssertionError): md.validate_wordings(w)
        broken(lambda w: w["kinds"]["cmax_tmax"][0].update(family="poetic"))
        broken(lambda w: w["kinds"]["cmax_tmax"][0].update(asked=["vdss"]))
        broken(lambda w: w["kinds"]["cmax_tmax"][0].update(id="half_life.99"))
        broken(lambda w: w["kinds"]["cmax_tmax"][0].update(text="Cmax {dose} ?"))
        broken(lambda w: w["kinds"]["nca_oneline"][0].update(route="slot"))              # declared slot, but the text implies the route
        broken(lambda w: w["kinds"]["not_supported"][0].update(asked=["cmax"]))
        broken(lambda w: w["kinds"]["import_nca"][0].pop("auc_method"))

    def test_near_duplicate_measure(self):
        assert md.near_duplicate("Bolus de 120 mg : Cmax ?", "bolus de 300 mg, cmax")          # numbers, case and punctuation do not count
        assert md.normalise("Écart à 2,5 h") == ["ecart", "a", "0", "0", "h"]
        assert not md.near_duplicate("Quelle est la demi-vie terminale ?", "Donne-moi la clairance et le volume.")
        assert md.jaccard("a b c d", "a b c e") == 1 / 3

    def test_no_wording_near_duplicates_a_reviewer_request(self):
        """decision/ood/requests.jsonl stays a frozen test set: no wording template and no sentence of any generated row equals one of
        the reviewer's 74 requests (or one of its lines) after normalisation, or shares more than 60 % of its word trigrams (Jaccard)."""
        ood = md.ood_requests()
        assert len(ood) >= 74
        texts = {x["text"] for x in md.WORDING_BY_ID.values()}
        for r, state, qs, gold, f in parsed(all_rows()):
            if not f["scripted_wording"]: texts |= {state["request"], state["user_dose_sentence"]}
        hits = [(t, o) for t in texts for o in ood if md.near_duplicate(t, o)]
        assert not hits, hits[:5]


class TestSplits(unittest.TestCase):
    def test_split_is_by_exercise(self):
        ex = {name: {f["exercise"] for *_, f in parsed(rows)} for name, rows in by_file().items()}
        bench_ids = {os.path.basename(d) for d in mk.list_exercises(md.BENCH_DIR)}
        new_ids = {os.path.basename(d) for d in mk.list_exercises(md.EXTRA_DIR)}
        tr, held, be = md.split_ids(md.load_exercises())
        assert ex[TRAIN] == ex[HW] == set(tr) and ex[HE] == ex[HB] == set(held) and ex[BENCH] == set(be) == bench_ids
        assert not (set(tr) & set(held) or set(tr) & bench_ids or set(held) & bench_ids) and set(tr) | set(held) == new_ids
        assert len(held) == md.HELDOUT_N == 20 and len(bench_ids) == 25

    def test_wording_split(self):
        held, train_side = md.half_ids("heldout"), md.half_ids("train")
        assert held and not held & train_side and held | train_side == set(md.WORDING_BY_ID)
        for kind, h in md.HALVES.items():
            n = len(md.WORDINGS[kind])
            assert len(h["heldout"]) == max(1, round(md.WORDING_HELDOUT_SHARE * n)), kind
            if kind in md.KINDS: assert 0.2 <= len(h["heldout"]) / n <= 0.3, kind
        for side in (held, train_side):                                  # every family on both sides
            assert {md.WORDING_BY_ID[i]["family"] for i in side} == set(md.FAMILIES)

    def test_no_held_out_wording_in_a_train_side_row(self):
        held = md.half_ids("heldout")
        for name, rows in by_file().items():
            for r, state, qs, gold, f in parsed(rows):
                used = {f[k] for k in ("wording_id", "intro_id", "route_phrase_id", "blq_note_id")} - {None}
                if name in (TRAIN, HE, BENCH): assert not used & held, (name, r["id"], used & held)
                else: assert used <= held and not f["scripted_wording"] and f["wording_heldout"], (name, r["id"])

    def test_no_held_out_sentence_in_train(self):
        """Stronger than the ids: no request text of a held-out-wording file is a request text of train."""
        train = {json.loads(r["state"])["request"] for r in by_file()[TRAIN]}
        for name in (HW, HB):
            assert not train & {json.loads(r["state"])["request"] for r in by_file()[name]}, name

    def test_every_option_and_parameter_in_every_file(self):
        """Every `analysis` option (including not_supported) has rows in train and in each held-out file; every asked_* key has true rows."""
        for name in (TRAIN,) + md.HELDOUT_FILES:
            st = md.stats(*data())[name]["hist"]
            assert set(st["analysis"]) == set(md.ANALYSES), (name, set(md.ANALYSES) - set(st["analysis"]))
            for k in md.PARAMETERS: assert st[f"asked_{k}"].get("true", 0) > 0, (name, k)
            for q, opts in (("route", md.ROUTES), ("auc_method", md.AUC_METHODS)): assert set(st[q]) == set(opts), (name, q)
            assert set(st["compare_pair"]) == {"not_applicable", "2+3", "3+2"} and set(st["is_not_available"]) == {"true", "false"}

    def test_exercise_folders(self):
        ids = [os.path.basename(d) for d in mk.list_exercises(md.EXTRA_DIR)]
        assert len(ids) == 75 and all(re.match(r"s[123]_ex\d\d_", i) for i in ids)
        assert not set(ids) & {os.path.basename(d) for d in mk.list_exercises(md.BENCH_DIR)}
        for d in mk.list_exercises(md.EXTRA_DIR):
            meta, csv = mk.load(d)
            assert meta["id"] == os.path.basename(d) and meta["noise"]["seed"] != 20261009 * 100 + meta["index"]
            assert "half.life" in meta["ground_truth"]["nca"]["linear"]["parameters"]

    @unittest.skipUnless(os.path.exists(apothicaire.MCP_BIN), "caladrius-mcp is not built")
    def test_exercises_regenerate_byte_identical(self):
        import make_exercises as dmk
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ex")
            dmk.generate(out)
            cmp = filecmp.dircmp(out, md.EXTRA_DIR)
            assert not cmp.left_only and not cmp.right_only
            for d in cmp.common_dirs:
                assert filecmp.cmp(os.path.join(out, d, "data.csv"), os.path.join(md.EXTRA_DIR, d, "data.csv"), shallow=False), d
                with open(os.path.join(out, d, "meta.json"), encoding="utf-8") as f: new = json.load(f)
                with open(os.path.join(md.EXTRA_DIR, d, "meta.json"), encoding="utf-8") as f: old = json.load(f)
                diff = json_difference(new, old)
                assert diff is None, f"{d}: {diff}"


def json_difference(a, b, path="$", rel=1e-12):
    """The first place where two JSON values differ, or None. Floats are equal within `rel` relative (the engine's
    results differ by a few ulp between platforms: libm, not the method; Caladrius promises 1e-6, docs/validation.md);
    everything else (keys and their order, strings, integers, booleans, null, list lengths) must be identical."""
    if isinstance(a, float) or isinstance(b, float):
        if type(a) is not type(b): return f"{path}: {a!r} vs {b!r}"
        return None if a == b or abs(a - b) <= rel * max(abs(a), abs(b)) else f"{path}: {a!r} vs {b!r}"
    if type(a) is not type(b): return f"{path}: {a!r} vs {b!r}"
    if isinstance(a, dict):
        if list(a) != list(b): return f"{path}: keys {list(a)} vs {list(b)}"
        return next((r for k in a if (r := json_difference(a[k], b[k], f"{path}.{k}", rel))), None)
    if isinstance(a, list):
        if len(a) != len(b): return f"{path}: {len(a)} items vs {len(b)}"
        return next((r for i, (x, y) in enumerate(zip(a, b)) if (r := json_difference(x, y, f"{path}[{i}]", rel))), None)
    return None if a == b else f"{path}: {a!r} vs {b!r}"


class TestJsonDifference(unittest.TestCase):
    """The comparison of the regeneration test: a few ulp pass, anything else is a difference."""
    def test_floats_within_1e_12_pass_and_the_rest_is_strict(self):
        self.assertIsNone(json_difference({"x": [0.3696049252727319, 1, "a"]}, {"x": [0.369604925272732, 1, "a"]}))
        for a, b in (({"x": 1.0}, {"x": 1.000001}), ({"x": 1}, {"x": 1.0}), ({"x": "1"}, {"x": "2"}), ({"x": 1, "y": 2}, {"y": 2, "x": 1}),
                     ([1.0], [1.0, 2.0]), ({"x": None}, {"x": 0.0}), ({"x": True}, {"x": 1})):
            self.assertIsNotNone(json_difference(a, b), (a, b))


class TestReadme(unittest.TestCase):
    def test_readme_blocks_match_the_data(self):
        st = md.stats(*data())
        with open(md.README, encoding="utf-8") as f: text = f.read()
        block = text[text.index(md.COUNTS_BEGIN):text.index(md.COUNTS_END) + len(md.COUNTS_END)]
        assert block == md.counts_block(st), "README counts are stale: run python decision/make_dataset.py"
        for q in ("analysis", "route", "auc_method", *(f"asked_{k}" for k in md.PARAMETERS), "dose_has_unit", "is_not_available", "compare_pair"):
            assert f"`{q}`" in block
        wblock = text[text.index(md.WORDINGS_BEGIN):text.index(md.WORDINGS_END) + len(md.WORDINGS_END)]
        assert wblock == md.wordings_block(), "README wordings block is stale: run python decision/make_dataset.py"
        assert "v1 (2026-10-09)" in text                                    # the v1 numbers are kept for the record

    def test_update_readme_replaces_both_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "R.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"a\n{md.COUNTS_BEGIN}\nold\n{md.COUNTS_END}\nb\n{md.WORDINGS_BEGIN}\nold\n{md.WORDINGS_END}\nc\n")
            assert md.update_readme([f"{md.COUNTS_BEGIN}\nX\n{md.COUNTS_END}", f"{md.WORDINGS_BEGIN}\nY\n{md.WORDINGS_END}"], p)
            with open(p, encoding="utf-8") as f: out = f.read()
            assert out == f"a\n{md.COUNTS_BEGIN}\nX\n{md.COUNTS_END}\nb\n{md.WORDINGS_BEGIN}\nY\n{md.WORDINGS_END}\nc\n"


if __name__ == "__main__":
    unittest.main()
