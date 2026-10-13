# -*- coding: utf-8 -*-
"""공식 기관 RSS를 읽어 새 글만 inbox 에 모아요.

  python scripts/fetch_sources.py
- 새 글: inbox/날짜.json
- 이미 본 글: state/seen_links.json (다시 모으지 않아요)
- 실패한 곳: logs/errors.jsonl 에 남기고 나머지는 계속 읽어요.
  다음에 돌릴 때 다시 읽으니, 그동안 올라온 글도 함께 들어와요.
"""
import json
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from common import ROOT, log_error, read_json, today_kst, write_json

UA = {"User-Agent": "Mozilla/5.0 (jecheol-feed; +rss reader)"}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse(xml_bytes):
    """RSS 2.0, RDF, Atom 을 모두 읽어 (제목, 링크, 날짜) 목록으로 돌려줘요."""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = date = ""
        for child in el:
            name = local(child.tag)
            if name == "title":
                title = (child.text or "").strip()
            elif name == "link":
                link = (child.text or "").strip() or child.get("href", "")
            elif name in ("pubDate", "date", "updated", "published") and not date:
                date = (child.text or "").strip()
        if title and link:
            out.append({"title": title, "link": link, "date": date})
    return out


def when(entry):
    """기사가 나온 때(초). 날짜를 읽지 못하면 가장 오래된 것으로 쳐요."""
    try:
        return parsedate_to_datetime(entry["date"]).timestamp()
    except Exception:
        return 0.0


def main():
    sources = read_json(ROOT / "sources.json")["rss"]
    seen = set(read_json(ROOT / "state" / "seen_links.json", []))
    health = read_json(ROOT / "state" / "source_health.json", {})
    first_run = not seen
    fresh = []
    for src in sources:
        try:
            req = urllib.request.Request(src["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=30) as res:
                entries = parse(res.read())
            new = [e for e in entries if e["link"] not in seen]
            for e in new:
                seen.add(e["link"])
                fresh.append({"source": src["id"], "source_name": src["name"], "use": src["use"], **e})
            health[src["id"]] = {"last_ok": today_kst(), "fails": 0}
            print(f"읽었어요: {src['name']} (새 글 {len(new)}개)")
        except Exception as e:
            log_error(f"fetch:{src['id']}", e)
            prev = health.get(src["id"], {})
            health[src["id"]] = {"last_ok": prev.get("last_ok"), "fails": prev.get("fails", 0) + 1, "last_error": str(e)[:200]}
            print(f"못 읽었어요: {src['name']} ({e})")
    # 먹거리 뉴스 (구글 뉴스 검색 RSS, 최근 이틀)
    for query in read_json(ROOT / "sources.json").get("news", []):
        try:
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query + " when:2d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as res:
                entries = sorted(parse(res.read()), key=when, reverse=True)[:8]  # 가장 새 기사부터
            new = [e for e in entries if e["link"] not in seen]
            for e in new:
                seen.add(e["link"])
                fresh.append({"source": "news", "source_name": "뉴스 검색: " + query, "use": "먹거리 소식", **e})
            print(f"읽었어요: 뉴스 '{query}' (새 글 {len(new)}개)")
        except Exception as e:
            log_error(f"fetch:news:{query}", e)
            print(f"못 읽었어요: 뉴스 '{query}' ({e})")

    # 서울 날씨 (Open-Meteo). 저녁 메뉴를 고를 때 써요.
    try:
        url = ("https://api.open-meteo.com/v1/forecast?latitude=37.57&longitude=126.98&timezone=Asia%2FSeoul&forecast_days=2"
               "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max")
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as res:
            daily = json.loads(res.read())["daily"]
        write_json(ROOT / "inbox" / f"{today_kst()}-weather.json", {
            "place": "서울", "source": "https://open-meteo.com/", "date": daily["time"][0],
            "weather_code": daily["weather_code"][0], "max_c": daily["temperature_2m_max"][0], "min_c": daily["temperature_2m_min"][0],
            "rain_chance_percent": daily["precipitation_probability_max"][0],
            "note": "weather_code: 0 맑음, 1~3 구름, 45~48 안개, 51~67 비, 71~77 눈, 80~82 소나기, 95~ 뇌우"})
        print("읽었어요: 서울 날씨")
    except Exception as e:
        log_error("fetch:weather", e)
        print(f"못 읽었어요: 날씨 ({e})")

    write_json(ROOT / "state" / "seen_links.json", sorted(seen))
    write_json(ROOT / "state" / "source_health.json", health)
    if first_run:
        # 처음에는 기관마다 쌓인 옛 글이 한꺼번에 들어와요. 곳마다 가장 위 10개만 남겨요.
        kept, count = [], {}
        for e in fresh:
            count[e["source"]] = count.get(e["source"], 0) + 1
            if count[e["source"]] <= 10:
                kept.append(e)
        fresh = kept
    path = ROOT / "inbox" / f"{today_kst()}.json"
    write_json(path, (read_json(path, []) or []) + fresh)
    print(f"끝. 오늘 새로 모은 글 {len(fresh)}개")


if __name__ == "__main__":
    main()
