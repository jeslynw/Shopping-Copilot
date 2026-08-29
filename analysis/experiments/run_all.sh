#!/usr/bin/env bash
# Re-run every §3 experiment; markdown to results/exp_NN.md, progress log to results/exp_NN.log. ~10 min on an M3 Pro.
set -u
cd "$(dirname "$0")"
PY=${PY:-../../.venv/bin/python}
mkdir -p results
for f in exp_*.py; do
  n=${f%.py}; echo "== $n"; "$PY" "$f" > "results/$n.md" 2> "results/$n.log" || echo "!! $n failed (see results/$n.log)"
done
echo "done"
