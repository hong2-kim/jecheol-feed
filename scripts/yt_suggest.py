# -*- coding: utf-8 -*-
"""유튜브 검색창 자동완성에 뜨는 검색어를 봐요. 쇼츠 키워드를 고를 때 써요. (2026-10-16 사용자가 정함)

  python scripts/yt_suggest.py "저녁 메뉴 추천" "떡볶이" "냉장 초코파이"

- 낱말마다 유튜브 자동완성 후보를 보여 줘요. 후보에 뜨면 사람들이 실제로 그 말로 찾는다는 뜻이에요.
- 자동완성은 검색량 숫자를 주지 않아요. 순서는 대략의 인기일 뿐이니, 게시글이나 보고에 "검색량 많음"처럼 숫자인 양 쓰지 않아요.
- 연결이 안 되면 "확인 못 함"이라고 알려 줘요. 그때는 확인하지 못한 채로 고른 것이라고 보고에 적어요.
"""
import json
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (jecheol-feed; +rss reader)"}


def suggest(q):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "ds": "yt", "hl": "ko", "gl": "KR", "oe": "utf-8", "q": q})
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read()
    return json.loads(raw.decode("utf-8"))[1]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    words = sys.argv[1:]
    if not words:
        print(__doc__)
        sys.exit(1)
    for w in words:
        try:
            got = suggest(w)
        except Exception as e:
            print(f"■ {w}: 확인 못 함 ({e.__class__.__name__})")
            continue
        exact = any(g.replace(" ", "") == w.replace(" ", "") for g in got)
        mark = "자동완성에 그대로 있어요" if exact else ("비슷한 말만 있어요" if got else "후보가 없어요 (찾는 사람이 적을 수 있어요)")
        print(f"■ {w}: {mark}")
        for g in got[:10]:
            print(f"   - {g}")


if __name__ == "__main__":
    main()
