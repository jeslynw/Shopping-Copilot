"""Validate agent responses against docs/agent_api_contract.json (pure-python check + jsonschema cross-check when installed).

    python tools/validate_contract.py results_responses.jsonl     # one JSON response per line
    python -c "from tools.validate_contract import validate; ..."
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from copilot.contract import validate_response  # noqa: E402

_SCHEMA = None


def schema_errors(resp: object) -> list[str]:
    global _SCHEMA
    try:
        import jsonschema
    except ImportError:
        return []
    if _SCHEMA is None:
        _SCHEMA = json.loads((ROOT / "docs" / "agent_api_contract.json").read_text())["turn_response"]
    v = jsonschema.Draft202012Validator(_SCHEMA)
    return [e.message for e in v.iter_errors(resp)]


def validate(resp: object) -> list[str]:
    return validate_response(resp) + schema_errors(resp)


if __name__ == "__main__":
    bad = 0
    for i, line in enumerate(Path(sys.argv[1]).read_text().splitlines()):
        errs = validate(json.loads(line))
        if errs:
            bad += 1
            print(i, errs)
    print(f"{bad} invalid responses")
    sys.exit(1 if bad else 0)
