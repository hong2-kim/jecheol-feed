# -*- coding: utf-8 -*-
"""뉴스 기사를 찾고, 구글 뉴스 주소를 원래 기사 주소로 바꾸고, 기사 본문을 뽑아요. (2026-10-19)
매일 실행이 같은 도구를 날마다 새로 만들지 않게 저장소에 둬요. 읽기만 하고 아무것도 쓰지 않아요.

  python3 scripts/news.py search "김천김밥축제" [--days 7] [--n 15]   구글 뉴스 검색: 날짜 | 매체 | 제목 | 주소
  python3 scripts/news.py url <구글 뉴스 주소> [주소 …]                원래 기사 주소
  python3 scripts/news.py text <주소> [--chars 3500] [--images]       제목, 날짜, 본문 앞부분 (구글 뉴스 주소도 된다)

- WebFetch 가 막힌 매체(연합뉴스, 조선비즈 등)도 text 로 열 수 있어요. 열지 못하면 한 줄로 알려 주고 끝나요.
- 본문은 **사실 확인용**이에요. 숫자·날짜·까닭을 확인하는 데만 쓰고, 기사 문장을 카드·영상·블로그에 그대로 옮기지 않아요(PROMPT.md "사실 확인").
- --images 는 기사에 실린 사진 주소(og:image 먼저)를 보여 줘요. 기자·통신사 사진은 쓰지 않는다는 규칙은 그대로예요.
"""
import argparse
import base64
import html
import json
import re
import sys
import urllib.parse
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from web import BROWSER, WebError, get

GNEWS = "https://news.google.com"


def search(query, days=None, n=15):
    q = query + (f" when:{days}d" if days else "")
    rss = get(f"{GNEWS}/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}), timeout=30)
    rows = []
    for it in ElementTree.fromstring(rss).iter("item"):
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").strftime("%m-%d %H:%M")
        except (TypeError, ValueError):
            when = ""
        rows.append((when, src, title, it.findtext("link") or ""))
    return rows[:n]


def _old_style(gid):
    """예전 구글 뉴스 주소는 id 안에 기사 주소가 그대로 들어 있어요."""
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
    except (ValueError, TypeError):
        return None
    if b"AU_yqL" in raw[:12]:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    return m.group(0).decode("ascii", "ignore") if m else None


def original_url(url):
    """구글 뉴스 기사 주소(news.google.com/rss/articles/…)를 원래 기사 주소로 바꿔요. 다른 주소는 그대로 돌려줘요."""
    if "news.google.com" not in url or "/articles/" not in url:
        return url
    gid = url.split("/articles/")[1].split("?")[0]
    found = _old_style(gid)
    if found:
        return found
    page = get(f"{GNEWS}/rss/articles/{gid}", headers=BROWSER, timeout=30).decode("utf-8", "replace")
    sig = re.search(r'data-n-a-sg="([^"]+)"', page)
    ts = re.search(r'data-n-a-ts="([^"]+)"', page)
    if not (sig and ts):
        raise WebError("구글 뉴스 주소를 풀 값을 찾지 못했어요")
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sig.group(1)}"]')
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
    res = get(f"{GNEWS}/_/DotsSplashUi/data/batchexecute", data=body.encode(), timeout=30,
              headers={**BROWSER, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}).decode("utf-8", "replace")
    m = re.search(r'garturlres\\",\\"(https?:[^"\\]+(?:\\\\u003d[^"\\]*)*)', res)
    if not m:
        raise WebError("구글 뉴스가 원래 주소를 알려 주지 않았어요")
    return m.group(1).replace("\\\\u003d", "=").replace("\\u003d", "=")


def _decode(raw, content_type=""):
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000]) or re.search(r"charset=([\w-]+)", content_type or "")
    names = [m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)] if m else []
    for enc in names + ["utf-8", "cp949"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def _meta(page, key):
    m = (re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]*content=["\']([^"\']+)', page, re.I)
         or re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(key)}["\']', page, re.I))
    return html.unescape(m.group(1)).strip() if m else ""


def _clean(fragment):
    fragment = re.sub(r"(?is)<(script|style|noscript|iframe|svg|figure|figcaption|button|form)[^>]*>.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in text.split("\n")]
    return "\n".join(l for l in lines if len(l) > 1)


BODY_HINT = re.compile(r'(?i)itemprop=["\']articleBody|(?:id|class)=["\'][^"\']*(?:article|story|news[-_]?(?:body|cnt|content|view|txt)|view[-_]?(?:cont|text|body)|txt[-_]?area|dic_area|newsct)')


def _element(page, start):
    """start 자리에서 열린 태그가 닫히는 곳까지(같은 이름 태그의 깊이를 세요)."""
    name = re.match(r"<(\w+)", page[start:]).group(1).lower()
    depth, pos = 0, start
    for m in re.finditer(rf"(?i)<(/?){name}\b[^>]*>", page[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return page[start:start + m.end()]
        pos = start + m.end()
    return page[start:pos + 20000]


def _score(fragment):
    """링크 글자를 뺀 한글 수. 메뉴·관련 기사 목록보다 본문이 높게 나와요."""
    links = "".join(re.findall(r"(?is)<a\b[^>]*>(.*?)</a>", fragment))
    return len(re.findall(r"[가-힣]", re.sub(r"<[^>]+>", "", fragment))) - 2 * len(re.findall(r"[가-힣]", links))


def _body(page):
    """기사 본문으로 보이는 덩어리. 본문 칸 이름이 붙은 태그를 모두 보고, 링크 아닌 한글이 가장 많은 것을 골라요."""
    page = re.sub(r"(?is)<(script|style|noscript|header|footer|nav|aside)[^>]*>.*?</\1>", " ", page)
    cands = [_element(page, m.start()) for m in re.finditer(r"(?i)<(?:article|div|section)\b[^>]*>", page) if BODY_HINT.search(m.group(0))]
    paras = "\n".join(re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", page))
    best = max(cands + [paras], key=_score) if cands or paras else page
    lines = [l for l in _clean(best).split("\n") if len(l) >= 8 and not UI_WORDS.search(l)]
    while lines and len(lines[0]) < 25:  # 앞쪽의 짧은 줄은 공유 단추·메뉴예요
        lines.pop(0)
    return "\n".join(lines)


UI_WORDS = re.compile(r"^(?:SNS ?기사보내기|스크롤 이동 상태바|URL ?공유|구독하기|기사 ?듣기|글자 ?크기|프린트|인쇄|카카오톡|페이스북)$")


def text(url, chars=3500, images=False):
    url = original_url(url)
    raw = get(url, headers=BROWSER, timeout=30)
    page = _decode(raw)
    title = _meta(page, "og:title") or html.unescape((re.search(r"(?is)<title[^>]*>(.*?)</title>", page) or [None, ""])[1]).strip()
    when = _meta(page, "article:published_time") or _meta(page, "og:regDate") or _meta(page, "pubdate")
    body = _body(page)
    out = ["※ 사실 확인용이에요. 숫자·사실만 확인하고 기사 문장은 그대로 옮기지 않아요.", f"URL {url}", f"제목 {title}"] + ([f"날짜 {when}"] if when else []) + ["", body[:chars] + (f" … [+{len(body) - chars}자]" if len(body) > chars else "")]
    if images:
        pics = [_meta(page, "og:image")] + re.findall(r'<img[^>]+src=["\']([^"\']+\.(?:jpe?g|png|webp)[^"\']*)', page, re.I)
        seen = []
        for p in pics:
            p = urllib.parse.urljoin(url, html.unescape(p)) if p else ""
            if p and p not in seen and not re.search(r"logo|icon|banner|btn|ad[_/]", p, re.I):
                seen.append(p)
        out.append("사진 " + json.dumps(seen[:10], ensure_ascii=False))
        out.append("※ 기자·통신사가 찍은 사진은 쓰지 않아요. 회사가 배포한 사진만 \"7. 요즘 뜨는 메뉴\"의 회사 사진 규칙대로 써요.")
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--days", type=int); s.add_argument("--n", type=int, default=15)
    u = sub.add_parser("url"); u.add_argument("urls", nargs="+")
    t = sub.add_parser("text"); t.add_argument("url"); t.add_argument("--chars", type=int, default=3500); t.add_argument("--images", action="store_true")
    a = ap.parse_args()
    try:
        if a.cmd == "search":
            for row in search(a.query, a.days, a.n):
                print(" | ".join(row))
        elif a.cmd == "url":
            for x in a.urls:
                try:
                    print(original_url(x))
                except WebError as e:
                    print(f"못 풀었어요 ({e}): {x}")
        else:
            print(text(a.url, a.chars, a.images))
    except WebError as e:
        sys.exit(f"열지 못했어요: {e}")


if __name__ == "__main__":
    main()
