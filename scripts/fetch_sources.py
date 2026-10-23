# -*- coding: utf-8 -*-
"""공식 기관 RSS를 읽어 새 글만 inbox 에 모아요.

  python scripts/fetch_sources.py
  python scripts/fetch_sources.py --dry 결과.json   아무것도 저장하지 않고, 지금 모일 글을 모두(이미 본 글 포함) 결과.json 에 써요 (시험용)
- 새 글: inbox/날짜.json
- 이미 본 글: state/seen_links.json (다시 모으지 않아요)
- 실패한 곳: logs/errors.jsonl 에 남기고 나머지는 계속 읽어요.
  다음에 돌릴 때 다시 읽으니, 그동안 올라온 글도 함께 들어와요.
- 글마다 `group`(어느 갈래의 정보원인지)과 `published`(한국 시간 발행일)를 적어요. (2026-10-23 2단계)
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
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


KST = timezone(timedelta(hours=9))


def when(entry):
    """기사가 나온 때(초). 날짜를 읽지 못하면 가장 오래된 것으로 쳐요.
    RSS 날짜는 'Mon, 19 Oct 2026 22:16:00 GMT' 꼴과 '2026-10-23 10:07:53'(한국 시간, 국내 매체) 꼴이 섞여 있어요."""
    d = entry.get("date", "")
    try:
        return parsedate_to_datetime(d).timestamp()
    except Exception:
        pass
    try:
        t = datetime.fromisoformat(d.replace("Z", "+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=KST)).timestamp()
    except Exception:
        return 0.0


def published(entry):
    """한국 시간 발행일 'YYYY-MM-DD HH:MM'. 읽지 못하면 빈칸."""
    t = when(entry)
    return datetime.fromtimestamp(t, KST).strftime("%Y-%m-%d %H:%M") if t else ""


def query_of(item):
    """sources.json 의 news 칸은 검색어 글자이거나 {"q": 검색어, "group": 갈래} 예요."""
    return (item, "기타") if isinstance(item, str) else (item["q"], item.get("group", "기타"))


STOP = set("출시 개최 진행 오늘 올해 내일 신제품 선봬 선보여 공개 운영 시작 확대 강화 기념 이벤트 행사 관련 위해 통해 대한 가운데 지난 이번 최대 첫선".split())


def words(title):
    """기사 제목의 낱말 (끝의 ' - 매체' 는 빼요)."""
    body = title.rsplit(" - ", 1)[0]
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", body) if w not in STOP}


def outlet(title):
    return title.rsplit(" - ", 1)[1].strip() if " - " in title else ""


def add_coverage(items):
    """같은 소식을 몇 곳이 썼는지 세어 coverage 에 적어요. 여러 매체가 쓴 소식일수록 많은 사람이 보는 소식이에요."""
    sets = [words(e["title"]) for e in items]
    parent = list(range(len(items)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = sets[i], sets[j]
            shared = len(a & b)
            if shared >= 3 or (shared >= 2 and shared / max(1, len(a | b)) >= 0.3):
                parent[root(i)] = root(j)
    groups = {}
    for i, e in enumerate(items):
        groups.setdefault(root(i), set()).add(outlet(e["title"]) or e["link"])
    for i, e in enumerate(items):
        e["coverage"] = len(groups[root(i)])
    top = sorted({root(i): items[i] for i in range(len(items))}.values(), key=lambda e: -e["coverage"])[:10]
    for e in top:
        if e["coverage"] > 1:
            print(f"  여러 곳이 쓴 소식 ({e['coverage']}곳): {e['title'][:60]}")


def keep(src, e, now):
    """RSS 한 곳에서 이 글을 모을지. keywords 가 있으면 제목에 그중 하나가 있어야 하고(회사 뉴스룸의 음식 아닌 글 거르기),
    max_age_days 가 있으면 그보다 오래된 글은 모으지 않아요(새로 넣은 곳의 옛 글이 한꺼번에 들어오지 않게)."""
    if src.get("keywords") and not any(k in e["title"] for k in src["keywords"]):
        return False
    if src.get("max_age_days"):
        t = when(e)
        return bool(t) and now - t <= src["max_age_days"] * 86400
    return True


def main():
    dry = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--dry" else None
    config = read_json(ROOT / "sources.json")
    sources = config["rss"]
    seen = set() if dry else set(read_json(ROOT / "state" / "seen_links.json", []))
    health = read_json(ROOT / "state" / "source_health.json", {})
    first_run = not seen and not dry
    fresh = []
    now = time.time()
    for src in sources:
        try:
            req = urllib.request.Request(src["url"], headers=UA)
            with urllib.request.urlopen(req, timeout=30) as res:
                entries = parse(res.read())
            new = [e for e in entries if e["link"] not in seen]
            for e in new:
                seen.add(e["link"])
            new = [e for e in new if keep(src, e, now)]
            for e in new:
                fresh.append({"source": src["id"], "source_name": src["name"], "use": src["use"], "group": src.get("group", "공공·해외"),
                              **e, "published": published(e)})
            health[src["id"]] = {"last_ok": today_kst(), "fails": 0}
            print(f"읽었어요: {src['name']} (새 글 {len(new)}개)")
        except Exception as e:
            if not dry:
                log_error(f"fetch:{src['id']}", e)
            prev = health.get(src["id"], {})
            health[src["id"]] = {"last_ok": prev.get("last_ok"), "fails": prev.get("fails", 0) + 1, "last_error": str(e)[:200]}
            print(f"못 읽었어요: {src['name']} ({e})")
    # 먹거리 뉴스 (구글 뉴스 검색 RSS, 최근 이틀)
    for item in config.get("news", []):
        query, group = query_of(item)
        try:
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query + " when:2d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as res:
                entries = sorted(parse(res.read()), key=when, reverse=True)[:15]  # 가장 새 기사부터
            new = [e for e in entries if e["link"] not in seen]
            for e in new:
                seen.add(e["link"])
                fresh.append({"source": "news", "source_name": "뉴스 검색: " + query, "use": "먹거리 소식", "group": group,
                              **e, "published": published(e)})
            print(f"읽었어요: 뉴스 '{query}' (새 글 {len(new)}개)")
        except Exception as e:
            if not dry:
                log_error(f"fetch:news:{query}", e)
            print(f"못 읽었어요: 뉴스 '{query}' ({e})")
        time.sleep(0.3)  # 검색어가 늘어 구글 뉴스 요청 제한(429)에 덜 걸리게
    add_coverage([e for e in fresh if e["source"] == "news"])
    if dry:
        write_json(dry, fresh)
        print(f"시험 끝. 저장하지 않았어요. 모인 글 {len(fresh)}개 → {dry}")
        return

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


def digest(day, per=8):
    """inbox 를 통째로 읽지 않도록 갈래별로 짧게(2026-10-23 6단계). 사흘 안의 글만, 같은 제목은 한 번, 여러 매체가 쓴 것·새것부터.
    지난 60일 콘텐츠와 겹치는 글은 끝에 (지난 콘텐츠와 겹침: …) 를 붙여요(scripts/history.py). 주소는 적지 않으니 고른 글은 번호로 다시 찾아요."""
    import history
    items = []
    for d in (day, (datetime.fromisoformat(day) - timedelta(days=1)).strftime("%Y-%m-%d")):
        items += read_json(ROOT / "inbox" / f"{d}.json", []) or []
    now = datetime.fromisoformat(day).replace(hour=23, tzinfo=KST).timestamp()
    seen, groups = set(), {}
    for n, e in enumerate(items):
        t = e["title"].rsplit(" - ", 1)[0].strip()
        age = (now - when(e)) / 86400 if when(e) else 9
        if t in seen or age > 3:
            continue
        seen.add(t)
        groups.setdefault(e.get("group") or e.get("use") or "기타", []).append((n, t, e))
    past = history.load_history(datetime.fromisoformat(day).date())
    out = [f"{day} inbox 요약 (사흘 안, 같은 제목 한 번). 번호는 python3 scripts/fetch_sources.py --show {day} 번호 로 주소를 봐요"]
    for g, rows in sorted(groups.items(), key=lambda x: -len(x[1])):
        rows.sort(key=lambda r: (-(r[2].get("coverage") or 1), -when(r[2])))
        shown, picked = [], []
        for r in rows:  # 같은 소식을 제목만 달리 쓴 기사는 하나만 (add_coverage 와 같은 기준)
            w = words(r[1])
            if any(len(w & x) >= 3 or (len(w & x) >= 2 and len(w & x) / max(1, len(w | x)) >= 0.3) for x in shown):
                continue
            shown.append(w)
            picked.append(r)
        out.append(f"\n## {g} (글 {len(rows)}건, 소식 {len(picked)}개)")
        for n, t, e in picked[:per]:
            hit = history.compare([history.unit("후보", day, "후보", t, t, t, [e["link"]], False)], past)
            mark = f"  (지난 콘텐츠와 겹침: {hit[0].split('↔')[1].split(chr(39))[0].strip()})" if hit else ""
            out.append(f"{n:4} [{e.get('coverage') or 1}곳] {e.get('published', '')[5:]} {t[:70]} <{(outlet(e['title']) or e.get('source_name', ''))[:12]}>{mark}")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--digest":  # python3 scripts/fetch_sources.py --digest 2026-10-24 [갈래마다 몇 건]
        sys.stdout.reconfigure(encoding="utf-8")
        print(digest(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8))
    elif len(sys.argv) > 3 and sys.argv[1] == "--show":  # python3 scripts/fetch_sources.py --show 2026-10-24 번호 [번호 …]
        sys.stdout.reconfigure(encoding="utf-8")
        day = sys.argv[2]
        items = (read_json(ROOT / "inbox" / f"{day}.json", []) or []) + (read_json(ROOT / "inbox" / f"{(datetime.fromisoformat(day) - timedelta(days=1)).strftime('%Y-%m-%d')}.json", []) or [])
        for n in sys.argv[3:]:
            e = items[int(n)]
            print(f"{n} | {e.get('published', e.get('date'))} | {e['title']} | {e['link']}")
    else:
        main()
