import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

from copilot.config import Config, llm_enabled_from_env, llm_provider_from_env, load_dotenv
from copilot.llm import LLM
from tests.conftest import CATALOG, PROFILE


class FakeClient:
    """Returns canned responses per call (text or dict → JSON); raise=True raises on every call."""

    def __init__(self, responses=(), raise_=False):
        self.responses, self.raise_, self.calls = list(responses), raise_, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_:
            raise RuntimeError("boom")
        r = self.responses.pop(0) if self.responses else ""
        text = json.dumps(r) if isinstance(r, dict) else str(r)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=120, output_tokens=30))


CFG = Config(llm=True, llm_extract=True)   # extraction is an ablation flag (off by default) — tests exercise it explicitly


def test_extract_keeps_only_grounded_spans_and_offered_categories():
    fake = FakeClient([{"category": "Jewelry Necklaces", "constraints": ["Material:alloy", "HALLUCINATED sparkle", "hi"],
                        "kind": "open_buying", "attribute": None}])
    llm = LLM(CFG, client=fake, provider="anthropic")
    llm.begin_turn()
    p = llm.extract("Hi! I need jewelry necklaces. It must have: Material:alloy.", 1, ["Jewelry Necklaces", "Jewelry"])
    assert p.constraints == [("Material:alloy", "llm")] and p.categories == ("Jewelry Necklaces",) and p.cat_prov == "llm"
    assert p.kind == "open_buying" and p.template is False
    assert llm.turn_usage == (120, 30) and fake.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_extract_strips_leadins_and_category_echo_and_marks_yield():
    fake = FakeClient([{"category": "Accessories Belts", "constraints": ["Non-negotiable: 100% Leather", "Accessories Belts"],
                        "kind": "open_buying", "attribute": None},
                       {"category": None, "constraints": ["Mostly Imported", "Buckle closure"], "kind": "unknown", "attribute": None}])
    llm = LLM(CFG, client=fake, provider="anthropic")
    llm.begin_turn()
    p = llm.extract("Can you help me find Accessories Belts? Non-negotiable: 100% Leather.", 1, ["Accessories Belts"])
    assert p.constraints == [("100% Leather", "llm")] and p.categories == ("Accessories Belts",)
    q = llm.extract("Mostly Imported; Buckle closure.", 2, [])
    assert [c for c, _ in q.constraints] == ["Imported", "Buckle closure"] and q.kind == "yield"


def test_extract_rejects_category_outside_candidates():
    llm = LLM(CFG, provider="anthropic", client=FakeClient([{"category": "Women Dresses", "constraints": [], "kind": "open_browsing", "attribute": None}]))
    llm.begin_turn()
    p = llm.extract("Show me some basketball men — still deciding.", 1, ["Basketball Men"])
    assert p.categories == () and p.cat_prov == "none" and p.constraints == []


def test_failures_return_none_and_open_breaker():
    fake = FakeClient(raise_=True)
    llm = LLM(CFG, client=fake, provider="anthropic")
    llm.begin_turn()
    for _ in range(3):
        assert llm.extract("anything", 2, []) is None
    assert llm.breaker_open and llm.failures == 3
    n = len(fake.calls)
    assert llm.polish("draft", {}) is None and len(fake.calls) == n      # breaker: no further calls


def test_polish_strips_urls_and_store_names():
    llm = LLM(CFG, provider="anthropic", client=FakeClient(["Great pick: the Hanes Women's Bra — see https://example.com for more! Any colour preference?"]))
    llm.begin_turn()
    out = llm.polish("draft", {"stores": ["Hanes"]})
    assert "http" not in out and "Hanes" not in out and "the the" not in out and "Women's Bra" in out


def test_rerank_is_grounded_to_offered_ids():
    llm = LLM(replace(CFG, llm_rerank=True), provider="anthropic", client=FakeClient([{"order": ["B", "ZZZ", "B", "A"]}]))
    llm.begin_turn()
    items = [{"asin": a, "title": a, "matches": []} for a in ("A", "B", "C")]
    assert llm.rerank(items, ["x"], "Cat") == ["B", "A", "C"]


def test_llm_extract_is_off_by_default(agent, monkeypatch):
    monkeypatch.setenv("COPILOT_LLM_PROVIDER", "anthropic")
    from copilot.agent import Agent
    fake = FakeClient(["POLISHED"] * 5)
    on = Agent(CATALOG, replace(agent.cfg, llm=True), llm_client=fake)
    on.reset("d", PROFILE)
    on.respond("d", "hey, browsing basketball men stuff — needs a Drawstring closure pls", 1, 10)
    assert len(fake.calls) == 1 and "draft" in fake.calls[0]["messages"][0]["content"]     # polish only, no extraction call
    assert on.sessions["d"].constraints and on.sessions["d"].constraints[0].provenance == "clause"


def test_agent_invariance_with_polish_on(agent, monkeypatch):
    monkeypatch.setenv("COPILOT_LLM_PROVIDER", "anthropic")
    from copilot.agent import Agent
    fake = FakeClient(["POLISHED"] * 20)
    on = Agent(CATALOG, replace(agent.cfg, llm=True), llm_client=fake)
    script = ["I'm looking for Basketball Men, but I'm still exploring.", "For that, what matters is: Drawstring closure.",
              "I don't have an additional preference for material."]
    outs = []
    for a in (agent, on):
        a.reset("inv", PROFILE)
        outs.append([a.respond("inv", m, i + 1, 10) for i, m in enumerate(script)])
    for off, o in zip(*outs):
        assert off["recommendations"] == o["recommendations"] and off["ask_attribute"] == o["ask_attribute"]
        assert o["message"] == "POLISHED" and o["usage"] == {"prompt_tokens": 120, "completion_tokens": 30}
        assert off["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
    assert len(fake.calls) == 3            # templates matched every message → no extraction calls, one polish per turn


def test_agent_uses_llm_extraction_only_when_templates_fail(agent, monkeypatch):
    monkeypatch.setenv("COPILOT_LLM_PROVIDER", "anthropic")
    from copilot.agent import Agent
    fake = FakeClient([{"category": "Basketball Men", "constraints": ["Drawstring closure"], "kind": "open_buying", "attribute": None},
                       "POLISHED"])
    on = Agent(CATALOG, replace(agent.cfg, llm=True, llm_extract=True), llm_client=fake)
    on.reset("p", PROFILE)
    r = on.respond("p", "hey, browsing basketball men stuff — needs a Drawstring closure pls", 1, 10)
    st = on.sessions["p"]
    assert [c.text for c in st.constraints] == ["Drawstring closure"] and st.constraints[0].provenance == "llm"
    assert st.categories == ("Basketball Men",) and st.cat_prov == "exact"    # deterministic exact match wins over the LLM's
    assert len(r["recommendations"]) == 10                                    # llm-provenance → gate releases, never top-1
    assert len(fake.calls) == 2


def test_agent_with_failing_llm_matches_offline(agent, monkeypatch):
    monkeypatch.setenv("COPILOT_LLM_PROVIDER", "anthropic")
    from copilot.agent import Agent
    bad = Agent(CATALOG, replace(agent.cfg, llm=True), llm_client=FakeClient(raise_=True))
    for a in (agent, bad):
        a.reset("f", PROFILE)
    m = "I'm looking for Jewelry Necklaces. A key requirement is: Material:alloy."
    assert agent.respond("f", m, 1, 10)["recommendations"] == bad.respond("f", m, 1, 10)["recommendations"]
    assert bad.internal_exceptions == 0


class FakeOpenAIClient:
    def __init__(self, responses=()):
        self.responses, self.calls = list(responses), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0) if self.responses else ""
        text = json.dumps(r) if isinstance(r, dict) else str(r)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                               usage=SimpleNamespace(prompt_tokens=80, completion_tokens=20))


def test_openai_provider_extract_and_polish():
    fake = FakeOpenAIClient([{"category": "Jewelry Necklaces", "constraints": ["Material:alloy", "made up"], "kind": "open_buying",
                              "attribute": None}, "Polished text."])
    llm = LLM(CFG, client=fake, provider="openai")
    assert llm.extract_model == "gpt-4.1-mini"
    llm.begin_turn()
    p = llm.extract("Hi! I need jewelry necklaces. It must have: Material:alloy.", 1, ["Jewelry Necklaces"])
    assert p.constraints == [("Material:alloy", "llm")] and p.categories == ("Jewelry Necklaces",)
    assert fake.calls[0]["response_format"]["json_schema"]["strict"] is True and "max_completion_tokens" in fake.calls[0]
    assert llm.polish("draft", {}) == "Polished text." and llm.turn_usage == (160, 40)


def test_dotenv_loader_sets_missing_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False); monkeypatch.setenv("COPILOT_KEEP", "orig")
    env = tmp_path / ".env"; env.write_text("# comment\nOPENAI_API_KEY=sk-file  # trailing\nCOPILOT_KEEP=changed\nEMPTY=\n")
    load_dotenv(env)
    assert os.environ["OPENAI_API_KEY"] == "sk-file" and os.environ["COPILOT_KEEP"] == "orig" and "EMPTY" not in os.environ


def test_env_switch(monkeypatch):
    for v in ("COPILOT_LLM", "COPILOT_OFFLINE", "COPILOT_LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("copilot.config.load_dotenv", lambda path=None: None)
    assert llm_provider_from_env() is None and llm_enabled_from_env() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_provider_from_env() == "openai" and llm_enabled_from_env() is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant"); assert llm_provider_from_env() == "openai"
    monkeypatch.setenv("COPILOT_LLM_PROVIDER", "anthropic"); assert llm_provider_from_env() == "anthropic"
    monkeypatch.delenv("COPILOT_LLM_PROVIDER"); monkeypatch.delenv("OPENAI_API_KEY")
    assert llm_provider_from_env() == "anthropic" and llm_enabled_from_env() is True
    monkeypatch.setenv("COPILOT_LLM", "0"); assert llm_enabled_from_env() is False
    monkeypatch.delenv("COPILOT_LLM"); monkeypatch.setenv("COPILOT_OFFLINE", "1"); assert llm_enabled_from_env() is False
    monkeypatch.delenv("COPILOT_OFFLINE"); monkeypatch.setenv("ANTHROPIC_API_KEY", ""); assert llm_enabled_from_env() is False
    monkeypatch.setenv("COPILOT_LLM", "1"); assert llm_enabled_from_env() is True
