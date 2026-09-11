#!/bin/bash
#
# Install a macOS LaunchAgent that refreshes the Google Scholar numbers and
# publishes them several times a day, so the citation counts on the site stay
# current without any manual step.
#
#   bash tools/install-schedule.sh      # install / update the schedule
#   bash tools/uninstall-schedule.sh    # remove it again
#
# NOTE: this has to be run from a real Terminal window. `launchctl bootstrap` is
# refused when driven from a sandboxed/agent shell ("Bootstrap failed: 5:
# Input/output error"), which is why it is not done for you automatically.
#
# Once installed the job pushes to GitHub on its own, so the live site updates
# without you running anything. Uninstall it if you would rather publish by hand.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.zhenqian.scholar-metrics"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$ROOT/tools/refresh-metrics.log"

if [ ! -f "$ROOT/tools/refresh-and-publish.sh" ]; then
  echo "ERROR: tools/refresh-and-publish.sh not found under $ROOT" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

# Every 6 hours, at :15 past, plus once at login. Four scrapes a day is often
# enough for citation counts to look live, and gentle enough that Scholar is
# unlikely to start rate-limiting the profile. Widen the gaps if you would
# rather it ran less.
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/tools/refresh-and-publish.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>15</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>15</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>15</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>15</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
  <!-- Also fire at login. StartCalendarInterval alone loses a slot whenever the
       Mac is powered off, and a laptop shut overnight misses two of the four
       daily runs. Login covers exactly that case; the 2-hour cooldown in
       refresh-and-publish.sh stops frequent logins from scraping repeatedly. -->
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
PLIST_EOF

# Replace any previous version of the job, then load the new one.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "  runs     : at login, then 00:15, 06:15, 12:15 and 18:15 local time"
echo "             (a run missed while the Mac is asleep happens on wake)"
echo "  does     : scrape Google Scholar, then commit + push the numbers"
echo "  cooldown : skips if the numbers were refreshed less than 2 h ago"
echo "  log      : $LOG"
echo "  run now  : launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "  remove   : bash tools/uninstall-schedule.sh"
