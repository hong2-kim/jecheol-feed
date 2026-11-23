# -*- coding: utf-8 -*-
"""묶음 쇼츠 세 주제의 관심도를 같은 기간으로 견줘요. (2026-11-23 사용자: 내가 보낸 3개로 묶을 때 영상 전에 비교)

  python3 scripts/compare_interest.py "딸기모찌" "두바이 초콜릿" "군고구마빵" [--days 30] [--json out.json]

견주는 것 (모두 같은 기간: 오늘부터 --days 일 전까지)
  1) 구글 검색 관심도: 구글 트렌드(한국, 지난 30일이면 'today 1-m')의 세 낱말 상대값 평균. 읽히면 이것을 먼저 봐요.
     구글이 자동 요청을 막으면(429 등) '못 읽음'으로 적고 건너뛰어요.
  2) 네이버 검색 추이: NAVER_CLIENT_ID·NAVER_CLIENT_SECRET 이 있으면 데이터랩으로 같은 기간 상대값(날마다).
  3) 최근 뉴스 보도: 구글 뉴스에서 그 이름이 들어간 기사 수(기간 안, 100개까지).
  4) 유튜브: GOOGLE_TTS_API_KEY(유튜브 Data API 도 허용된 키)가 있으면 기간 안에 올라온 영상 상위 10개의 조회수 합·가장 많은 것.
  인스타그램은 로그인 없이 읽을 수 있는 숫자가 거의 없어서 이 스크립트는 보지 않아요. 웹에서 확인한 것이 있으면 설계도에 따로 적어요.

판정: 구글 검색 관심도가 읽혔으면 그 순서. 못 읽었으면 네이버 → 뉴스·유튜브 순위를 더한 순서.
맨 끝에 설계도 interest 칸에 넣을 {period, rows, pick, basis} 를 JSON 으로 보여 줘요(pick 은 낱말 그대로라 소재 id 로 바꿔 적어요).
"""
import argparse
import http.cookiejar
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def google_trends(names, days):
    """구글 트렌드 상대값 평균 {이름: 값}. 못 읽으면 (None, 까닭)."""
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = list(UA.items())
    timeframe = {7: "now 7-d", 30: "today 1-m", 90: "today 3-m"}.get(days) or f"{(date.today() - timedelta(days=days)).isoformat()} {date.today().isoformat()}"
    try:
        op.open("https://trends.google.com/trends/?geo=KR", timeout=20).read()
        req = {"comparisonItem": [{"keyword": n, "geo": "KR", "time": timeframe} for n in names], "category": 0, "property": ""}
        url = "https://trends.google.com/trends/api/explore?" + urllib.parse.urlencode({"hl": "ko", "tz": "-540", "req": json.dumps(req, ensure_ascii=False)})
        body = op.open(url, timeout=30).read().decode("utf-8")
        widgets = json.loads(body[body.index("{"):])["widgets"]
        w = next(w for w in widgets if w.get("id") == "TIMESERIES")
        url = "https://trends.google.com/trends/api/widgetdata/multiline?" + urllib.parse.urlencode(
            {"hl": "ko", "tz": "-540", "req": json.dumps(w["request"], ensure_ascii=False), "token": w["token"]})
        body = op.open(url, timeout=30).read().decode("utf-8")
        data = json.loads(body[body.index("{"):])["default"]["timelineData"]
    except Exception as e:
        why = f"HTTP {e.code}" if hasattr(e, "code") else type(e).__name__
        return None, f"구글 트렌드 못 읽음({why})"
    if not data:
        return None, "구글 트렌드 값 없음"
    out = {}
    for k, n in enumerate(names):
        vals = [p["value"][k] for p in data if len(p.get("value", [])) > k]
        out[n] = round(sum(vals) / max(1, len(vals)), 1)
    return out, "구글 트렌드(한국) 읽음"


def naver(names, days):
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        return None, "네이버 데이터랩 키 없음"
    try:
        body = json.dumps({"startDate": (date.today() - timedelta(days=days)).isoformat(), "endDate": date.today().isoformat(),
                           "timeUnit": "date", "keywordGroups": [{"groupName": n, "keywords": [n]} for n in names]}).encode()
        req = urllib.request.Request("https://openapi.naver.com/v1/datalab/search", data=body, method="POST",
                                     headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret, "Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        return {r["title"]: round(sum(p["ratio"] for p in r["data"]) / max(1, len(r["data"])), 1) for r in res["results"]}, "네이버 데이터랩 읽음"
    except Exception as e:
        return None, f"네이버 데이터랩 못 읽음({type(e).__name__})"


def news(name, days):
    start = (date.today() - timedelta(days=days)).isoformat()
    q = f'"{name}" after:{start}'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    try:
        xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8")
        return len(re.findall(r"<item>", xml))
    except Exception:
        return None


def youtube(name, days):
    key = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    if not key:
        return None
    after = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00Z"
    try:
        q = urllib.parse.urlencode({"part": "id", "q": name, "type": "video", "maxResults": 10, "order": "viewCount",
                                    "publishedAfter": after, "regionCode": "KR", "relevanceLanguage": "ko", "key": key})
        ids = [i["id"]["videoId"] for i in json.loads(urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{q}", timeout=30).read())["items"]]
        if not ids:
            return {"views": 0, "top": 0, "videos": 0}
        q = urllib.parse.urlencode({"part": "statistics,snippet", "id": ",".join(ids), "key": key})
        items = json.loads(urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/videos?{q}", timeout=30).read())["items"]
        # 제목에 그 낱말이 없는 영상은 세지 않아요(검색이 엉뚱한 인기 영상을 섞어 줄 때가 있어요)
        key_word = name.replace(" ", "")
        items = [i for i in items if key_word in i["snippet"]["title"].replace(" ", "")]
        views = [int(i["statistics"].get("viewCount", 0)) for i in items]
        return {"views": sum(views), "top": max(views, default=0), "videos": len(views)}
    except Exception as e:
        return {"error": type(e).__name__}


def rank(values):
    """{이름: 값} → {이름: 순위(1이 가장 높음)}. 값이 없으면 None."""
    have = {k: v for k, v in values.items() if isinstance(v, (int, float))}
    order = sorted(have, key=lambda k: -have[k])
    return {k: (order.index(k) + 1 if k in have else None) for k in values}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json")
    a = ap.parse_args()
    names, days = a.names, a.days
    period = f"{(date.today() - timedelta(days=days)).isoformat()}~{date.today().isoformat()}"
    g, g_why = google_trends(names, days)
    nv, nv_why = naver(names, days)
    nw = {n: news(n, days) for n in names}
    yt = {n: youtube(n, days) for n in names}
    yt_views = {n: (v or {}).get("views") if isinstance(v, dict) else None for n, v in yt.items()}
    print(f"기간 {period} · {g_why} · {nv_why} · 유튜브 {'읽음' if any(isinstance(v, int) for v in yt_views.values()) else '키 없음/못 읽음'}")
    rows = []
    for n in names:
        row = {"name": n}
        if g:
            row["구글 관심도"] = g.get(n)
        if nv:
            row["네이버 검색"] = nv.get(n)
        row["뉴스"] = f"{nw[n]}건" if nw[n] is not None else "못 읽음"
        v = yt[n]
        if isinstance(v, dict) and "views" in v:
            row["유튜브"] = f"상위 {v['videos']}개 조회 {v['views']:,}회(최고 {v['top']:,})"
        rows.append(row)
        print(" · " + ", ".join(f"{k} {x}" for k, x in row.items()))
    if g and any(g.values()):
        order, basis = sorted(names, key=lambda n: -(g.get(n) or 0)), "구글 검색 관심도 평균"
    elif nv:
        order, basis = sorted(names, key=lambda n: -(nv.get(n) or 0)), "네이버 검색 추이 평균(구글 트렌드 못 읽음)"
    else:
        rn, ry = rank(nw), rank(yt_views)
        score = {n: (rn[n] or len(names) + 1) + (ry[n] or len(names) + 1) for n in names}
        order = sorted(names, key=lambda n: (score[n], -(nw[n] or 0)))
        basis = "검색 관심도를 못 읽어 최근 뉴스 기사 수·유튜브 조회수 순위로 판단"
    print(f"\n관심도 순서: {' > '.join(order)} ({basis})")
    out = {"period": period, "rows": rows, "pick": order[0], "order": order, "basis": basis,
           "read": {"google": g_why, "naver": nv_why}}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
