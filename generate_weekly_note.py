#!/usr/bin/env python3
"""주간 노트 자동 생성 배치 스크립트.

매주 월요일 실행되어 지난주(직전 월~일)의 데일리노트를 읽고,
태그별로 묶은 위클리노트를 daily-notes/{year}-aggregate/ 에 생성한다.

규칙 (obsidian/weekly-note-convention.md):
- 태그 하나당 H2 헤더 하나를 만든다 (## #tag, 태그 그대로 표기)
- 한 줄 띄우고 그 태그에 속하는 데일리노트 내용을 모두 불릿 리스트로 넣는다
- 한 줄 띄우고 다음 태그 헤더를 넣는다
- 태그 순서는 먼저 나온 것부터 차례대로
- 한 불릿에 태그가 여러 개면 각 태그 섹션에 모두 중복해서 넣는다

의존성 없이 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path

# 볼트 경로는 --vault 인자 또는 OBSIDIAN_VAULT 환경변수로 지정한다.
# (개인 경로를 코드에 하드코딩하지 않는다.) main()에서 설정된다.
VAULT: Path

TEMPLATE_REL = "templates/weekly-note.md"
DAILY_DIR_FMT = "daily-notes/{year}"                 # 데일리노트 폴더 (연도별)
AGGREGATE_DIR_FMT = "daily-notes/{year}-aggregate"   # 위클리노트 폴더

# 태그: '#' 뒤 영숫자/밑줄로 시작, 이후 영숫자/밑줄/-// 허용
TAG_RE = re.compile(r"#([A-Za-z0-9_][A-Za-z0-9_/-]*)")
# 최상위 불릿: 들여쓰기 없이 '- ' 로 시작
TOP_BULLET_RE = re.compile(r"^- ")


def week_of(d: date) -> list[date]:
    """d가 속한 주의 월~일 7일을 반환한다."""
    monday = d - timedelta(days=d.weekday())  # weekday(): Mon=0
    return [monday + timedelta(days=i) for i in range(7)]


def target_week(run_date: date) -> list[date]:
    """run_date 기준 '지난주'의 월~일 7일을 반환한다."""
    return week_of(run_date - timedelta(days=7))


def strip_frontmatter(text: str) -> str:
    """맨 앞 --- ... --- frontmatter 블록을 제거한 본문을 반환한다."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


def _extract_tags(first_line: str) -> list[str]:
    """블록의 첫 줄(최상위 불릿)에서 태그를 등장 순서대로, 중복 없이 뽑는다."""
    seen: list[str] = []
    for m in TAG_RE.finditer(first_line):
        tag = m.group(1)
        if tag not in seen:
            seen.append(tag)
    return seen


def _finalize(lines: list[str]) -> tuple[list[str], list[str]]:
    tags = _extract_tags(lines[0])
    while lines and lines[-1].strip() == "":
        lines.pop()
    return tags, lines


def parse_blocks(body: str) -> list[tuple[list[str], list[str]]]:
    """본문을 (태그리스트, 블록라인들) 목록으로 파싱한다.

    최상위 불릿('- ' 로 시작, 들여쓰기 없음)이 블록의 시작이고,
    이후 들여쓰기된 하위 불릿/이어지는 줄은 같은 블록에 포함된다.
    """
    blocks: list[tuple[list[str], list[str]]] = []
    cur: list[str] | None = None
    for raw in body.splitlines():
        if TOP_BULLET_RE.match(raw):
            if cur is not None:
                blocks.append(_finalize(cur))
            cur = [raw]
        elif cur is not None:
            if raw.strip() == "":
                blocks.append(_finalize(cur))
                cur = None
            else:
                cur.append(raw)
    if cur is not None:
        blocks.append(_finalize(cur))
    return blocks


def collect(days: list[date]) -> tuple["OrderedDict[str, list[list[str]]]", int]:
    """지난주 데일리노트를 읽어 태그별 블록 목록과 파일 개수를 반환한다."""
    tag_blocks: "OrderedDict[str, list[list[str]]]" = OrderedDict()
    found = 0
    for d in days:
        f = VAULT / DAILY_DIR_FMT.format(year=d.year) / f"{d.isoformat()}.md"
        if not f.exists():
            continue
        found += 1
        body = strip_frontmatter(f.read_text(encoding="utf-8"))
        for tags, lines in parse_blocks(body):
            if not tags:
                continue
            for tag in tags:
                tag_blocks.setdefault(tag, []).append(lines)
    return tag_blocks, found


def load_frontmatter() -> str:
    """템플릿의 frontmatter를 읽어 {{date}}/{{time}}를 실행 시각으로 채운다."""
    tpl = (VAULT / TEMPLATE_REL).read_text(encoding="utf-8")
    now = datetime.now()
    return tpl.replace("{{date}}", now.strftime("%Y-%m-%d")).replace(
        "{{time}}", now.strftime("%H:%M")
    )


def render(frontmatter: str, tag_blocks: "OrderedDict[str, list[list[str]]]") -> str:
    sections = []
    for tag, blocks in tag_blocks.items():
        block_text = "\n".join("\n".join(b) for b in blocks)
        sections.append(f"## #{tag}\n\n{block_text}")
    fm = frontmatter.rstrip("\n")
    if not sections:
        return fm + "\n"
    return fm + "\n" + "\n\n".join(sections) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="지난주 데일리노트로 위클리노트를 생성한다.")
    ap.add_argument("--vault", metavar="PATH",
                    help="Obsidian 볼트 경로 (미지정 시 OBSIDIAN_VAULT 환경변수 사용)")
    ap.add_argument("--week", metavar="YYYY-MM-DD",
                    help="이 날짜가 속한 주의 위클리노트를 생성 (지난주가 아니라 그 주)")
    ap.add_argument("--run-date", help="실행일 시뮬레이션 (그 날 기준 지난주가 대상)")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    global VAULT
    vault_str = args.vault or os.environ.get("OBSIDIAN_VAULT")
    if not vault_str:
        ap.error("볼트 경로가 필요합니다. --vault PATH 또는 OBSIDIAN_VAULT 환경변수로 지정하세요.")
    VAULT = Path(vault_str).expanduser()

    if args.week:
        days = week_of(date.fromisoformat(args.week))
    else:
        run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
        days = target_week(run_date)
    monday = days[0]

    tag_blocks, found = collect(days)

    iso = monday.isocalendar()
    fname = f"{iso[0]}-W{iso[1]:02d}.md"
    out_dir = VAULT / AGGREGATE_DIR_FMT.format(year=monday.year)
    out_path = out_dir / fname

    content = render(load_frontmatter(), tag_blocks)

    print(f"[weekly-note] 대상 주: {monday} ~ {days[-1]} "
          f"(데일리노트 {found}개, 태그 {len(tag_blocks)}개)")
    print(f"[weekly-note] 출력 경로: {out_path}")

    if args.dry_run:
        print("----- DRY RUN -----")
        print(content)
        return

    if found == 0:
        print("[weekly-note] 지난주 데일리노트가 없어 생성을 건너뜁니다.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print("[weekly-note] 생성 완료.")


if __name__ == "__main__":
    main()
