# -*- coding: utf-8 -*-
"""items 폴더의 글로 RSS 2.0 피드와 읽기용 페이지를 만들어요.

  python scripts/build_feed.py
만드는 것: public/feed.xml, public/index.html
"""
import html
import sys
from datetime import datetime
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from common import KST, ROOT, load_items, log_error, read_json


def esc(text):
    return html.escape(str(text))


def body_html(item):
    """한 항목을 릴스 형식 8가지로 풀어 쓴 HTML."""
    def ul(lines):
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in lines) + "</ul>"

    script = item["script"]
    place = " · ".join(x for x in [item["country"], item.get("region")] if x)
    parts = [
        f"<p><b>{esc(item['category'])}</b> · {esc(place)}</p>",
        f"<p><b>시기</b> {esc(item['season'])}</p>" if item.get("season") else "",
        "<h3>2. 핵심 내용</h3>", ul(item["summary"]),
        "<h3>3. 흥미로운 사실</h3>", ul(item["facts"]),
        "<h3>4. 추천 영상 구성</h3>",
        f"<p><b>첫 3초</b> {esc(script['hook'])}</p>", ul(script["flow"]),
        f"<p><b>마무리</b> {esc(script['closing'])}</p>",
        f"<h3>5. 추천 길이</h3><p>{int(item['length_sec'])}초</p>",
        "<h3>6. 화면 자료 아이디어</h3>", ul(item["visuals"]),
        f"<h3>어울리는 술</h3><p>{esc(item['pairing']['drink'])}<br><small>{esc(item['pairing']['note'])}</small></p>",
        "<h3>7. 출처 및 검증 자료</h3><ul>" + "".join(
            f'<li><a href="{esc(s["url"])}">{esc(s["name"])}</a>{" (공식)" if s.get("official") else ""}</li>'
            for s in item["sources"]) + "</ul>",
        f"<p>정보 확인 날짜 {esc(item['checked'])}</p>",
        "<h3>8. 주의사항</h3>", ul(item["cautions"]),
    ]
    if item.get("unverified"):
        parts += ["<h3>추가 확인 필요</h3>", ul(item["unverified"])]
    return "".join(parts)


def build_rss(items, cfg):
    site = cfg.get("site_url", "").rstrip("/")
    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = cfg["title"]
    ET.SubElement(ch, "link").text = (site + "/") if site else items[0]["sources"][0]["url"]
    ET.SubElement(ch, "description").text = cfg["description"]
    ET.SubElement(ch, "language").text = "ko"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(datetime.now(KST))
    if site:
        ET.SubElement(ch, "atom:link", {"href": site + "/feed.xml", "rel": "self", "type": "application/rss+xml"})
    for item in items[: cfg.get("feed_max_items", 60)]:
        el = ET.SubElement(ch, "item")
        ET.SubElement(el, "title").text = f"[{item['category']}] {item['title']}"
        ET.SubElement(el, "link").text = f"{site}/#{item['id']}" if site else item["sources"][0]["url"]
        ET.SubElement(el, "guid", {"isPermaLink": "false"}).text = item["id"]
        ET.SubElement(el, "category").text = item["category"]
        ET.SubElement(el, "category").text = item["country"]
        y, m, d = map(int, item["date"].split("-"))
        ET.SubElement(el, "pubDate").text = format_datetime(datetime(y, m, d, 7, 0, tzinfo=KST))
        ET.SubElement(el, "source", {"url": item["sources"][0]["url"]}).text = item["sources"][0]["name"]
        ET.SubElement(el, "description").text = f"<h3>1. 릴스 제목</h3><p>{esc(item['title'])}</p>" + body_html(item)
    ET.indent(rss)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def build_page(items, cfg):
    blocks, last = [], None
    for item in items:
        if item["date"] != last:
            blocks.append(f"<h2>{esc(item['date'])}</h2>")
            last = item["date"]
        blocks.append(f'<article id="{esc(item["id"])}"><h3 class="t">{esc(item["title"])}</h3>{body_html(item)}</article>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(cfg['title'])}</title>
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['title'])}" href="feed.xml">
<style>
body {{ font-family: "Noto Sans KR", "Malgun Gothic", sans-serif; margin: 0 auto; max-width: 760px; padding: 20px 16px 60px; line-height: 1.6; color: #231C15; background: #F7F0E4; }}
h1 {{ font-size: 24px; }} h2 {{ margin-top: 36px; font-size: 18px; color: #7A6A58; }}
article {{ background: #fff; border-radius: 14px; padding: 18px 20px; margin: 14px 0; }}
article h3 {{ font-size: 14px; color: #B4441A; margin: 18px 0 4px; }} article h3.t {{ font-size: 20px; color: #231C15; margin: 0 0 6px; }}
ul {{ margin: 4px 0; padding-left: 20px; }} a {{ color: #B4441A; word-break: break-all; }} small {{ color: #7A6A58; }}
</style></head><body>
<h1>{esc(cfg['title'])}</h1>
<p>{esc(cfg['description'])} <a href="feed.xml">RSS 주소</a></p>
<p><small>마지막 갱신 {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} · 글 {len(items)}개</small></p>
{''.join(blocks)}
</body></html>"""


def main():
    cfg = read_json(ROOT / "config.json")
    items, problems = load_items()
    for p in problems:
        print("확인 필요:", p)
        log_error("build_feed", p)
    if not items:
        sys.exit("내보낼 글이 없어요.")
    out = ROOT / "public"
    out.mkdir(exist_ok=True)
    (out / "feed.xml").write_text(build_rss(items, cfg), encoding="utf-8")
    (out / "index.html").write_text(build_page(items, cfg), encoding="utf-8")
    print(f"피드를 만들었어요: 글 {len(items)}개, 문제 {len(problems)}건")


if __name__ == "__main__":
    main()
