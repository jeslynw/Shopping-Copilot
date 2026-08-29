import os
from pathlib import Path

from copilot.catalog import _open_text, resolve_catalog_path
from tests.conftest import ROOT


def test_relative_from_repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert resolve_catalog_path("data/catalog.jsonl") == ROOT / "data/catalog.jsonl"


def test_relative_from_other_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert resolve_catalog_path("data/catalog.jsonl") == ROOT / "data/catalog.jsonl"   # resolved relative to the package


def test_gz_twin_and_gzip_sniff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = resolve_catalog_path("data/catalog.jsonl.gz")
    assert p is not None and p.suffix == ".gz"
    with _open_text(p) as fh:
        assert fh.readline().startswith("{")
    # a gz file under a plain name is sniffed by magic bytes, not by extension
    disguised = tmp_path / "catalog.jsonl"
    disguised.write_bytes(p.read_bytes()[:200000])
    with _open_text(disguised) as fh:
        assert fh.read(1) == "{"


def test_missing_returns_none_and_agent_degrades(tmp_path):
    assert resolve_catalog_path(tmp_path / "nope.jsonl") is None
    from copilot.agent import Agent
    a = Agent(tmp_path / "nope.jsonl")
    assert a.init_error and a.catalog is None
    a.reset("s", {})
    resp = a.respond("s", "hello", 1, 10)
    assert resp["recommendations"] == [] and resp["ask_attribute"] is not None
