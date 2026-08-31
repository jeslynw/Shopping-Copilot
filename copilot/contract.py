from __future__ import annotations

ALLOWED_ATTRIBUTES = {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}


def validate_response(resp: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(resp, dict):
        return ["response is not a dict"]
    extra = set(resp) - {"message", "ask_attribute", "recommendations", "usage"}
    if extra:
        errors.append(f"extra keys {sorted(extra)}")
    for k in ("message", "ask_attribute", "recommendations"):
        if k not in resp:
            errors.append(f"missing {k}")
    if not isinstance(resp.get("message"), str):
        errors.append("message not a str")
    a = resp.get("ask_attribute")
    if a is not None and a not in ALLOWED_ATTRIBUTES:
        errors.append(f"ask_attribute {a!r} not allowed")
    recs = resp.get("recommendations")
    if not isinstance(recs, list) or len(recs) > 100:
        errors.append("recommendations not a list of ≤100")
    else:
        for i, r in enumerate(recs):
            if not isinstance(r, dict) or set(r) - {"parent_asin", "score"} or "parent_asin" not in r:
                errors.append(f"recommendations[{i}] keys invalid")
            elif not isinstance(r["parent_asin"], str) or not r["parent_asin"]:
                errors.append(f"recommendations[{i}].parent_asin invalid")
            elif "score" in r and not isinstance(r["score"], (int, float)):
                errors.append(f"recommendations[{i}].score not a number")
    if "usage" in resp:
        u = resp["usage"]
        if (not isinstance(u, dict) or set(u) != {"prompt_tokens", "completion_tokens"}
                or any(not isinstance(u[k], int) or isinstance(u[k], bool) or u[k] < 0 for k in u)):
            errors.append("usage invalid")
    return errors
