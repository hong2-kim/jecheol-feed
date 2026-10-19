# -*- coding: utf-8 -*-
"""오늘 읽을 규칙 파일을 골라 알려 줘요. 공통 규칙은 PROMPT.md, 나머지는 rules/ 에 있어요. (2026-10-19)

  python3 scripts/today_rules.py                 오늘(한국 시간) 읽을 파일
  python3 scripts/today_rules.py 2026-11-01      그날 읽을 파일
  python3 scripts/today_rules.py --show blog     파일 하나를 보여 줘요 (이름이나 경로)
  python3 scripts/today_rules.py --check 2026-10-19   그날 설계도에 보류 중인 칸이 들어갔는지 봐요

고르는 기준은 PROMPT.md 의 "만드는 영상" 표와 같아요. 요일, config.json 의 blog_days, myphotos/index.json 의 plan·side,
이번 달 videos/ 에 달마다 만드는 것이 있는지를 봐요. 읽기만 하고 아무것도 쓰지 않아요.
rules/_hold/ 는 보류 중인 규칙이라 어느 날에도 고르지 않아요.
"""
import argparse
import json
import sys
from datetime import date, datetime

from common import KST, ROOT, read_json

WEEK = "월화수목금토일"
# 처음에 읽을 파일 / 그 차례에 읽을 파일. 늦게 쓰는 것을 늦게 읽으면, 그 앞의 턴마다 그 글이 맥락에 실리지 않아요.
# trend.md 는 처음에 읽어요: 카드·저녁·발견형 제목의 "유행 음식 쇼츠 말투", 발견형·해외 트렌드의 근거·사진 규칙이 거기 있어요.
DAILY = [("rules/daily/cards.md", "카드 뉴스"), ("rules/daily/dinner.md", "저녁 TOP 5"),
         ("rules/daily/shorts.md", "모든 쇼츠 공통"), ("rules/daily/voice.md", "내레이션 쇼츠"),
         ("rules/daily/trend.md", "트렌드 후보, 유행 음식 쇼츠 말투, 유행 근거·회사 사진 규칙")]
DAILY_LATER = [("rules/daily/items.md", "순서 4번, 소식 글을 쓰기 직전")]
MONTHLY_DAY1 = ("1-monthly", "5-world", "1-check", "1-sheet")
# 소급해 만들지 않는 달마다 영상 (달, 이름). 2026-10 해외 트렌드는 규칙이 10월 14일에 생겨 만들지 않는다
# (2026-10-19 사용자가 정함). 11월부터는 규칙대로 만든다.
SKIP_MONTHLY = {("2026-10", "9-abroad")}
# 보류 중인 칸 (2026-10-19 사용자가 보류함, rules/_hold/README.md). 설계도에 들어가면 안 돼요.
HELD_META = ("score", "total_checked", "total_with_guess", "target", "channel_ref")
HELD_TAGS = ("트렌드", "연구")


def made_this_month(day, name, morning=False):
    """이번 달 videos/ 에 그 영상이 있는지. 오늘 폴더도 봐요(새벽에 미리 만든 것을 또 만들지 않게).
    morning=True 면 그날 아침 상태(오늘 폴더 빼고)로 봐요. 지난 날을 시험할 때 써요."""
    month, today = day.strftime("%Y-%m"), day.isoformat()
    return any((d / f"{name}.json").exists() for d in (ROOT / "videos").glob(f"{month}-*")
               if d.name < today or (d.name == today and not morning))


def photos_today(day):
    items = read_json(ROOT / "myphotos" / "index.json", []) or []
    today = day.isoformat()
    return [x for x in items if (x.get("plan") == today or x.get("side") == today)
            and not x.get("used") and not x.get("deleted")]


def pick(day, morning=False):
    """(처음에 읽을 파일, 그 차례에 읽을 파일, 정했을 때 읽을 파일). 모두 (경로, 까닭) 목록이에요."""
    wd = WEEK[day.weekday()]
    now, later = list(DAILY), list(DAILY_LATER)
    maybe = [("rules/when/cards-collection.md", "카드를 모음 카드로 만들기로 정했을 때"),
             ("rules/when/steps.md", "그날 내레이션 대신 넘겨 보는 해설로 만들 때")]
    greeting = ("rules/when/greeting-open.md", "말 거는 한마디로 여는 영상을 만드는 날")
    if wd in "월수금토일":
        now.append(("rules/weekday/find.md", f"{wd}요일 발견형"))
    else:
        maybe.append(("rules/weekday/find.md", "큰 이슈가 있어 발견형을 더 만들 때"))
    if wd == "화":
        now.append(("rules/weekday/story.md", "화요일 맛의 이야기"))
    if wd == "목":
        now += [("rules/weekday/local.md", "목요일 지역의 먹거리"), greeting]
    if wd == "금":
        later.append(("rules/weekday/trend-friday.md", "금요일, 순서 5-1번에 8-trend 를 쓰기 직전"))
    blog_days = (read_json(ROOT / "config.json", {}) or {}).get("blog_days") or []
    if wd in blog_days:
        now.append(("rules/weekday/blog-topic.md", f"{wd}요일 블로그 초안의 쓰는 날·주제 (발견형과 같은 음식)"))
        later.append(("rules/weekday/blog.md", "순서 6번, 블로그 초안을 쓰기 직전"))
        if wd == "토":  # 토요일 글은 주제를 고를 때부터 필요해요 (blog-topic.md 의 요일표가 가리켜요)
            now.append(("rules/weekday/blog-saturday.md", "토요일 블로그 글: 고르는 것부터"))
    month = day.strftime("%Y-%m")
    missing = [n for n in MONTHLY_DAY1 if (month, n) not in SKIP_MONTHLY and not made_this_month(day, n, morning)]
    if missing:  # 이번 달에 이미 있는 것은 다시 만들지 않아요
        now.append(("rules/monthly/day1.md", ("매달 1일" if day.day == 1 else "밀린 것") + ". 오늘 만들 것: " + ", ".join(missing)))
        if greeting not in now:
            now.append(greeting)
    if day.day >= 2 and (month, "9-abroad") not in SKIP_MONTHLY and not made_this_month(day, "9-abroad", morning):
        now.append(("rules/monthly/day2.md", ("매달 2일" if day.day == 2 else "밀린 것") + ". 오늘 만들 것: 9-abroad"))
    if photos_today(day):
        now.append(("rules/when/myphotos.md", "사용자가 보낸 사진·동영상을 오늘 씀"))
    return now, later, maybe


def size(path):
    return len((ROOT / path).read_text(encoding="utf-8"))


def check(day):
    """그날 설계도에 보류 중인 칸이 있으면 알려 줘요. 있으면 1 로 끝나요."""
    found = []
    for f in sorted((ROOT / "videos" / day.isoformat()).glob("*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        meta = spec.get("meta") or {}
        keys = [k for k in HELD_META if k in meta]
        keys += [f"others.{k}" for o in meta.get("others") or [] for k in HELD_META if k in o]
        tags = [c.get("tag") for c in spec.get("cards") or [] if c.get("tag") in HELD_TAGS]
        if keys or tags:
            found.append(f"{f.name}: " + ", ".join([f"meta 의 {k}" for k in dict.fromkeys(keys)] + [f"카드 tag '{t}'" for t in tags]))
    for line in found:
        print("  보류 중인 칸이에요. 지워 주세요: " + line)
    print(f"보류 칸 검사: {len(found)}개 파일" if found else "보류 칸 검사: 없음")
    return 1 if found else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("day", nargs="?", help="YYYY-MM-DD (없으면 오늘, 한국 시간)")
    ap.add_argument("--show", help="파일 하나를 보여 줘요 (blog, rules/weekday/blog.md 처럼)")
    ap.add_argument("--check", metavar="DAY", help="그날 설계도의 보류 칸 검사")
    a = ap.parse_args()
    if a.check:
        sys.exit(check(date.fromisoformat(a.check)))
    if a.show:
        hits = [p for p in (ROOT / "rules").rglob("*.md") if "_hold" not in p.parts
                and (p.stem == a.show or p.relative_to(ROOT).as_posix() == a.show)]
        if not hits:
            sys.exit(f"그런 규칙 파일이 없어요: {a.show}")
        print(hits[0].read_text(encoding="utf-8"))
        return
    day = date.fromisoformat(a.day) if a.day else datetime.now(KST).date()
    now, later, maybe = pick(day)
    print(f"{day.isoformat()} {WEEK[day.weekday()]}요일. PROMPT.md(공통 규칙)에 더해 아래 파일을 Read 로 끝까지 읽어요.")
    print("지금 읽을 파일:")
    for path, why in now:
        print(f"  {path}  ({why}, {size(path):,}자)")
    print("그 차례에 읽을 파일 (그 일을 시작하기 직전에 꼭 읽는다):")
    for path, why in later:
        print(f"  {path}  ({why}, {size(path):,}자)")
    print("정했을 때 읽을 파일:")
    for path, why in maybe:
        print(f"  {path}  ({why})")
    print("rules/_hold/ 는 보류 중인 규칙이라 읽지 않아요.")


if __name__ == "__main__":
    main()
