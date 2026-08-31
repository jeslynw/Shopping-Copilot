import random
from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
base = C.POP()
rules = [("R0", "R0 always top-10 (control)"), ("R1", "R1 turn 1 & 0 constraints → top-3"), ("R2", "R2 turn 1 & 0 constraints → top-1"),
         ("R3", "R3 turn 1 & 0 constraints → [] (pure ask)"), ("R4", "R4 turn ≤2 & <2 constraints → top-3"),
         ("R5", "R5 tier_size>10 & turn ≤2 → top-3"), ("R6", "R6 tier_size>10 & turn ≤3 → top-1"),
         ("R7", "R7 tier_size>30 & turn ≤2 → top-1"), ("R8", "R8 turn 1 → top-1 always"),
         ("gated", "information-gated R6 (turn 1 or reply yielded a template constraint; no clause constraints)"),
         ("gated2", "information-gated R6, recognised exhausted/boundary reply counts as yielded"),
         ("top1", "DEGENERATE always top-1 (metric artifact — disclosed, never shipped)")]
rows = [C.run(replace(base, label=lbl, cutoff=r, extractor="hybrid"), cat, S) for r, lbl in rules]
C.header("§3j Cutoff rules (on the popularity variant, hybrid extractor)")
print(C.table(rows))
r6 = rows[6]; print(f"\nR6 per-scenario: {C.per_scenario(r6)}")

# per-session accounting R6 vs R0
def contrib(s): return 0.5 * s["hit"] + 0.3 * s["reciprocal_rank"] + 0.2 * (11 - (s["first_hit_turn"] or 11)) / 10
r0 = {s["sample_id"]: s for s in rows[0]["sessions"]}; hurt = helped = withheld = delayed = lost = 0; deltas = []
for s in r6["sessions"]:
    a = r0[s["sample_id"]]; d = contrib(s) - contrib(a); deltas.append(d)
    hurt += d < -1e-9; helped += d > 1e-9
    if a["hit"] and (s["first_hit_turn"] or 99) > a["first_hit_turn"]:
        withheld += 1; delayed += s["hit"]; lost += not s["hit"]
print(f"R6 vs R0 per session: withheld a would-be hit {withheld} (delayed {delayed}, lost {lost}); net-hurt {hurt} (worst {min(deltas):+.3f}), "
      f"net-helped {helped}, mean Δ {sum(deltas)/len(deltas):+.4f}")

# phantom-phrase injection: a wrong constraint enters state with probability p per turn
class Phantom:
    def __init__(self, agent, p, prov, seed=0):
        self.a, self.p, self.prov, self.rng = agent, p, prov, random.Random(seed)
        self.pool = [f for prod in list(cat.products.values())[:5000] for f in (prod.get("features") or []) if len(f) > 10]
    def reset(self, *a): self.a.reset(*a)
    def respond(self, sid, msg, turn, k):
        if self.rng.random() < self.p:
            self.a.st.constraints.append((self.rng.choice(self.pool), self.prov))
        return self.a.respond(sid, msg, turn, k)
prow = []
for prov in ("template", "clause"):
    for r in ("R0", "R6", "gated"):
        prow.append(C.run(replace(base, label=f"phantom p=0.10 ({prov}-tagged) + {r}", cutoff=r, extractor="hybrid"), cat, S,
                          agent_wrapper=lambda ag, prov=prov: Phantom(ag, 0.10, prov)))
print("\n### Phantom-phrase injection (p = 0.10 per turn)\n"); print(C.table(prow))
print("\nReading: the cutoff multiplies extraction errors; the gate releases to a full shelf when a constraint is clause-tagged, "
      "but cannot see a phantom that passes as template — hence no LLM extractor in the scored path.")
C.save("exp_08_cutoff", rows + prow, {"accounting": {"withheld": withheld, "delayed": delayed, "lost": lost, "hurt": hurt, "helped": helped}})
