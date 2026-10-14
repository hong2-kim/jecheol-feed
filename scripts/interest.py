# -*- coding: utf-8 -*-
"""소재에 사람들이 관심이 있는지 지난 2년을 살펴봐요. 관심이 너무 없으면 올리지 않아요. (사용자가 2026-10-14 정함)

  python scripts/interest.py "강경젓갈축제" "가을엔 절로 페스타" --coverage 7

- 뉴스: 구글 뉴스에서 그 이름이 들어간 기사를 해마다 세요(지난 1년(요즘 한 달 빼고), 그 전 1년. 한 해 100개까지). 대략의 크기만 봐요.
- 검색량: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 이 있으면 네이버 데이터랩으로 지난 24개월 검색 추이를
  기준 낱말과 견줘요. 없으면 건너뛰어요.
- --coverage: 오늘 같은 소식을 쓴 매체 수(inbox 의 coverage). 처음 열리는 행사는 지난 기사가 없으니 이것으로 봐요.

판정: 올림(관심 많음) / 보통(써도 되지만 맨 앞에 두지 않음) / 뺌(관심이 너무 없음)
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (jecheol-feed; +rss reader)"}
BENCH = "제철음식"  # 데이터랩 검색량을 견줄 기준 낱말. 해마다 꾸준히 찾는 말이에요.


def news_count(name, start, end):
    q = f'"{name}" after:{start} before:{end}'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8")
    return len(re.findall(r"<item>", xml))


def search_trend(names, today):
    """네이버 데이터랩 검색어 트렌드. 기준 낱말의 평균을 1로 놓은 비율을 돌려줘요. 키가 없으면 None."""
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        return None
    out = {}
    for i in range(0, len(names), 4):  # 한 번에 다섯 묶음까지. 기준 낱말 하나 + 네 개씩
        groups = [{"groupName": BENCH, "keywords": [BENCH]}] + [{"groupName": n, "keywords": [n]} for n in names[i:i + 4]]
        body = json.dumps({"startDate": (today - timedelta(days=730)).isoformat(), "endDate": today.isoformat(),
                           "timeUnit": "month", "keywordGroups": groups}).encode()
        req = urllib.request.Request("https://openapi.naver.com/v1/datalab/search", data=body, method="POST",
                                     headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret, "Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        avg = {r["title"]: sum(p["ratio"] for p in r["data"]) / max(1, len(r["data"])) for r in res["results"]}
        peak = {r["title"]: max((p["ratio"] for p in r["data"]), default=0) for r in res["results"]}
        base = avg.get(BENCH) or 1
        for n in names[i:i + 4]:
            out[n] = {"avg_vs_bench": round(avg.get(n, 0) / base, 3), "peak_vs_bench": round(peak.get(n, 0) / base, 3)}
    return out


def verdict(recent, before, coverage, trend):
    total = recent + before
    if trend is not None and trend["peak_vs_bench"] < 0.02 and coverage < 5:
        return "뺌", "지난 2년 검색이 거의 없어요"
    if total >= 10 or coverage >= 5:
        return "올림", "지난 2년 기사가 많거나 오늘 여러 매체가 다뤘어요"
    if total >= 3 or coverage >= 3:
        return "보통", "관심이 조금 있어요. 맨 앞에는 두지 않아요"
    return "뺌", "지난 2년 기사도, 오늘 다룬 매체도 적어요"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--coverage", type=int, default=0)
    a = ap.parse_args()
    today = date.today()
    now = today - timedelta(days=30)  # 요즘 한 달 기사는 빼요. 지금 쏟아지는 기사는 --coverage 로 따로 봐요
    y1, y2 = today - timedelta(days=365), today - timedelta(days=730)
    trends = None
    try:
        trends = search_trend(a.names, today)
    except Exception as e:  # 검색량을 못 읽어도 뉴스로 판단해요
        print(json.dumps({"검색량": f"못 읽었어요 ({str(e)[:80]})"}, ensure_ascii=False))
    for n in a.names:
        recent, before = news_count(n, y1, now), news_count(n, y2, y1)
        t = (trends or {}).get(n)
        v, why = verdict(recent, before, a.coverage, t)
        row = {"이름": n, "지난1년_기사(최근한달제외)": recent, "그전1년_기사": before, "오늘_매체수": a.coverage, "판정": v, "까닭": why}
        if before == 0 and recent <= 2:
            row["참고"] = "처음 열리거나 새로 생긴 것일 수 있어요. 오늘 다룬 매체 수와 주최(지자체·관광공사 등)를 함께 봐요"
        if t:
            row["검색량_기준대비"] = t
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
