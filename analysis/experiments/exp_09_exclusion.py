"""§3k — Seen-set exclusion (implicit negative feedback): naive (lethal) vs override-safe vs turn≥5 vs previous-turn-only; inverse detection test."""
from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
r0, r6 = replace(C.NORM(), extractor="hybrid"), replace(C.NORM(), extractor="hybrid", cutoff="R6")
rows = [
    C.run(replace(r0, label="R0 top-10 (control)"), cat, S),
    C.run(replace(r0, label="R0 + naive exclusion (cumulative, always)", exclusion="naive"), cat, S),
    C.run(replace(r0, label="R0 + override-safe exclusion (detection-gated)", exclusion="override_safe"), cat, S),
    C.run(replace(r6, label="R6 cutoff (control)"), cat, S),
    C.run(replace(r6, label="R6 + override-safe exclusion (detection-gated) — not shipped", exclusion="override_safe"), cat, S),
    C.run(replace(r6, label="R6 + cumulative exclusion from turn ≥ 5 (turns ≥ 4 only)", exclusion="turn5"), cat, S),
    C.run(replace(r6, label="R6 + previous-turn-only exclusion (detection-free, self-healing)", exclusion="prev_turn"), cat, S),
]
# inverse test: force the scenario detector to "buying" for every session → detection-gated exclusion becomes cumulative
class ForceBuying:
    def __init__(self, a): self.a = a
    def reset(self, *x): self.a.reset(*x)
    def respond(self, *x):
        out = self.a.respond(*x); self.a.st.scenario = "buying"; return out
rows.append(C.run(replace(r6, label="R6 + override-safe exclusion, detector forced to 'buying' (paraphrase failure simulation)",
                          exclusion="override_safe"), cat, S, agent_wrapper=ForceBuying))
rows.append(C.run(replace(r6, label="R6 + previous-turn-only exclusion, detector forced to 'buying' (no dependency)",
                          exclusion="prev_turn"), cat, S, agent_wrapper=ForceBuying))
C.header("§3k Seen-set exclusion")
print(C.table(rows))
print("\nReading: any cumulative set whose detection fails deletes the target in override sessions (pre-override hits don't count); "
      "previous-turn-only exclusion needs no detection and is back to a full shelf the next turn.")
C.save("exp_09_exclusion", rows)
