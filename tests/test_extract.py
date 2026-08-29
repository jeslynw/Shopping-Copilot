"""Category matcher: 200 openers × 3 templates resolve exactly (template path AND vocabulary path); reply shapes parse."""
from copilot.extract import extract, tokens


def _openers(cat, card):
    c = card["hard_constraints"][0] if card["hard_constraints"] else "Imported"
    soft = card["soft_preferences"][-1] if card["soft_preferences"] else c
    return [f"I'm looking for {cat}. A key requirement is: {c}.", f"I'm looking for {cat}, but I'm still exploring.",
            f"I'm looking for {cat}. {soft}"]


def test_openers_resolve_exactly_template_path(agent, cards):
    cm = agent.catalog.matcher
    bad = []
    for s, t, cat, card in cards:
        for msg in _openers(cat, card):
            p = extract(msg, 1, "template", cm)
            if cat not in p.categories or p.cat_prov != "template":
                bad.append((s["sample_id"], cat, p.categories, msg[:60]))
    assert not bad, bad[:5]


def test_openers_resolve_exactly_vocab_path(agent, cards):
    cm = agent.catalog.matcher
    bad = [(s["sample_id"], cat, cm.match(msg)) for s, t, cat, card in cards for msg in _openers(cat, card)
           if cat not in cm.match(msg)[0]]
    assert not bad, bad[:5]


def test_opener_constraints_are_verbatim(agent, cards):
    cm = agent.catalog.matcher
    for s, t, cat, card in cards:
        if not card["hard_constraints"]:
            continue
        c = card["hard_constraints"][0]
        p = extract(f"I'm looking for {cat}. A key requirement is: {c}.", 1, "hybrid", cm)
        assert p.kind == "open_buying" and p.constraints == [(c, "template")]


def test_reply_shapes(agent):
    cm = agent.catalog.matcher
    p = extract("For that, what matters is: Rubber sole; Shaft measures approximately 8.37\" from arch.", 2, "hybrid", cm)
    assert p.kind == "yield" and [c for c, _ in p.constraints] == ["Rubber sole", 'Shaft measures approximately 8.37" from arch']
    assert extract("I don't have an additional preference for material.", 2, "hybrid", cm).kind == "exhausted"
    b = extract("I don't have a preference for feature; please use your judgment.", 2, "hybrid", cm)
    assert b.kind == "boundary" and b.attribute == "feature"
    o = extract("Actually, ignore my earlier preference. What I need is: leather.", 3, "hybrid", cm)
    assert o.kind == "override" and o.constraints == [("leather", "template")]
    assert extract("Those options are not quite right yet. Ask me about one specific attribute.", 2, "hybrid", cm).kind == "noinfo"


def test_clause_fallback_is_tagged_and_finds_category(agent):
    cm = agent.catalog.matcher
    p = extract("Hi! I need jewelry necklaces. It must have: Material:alloy.", 1, "hybrid", cm)
    assert "Jewelry Necklaces" in p.categories and p.cat_prov == "exact"
    assert p.constraints == [("Material:alloy", "clause")] and p.template is False


def test_permutation_tied_vocab_phrases_return_a_set(agent):
    cm = agent.catalog.matcher
    tied = [v for v in cm.by_multiset.values() if len(v) > 1]
    assert tied, "expected vocab phrases sharing a token multiset"
    # a re-ordered paraphrase of a tied phrase resolves to the whole tie set via the fuzzy path
    group = max(tied, key=len)
    singular = " ".join(t[:-1] if len(t) > 3 and t.endswith("s") else t for t in group[0].lower().split())
    cands, prov = cm.match(f"I want {singular} please")      # not an exact substring → fuzzy → whole tie set
    assert prov == "fuzzy" and set(group) <= set(cands), (group, cands, prov)


def test_quote_bearing_constraints_tokenize_safely(agent, cards):
    quoted = [c for _, _, _, card in cards for c in card["hard_constraints"] + card["soft_preferences"] if '"' in c]
    assert len(quoted) >= 10
    for c in quoted:
        assert all(t.isalnum() for t in tokens(c))
        agent.catalog.search(tokens(c), 5)   # must not raise


def test_peel_leadin_keeps_catalog_strings_intact():
    from copilot.extract import peel_leadin
    assert peel_leadin("Oh, for that one, what matters is: Imported") == "Imported"
    assert peel_leadin("So,  : cotton blend") == "cotton blend"
    assert peel_leadin("Key requirement is: spandex") == "spandex"
    assert peel_leadin("Need: Made in the USA") == "Made in the USA"
    assert peel_leadin("Needs 5% spandex") == "5% spandex"
    assert peel_leadin("Solid colors: 100% Cotton") == "Solid colors: 100% Cotton"
    assert peel_leadin("Material:alloy") == "Material:alloy"
    assert peel_leadin("Shaft measures approximately 8.37\" from arch") == "Shaft measures approximately 8.37\" from arch"


def test_clause_extractor_on_fixture_style_paraphrases(agent):
    cm = agent.catalog.matcher
    p = extract("Hey there! I'm on the hunt for some Tees & Blouses T-Shirts, and a key requirement is: cotton. I just love how comfy cotton feels, don't you?", 1, "hybrid", cm)
    assert "Tees & Blouses T-Shirts" in p.categories and ("cotton", "clause") in p.constraints
    q = extract("Oh, for that one, what matters is: Imported; Pull On closure. Just thought I'd share in case it helps.", 2, "hybrid", cm)
    assert [c for c, _ in q.constraints][:2] == ["Imported", "Pull On closure"]
    r = extract("Need: Made in the USA; Pull On closure.", 2, "hybrid", cm)
    assert [c for c, _ in r.constraints] == ["Made in the USA", "Pull On closure"]
