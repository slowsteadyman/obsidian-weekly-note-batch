# 위클리노트 자동 생성 배치

매주 월요일, 지난주(직전 월~일)의 데일리노트를 읽어 태그별로 묶은 위클리노트를
`daily-notes/{year}-aggregate/` 폴더에 자동 생성한다.

## 동작 규칙

`obsidian/weekly-note-convention.md` + 협의 사항에 따른다.

- 태그 하나당 `## #태그` H2 헤더 (태그 그대로 표기)
- 헤더 아래 한 줄 띄우고, 그 태그에 속한 데일리노트 내용을 불릿으로 나열
- 태그 순서는 그 주에 **처음 등장한 순서**
- 한 불릿에 태그가 여러 개면 **각 태그 섹션에 모두 중복** 삽입
- 본문 최상위 불릿의 **태그는 제거**(헤더에 이미 있으므로), 하위 불릿은 원문 보존
- 파일명: `{ISO연도}-W{ISO주차}.md` (예: `2026-W37.md`)
- frontmatter는 `templates/weekly-note.md`를 사용하며 `{{date}} {{time}}`을 실행 시각으로 채움

## 파일

| 파일 | 설명 |
|---|---|
| `generate_weekly_note.py` | 생성 스크립트 (표준 라이브러리만 사용) |
| `com.obsidian.weekly-note.plist` | launchd 설정 **템플릿** (경로 플레이스홀더 포함) |
| `install.sh` / `uninstall.sh` | launchd 자동 실행 등록/해제 |

## 볼트 경로 지정

개인 경로를 코드에 넣지 않는다. 볼트 경로는 `--vault` 인자나 `OBSIDIAN_VAULT`
환경변수로 지정한다.

```bash
export OBSIDIAN_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<볼트이름>"
```

## 수동 실행

```bash
# 지난주 위클리노트 생성 (배치가 매주 월요일 실행하는 것과 동일)
python3 generate_weekly_note.py --vault "$OBSIDIAN_VAULT"

# 특정 날짜가 '속한 주'의 위클리노트 생성 (지난주가 아니라 그 주)
python3 generate_weekly_note.py --week 2026-09-10   # -> 2026-09-07~09-13 (W37)

# 특정 날짜를 실행일로 시뮬레이션 (그 날 기준 '지난주'가 대상)
python3 generate_weekly_note.py --run-date 2026-09-14

# 파일을 쓰지 않고 결과만 미리보기 (아무 옵션과 조합 가능)
python3 generate_weekly_note.py --week 2026-09-10 --dry-run
```

(`OBSIDIAN_VAULT`를 export 해뒀다면 `--vault`는 생략 가능.)

## 자동 실행 등록 (launchd)

`install.sh`가 plist 템플릿의 플레이스홀더(파이썬/스크립트/볼트/로그 경로)를 채워
`~/Library/LaunchAgents/` 에 설치하고 로드한다.

```bash
# 등록 (매주 월요일 09:00 자동 실행)
# PYTHON: launchd가 쓸 파이썬. 경로가 안 바뀌는 것을 권장(아래 FDA 참고)
PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  ./install.sh "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<볼트이름>"

# 등록 확인 / 즉시 한 번 실행(테스트)
launchctl list | grep weekly-note
launchctl start com.obsidian.weekly-note

# 해제
./uninstall.sh
```

### ⚠️ 전체 디스크 접근 권한 (필수)

macOS 개인정보 보호(TCC) 때문에, launchd로 도는 프로세스는 기본적으로
`~/Desktop`·iCloud(`~/Library/Mobile Documents`) 폴더를 읽지 못한다.
**시스템 설정 → 개인정보 보호 및 보안 → 전체 디스크 접근 권한**에
`install.sh`에 넘긴 `PYTHON` 바이너리를 추가해야 한다. 이 권한이 없으면
`Operation not permitted` 로 실패한다.

> 파이썬을 업데이트해 경로가 바뀌면 권한을 다시 추가해야 하므로,
> 패치 릴리스에도 경로가 안 바뀌는 파이썬(예: python.org 프레임워크
> `.../Versions/3.12/bin/python3.12`)을 쓰는 것이 좋다.

> 예약 시각(월 09:00)에 Mac이 꺼져 있거나 잠들어 있었다면, launchd가 다음에
> 깨어날 때 놓친 작업을 한 번 실행한다.
