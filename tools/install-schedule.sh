#!/bin/bash
#
# Install a macOS LaunchAgent that re-scrapes the Google Scholar metrics once a
# day, so the numbers on the homepage stay current without any manual step.
#
#   bash tools/install-schedule.sh      # install / update the schedule
#   bash tools/uninstall-schedule.sh    # remove it again
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.zhenqian.scholar-metrics"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$ROOT/tools/refresh-metrics.log"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"

if [ ! -f "$ROOT/tools/refresh_metrics.py" ]; then
  echo "ERROR: tools/refresh_metrics.py not found under $ROOT" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/tools/refresh_metrics.py</string>
    <string>--quiet</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST_EOF

# Replace any previous version of the job, then load the new one.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "  runs     : every day at 09:15 local time"
echo "  script   : $ROOT/tools/refresh_metrics.py"
echo "  log      : $LOG"
echo "  remove   : bash tools/uninstall-schedule.sh"
