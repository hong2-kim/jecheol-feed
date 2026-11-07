# -*- coding: utf-8 -*-
"""영상에 쓸 실제 사진과 축제 일정을 찾아요.

  python scripts/photos.py tour 대하구이          한국관광공사 포토코리아 사진 (공공누리 1유형)
  python scripts/photos.py commons "sanma shioyaki"  위키미디어 공용 사진 (CC0·퍼블릭 도메인·CC BY 만)
  python scripts/photos.py openverse "tteokbokki"  오픈버스(플리커·위키미디어 등) CC0·퍼블릭 도메인·CC BY 사진 (키 없이 돼요. 영어로 찾아야 잘 나와요, 2026-10-24)
  python scripts/photos.py pexels "grilled pork belly"  Pexels 무료 사진 (인스타·쇼츠·블로그 모두 돼요. 영어로 찾아야 잘 나와요)
  python scripts/photos.py unsplash "bibimbap"     Unsplash 무료 사진 (상업적 이용·수정 가능. Unsplash+ 유료 사진은 빼요, 2026-11-07)
  python scripts/photos.py festival 20261012      그날 이후 열리는 축제 (한국관광공사, 공식 일정)
  python scripts/photos.py get <주소> <저장할 파일>   사진을 내려받아 직접 눈으로 확인할 때
  python scripts/photos.py sheet tour 굴구이 15 /tmp/s.jpg   후보 여러 장을 번호를 붙여 한 장에 모아요 (commons·openverse 도 된다)
  python scripts/photos.py leads festival "죽변항 수산물축제" 2026   넓게 찾을 검색어(뉴스·블로그·SNS·유튜브·지난 회차) + 이미 확인한 출처 + 확인 차례
  python scripts/photos.py exif 사진.jpg              촬영일(EXIF) — 지난 축제 사진의 연도 확인

tour, festival 은 환경 변수 TOUR_API_KEY, pexels 는 PEXELS_API_KEY, unsplash 는 UNSPLASH_ACCESS_KEY 가 있어야 해요. 결과는 한 줄에 하나씩 JSON으로 나와요.
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


def get(url, timeout=40):
    return web_get(url, timeout=timeout)


def cached(kind, query, fn):
    """같은 검색어는 6시간 동안 다시 묻지 않아요."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{kind}-{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"
    if path.exists() and time.time() - path.stat().st_mtime < SEARCH_TTL:
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
    for row in cached("openverse", query, openverse_rows):
        print(json.dumps(row, ensure_ascii=False))


def commons(query):
    for row in cached("commons", query, commons_rows):
        print(json.dumps(row, ensure_ascii=False))


def pexels(query):
    """Pexels 는 누구나 무료로 쓸 수 있고 AI로 만든 그림은 받지 않아요. API로 찾은 사진은 찍은 사람과 Pexels 를 적어 줘요."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        sys.exit("PEXELS_API_KEY 가 없어요. Pexels 사진은 찾을 수 없어요. 다른 곳에서 찾아 주세요.")
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "per_page": 20})
    data = json.loads(web_get(url, timeout=40, headers={"Authorization": key}))
    print(json.dumps({"keyword": query, "total": data.get("total_results", 0)}, ensure_ascii=False))
    for p in data.get("photos", []):
        if p.get("width", 0) < 1200:
            continue
        print(json.dumps({"url": p["src"]["large2x"], "title": p.get("alt") or "", "size": f"{p['width']}x{p['height']}",
                          "license": "Pexels", "page": p["url"], "credit": f"사진: {p['photographer']} / Pexels"}, ensure_ascii=False))


UNSPLASH_TERMS = "Unsplash 라이선스: 무료, 상업적 이용·수정 가능, 출처 표시 없어도 됨. 사진만 그대로 되팔기·비슷한 사진 서비스 금지. 사진 속 인물·상표·작품은 따로 확인"


def unsplash_rows(query):
    """Unsplash 무료 사진(2026-11-07 사용자가 더함). Unsplash+(유료) 사진은 빼요(plus·premium 표시, plus.unsplash.com 주소).
    사진 속 사람 얼굴·상표·작품은 라이선스와 따로라 열어 보고 판단해요. 실제 그 축제·그 제품 사진이 아니면 '같은 종류'·'분위기'로만 적어요."""
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        sys.exit("UNSPLASH_ACCESS_KEY 가 없어요. Unsplash 는 WebSearch 'site:unsplash.com/photos 영어 검색어' 로 찾고, 사진 페이지에서 "
                 "Unsplash+ 가 아닌지(주소가 plus.unsplash.com 이 아닌지) 본 뒤 images.unsplash.com 주소와 page 를 적어요.")
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
    for row in cached("unsplash", query, unsplash_rows):
        print(json.dumps(row, ensure_ascii=False))


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
            else cached(source, query, {"openverse": openverse_rows, "unsplash": unsplash_rows}.get(source, commons_rows)))[:n]
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
                 "{n} 보도자료 사진", "{n} 사진DB", "{n} 공유마당", "{n} 후기 블로그", "{n} 티스토리", "{n} 유튜브", "{n} 인스타그램",
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
        if len(sys.argv) < 4 or arg not in ("tour", "commons", "openverse"):
            sys.exit("python scripts/photos.py sheet tour|commons|openverse 검색어 [장 수] [저장할 파일]")
        sheet(arg, sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 15, sys.argv[5] if len(sys.argv) > 5 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
