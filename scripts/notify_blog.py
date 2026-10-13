# -*- coding: utf-8 -*-
"""블로그 초안이 새로 생겼을 때와 네이버에 올렸을 때 텔레그램 봇으로 알려요.

  python scripts/notify_blog.py
필요한 값(환경 변수): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
이미 알린 것은 state/sent_blog.json 에 적어 두고 다시 보내지 않아요.
처음 돌 때는 가장 최근 초안 하나를 본보기로 보내요.
네이버에 올린 기록(state/blog_posted.json)은 사용자의 컴퓨터가 올린 뒤에 적어 보내요.
"""
import html
import os
import sys
from datetime import datetime, timedelta

from build_blog import load_posts, todo
from common import KST, ROOT, log_error, read_json, write_json
from notify_telegram import api


def message(post, site, first, auto):
    e = html.escape
    left = todo(post)
    lines = [
        "<b>네이버 블로그 초안이 준비됐어요</b>" + (" (본보기)" if first else ""),
        e(post["title"]),
        "",
    ]
    if auto and not first:
        lines.append("컴퓨터가 켜져 있으면 오전 중에 네이버에 자동으로 올라가요. 올라가면 주소를 다시 알려 드려요.")
    else:
        lines.append(f"사진 자리 {left['photo']}곳 · 경험 자리 {left['exp']}곳 · 태그 {len(post['tags'])}개")
        lines.append("사진과 경험 한두 줄만 넣어 네이버에 올리면 돼요.")
    if site:
        lines.append(f'<a href="{site}/blog/{e(post["id"])}.html">초안 보기 (제목·본문·태그 복사 버튼)</a>')
    return "\n".join(lines)


def posted_message(event, site):
    """네이버에 올린 결과 한 건."""
    e = html.escape
    title, note = e(event.get("title") or ""), e(event.get("note") or "")
    page = f'\n<a href="{site}/blog/{e(event["id"])}.html">초안 보기</a>' if site and event.get("id") else ""
    status = event.get("status")
    if status == "published":
        return f"✅ <b>네이버 블로그에 올렸어요</b>\n{title}\n{e(event.get('url') or '')}"
    if status == "login":
        return ("❌ <b>네이버 로그인이 만료돼 블로그를 올리지 못했어요</b>\n"
                "컴퓨터에서 Claude 에게 \"네이버 로그인 창 열어 줘\"라고 한 뒤 직접 로그인해 주세요. 로그인하면 밀린 초안부터 올라가요.")
    if status == "skipped":
        return f"⚠️ <b>블로그를 자동으로 올리지 않았어요</b>\n{title}\n{note}{page}"
    return f"❌ <b>블로그를 올리지 못했어요</b>\n{title}\n{note}\n다음 날 한 번 더 시도해요.{page}"


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        print("텔레그램 설정이 없어 블로그 알림은 건너뛰어요.")
        return
    cfg = read_json(ROOT / "config.json") or {}
    site = cfg.get("site_url", "").rstrip("/")
    auto = bool((cfg.get("blog_publish") or {}).get("on"))
    path = ROOT / "state" / "sent_blog.json"
    first = not path.exists()
    sent = set(read_json(path, []))
    send = lambda text: api(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview="true")

    posts, _ = load_posts()
    base = datetime.now(KST)
    days = [(base - timedelta(days=n)).strftime("%Y-%m-%d") for n in range(3)]
    picked = [p for p in reversed(posts) if p["id"] not in sent and p["date"] in days]
    if first and not picked:
        picked = posts[:1]
    for post in picked:
        send(message(post, site, first and post["date"] not in days, auto))
    # 오래된 초안을 나중에 한꺼번에 알리지 않도록, 지금 있는 초안은 모두 알린 것으로 적어요.
    sent.update(p["id"] for p in posts)

    events = [ev for ev in (read_json(ROOT / "state" / "blog_posted.json", []) or []) if "posted:" + ev["key"] not in sent]
    for event in events:
        send(posted_message(event, site))
        sent.add("posted:" + event["key"])

    write_json(path, sorted(sent))
    print(f"보냈어요: 블로그 초안 {len(picked)}개, 발행 소식 {len(events)}건")


def main():
    try:
        run()
    except Exception as e:
        log_error("notify_blog", e)
        sys.exit(f"블로그 알림 실패: {e}")


if __name__ == "__main__":
    main()
