from copilot.config import Config
from copilot.rank import compile_matchers
from copilot.state import Constraint


def test_self_match_at_least_770_of_800(agent, cards):
    cfg = Config()
    total = ok = 0
    for s, t, cat, card in cards:
        cons = list(dict.fromkeys(card["hard_constraints"] + card["soft_preferences"]))
        text = agent.catalog.texts([t])[t]
        for m in compile_matchers([Constraint(c, "template", 1) for c in cons], cfg, agent.catalog):
            total += 1
            ok += bool(m.fn(text, t))
    print(f"self-match {ok}/{total}")
    assert total >= 780 and ok >= 770, (ok, total)


def test_color_and_budget_forms(agent):
    cfg = Config()
    ms = compile_matchers([Constraint("color: black", "template", 1), Constraint("budget around $10.00", "template", 1)], cfg, agent.catalog)
    assert ms[0].fn("a black shoe", "X") and not ms[0].fn("blackish", "X")
    asin = next(a for a, p in agent.catalog.price.items() if 9.0 <= p <= 11.0)
    assert ms[1].fn("", asin)


def test_two_agents_rank_identically(agent):
    from copilot.agent import Agent
    other = Agent(agent.catalog.path)
    script = ["I'm looking for Jewelry Necklaces. A key requirement is: Material:alloy.",
              "For that, what matters is: Triple Moon Pentagram Symbol.", "I don't have an additional preference for material."]
    outs = []
    for a in (agent, other):
        a.reset("det", {"purchase_frequency": "", "average_prior_rating": None, "rating_style": "", "preference_tags": [], "summary": ""})
        outs.append([a.respond("det", m, i + 1, 10)["recommendations"] for i, m in enumerate(script)])
    assert outs[0] == outs[1] and any(outs[0])
