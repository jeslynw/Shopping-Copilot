#!/usr/bin/env bash
# Fetch the frozen catalog from the participant-kit release and verify its SHA256 (the catalog is not committed — see DATA_ATTRIBUTION.md).
set -euo pipefail
cd "$(dirname "$0")/.."
URL=https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
SHA=07fd142631fd6b03e2b4d09988c3eb7d53720e9d57010c79db48eeaada50a8f8
mkdir -p data
if [ ! -f data/catalog.jsonl.gz ]; then echo "downloading catalog.jsonl.gz (19 MB)…"; curl -sL "$URL" -o data/catalog.jsonl.gz; fi
got=$(shasum -a 256 data/catalog.jsonl.gz | cut -d' ' -f1)
[ "$got" = "$SHA" ] || { echo "SHA256 mismatch: $got"; exit 1; }
[ -f data/catalog.jsonl ] || gzip -dk data/catalog.jsonl.gz
echo "ok: data/catalog.jsonl ($(wc -l < data/catalog.jsonl | tr -d ' ') products), sha256 verified"
