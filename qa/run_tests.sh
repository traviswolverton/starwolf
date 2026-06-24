#!/usr/bin/env bash
# Run tests and save a dated log to qa/results/.
#
# Usage:
#   ./qa/run_tests.sh           — scorer unit tests only (no app needed)
#   ./qa/run_tests.sh ui        — Playwright UI tests only (app must be running)
#   ./qa/run_tests.sh all       — both suites

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE="$(date +%Y-%m-%d)"
PYTEST="$REPO_ROOT/venv/bin/pytest"

cd "$REPO_ROOT"

MODE="${1:-unit}"

run_unit() {
    OUTFILE="$REPO_ROOT/qa/results/${DATE}_scorer.txt"
    echo "Running scorer unit tests → $OUTFILE"
    "$PYTEST" tests/test_scorer.py -v 2>&1 | tee "$OUTFILE"
}

run_ui() {
    OUTFILE="$REPO_ROOT/qa/results/${DATE}_playwright.txt"
    echo "Running Playwright UI tests → $OUTFILE"
    echo "(App must be running on localhost:8501)"
    "$PYTEST" tests/test_playwright.py -v --browser chromium 2>&1 | tee "$OUTFILE"
}

case "$MODE" in
    unit) run_unit ;;
    ui)   run_ui ;;
    all)  run_unit; echo; run_ui ;;
    *)    echo "Usage: $0 [unit|ui|all]"; exit 1 ;;
esac
