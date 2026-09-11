#!/bin/bash
#
# Refresh the Google Scholar numbers AND publish them, so the live site stays
# current with no manual step.
#
#   bash tools/refresh-and-publish.sh
#
# This is what the LaunchAgent (tools/install-schedule.sh) runs. Run it by hand
# any time you want the published numbers updated immediately.
#
# Why this exists rather than relying on the GitHub Actions workflow alone:
# Scholar blocks requests from datacenter IPs, and GitHub-hosted runners are
# datacenter IPs. Scraping from this machine works because it goes out on a home
# connection. The workflow is kept as a backstop for when the Mac is off.
#
# Only the three generated files are ever committed, so work in progress is left
# alone and a dirty tree does not stop publishing.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$(command -v python3 || echo /usr/bin/python3)"
FILES=(assets/metrics.json assets/metrics-data.js index.html)

echo "=== $(date '+%Y-%m-%d %H:%M:%S') refresh-and-publish ==="

if ! "$PYTHON" tools/refresh_metrics.py --quiet; then
  echo "scrape failed - leaving the published numbers as they are."
  exit 1
fi

if git diff --quiet -- "${FILES[@]}"; then
  echo "numbers unchanged; nothing to publish."
  exit 0
fi

# `git commit -- <paths>` records only these files, ignoring whatever else may be
# staged, so an unrelated edit can never ride along in this commit.
git commit -q -m "chore: refresh Google Scholar metrics" -- "${FILES[@]}" || true
echo "committed refreshed numbers."

# Push straight away - this succeeds regardless of any work in progress, because
# the commit only touched our own files. A rebase is only needed if the remote
# has moved on, which happens when the GitHub Actions backstop also committed a
# refresh.
if git push -q origin HEAD:main 2>/dev/null; then
  echo "published."
  exit 0
fi

echo "remote has moved on; rebasing before retrying."
git fetch -q origin main
if ! git rebase -q origin/main 2>/dev/null; then
  git rebase --abort >/dev/null 2>&1 || true
  echo "could not rebase cleanly (work in progress?) - committed locally, not published."
  exit 0
fi
git push -q origin HEAD:main && echo "published."
