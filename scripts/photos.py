# -*- coding: utf-8 -*-
"""영상에 쓸 실제 사진과 축제 일정을 찾아요.

  python scripts/photos.py tour 대하구이          한국관광공사 포토코리아 사진 (공공누리 1유형)
  python scripts/photos.py commons "sanma shioyaki"  위키미디어 공용 사진 (CC0·퍼블릭 도메인·CC BY 만)
  python scripts/photos.py openverse "tteokbokki"  오픈버스(플리커·위키미디어 등) CC0·퍼블릭 도메인·CC BY 사진 (키 없이 돼요. 영어로 찾아야 잘 나와요, 2026-10-24)
  python scripts/photos.py pexels "grilled pork belly"  Pexels 무료 사진 (인스타·쇼츠·블로그 모두 돼요. 영어로 찾아야 잘 나와요)
  python scripts/photos.py unsplash "bibimbap"     Unsplash 무료 사진 (상업적 이용·수정 가능. Unsplash+ 유료 사진은 빼요, 2026-11-07)
  python scripts/photos.py pixabay "oysters"       Pixabay 무료 사진 (상업적 이용·수정 가능, 표기 없어도 돼요. AI 그림은 빼요, 2026-11-13)
  python scripts/photos.py food "짬뽕" [--en "Korean spicy seafood noodle soup;jjamppong"]   음식 사진 한 번에:
                                                  보관함 → 관광공사 → Unsplash·Pexels·Pixabay → 오픈버스·위키미디어 (2026-11-12)
                                                  --vault-last: 보관함을 맨 뒤로(저녁 추천, 2026-11-13: 바깥 사진에 맞는 게 없을 때만 보관함)
  python scripts/photos.py en "굴"                  그 음식·재료의 영어 검색어(ideas/dinner_menu.json·ideas/food_en.json)
  python scripts/photos.py festival 20261012      그날 이후 열리는 축제 (한국관광공사, 공식 일정)
  python scripts/photos.py get <주소> <저장할 파일>   사진을 내려받아 직접 눈으로 확인할 때
  python scripts/photos.py sheet tour 굴구이 15 /tmp/s.jpg   후보 여러 장을 번호를 붙여 한 장에 모아요 (commons·openverse 도 된다)
  python scripts/photos.py leads festival "죽변항 수산물축제" 2026   넓게 찾을 검색어(뉴스·블로그·SNS·유튜브·지난 회차) + 이미 확인한 출처 + 확인 차례
  python scripts/photos.py exif 사진.jpg              촬영일(EXIF) — 지난 축제 사진의 연도 확인

tour, festival 은 환경 변수 TOUR_API_KEY, pexels 는 PEXELS_API_KEY, pixabay 는 PIXABAY_API_KEY 가 있어야 해요.
unsplash 는 키가 없어도 돼요(2026-11-13 사용자: API 신경 쓰지 말고 그냥 써): 영어 검색 페이지 주소를 알려 주니 WebFetch 로 열어
images.unsplash.com 사진 주소·사진 페이지·찍은 사람을 읽고 get 으로 받아요. 키가 있으면 API 로 바로 찾아요.
결과는 한 줄에 하나씩 JSON으로 나와요.
unsplash·pexels·pixabay·openverse·commons 는 영어로 찾아야 사진이 많이 나와서(2026-11-13 사용자), 한국어 이름을 주면 영어 검색어로
먼저 찾고 한국어 결과는 뒤에 붙여요(영어로 찾은 줄에 "query"·"check" 가 붙어요). 영어 검색어는 사전에서 찾고, 없으면 --en 으로 줘요.
영어로 찾은 사진은 검색어가 비슷할 뿐이라, 사진 속 음식이 정말 그 음식인지 눈으로 보고 shows·match 를 적어요(짬뽕을 찾다 나온 라면 사진은 쓰지 않아요).
tour·commons 검색 결과는 임시 폴더에 6시간 저장해 같은 검색어를 다시 묻지 않아요. 내려받기는 scripts/web.py 로 해요
(같은 곳에 너무 자주 묻지 않고, 요청 제한(429)에는 Retry-After 를 지켜 세 번까지만 다시 해요. 2026-10-19).
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from web import WebError, get as web_get

CACHE = Path(tempfile.gettempdir()) / "jecheol-photos"
SEARCH_TTL = 6 * 3600


MENU = Path(__file__).resolve().parent.parent / "ideas" / "dinner_menu.json"
FOOD_EN = Path(__file__).resolve().parent.parent / "ideas" / "food_en.json"  # 제철 재료·간식 영어 이름(2026-11-13)
FEW = 6  # 검색 결과가 이보다 적으면 다른 말로 더 찾아요
EN_FIRST = {"unsplash", "pexels", "pixabay", "openverse", "commons"}  # 영어로 먼저 찾는 곳(2026-11-13 사용자)


def hangul(text):
    return bool(re.search(r"[가-힣]", text or ""))


def _n(s):
    return re.sub(r"[\s·\-()]", "", s or "")


def en_terms(name):
    """음식 이름의 영어 검색어(흔한 영문명 → 정확한 영문명). 메뉴 사전(ideas/dinner_menu.json)과 제철 재료 사전(ideas/food_en.json)의
    이름·aka 로 찾고, 없으면 이름 안에 든 가장 긴 이름으로 찾아요('얼큰한 순대국밥' → 순대국밥, '영덕 대게찜' → 대게).
    한 글자 이름(굴·밤·무·감)은 통째로 같을 때만 써요('무화과'가 '무'로 잡히지 않게). 못 찾으면 []."""
    items = []
    for f in (MENU, FOOD_EN):
        try:
            items += json.loads(f.read_text(encoding="utf-8"))["items"]
        except Exception:
            continue
    key, best = _n(name), None
    for x in items:
        for k in [x["name"], *x.get("aka", [])]:
            kk = _n(k)
            if kk == key:
                return list(x.get("en") or [])
            if len(kk) >= 2 and kk in key and (best is None or len(kk) > len(best[0])):
                best = (kk, x)
    if best:
        return list(best[1].get("en") or [])
    words = name.split()  # '통영 굴' → 띄어 쓴 낱말이 사전 이름과 통째로 같으면('굴') 그것으로
    if len(words) > 1:
        for w in reversed(words):
            got = en_terms(w)
            if got:
                return got
    return []


def _english_rows(rows, seen, term, query, rows_fn):
    try:
        more = rows_fn(term)
    except (WebError, ValueError):
        return
    for r in more:
        if r.get("url") in seen:
            continue
        seen.add(r.get("url"))
        rows.append({**r, "query": term, "check": f"영어 검색어 '{term}' 로 찾은 사진이에요. 사진 속 음식이 정말 '{query}' 인지 "
                                                 "눈으로 보고 shows·match 를 적어요(비슷한 다른 음식이면 쓰지 않아요)"})


def with_english(source, query, rows_fn, en=None):
    """한국어 이름으로 찾을 때 영어 검색어를 함께 써요. 같은 사진은 한 번만.
    Unsplash·Pexels·Pixabay·오픈버스·위키미디어(EN_FIRST)는 영어로 찾아야 사진이 많이 나와서(2026-11-13 사용자) 영어 검색어를 모두 먼저 찾고
    한국어 결과를 뒤에 붙여요. 다른 곳은 한국어로 찾고 FEW 장보다 적을 때만 영어로 더 찾아요."""
    if not hangul(query):
        return list(rows_fn(query))
    terms = en or en_terms(query)
    if not terms and source in EN_FIRST:
        print(json.dumps({"출처": source, "알림": f"'{query}' 의 영어 검색어가 사전에 없어요. 이 곳은 영어로 찾아야 사진이 많이 나와요 — "
                                                "영어 이름으로 다시 찾거나(food 는 --en '흔한 영어 이름;정확한 영어 이름'), ideas/food_en.json 에 더해요"},
                         ensure_ascii=False), file=sys.stderr)
    rows, seen = [], set()
    if source in EN_FIRST:
        for term in terms:
            _english_rows(rows, seen, term, query, rows_fn)
        if len(rows) < FEW * 2:
            try:
                for r in rows_fn(query):
                    if r.get("url") not in seen:
                        seen.add(r.get("url"))
                        rows.append(r)
            except (WebError, ValueError):  # 키가 없으면(SystemExit) 그 안내를 그대로 보여 줘요
                if not rows and not terms:
                    raise
        return rows
    try:
        rows = list(rows_fn(query))
    except (WebError, ValueError):
        rows = []  # 한국어 검색이 실패해도 영어로는 찾아봐요
    if len(rows) >= FEW:
        return rows
    seen = {r.get("url") for r in rows}
    for term in terms:
        _english_rows(rows, seen, term, query, rows_fn)
        if len(rows) >= FEW * 2:
            break
    return rows


def get(url, timeout=40):
    return web_get(url, timeout=timeout)


def cached(kind, query, fn):
    """같은 검색어는 6시간 동안 다시 묻지 않아요."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{kind}-{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"
    ttl = 24 * 3600 if kind == "pixabay" else SEARCH_TTL  # Pixabay API 는 검색 결과를 24시간 저장해 쓰라고 해요
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fn(query)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def tour_call(service, op, **params):
    key = os.environ.get("TOUR_API_KEY", "").strip()
    if not key:
        sys.exit("TOUR_API_KEY 가 없어요. 관광공사 사진과 축제 일정은 찾을 수 없어요.")
    q = {"serviceKey": key, "numOfRows": 40, "pageNo": 1, "MobileOS": "ETC", "MobileApp": "jecheolFeed", "_type": "json", **params}
    data = json.loads(get(f"https://apis.data.go.kr/B551011/{service}/{op}?" + urllib.parse.urlencode(q)).decode("utf-8", "replace"))
    body = data.get("response", {}).get("body", {})
    items = (body.get("items") or {}).get("item", []) if body.get("items") else []
    return body.get("totalCount", 0), items


def tour_rows(keyword):
    total, items = tour_call("PhotoGalleryService1", "gallerySearchList1", keyword=keyword, arrange="A")
    if isinstance(items, dict):  # 한 장뿐이면 목록이 아니라 하나로 와요
        items = [items]
    rows = []
    for it in items:
        if not it.get("galWebImageUrl"):  # 주소가 빠진 항목은 건너뛰어요 (2026-10-19 실행에서 멈춘 곳)
            continue
        who = (it.get("galPhotographer") or "").replace("한국관광공사 ", "")
        rows.append({"url": it["galWebImageUrl"], "title": it.get("galTitle"), "where": it.get("galPhotographyLocation"),
                     "shot": it.get("galPhotographyMonth"), "credit": f"ⓒ한국관광공사 포토코리아-{who}"})
    return {"total": total, "rows": rows}


def tour(keyword):
    data = cached("tour", keyword, tour_rows)
    print(json.dumps({"keyword": keyword, "total": data["total"]}, ensure_ascii=False))
    for row in data["rows"]:
        print(json.dumps(row, ensure_ascii=False))


def commons_rows(query):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 20,
        "gsrsearch": f"{query} filetype:bitmap -haslicense:attribution-same-license",
        "prop": "imageinfo", "iiprop": "size|extmetadata"})
    pages = (json.loads(get(url)).get("query", {}).get("pages", {}) or {}).values()
    rows = []
    for p in sorted(pages, key=lambda p: p.get("index", 0)):
        ii = p["imageinfo"][0]
        m = ii.get("extmetadata", {})
        lic = m.get("LicenseShortName", {}).get("value", "")
        ok = lic in ("CC0", "Public domain") or re.fullmatch(r"CC BY \d\.\d( [a-z]+)?", lic)
        if not ok or ii.get("width", 0) < 1200:
            continue
        name = p["title"].split(":", 1)[1]
        who = re.sub(r"<[^>]+>", "", m.get("Artist", {}).get("value", "")).strip()[:50]
        free = lic in ("CC0", "Public domain")
        rows.append({"url": "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(name) + "?width=1600",
                     "title": name, "size": f"{ii['width']}x{ii['height']}", "license": lic,
                     "credit": "" if free else f"{who} ({lic}) · commons.wikimedia.org/?curid={p['pageid']}",
                     "note": "출처 표시가 필요 없어요" if free else "저작자·라이선스·주소를 표시해야 해요"})
    return rows


LICENSE_MARK = {"by": "creativecommons.org/licenses/by/", "cc0": "creativecommons.org/publicdomain/zero/",
                "pdm": "creativecommons.org/publicdomain/mark/"}


def flickr_still_free(page, lic):
    """오픈버스가 가진 플리커 라이선스는 옛것일 수 있어요. 2026-10-24 CC BY 로 나온 사진 2장이 원본에서는
    '모든 권리 보유'로 바뀌어 있었어요. 원본 페이지에 지금도 같은 라이선스 주소가 있는지 봐요. 못 읽으면 쓰지 않아요."""
    try:
        html = web_get(page, timeout=25, retries=1, quiet=True).decode("utf-8", "ignore")
    except WebError:
        return False
    return LICENSE_MARK[lic] in html


def openverse_rows(query):
    """오픈버스는 플리커·위키미디어 등 여러 곳의 자유 이용 사진을 한꺼번에 찾아요. 상업적 이용과 수정이 되는 것 중
    CC0·퍼블릭 도메인·CC BY 만 남겨요(CC BY-SA 는 우리 영상까지 같은 라이선스로 풀어야 해서 빼요).
    플리커 사진은 원본 페이지에서 지금 라이선스를 다시 확인한 것만 남겨요."""
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({
        "q": query, "license": "cc0,pdm,by", "page_size": 20, "mature": "false"})  # 키 없이는 20장까지(넘으면 401)
    data = json.loads(get(url))
    rows, today = [], time.strftime("%Y-%m-%d")
    for r in data.get("results", []):
        if (r.get("width") or 0) < 1000:
            continue
        page = r.get("foreign_landing_url") or ""
        if "flickr.com" in page and not flickr_still_free(page, r["license"]):
            continue
        lic = "CC0" if r["license"] == "cc0" else "Public domain" if r["license"] == "pdm" else f"CC BY {r.get('license_version') or ''}".strip()
        free = r["license"] in ("cc0", "pdm")
        who = (r.get("creator") or "작자 미상")[:50]
        page = r.get("foreign_landing_url") or ""
        rows.append({"url": r["url"], "title": (r.get("title") or "")[:80], "size": f"{r.get('width')}x{r.get('height')}",
                     "license": lic, "from": r.get("source"),
                     "credit": "" if free else f"{who} ({lic}) · {page.split('://', 1)[-1]}",
                     "terms": {"url": r.get("license_url") or page, "checked": today, "scope": f"{lic}, 상업적 이용·수정 가능", "ok": True},
                     "note": "출처 표시가 필요 없어요" if free else "저작자·라이선스·주소를 표시해야 해요(credit 그대로)"})
    return rows


def openverse(query):
    for row in with_english("openverse", query, lambda q: cached("openverse", q, openverse_rows)):
        print(json.dumps(row, ensure_ascii=False))


def commons(query):
    for row in with_english("commons", query, lambda q: cached("commons", q, commons_rows)):
        print(json.dumps(row, ensure_ascii=False))


def pexels_rows(query):
    """Pexels 는 누구나 무료로 쓸 수 있고 AI로 만든 그림은 받지 않아요. API로 찾은 사진은 찍은 사람과 Pexels 를 적어 줘요."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        sys.exit("PEXELS_API_KEY 가 없어요. " + NO_KEY["pexels"])
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "per_page": 20})
    data = json.loads(web_get(url, timeout=40, headers={"Authorization": key}))
    return [{"url": p["src"]["large2x"], "title": p.get("alt") or "", "size": f"{p['width']}x{p['height']}",
             "license": "Pexels", "from": "pexels", "page": p["url"], "credit": f"사진: {p['photographer']} / Pexels"}
            for p in data.get("photos", []) if p.get("width", 0) >= 1200]


def pexels(query):
    for row in with_english("pexels", query, lambda q: cached("pexels", q, pexels_rows)):
        print(json.dumps(row, ensure_ascii=False))


UNSPLASH_TERMS = "Unsplash 라이선스: 무료, 상업적 이용·수정 가능, 출처 표시 없어도 됨. 사진만 그대로 되팔기·비슷한 사진 서비스 금지. 사진 속 인물·상표·작품은 따로 확인"


def unsplash_links(query, en=None):
    """키 없이 Unsplash 를 쓰는 길(2026-11-13): 영어 검색 페이지 주소(무료 사진만). WebFetch 로 열면 사진 주소가 그대로 나와요."""
    terms = [query] if not hangul(query) else (en or en_terms(query))
    return [f"https://unsplash.com/s/photos/{urllib.parse.quote(re.sub(r'\s+', '-', t.strip().lower()))}?license=free" for t in terms]


def unsplash_rows(query):
    """Unsplash 무료 사진(2026-11-07 사용자가 더함). Unsplash+(유료) 사진은 빼요(plus·premium 표시, plus.unsplash.com 주소).
    사진 속 사람 얼굴·상표·작품은 라이선스와 따로라 열어 보고 판단해요. 실제 그 축제·그 제품 사진이 아니면 '같은 종류'·'분위기'로만 적어요."""
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        sys.exit("UNSPLASH_ACCESS_KEY 가 없어요. " + NO_KEY["unsplash"])
    url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode({"query": query, "per_page": 30, "content_filter": "high"})
    data = json.loads(web_get(url, timeout=40, headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}))
    rows, today, track = [], time.strftime("%Y-%m-%d"), {}
    for r in data.get("results", []):
        raw = (r.get("urls") or {}).get("raw") or ""
        if r.get("premium") or r.get("plus") or "plus.unsplash.com" in raw or "premium_photo" in raw or (r.get("width") or 0) < 1200:
            continue
        who = ((r.get("user") or {}).get("name") or "작자 미상")[:50]
        page = (r.get("links") or {}).get("html") or ""
        track[r["id"]] = (r.get("links") or {}).get("download_location") or ""
        rows.append({"url": raw + ("&" if "?" in raw else "?") + "w=2000&q=85&fm=jpg", "title": (r.get("alt_description") or r.get("description") or "")[:80],
                     "size": f"{r.get('width')}x{r.get('height')}", "license": "Unsplash", "from": "unsplash", "page": page,
                     "credit": f"사진: {who} / Unsplash",
                     "terms": {"url": "https://unsplash.com/license", "checked": today, "scope": UNSPLASH_TERMS, "ok": True},
                     "note": "무료 사진이에요. 사람 얼굴·상표가 크게 보이면 쓰지 않고, 실제 그 행사·제품 사진처럼 쓰지 않아요"})
    if track:  # 고른 사진을 get 할 때 Unsplash 에 내려받음을 알려요(API 안내)
        CACHE.mkdir(exist_ok=True)
        f = CACHE / "unsplash-track.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        f.write_text(json.dumps({**old, **track}, ensure_ascii=False), encoding="utf-8")
    return rows


def unsplash(query):
    if not os.environ.get("UNSPLASH_ACCESS_KEY", "").strip():
        links = unsplash_links(query)
        print(json.dumps({"출처": "Unsplash", "WebFetch": links or f"'{query}' 의 영어 이름으로 다시 찾아요",
                          "할 일": NO_KEY["unsplash"]}, ensure_ascii=False))
        return
    for row in with_english("unsplash", query, lambda q: cached("unsplash", q, unsplash_rows)):
        print(json.dumps(row, ensure_ascii=False))


PIXABAY_TERMS = "Pixabay 콘텐츠 라이선스: 무료, 상업적 이용·수정 가능, 출처 표시 없어도 됨. 사진만 그대로 되팔기 금지. 사진 속 인물·상표·작품은 따로 확인"


def pixabay_rows(query):
    """Pixabay 무료 사진(2026-11-03·11-13 사용자). 사진만(그림·벡터 빼고) 받고, 태그에 AI 표시가 있으면 빼요.
    사진 속 사람 얼굴·상표는 라이선스와 따로라 열어 보고 판단해요. 실제 그 축제·그 제품 사진이 아니면 '같은 종류'·'분위기'로만 적어요."""
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        sys.exit("PIXABAY_API_KEY 가 없어요. " + NO_KEY["pixabay"])
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode({"key": key, "q": query[:100], "image_type": "photo", "lang": "en",
                                                                 "safesearch": "true", "per_page": 30, "min_width": 1200})
    data = json.loads(web_get(url, timeout=40))
    rows, today = [], time.strftime("%Y-%m-%d")
    for h in data.get("hits", []):
        tags = (h.get("tags") or "").lower()
        if "ai generated" in tags or "ai-generated" in tags or h.get("isAiGenerated") or h.get("ai_generated"):
            continue
        rows.append({"url": h.get("largeImageURL") or h.get("webformatURL"), "title": h.get("tags") or "",
                     "size": f"{h.get('imageWidth')}x{h.get('imageHeight')}", "license": "Pixabay", "from": "pixabay",
                     "page": h.get("pageURL") or "", "credit": f"사진: {(h.get('user') or '작자 미상')[:50]} / Pixabay",
                     "terms": {"url": "https://pixabay.com/service/license-summary/", "checked": today, "scope": PIXABAY_TERMS, "ok": True},
                     "note": "무료 사진이에요. 고르면 바로 내려받아요(주소가 오래가지 않아요). 사람 얼굴·상표가 크게 보이거나 AI 그림이면 쓰지 않아요"})
    return rows


def pixabay(query):
    for row in with_english("pixabay", query, lambda q: cached("pixabay", q, pixabay_rows)):
        print(json.dumps(row, ensure_ascii=False))


# 키가 없을 때 대신 찾는 법(사이트 검색도 영어로)
NO_KEY = {
    "unsplash": "Unsplash 는 키 없이 써요: 아래 'WebFetch' 주소(영어 검색 페이지, 무료 사진만)를 WebFetch 로 열어 "
                "images.unsplash.com/photo-… 사진 주소·사진 페이지(page)·찍은 사람을 읽어요. plus.unsplash.com·premium_photo(Unsplash+)는 빼요. "
                "고른 사진은 python scripts/photos.py get '사진 주소?w=2000&q=85&fm=jpg' 파일 로 받아 열어 보고, credit 은 '사진: 이름 / Unsplash'.",
    "pexels": "Pexels 는 WebSearch 'site:pexels.com/photo 영어 검색어' 로 찾고, 사진 페이지 주소 끝 번호(ID)로 "
              "https://images.pexels.com/photos/ID/pexels-photo-ID.jpeg?auto=compress&cs=tinysrgb&w=1880 을 url 로, 사진 페이지를 page 로, "
              "'사진: 찍은 사람 / Pexels' 를 credit 으로 적어요.",
    "pixabay": "Pixabay 는 WebSearch 'site:pixabay.com/photos 영어 검색어' 로 찾고, 사진 페이지에서 사진(그림·AI 아님)인지 본 뒤 "
               "cdn.pixabay.com 사진 주소와 page, '사진: 올린 사람 / Pixabay' 를 적어요. 페이지가 안 열리면 다른 곳으로 넘어가요.",
}


def vault_hits(name):
    """비공개 보관함(../jecheol-photos/index.json)에서 note 에 그 음식 이름이 든 사진(ask·skip 빼고)."""
    p = Path(__file__).resolve().parent.parent.parent / "jecheol-photos" / "index.json"
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = _n(name)
    return [{"url": f"vault:{x['file']}", "note": x.get("note"), "used": len(x.get("used") or []), "size": f"{x.get('w')}x{x.get('h')}"}
            for x in idx if x.get("type") == "photo" and not x.get("skip") and not x.get("ask") and key and key in _n(x.get("note"))]


def food(name, en=None, n=6, vault_last=False):
    """음식 사진을 한 번에 찾아요(2026-11-12 사용자: 사진을 못 찾아 소재가 좁아지지 않게, Unsplash·영어 검색까지).
    차례: ① 비공개 보관함 ② 한국관광공사(한국어) ③ Unsplash ④ Pexels·Pixabay ⑤ 오픈버스·위키미디어. ③~⑤는 영어로 먼저 찾아요(2026-11-13).
    키가 없는 곳은 건너뛰고 알려 줘요(멈추지 않아요). 사진은 고르기 전에 sheet·get 으로 꼭 열어 보고, 음식이 맞는지·사람 얼굴·상표를 봐요."""
    en = en or en_terms(name)
    print(json.dumps({"음식": name, "영어 검색어": en or "사전에 없어요 — Unsplash·Pexels·Pixabay 는 영어로 찾아야 사진이 많이 나와요. "
                      "--en '흔한 영어 이름;정확한 영어 이름' 으로 다시 찾고, 재료는 ideas/food_en.json·메뉴는 dinner_pick.py add 로 사전에 더해요"},
                     ensure_ascii=False))
    v = vault_hits(name)
    if v and not vault_last:
        print(json.dumps({"출처": "① 비공개 보관함", "장수": len(v), "사진": v[:n]}, ensure_ascii=False))
    steps = [("② 한국관광공사", "tour", "TOUR_API_KEY", tour_rows),
             ("③ Unsplash", "unsplash", "UNSPLASH_ACCESS_KEY", unsplash_rows),
             ("④ Pexels", "pexels", "PEXELS_API_KEY", pexels_rows),
             ("④ Pixabay", "pixabay", "PIXABAY_API_KEY", pixabay_rows),
             ("⑤ 오픈버스(플리커·위키미디어)", "openverse", "", openverse_rows),
             ("⑤ 위키미디어", "commons", "", commons_rows)]
    found = 0
    for label, src, key, fn in steps:
        if src == "unsplash" and not os.environ.get(key, "").strip():
            print(json.dumps({"출처": label, "WebFetch": unsplash_links(name, en) or "영어 이름(--en)을 주면 주소를 만들어요",
                              "할 일": NO_KEY["unsplash"]}, ensure_ascii=False))
            continue
        if key and not os.environ.get(key, "").strip():
            hint = NO_KEY[src].replace("영어 검색어", en[0] if en else "영어 검색어") if src in NO_KEY else "다음 곳으로 넘어가요"
            print(json.dumps({"출처": label, "건너뜀": f"{key} 가 없어요", "대신": hint}, ensure_ascii=False))
            continue
        try:
            if src == "tour":
                rows = cached("tour", name, tour_rows)["rows"]
            else:
                rows = with_english(src, name, lambda q, f=fn, s_=src: cached(s_, q, f), en)
        except (WebError, SystemExit, ValueError) as e:
            print(json.dumps({"출처": label, "못 읽음": str(e)[:120]}, ensure_ascii=False))
            continue
        ko = sum(1 for r in rows if not r.get("query"))
        found += len(rows)
        print(json.dumps({"출처": label, "한국어로": ko, "영어로 더": len(rows) - ko,
                          "사진": [{k: r.get(k) for k in ("url", "title", "size", "license", "credit", "page", "query", "check") if r.get(k)} for r in rows[:n]]},
                         ensure_ascii=False))
    if v and vault_last:  # 저녁 추천(2026-11-13 사용자): 메뉴를 먼저 고르고 바깥 사진을 찾은 뒤, 맞는 게 없을 때만 보관함
        print(json.dumps({"출처": "⑥ 비공개 보관함(마지막)", "장수": len(v), "사진": v[:n],
                          "언제": "위 바깥 사진 가운데 그 메뉴가 정확히 맞는 것이 없을 때만 써요(비슷한 다른 음식 사진은 맞는 것이 아니에요)"}, ensure_ascii=False))
    print(json.dumps({"모두": found, "다음": "후보는 sheet 로 모아 열어 보고(python scripts/photos.py sheet 출처 검색어 15 그림.jpg), 음식이 같은지 확인한 것만 써요. "
                              "credit 이 있으면 credits 에 글자 그대로, Unsplash·Pexels·Pixabay 는 page 를 함께 적어요. 맞는 사진이 없으면 다른 메뉴로 바꿔요(비슷한 다른 음식 사진으로 채우지 않아요)."},
                     ensure_ascii=False))


def unsplash_track(url):
    """Unsplash API 안내대로, 쓰려고 내려받은 사진은 download_location 을 한 번 불러요(키와 검색 기록이 있을 때만)."""
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    m = re.search(r"images\.unsplash\.com/photo-[\w-]+", url)
    f = CACHE / "unsplash-track.json"
    if not (key and m and f.exists()):
        return
    for pid, loc in json.loads(f.read_text(encoding="utf-8")).items():
        if loc and pid and pid in url:
            try:
                web_get(loc, timeout=20, retries=1, quiet=True, headers={"Authorization": f"Client-ID {key}"})
            except (WebError, TypeError):
                pass
            return


def festival(start):
    total, items = tour_call("KorService2", "searchFestival2", eventStartDate=start, arrange="A", numOfRows=100)
    print(json.dumps({"from": start, "total": total}, ensure_ascii=False))
    for it in items:
        print(json.dumps({"title": it.get("title"), "start": it.get("eventstartdate"), "end": it.get("eventenddate"),
                          "addr": it.get("addr1"), "image": it.get("firstimage")}, ensure_ascii=False))


FONT = Path(__file__).resolve().parent.parent / "video" / "fonts" / "NotoSansKR-VF.ttf"


def _thumb(row, source):
    """후보 하나를 작게 받아 와요(받은 것은 임시 폴더에 두고 다시 써요). 못 받으면 None."""
    url = (row["url"].replace("?width=1600", "?width=480") if source == "commons"
           else row["url"].replace("w=2000", "w=480") if source == "unsplash" else row["url"])
    path = CACHE / f"img-{hashlib.sha1(url.encode()).hexdigest()[:16]}.jpg"
    if not path.exists():
        try:
            path.write_bytes(web_get(urllib.parse.quote(url, safe=":/?&=%+,;@()"), timeout=25, retries=1, quiet=True))
        except WebError:
            return None
    return path


def sheet(source, query, n=15, out=None):
    """검색 결과 n 장을 번호를 붙여 한 장에 모아요. 사진마다 따로 받고 따로 여는 일을 줄여요. 줄마다 번호와 사진 정보가 나와요."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    CACHE.mkdir(exist_ok=True)
    rows = (cached("tour", query, tour_rows)["rows"] if source == "tour"
            else with_english(source, query, lambda q: cached(source, q, {"openverse": openverse_rows, "unsplash": unsplash_rows,
                                                                          "pexels": pexels_rows, "pixabay": pixabay_rows}.get(source, commons_rows))))[:n]
    out = Path(out or CACHE / f"sheet-{source}-{hashlib.sha1(query.encode()).hexdigest()[:8]}.jpg")
    # 관광공사는 함께 받아도 되고, 위키미디어는 web.py 가 1초 간격을 지켜요
    with ThreadPoolExecutor(max_workers=6 if source == "tour" else 2) as pool:
        files = list(pool.map(lambda r: _thumb(r, source), rows))
    cols, tw, th = 5, 320, 260
    grid = Image.new("RGB", (cols * tw, max(1, -(-len(rows) // cols)) * th), (24, 24, 24))
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype(str(FONT), 28)
    except OSError:
        font = ImageFont.load_default()
    for i, (row, f) in enumerate(zip(rows, files)):
        x, y = (i % cols) * tw, (i // cols) * th
        if f:
            try:
                im = ImageOps.contain(Image.open(f).convert("RGB"), (tw - 8, th - 8))
                grid.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            except OSError:
                f = None
        if not f:
            draw.text((x + 120, y + 110), "못 받음", fill=(200, 80, 80), font=font)
        draw.rectangle([x + 4, y + 4, x + 52, y + 40], fill=(0, 0, 0))
        draw.text((x + 10, y + 4), str(i), fill=(255, 210, 60), font=font)
    grid.save(out, quality=82)
    print(json.dumps({"sheet": str(out), "source": source, "keyword": query, "count": len(rows),
                      "missing": [i for i, f in enumerate(files) if not f]}, ensure_ascii=False))
    for i, row in enumerate(rows):
        print(json.dumps({"no": i, **row}, ensure_ascii=False))


# 찾는 차례(2026-11-07 사용자: 몇 장 찾고 없다고 하지 말고 끝까지. 차례대로 넓히되 검색은 한꺼번에 해요)
SEARCH_ORDER = [
    "① 공식·공공: 공식 누리집, 지자체·기관(사진DB·보도자료), 한국관광공사(tour), 공공누리, 공유마당(gongu.copyright.or.kr), 위키미디어(commons)·오픈버스(openverse)",
    "② 이용 조건이 분명한 무료 사진: Unsplash(unsplash, Unsplash+ 유료 제외) · Pexels(pexels) · Pixabay",
    "③ 관련 뉴스·보도자료·행사 자료: 뉴스와이어(news.py press), 기사 사진 설명 '○○ 제공'(원본을 낸 곳으로), 축제 공식 자료",
    "④ 개인 블로그: 네이버 블로그·티스토리 방문·구매 후기",
    "⑤ 유튜브 영상·썸네일",
    "⑥ 인스타그램 등 SNS 게시물",
]
LEAD_KINDS = {
    # 2026-11-06 사용자: 지자체·공공누리에만 묶지 말고 처음부터 넓게 찾는다. 찾기(후보)와 이용 조건 확인은 따로 한다
    # 2026-11-07 사용자: 검색어·지역명·음식명·비슷한 표현을 넓혀 충분히 찾는다. 공유마당·Unsplash 를 더함
    "festival": ["{n} {y}", "{n} {y1}", "{n} {y2}", "{n} 현장", "{n} 개막 사진 제공", "{n} 먹거리 부스", "{n} 방문객",
                 "{n} 보도자료 사진", "{n} 사진DB", "지자체 누리집 사진·포토 게시판(행사 당일 공식 사진)", "지자체 보도자료 게시판 검색 '{n}'(지난 회차 결과 보도자료)", "{n} 공유마당", "{n} 후기 블로그", "{n} 티스토리", "{n} 유튜브", "{n} 인스타그램",
                 "{n} 지역명+축제 대표 음식(예: '죽변 대게')"],
    "product": ["{n}", "{n} 출시 사진 제공", "{n} 보도자료", "{n} 뉴스룸", "{n} 뉴스와이어", "{n} 공식 인스타그램", "{n} 후기",
                "{n} 리뷰 블로그", "{n} 티스토리", "{n} 유튜브 리뷰", "{n} 줄임말·띄어쓰기 뺀 말·영어 이름"],
    "food": ["{n}", "{n} 사진", "{n} 지역 이름(산지·유명한 곳)", "{n} 비슷한 이름·사투리", "{n} 영어 이름 (unsplash·pexels·commons)",
             "{n} 공유마당", "{n} 지역 축제", "{n} 시장", "{n} 후기 블로그", "{n} 유튜브", "{n} 인스타그램"],
}


def leads(kind, name, year=None):
    """사진 찾기 순서표. ① 넓게 찾을 검색어(공식·공공 → 무료 사진 → 뉴스·보도자료 → 블로그 → 유튜브 → SNS, 지난 회차까지)
    ② 이미 이용 조건을 확인한 출처(sources.json photo_rights) — 등록부에 있는 곳은 다시 조사하지 않고 적힌 상태대로 써요. ③ 확인하는 차례.
    (2026-11-06, 2026-11-07 차례·Unsplash·공유마당 더함)"""
    y = int(year or time.strftime("%Y"))
    plan = [q.format(n=name, y=y, y1=y - 1, y2=y - 2) for q in LEAD_KINDS.get(kind, LEAD_KINDS["food"])]
    print(json.dumps({"찾기": "아래 검색어를 한꺼번에 찾고(WebSearch 를 같은 차례에 여러 개), 기사 속 사진 설명('○○ 제공')·앨범 제목·현수막으로 대상과 연도를 먼저 맞춰요. "
                              "없으면 검색어(지역명·음식명·비슷한 표현·영어)를 바꿔 한 번 더 찾아요. 사진이 없다고 단색·지도·글자 화면으로 바꾸지 않아요",
                      "차례": SEARCH_ORDER, "검색어": plan}, ensure_ascii=False))
    reg = json.loads((Path(__file__).resolve().parent.parent / "sources.json").read_text(encoding="utf-8")).get("photo_rights") or []
    known = [{"출처": r.get("name"), "상태": r.get("status"), "범위": (r.get("scope") or "")[:80], "확인": r.get("checked")}
             for r in reg if r.get("status") and r.get("status") != "확인 필요"]
    print(json.dumps({"이미 확인한 출처(다시 조사하지 않음)": known}, ensure_ascii=False))
    print(json.dumps({"확인 차례": ["후보마다 shows(실제로 찍힌 것)·연도(EXIF·앨범·현수막·기사 날짜)를 적는다",
                                    "그다음 이용 조건: 등록부 → 사진·앨범에 붙은 공공누리 유형·CC → 회사·축제가 배포한 사진(10-26 결정) → 블로그·유튜브·SNS 는 작성자 허락이나 이용 조건이 있을 때만(출처 표기만으로는 안 돼요)",
                                    "허락이 불분명한 블로그·유튜브·SNS 사진은 넣지 않고 설계도 photo_candidates 에 장면·원본 링크와 함께 적는다(텔레그램 사진 보고에 나감)",
                                    "Unsplash: Unsplash+ 유료 제외, 사진 속 인물·상표 확인, 실제 그 행사·제품 사진처럼 쓰지 않는다(match 같은 종류·분위기)",
                                    "언론사·기자가 찍은 사진·방송 화면은 단서로만 쓰고 그 사진은 쓰지 않는다(원본을 낸 곳을 찾아간다)"]}, ensure_ascii=False))


def exif_date(path):
    """사진 파일의 촬영일(EXIF). 지난 축제 사진의 연도를 확인할 때 써요(축제 기간 안인지 함께 봐요)."""
    from PIL import Image
    with Image.open(path) as im:
        ex = im.getexif()
        try:
            shot = ex.get_ifd(0x8769).get(36867)
        except Exception:
            shot = None
        print(json.dumps({"파일": str(path), "크기": im.size, "촬영": shot, "수정": ex.get(306), "기기": ex.get(272)}, ensure_ascii=False))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    try:
        run(cmd, arg)
    except WebError as e:
        sys.exit(f"{cmd} {arg}: 못 읽었어요 ({e}). 다른 검색어나 다른 사진으로 넘어가요.")


def run(cmd, arg):
    if cmd == "tour":
        tour(arg)
    elif cmd == "commons":
        commons(arg)
    elif cmd == "openverse":
        openverse(arg)
    elif cmd == "pexels":
        pexels(arg)
    elif cmd == "unsplash":
        unsplash(arg)
    elif cmd == "pixabay":
        pixabay(arg)
    elif cmd == "food":
        en = sys.argv[sys.argv.index("--en") + 1].split(";") if "--en" in sys.argv else None
        food(arg, [e.strip() for e in en] if en else None, vault_last="--vault-last" in sys.argv)
    elif cmd == "en":
        print(json.dumps({"음식": arg, "영어 검색어": en_terms(arg)}, ensure_ascii=False))
    elif cmd == "festival":
        festival(arg)
    elif cmd == "get":
        safe = urllib.parse.quote(arg, safe=":/?&=%+,;@()")
        data = get(safe, 60)
        with open(sys.argv[3], "wb") as f:
            f.write(data)
        unsplash_track(arg)
        print("저장했어요:", sys.argv[3])
    elif cmd == "leads":
        if len(sys.argv) < 4:
            sys.exit('python scripts/photos.py leads festival|product|food "이름" [연도]')
        leads(arg, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "exif":
        exif_date(arg)
    elif cmd == "sheet":
        if len(sys.argv) < 4 or arg not in ("tour", "commons", "openverse", "unsplash", "pexels", "pixabay"):
            sys.exit("python scripts/photos.py sheet tour|commons|openverse|unsplash|pexels|pixabay 검색어 [장 수] [저장할 파일]")
        sheet(arg, sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 15, sys.argv[5] if len(sys.argv) > 5 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
