#!/usr/bin/env bash
# Run the scorer test suite and save a dated log to qa/results/.
# Usage: ./qa/run_tests.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE="$(date +%Y-%m-%d)"
OUTFILE="$REPO_ROOT/qa/results/${DATE}_scorer.txt"

cd "$REPO_ROOT"
echo "Running scorer tests → $OUTFILE"
"$REPO_ROOT/venv/bin/pytest" tests/test_scorer.py -v 2>&1 | tee "$OUTFILE"
