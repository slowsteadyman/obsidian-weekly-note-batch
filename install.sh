#!/usr/bin/env bash
# launchd 자동 실행 등록 스크립트.
# plist 템플릿의 플레이스홀더를 실제 절대경로로 채워 ~/Library/LaunchAgents/ 에
# 설치하고 로드한다.
#
#   사용법:  ./install.sh <볼트 절대경로>
#            OBSIDIAN_VAULT=<볼트경로> ./install.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT="${1:-${OBSIDIAN_VAULT:-}}"

if [ -z "$VAULT" ]; then
    echo "볼트 경로가 필요합니다. 사용법: ./install.sh <볼트 절대경로>" >&2
    echo "  (또는 OBSIDIAN_VAULT 환경변수 지정)" >&2
    exit 1
fi

LABEL="com.obsidian.weekly-note"
PLIST_SRC="$DIR/com.obsidian.weekly-note.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$DIR/logs" "$HOME/Library/LaunchAgents"

sed -e "s|__SCRIPT_PATH__|$DIR/generate_weekly_note.py|" \
    -e "s|__VAULT_PATH__|$VAULT|" \
    -e "s|__LOG_DIR__|$DIR/logs|" \
    "$PLIST_SRC" > "$PLIST_DST"

# 이미 로드돼 있으면 갱신을 위해 언로드 후 재로드
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "등록 완료: $LABEL"
echo "  스크립트: $DIR/generate_weekly_note.py"
echo "  볼트    : $VAULT"
echo "  로그    : $DIR/logs/"
launchctl list | grep weekly-note || true
