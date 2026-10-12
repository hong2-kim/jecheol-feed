# -*- coding: utf-8 -*-
"""영상에 쓸 실제 사진과 축제 일정을 찾아요.

  python scripts/photos.py tour 대하구이          한국관광공사 포토코리아 사진 (공공누리 1유형)
  python scripts/photos.py commons "sanma shioyaki"  위키미디어 공용 사진 (CC0·퍼블릭 도메인·CC BY 만)
  python scripts/photos.py festival 20261012      그날 이후 열리는 축제 (한국관광공사, 공식 일정)
  python scripts/photos.py get <주소> <저장할 파일>   사진을 내려받아 직접 눈으로 확인할 때

tour, festival 은 환경 변수 TOUR_API_KEY 가 있어야 해요. 결과는 한 줄에 하나씩 JSON으로 나와요.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "jecheol-feed/1.0 (https://github.com/hong2-kim/jecheol-feed)"}


def get(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def tour_call(service, op, **params):
    key = os.environ.get("TOUR_API_KEY", "").strip()
    if not key:
        sys.exit("TOUR_API_KEY 가 없어요. 관광공사 사진과 축제 일정은 찾을 수 없어요.")
    q = {"serviceKey": key, "numOfRows": 40, "pageNo": 1, "MobileOS": "ETC", "MobileApp": "jecheolFeed", "_type": "json", **params}
    data = json.loads(get(f"https://apis.data.go.kr/B551011/{service}/{op}?" + urllib.parse.urlencode(q)).decode("utf-8", "replace"))
    body = data.get("response", {}).get("body", {})
    items = (body.get("items") or {}).get("item", []) if body.get("items") else []
    return body.get("totalCount", 0), items


def tour(keyword):
    total, items = tour_call("PhotoGalleryService1", "gallerySearchList1", keyword=keyword, arrange="A")
    print(json.dumps({"keyword": keyword, "total": total}, ensure_ascii=False))
    for it in items:
        who = (it.get("galPhotographer") or "").replace("한국관광공사 ", "")
        print(json.dumps({"url": it["galWebImageUrl"], "title": it["galTitle"], "where": it.get("galPhotographyLocation"),
                          "shot": it.get("galPhotographyMonth"), "credit": f"ⓒ한국관광공사 포토코리아-{who}"}, ensure_ascii=False))


def commons(query):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 20,
        "gsrsearch": f"{query} filetype:bitmap -haslicense:attribution-same-license",
        "prop": "imageinfo", "iiprop": "size|extmetadata"})
    pages = (json.loads(get(url)).get("query", {}).get("pages", {}) or {}).values()
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
        print(json.dumps({"url": "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(name) + "?width=1600",
                          "title": name, "size": f"{ii['width']}x{ii['height']}", "license": lic,
                          "credit": "" if free else f"{who} ({lic}) · commons.wikimedia.org/?curid={p['pageid']}",
                          "note": "출처 표시가 필요 없어요" if free else "저작자·라이선스·주소를 표시해야 해요"}, ensure_ascii=False))


def festival(start):
    total, items = tour_call("KorService2", "searchFestival2", eventStartDate=start, arrange="A", numOfRows=100)
    print(json.dumps({"from": start, "total": total}, ensure_ascii=False))
    for it in items:
        print(json.dumps({"title": it.get("title"), "start": it.get("eventstartdate"), "end": it.get("eventenddate"),
                          "addr": it.get("addr1"), "image": it.get("firstimage")}, ensure_ascii=False))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "tour":
        tour(arg)
    elif cmd == "commons":
        commons(arg)
    elif cmd == "festival":
        festival(arg)
    elif cmd == "get":
        safe = urllib.parse.quote(arg, safe=":/?&=%+,;@()")
        with open(sys.argv[3], "wb") as f:
            f.write(get(safe, 60))
        print("저장했어요:", sys.argv[3])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
