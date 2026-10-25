#!/bin/bash
# Daily availability refresh for the downtown-eats board.
# Runs from launchd (com.james.eats-dailyrefresh) each morning; zero Claude tokens.
set -e
cd "$(dirname "$0")/.."
/usr/bin/python3 scripts/refresh_availability.py
if ! git diff --quiet data/availability.js; then
  git add data/availability.js
  git commit -m "Daily availability refresh $(date +%Y-%m-%d)"
  git push
fi
