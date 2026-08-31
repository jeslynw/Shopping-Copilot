import sqlite3

from copilot.extract import tokens


def test_fts_fuzz(agent, cards):
    strings = [c for _, _, _, card in cards for c in card["hard_constraints"] + card["soft_preferences"]]
    rows = agent.catalog.con.execute("SELECT title, features FROM products LIMIT 2500").fetchall()
    strings += [r[0] for r in rows] + [r[1] for r in rows]
    assert len(strings) > 5000
    errors = 0
    for s in strings:
        try:
            agent.catalog.search(tokens(s), 3)
            agent.catalog.search([s], 3)          # raw string → filtered out, never passed to MATCH
        except sqlite3.OperationalError:
            errors += 1
    assert errors == 0
