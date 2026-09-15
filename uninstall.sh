#!/usr/bin/env bash
# launchd 자동 실행 해제 스크립트.
set -euo pipefail

LABEL="com.obsidian.weekly-note"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"

echo "해제 완료: $LABEL"
