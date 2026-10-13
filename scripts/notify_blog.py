# -*- coding: utf-8 -*-
"""새 블로그 초안이 생기면 텔레그램 봇으로 알려요.

  python scripts/notify_blog.py
필요한 값(환경 변수): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
이미 알린 초안은 state/sent_blog.json 에 적어 두고 다시 보내지 않아요.
처음 돌 때는 가장 최근 초안 하나를 본보기로 보내요.
"""
import html
import os
import sys
from datetime import datetime, timedelta

from build_blog import load_posts, todo
from common import KST, ROOT, log_error, read_json, write_json
from notify_telegram import api


def message(post, site, first):
    e = html.escape
    left = todo(post)
    lines = [
        "<b>네이버 블로그 초안이 준비됐어요</b>" + (" (본보기)" if first else ""),
        e(post["title"]),
        "",
        f"사진 자리 {left['photo']}곳 · 경험 자리 {left['exp']}곳 · 태그 {len(post['tags'])}개",
    ]
    if site:
        lines.append(f'<a href="{site}/blog/{e(post["id"])}.html">초안 열기 (제목·본문·태그 복사 버튼)</a>')
    lines.append("사진과 경험 한두 줄만 넣어 네이버에 올리면 돼요.")
    return "\n".join(lines)


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        print("텔레그램 설정이 없어 블로그 알림은 건너뛰어요.")
        return
    site = (read_json(ROOT / "config.json") or {}).get("site_url", "").rstrip("/")
    path = ROOT / "state" / "sent_blog.json"
    first = not path.exists()
    sent = set(read_json(path, []))
    posts, _ = load_posts()
    base = datetime.now(KST)
    days = [(base - timedelta(days=n)).strftime("%Y-%m-%d") for n in range(3)]
    picked = [p for p in reversed(posts) if p["id"] not in sent and p["date"] in days]
    if first and not picked:
        picked = posts[:1]
    for post in picked:
        api(token, "sendMessage", chat_id=chat_id, text=message(post, site, first and post["date"] not in days),
            parse_mode="HTML", disable_web_page_preview="true")
    # 오래된 초안을 나중에 한꺼번에 알리지 않도록, 지금 있는 초안은 모두 알린 것으로 적어요.
    sent.update(p["id"] for p in posts)
    write_json(path, sorted(sent))
    print(f"보냈어요: 블로그 초안 {len(picked)}개")


def main():
    try:
        run()
    except Exception as e:
        log_error("notify_blog", e)
        sys.exit(f"블로그 알림 실패: {e}")


if __name__ == "__main__":
    main()
