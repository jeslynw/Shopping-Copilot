"""Every response is contract-valid; adversarial inputs never raise; ask_attribute is never null."""
from tests.conftest import PROFILE
from tools.validate_contract import validate

ADVERSARIAL = ["", " ", "x" * 10_000, "🙂 ünïcödé — “quotes” & <tags> {json}", "I'm looking for Jewelry Necklaces. A key requirement "
               "is: \"quoted\" thing; with: colons: and * ^ - NOT OR AND NEAR() fts5 operators.", None, 123, ["list"], {"d": 1}]


def test_adversarial_inputs_never_raise(agent):
    before = agent.internal_exceptions
    agent.reset("adv", PROFILE)
    for turn, msg in enumerate(ADVERSARIAL, start=1):
        resp = agent.respond("adv", msg, turn, 10)
        assert validate(resp) == [], (msg, validate(resp))
        assert resp["ask_attribute"] is not None
    assert agent.internal_exceptions == before


def test_weird_turn_and_top_k_values(agent):
    agent.reset("weird", PROFILE)
    for turn, k in [(0, 10), ("3", None), (True, -5), (11, 10 ** 6)]:
        resp = agent.respond("weird", "I'm looking for Women Shoes, but I'm still exploring.", turn, k)
        assert validate(resp) == []
        assert len(resp["recommendations"]) <= 100


def test_respond_without_reset_is_valid(agent):
    resp = agent.respond("never-reset", "hello", 1, 10)
    assert validate(resp) == []


def test_exactly_four_keys_and_asin_only_recs(agent):
    agent.reset("k", PROFILE)
    resp = agent.respond("k", "I'm looking for Jewelry Necklaces. A key requirement is: Material:alloy.", 1, 10)
    assert set(resp) == {"message", "ask_attribute", "recommendations", "usage"}
    assert all(set(r) == {"parent_asin"} for r in resp["recommendations"])
    assert set(resp["usage"]) == {"prompt_tokens", "completion_tokens"}
    assert len({r["parent_asin"] for r in resp["recommendations"]}) == len(resp["recommendations"])
