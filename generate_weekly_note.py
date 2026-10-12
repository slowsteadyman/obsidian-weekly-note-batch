#!/usr/bin/env python3
"""주간 노트 자동 생성 배치 스크립트.

매주 월요일 실행되어 지난주(직전 월~일)의 데일리노트를 읽고,
태그별로 묶은 위클리노트를 daily-notes/{year}-aggregate/ 에 생성한다.

규칙 (obsidian/weekly-note-convention.md):
- `## 만든 노트` 헤더로 시작. 각 데일리노트의 `## 만든 노트` 섹션 불릿을
  날짜순으로 모아 붙이고, 노트명(위키링크) 기준 중복을 제거한다.
  그 주에 만든 노트가 없으면 헤더만 두고 한 줄 띄워 다음 섹션으로 넘어간다.
- 태그 하나당 H2 헤더 하나를 만든다 (## #tag, 태그 그대로 표기)
- 한 줄 띄우고 그 태그에 속하는 데일리노트 내용을 모두 불릿 리스트로 넣는다
- 한 줄 띄우고 다음 태그 헤더를 넣는다
- 태그 순서는 먼저 나온 것부터 차례대로
- 한 불릿에 태그가 여러 개면 각 태그 섹션에 모두 중복해서 넣는다
- 본문 최상위 불릿의 태그는 제거한다 (헤더에 이미 태그가 있으므로)
- 태그가 없는 최상위 불릿은 맨 아래 `## #태그없음` 섹션에 모아 넣는다
- `## 만든 노트`가 아닌 다른 H2 섹션(예: `## 보고 느낀 것`)의 불릿만 태그
  집계 대상이다. 헤더가 없는(구버전) 데일리노트는 본문 전체가 집계 대상이다.

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

TEMPLATE_REL = "templates/new-note-quartz.md"
DAILY_DIR_FMT = "daily-notes/{year}"                 # 데일리노트 폴더 (연도별)
AGGREGATE_DIR_FMT = "daily-notes/{year}-aggregate"   # 위클리노트 폴더

CREATED_NOTES_HEADER = "만든 노트"
NO_TAG_HEADER = "태그없음"

# 태그: '#' 뒤 유니코드 word 문자(한글 포함)로 시작, 이후 word/-// 허용
TAG_RE = re.compile(r"#(\w[\w/-]*)")
# 본문에서 태그 제거용: 앞쪽 공백까지 함께 지운다 (헤더에 이미 태그가 있으므로)
TAG_STRIP_RE = re.compile(r"\s*#\w[\w/-]*")
# 최상위 불릿: 들여쓰기 없이 '- ' 로 시작
TOP_BULLET_RE = re.compile(r"^- ")
# H2 섹션 헤더
SECTION_HEADER_RE = re.compile(r"^## (.+?)\s*$")
# 위키링크: [[노트명]] 또는 [[노트명|별칭]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


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


def split_sections(body: str) -> list[tuple[str, str]]:
    """본문을 (H2 헤더 제목, 섹션 본문) 목록으로 분리한다.

    첫 헤더 이전의 내용은 헤더 ''(빈 문자열)에 속한다 (헤더 없는 구버전 노트 대응).
    """
    sections: list[tuple[str, list[str]]] = []
    header = ""
    cur: list[str] = []
    for raw in body.splitlines():
        m = SECTION_HEADER_RE.match(raw)
        if m:
            sections.append((header, cur))
            header = m.group(1)
            cur = []
        else:
            cur.append(raw)
    sections.append((header, cur))
    return [(h, "\n".join(lines)) for h, lines in sections]


def _is_empty_bullet(lines: list[str]) -> bool:
    """내용 없는 빈 불릿('- ' 만 있는 템플릿 placeholder)인지 확인한다."""
    return len(lines) == 1 and lines[0][2:].strip() == ""


def split_top_blocks(text: str) -> list[list[str]]:
    """최상위 불릿('- ' 로 시작, 들여쓰기 없음) 단위로 블록을 나눈다.

    들여쓰기된 하위 불릿/이어지는 줄은 같은 블록에 포함된다.
    내용 없는 빈 불릿은 결과에서 제외한다.
    """
    blocks: list[list[str]] = []
    cur: list[str] | None = None

    def finalize(block: list[str]) -> None:
        while block and block[-1].strip() == "":
            block.pop()
        if block and not _is_empty_bullet(block):
            blocks.append(block)

    for raw in text.splitlines():
        if TOP_BULLET_RE.match(raw):
            if cur is not None:
                finalize(cur)
            cur = [raw]
        elif cur is not None:
            if raw.strip() == "":
                finalize(cur)
                cur = None
            else:
                cur.append(raw)
    if cur is not None:
        finalize(cur)
    return blocks


def _extract_tags(first_line: str) -> list[str]:
    """블록의 첫 줄(최상위 불릿)에서 태그를 등장 순서대로, 중복 없이 뽑는다."""
    seen: list[str] = []
    for m in TAG_RE.finditer(first_line):
        tag = m.group(1)
        if tag not in seen:
            seen.append(tag)
    return seen


def parse_tagged_blocks(text: str) -> list[tuple[list[str], list[str]]]:
    """태그 집계 대상 섹션 본문을 (태그리스트, 블록라인들) 목록으로 파싱한다."""
    result: list[tuple[list[str], list[str]]] = []
    for block in split_top_blocks(text):
        tags = _extract_tags(block[0])
        block[0] = TAG_STRIP_RE.sub("", block[0]).rstrip()
        result.append((tags, block))
    return result


def _created_note_key(block: list[str]) -> str:
    """'만든 노트' 블록의 중복 제거 키 (위키링크 노트명, 없으면 첫 줄 전체)."""
    m = WIKILINK_RE.search(block[0])
    return m.group(1).strip() if m else block[0].strip()


def collect(
    days: list[date],
) -> tuple[list[list[str]], "OrderedDict[str, list[list[str]]]", list[list[str]], int]:
    """지난주 데일리노트를 읽어 만든 노트, 태그별 블록, 무태그 블록, 파일 개수를 반환한다."""
    created_notes: list[list[str]] = []
    tag_blocks: "OrderedDict[str, list[list[str]]]" = OrderedDict()
    notag_blocks: list[list[str]] = []
    found = 0
    for d in days:
        f = VAULT / DAILY_DIR_FMT.format(year=d.year) / f"{d.isoformat()}.md"
        if not f.exists():
            continue
        found += 1
        body = strip_frontmatter(f.read_text(encoding="utf-8"))
        for header, section_text in split_sections(body):
            if header == CREATED_NOTES_HEADER:
                created_notes.extend(split_top_blocks(section_text))
                continue
            for tags, lines in parse_tagged_blocks(section_text):
                if tags:
                    for tag in tags:
                        tag_blocks.setdefault(tag, []).append(lines)
                else:
                    notag_blocks.append(lines)

    seen_keys: set[str] = set()
    deduped_created: list[list[str]] = []
    for block in created_notes:
        key = _created_note_key(block)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_created.append(block)

    return deduped_created, tag_blocks, notag_blocks, found


def load_frontmatter(title: str) -> str:
    """템플릿의 frontmatter를 읽어 {{title}}/{{date}}를 채운다."""
    tpl = (VAULT / TEMPLATE_REL).read_text(encoding="utf-8")
    today = date.today().isoformat()
    return tpl.replace("{{title}}", title).replace("{{date}}", today)


def render(
    frontmatter: str,
    created_notes: list[list[str]],
    tag_blocks: "OrderedDict[str, list[list[str]]]",
    notag_blocks: list[list[str]],
) -> str:
    sections = [f"## {CREATED_NOTES_HEADER}"]
    if created_notes:
        sections[0] += "\n\n" + "\n".join("\n".join(b) for b in created_notes)

    for tag, blocks in tag_blocks.items():
        block_text = "\n".join("\n".join(b) for b in blocks)
        sections.append(f"## #{tag}\n\n{block_text}")

    if notag_blocks:
        block_text = "\n".join("\n".join(b) for b in notag_blocks)
        sections.append(f"## #{NO_TAG_HEADER}\n\n{block_text}")

    fm = frontmatter.rstrip("\n")
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

    created_notes, tag_blocks, notag_blocks, found = collect(days)

    iso = monday.isocalendar()
    fname = f"{iso[0]}-W{iso[1]:02d}.md"
    out_dir = VAULT / AGGREGATE_DIR_FMT.format(year=monday.year)
    out_path = out_dir / fname

    content = render(load_frontmatter(fname[:-3]), created_notes, tag_blocks, notag_blocks)

    print(f"[weekly-note] 대상 주: {monday} ~ {days[-1]} "
          f"(데일리노트 {found}개, 만든 노트 {len(created_notes)}개, 태그 {len(tag_blocks)}개)")
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
