# -*- coding: utf-8 -*-
"""오늘 소재를 텔레그램 봇으로 보내요.

  python scripts/notify_telegram.py            오늘 글 (못 보낸 최근 3일 치도 함께)
  python scripts/notify_telegram.py 2026-10-12  그 날짜 글만
필요한 값(환경 변수):
  TELEGRAM_BOT_TOKEN  봇 토큰 (BotFather 가 준 것)
  TELEGRAM_CHAT_ID    받을 사람 번호. 비워 두면 봇에게 마지막으로 말을 건 사람에게 보내요.
이미 보낸 글은 state/sent.json 에 적어 두고 다시 보내지 않아요.
"""
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from common import KST, ROOT, load_items, log_error, read_json, today_kst, write_json


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=30) as res:
        return json.loads(res.read())["result"]


def find_chat_id(token):
    for update in reversed(api(token, "getUpdates")):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            return chat["id"]
    raise RuntimeError("받을 사람을 찾지 못했어요. 텔레그램에서 봇 대화방에 들어가 아무 말이나 한 번 보내 주세요.")


def message(item, site):
    e = html.escape
    lines = [
        f"<b>[{e(item['category'])}] {e(item['title'])}</b>",
        e(" · ".join(x for x in [item["country"], item.get("region")] if x)),
        "",
        *[f"• {e(s)}" for s in item["summary"]],
        "",
        f"<b>첫 3초</b> {e(item['script']['hook'])}",
        f"<b>어울리는 술</b> {e(item['pairing']['drink'])}",
        f"<b>길이</b> {int(item['length_sec'])}초",
        "",
        f"<b>출처</b> <a href=\"{e(item['sources'][0]['url'])}\">{e(item['sources'][0]['name'])}</a>",
        f"확인 날짜 {e(item['checked'])}",
    ]
    if item.get("unverified"):
        lines.append(f"추가 확인 필요 {len(item['unverified'])}건")
    if site:
        lines.append(f"<a href=\"{site}/#{e(item['id'])}\">전체 내용 보기</a>")
    return "\n".join(lines)


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 이 없어요. 깃허브 비밀 보관함에 넣었는지 확인해 주세요.")
    cfg = read_json(ROOT / "config.json")
    site = cfg.get("site_url", "").rstrip("/")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        if not chat_id:
            # 텔레그램은 받은 말을 하루만 보관해요. 번호를 비밀 보관함에 넣어 두면 매번 찾지 않아도 돼요.
            chat_id = find_chat_id(token)
            api(token, "sendMessage", chat_id=chat_id, text=(
                "연결됐어요. 알림이 끊기지 않게 아래 숫자를 깃허브 비밀 보관함에 넣어 주세요.\n"
                f"Name: TELEGRAM_CHAT_ID\nSecret: {chat_id}"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            raise RuntimeError("텔레그램이 토큰을 받아 주지 않아요. 토큰을 다시 복사해 넣어 주세요.") from e
        raise
    today = today_kst()
    if len(sys.argv) > 1:
        days = [sys.argv[1]]
    else:
        # 며칠 실패했다가 다시 돌아도 빠진 글을 보내도록 최근 3일을 함께 봐요.
        base = datetime.now(KST)
        days = [(base - timedelta(days=n)).strftime("%Y-%m-%d") for n in range(3)]
    sent = set(read_json(ROOT / "state" / "sent.json", []))
    items, _ = load_items()
    todays = [i for i in items if i["date"] == days[0]]
    todo = [i for i in reversed(items) if i["date"] in days and i["id"] not in sent]
    if not todays and not todo:
        api(token, "sendMessage", chat_id=chat_id, text=f"{days[0]} 소재를 만들지 못했어요. 다음 수집 때 다시 시도해요.")
        raise RuntimeError(f"{days[0]} 글이 없어요")
    if not todo:
        print("새로 보낼 글이 없어요.")
        return
    head = f"{today} 릴스 소재 {len(todo)}개예요."
    if len(sys.argv) == 1 and len(todays) < cfg.get("daily_minimum", 3):
        head += " 확인된 내용이 모자라 억지로 채우지 않았어요."
    api(token, "sendMessage", chat_id=chat_id, text=head)
    failed = 0
    for item in todo:
        try:
            api(token, "sendMessage", chat_id=chat_id, text=message(item, site),
                parse_mode="HTML", disable_web_page_preview="true")
            sent.add(item["id"])
        except Exception as e:
            failed += 1
            log_error(f"notify:{item['id']}", e)
            print(f"못 보냈어요: {item['id']} ({e})")
    write_json(ROOT / "state" / "sent.json", sorted(sent))
    print(f"보냈어요: {len(todo) - failed}개")


def main():
    try:
        run()
    except Exception as e:
        log_error("notify", e)
        sys.exit(f"알림 실패: {e}")


if __name__ == "__main__":
    main()
