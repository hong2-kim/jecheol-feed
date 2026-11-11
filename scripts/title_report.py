# -*- coding: utf-8 -*-
"""우리 채널 쇼츠 성적표 — 제목·썸네일 판정(title-judge)에 넣는 자료 (2026-11-11)

  python3 scripts/title_report.py              오늘 성적표 (7일 지난 쇼츠, 중앙값·배수, 잘 된 편·안 된 편, 갈래별)
  python3 scripts/title_report.py --kind 해설   그 갈래(kind)만 따로 한 번 더 보여 줘요
  python3 scripts/title_report.py --like 김 수출  제목에 그 낱말이 든 지난 쇼츠와 배수

state/yt_stats.json(ytstats 작업이 매일 09시에 쌓음)만 읽어요. 인터넷·Claude 를 쓰지 않고, 아무것도 쓰지 않아요.
판정 방법은 시스메이커 무료 자료 「제목·썸네일 판정」 스킬(2026-10-20)을 따랐어요:
올린 지 7일 안 된 영상은 '쌓이는 중'으로 빼고, 채널 중앙값의 몇 배인지로 견줘요.
"""
import argparse
import statistics
import sys
from datetime import datetime, timedelta

from common import KST, ROOT, read_json

FRESH_DAYS = 7


def load():
    s = read_json(ROOT / "state" / "yt_stats.json", {}) or {}
    days = s.get("days") or {}
    if not days:
        return None, [], []
    last = sorted(days)[-1]
    kinds = s.get("kinds") or {}
    now = datetime.now(KST)
    ripe, fresh = [], []
    for vid, x in (days[last].get("videos") or {}).items():
        at = datetime.fromisoformat(str(x.get("at", "")).replace("Z", "+00:00"))
        row = {"id": vid, "title": str(x.get("t", "")).replace("\n", " "), "views": int(x.get("v") or 0),
               "at": at.astimezone(KST).date().isoformat(), "kind": kinds.get(vid) or "-"}
        (fresh if now - at < timedelta(days=FRESH_DAYS) else ripe).append(row)
    return last, ripe, fresh


def show(rows, median, limit=None):
    for r in rows[:limit] if limit else rows:
        print(f"  {r['views'] / median:4.1f}배  {r['views']:>5}회  {r['at']}  [{r['kind']}]  {r['title'][:60]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", help="이 갈래(kind)만 따로: 해설, 발견, 소식, 저녁추천 …")
    ap.add_argument("--like", nargs="+", help="제목에 이 낱말이 든 지난 쇼츠")
    a = ap.parse_args()
    last, ripe, fresh = load()
    if not ripe:
        print("성적표가 비었어요(state/yt_stats.json). 판정 없이 평소 규칙대로 제목을 정해요.")
        return
    median = statistics.median(r["views"] for r in ripe)
    print(f"성적표 {last} 기준 · 7일 지난 쇼츠 {len(ripe)}편 · 채널 중앙값 {median:g}회 (배수 = 조회수 ÷ 중앙값)")
    by = sorted(ripe, key=lambda r: -r["views"])
    print("\n잘 된 편 (2배 이상):")
    show([r for r in by if r["views"] >= 2 * median], median)
    print("\n안 된 편 (0.5배 이하, 낮은 차례로 10편):")
    show(sorted([r for r in by if r["views"] <= 0.5 * median], key=lambda r: r["views"]), median, 10)
    print("\n갈래별 중앙값 (편수):")
    groups = {}
    for r in ripe:
        groups.setdefault(r["kind"], []).append(r["views"])
    for k, l in sorted(groups.items(), key=lambda kv: -statistics.median(kv[1])):
        print(f"  [{k}] {statistics.median(l) / median:.1f}배 ({len(l)}편)")
    print("\n최근 20편 (올린 차례):")
    show(sorted(ripe, key=lambda r: r["at"], reverse=True), median, 20)
    if a.kind:
        print(f"\n[{a.kind}] 만:")
        show([r for r in by if r["kind"] == a.kind], median)
    if a.like:
        hits = [r for r in by if any(w in r["title"] for w in a.like)]
        print(f"\n제목에 {' / '.join(a.like)} 가 든 지난 쇼츠:")
        show(hits, median) if hits else print("  없어요")
    if fresh:
        print(f"\n아직 쌓이는 중 (7일 미만, 비교에서 뺌): {len(fresh)}편")
        for r in sorted(fresh, key=lambda r: r["at"], reverse=True)[:10]:
            print(f"  {r['views']:>5}회  {r['at']}  [{r['kind']}]  {r['title'][:60]}")


if __name__ == "__main__":
    main()
