# -*- coding: utf-8 -*-
"""오늘 소재를 텔레그램 봇으로 보내요.

  python scripts/notify_telegram.py            오늘 날짜 글
  python scripts/notify_telegram.py 2026-10-12  그 날짜 글
필요한 값(환경 변수):
  TELEGRAM_BOT_TOKEN  봇 토큰 (BotFather 가 준 것)
  TELEGRAM_CHAT_ID    받을 사람 번호. 비워 두면 봇에게 마지막으로 말을 건 사람에게 보내요.
이미 보낸 글은 state/sent.json 에 적어 두고 다시 보내지 않아요.
"""
import html
import json
import os
import sys
import urllib.parse
import urllib.request

from common import ROOT, load_items, log_error, read_json, today_kst, write_json


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=30) as res:
        return json.loads(res.read())["result"]


def find_chat_id(token):
    for update in reversed(api(token, "getUpdates")):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            return chat["id"]
    sys.exit("받을 사람을 찾지 못했어요. 텔레그램에서 봇 대화방에 들어가 아무 말이나 한 번 보내 주세요.")


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


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN 이 없어요.")
    day = sys.argv[1] if len(sys.argv) > 1 else today_kst()
    cfg = read_json(ROOT / "config.json")
    site = cfg.get("site_url", "").rstrip("/")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or find_chat_id(token)
    sent = set(read_json(ROOT / "state" / "sent.json", []))
    items, _ = load_items()
    todays = [i for i in items if i["date"] == day]
    todo = [i for i in reversed(todays) if i["id"] not in sent]
    if not todays:
        log_error("notify", f"{day} 글이 없어요")
        api(token, "sendMessage", chat_id=chat_id, text=f"{day} 소재를 만들지 못했어요. 다음 수집 때 다시 시도해요.")
        sys.exit(1)
    if not todo:
        print("새로 보낼 글이 없어요.")
        return
    head = f"{day} 릴스 소재 {len(todays)}개예요."
    if len(todays) < cfg.get("daily_minimum", 3):
        head += " 확인된 내용이 모자라 억지로 채우지 않았어요."
    api(token, "sendMessage", chat_id=chat_id, text=head)
    for item in todo:
        try:
            api(token, "sendMessage", chat_id=chat_id, text=message(item, site),
                parse_mode="HTML", disable_web_page_preview="true")
            sent.add(item["id"])
        except Exception as e:
            log_error(f"notify:{item['id']}", e)
            print(f"못 보냈어요: {item['id']} ({e})")
    write_json(ROOT / "state" / "sent.json", sorted(sent))
    print(f"보냈어요: {len(todo)}개")


if __name__ == "__main__":
    main()
