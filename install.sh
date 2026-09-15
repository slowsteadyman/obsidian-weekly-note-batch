#!/usr/bin/env bash
# launchd 자동 실행 등록 스크립트.
# plist 템플릿의 플레이스홀더를 실제 절대경로로 채워 ~/Library/LaunchAgents/ 에
# 설치하고 로드한다.
#
#   사용법:  ./install.sh <볼트 절대경로>
#            OBSIDIAN_VAULT=<볼트경로> ./install.sh
#
#   파이썬 인터프리터는 PYTHON 환경변수로 지정한다(미지정 시 /usr/bin/python3).
#   macOS 개인정보 보호(TCC) 때문에, 여기 지정한 파이썬 바이너리에
#   '전체 디스크 접근 권한'을 부여해야 Desktop/iCloud 볼트를 읽을 수 있다.
#   경로가 안 바뀌는 파이썬(예: python.org 프레임워크)을 쓰는 것을 권장한다.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT="${1:-${OBSIDIAN_VAULT:-}}"
PYTHON="${PYTHON:-/usr/bin/python3}"

if [ -z "$VAULT" ]; then
    echo "볼트 경로가 필요합니다. 사용법: ./install.sh <볼트 절대경로>" >&2
    echo "  (또는 OBSIDIAN_VAULT 환경변수 지정)" >&2
    exit 1
fi

LABEL="com.obsidian.weekly-note"
PLIST_SRC="$DIR/com.obsidian.weekly-note.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$DIR/logs" "$HOME/Library/LaunchAgents"

sed -e "s|__PYTHON__|$PYTHON|" \
    -e "s|__SCRIPT_PATH__|$DIR/generate_weekly_note.py|" \
    -e "s|__VAULT_PATH__|$VAULT|" \
    -e "s|__LOG_DIR__|$DIR/logs|" \
    "$PLIST_SRC" > "$PLIST_DST"

# 이미 로드돼 있으면 갱신을 위해 언로드 후 재로드
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "등록 완료: $LABEL"
echo "  파이썬  : $PYTHON"
echo "  스크립트: $DIR/generate_weekly_note.py"
echo "  볼트    : $VAULT"
echo "  로그    : $DIR/logs/"
launchctl list | grep weekly-note || true

echo
echo "※ 시스템 설정 > 개인정보 보호 및 보안 > 전체 디스크 접근 권한 에"
echo "  다음 바이너리를 추가해야 Desktop/iCloud 볼트를 읽을 수 있습니다:"
echo "    $PYTHON"
