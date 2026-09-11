#!/bin/bash
#
# Remove the daily Scholar-metrics LaunchAgent installed by install-schedule.sh.
# The scraped data files (assets/metrics.json, assets/metrics-data.js) are left
# alone, so the page keeps showing the last known numbers.
#
set -euo pipefail

LABEL="com.zhenqian.scholar-metrics"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [ -f "$PLIST" ]; then
  rm -f "$PLIST"
  echo "Removed $PLIST"
else
  echo "No plist at $PLIST (nothing to remove)."
fi

echo "The daily metrics refresh is now disabled."
