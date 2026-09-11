#!/bin/bash
#
# Refresh the Google Scholar numbers AND publish them, so the live site stays
# current with no manual step.
#
#   bash tools/refresh-and-publish.sh            # respects the cooldown
#   bash tools/refresh-and-publish.sh --force    # scrape no matter what
#
# This is what the LaunchAgent (tools/install-schedule.sh) runs, both on a
# 6-hourly schedule and at login. Run it by hand any time you want the published
# numbers updated immediately.
#
# The cooldown exists because the job also fires at login: without it, opening
# the laptop five times a day would mean five scrapes. The scheduled runs are 6
# hours apart, so a 2-hour cooldown never blocks them.
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
MIN_AGE_MIN=120  # skip if the numbers were refreshed this recently

force=0
for arg in "$@"; do
  [ "$arg" = "--force" ] && force=1
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') refresh-and-publish ==="

if [ "$force" -eq 0 ]; then
  # Age of the last successful refresh, in minutes. Empty means "unknown"
  # (missing or unparsable file) - in that case scrape rather than skip.
  age="$("$PYTHON" - "$ROOT/assets/metrics.json" <<'PY'
import datetime, json, sys
try:
    t = datetime.datetime.fromisoformat(
        json.load(open(sys.argv[1], encoding="utf-8"))["updated"])
except Exception:
    print("")
    raise SystemExit
print(int((datetime.datetime.now(t.tzinfo) - t).total_seconds() // 60))
PY
)"
  if [ -n "$age" ] && [ "$age" -lt "$MIN_AGE_MIN" ]; then
    echo "refreshed ${age} min ago (cooldown ${MIN_AGE_MIN} min); nothing to do."
    exit 0
  fi
fi

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
