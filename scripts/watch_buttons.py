# -*- coding: utf-8 -*-
"""버튼 지킴이: 버튼 붙은 알림을 보낸 뒤 얼마 동안 텔레그램을 지켜보다가, 누르거나 답장하면 photos 작업을 바로 불러요. (2026-11-06)

깃허브 일정 실행(photos.yml 의 10분마다)은 실제로는 몇 시간씩 밀려서, 밖에서 버튼을 눌러도 반나절 뒤에야 이어졌어요.
produce·publish 작업이 버튼을 보냈으면(build/buttons_sent) buttons.yml 을 부르고, 이 스크립트가 정해진 시간 동안
20초마다 텔레그램에 새로 온 것이 있는지 '보기만' 해요. 처리(버튼 실행·기록)는 지금처럼 photos 작업(fetch_photos.py)이 해요.

- 보기만 하는 법: photos 가 저장한 다음 번호(state/tg_offset.json 의 next, main 최신)부터 getUpdates 를 timeout=0 으로 불러요.
  그 번호 앞의 것은 photos 가 이미 처리한 것이라 확인 처리돼도 괜찮아요. 그 뒤의 것은 건드리지 않아요.
- photos 가 돌고 있으면 기다리고, 끝난 뒤에도 새 것이 남아 있으면 다시 불러요.

  python scripts/watch_buttons.py --hours 3          지켜보기
  python scripts/watch_buttons.py --hours 3 --test   연결 확인 버튼을 보내고 지켜보기
필요한 값: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GH_TOKEN(작업 부르기)
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KST, ROOT  # noqa: E402

STEP = 20          # 몇 초마다 볼지
MAX_CALLS = 40     # 한 번 지키는 동안 photos 를 부르는 최대 횟수(잘못돼 계속 부르는 것을 막아요)
PHOTOS_WAIT = 30 * 60


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=30) as res:
        return json.loads(res.read())["result"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def saved_offset():
    """photos 가 main 에 저장한 다음 번호. 못 읽으면 None(그때는 보지 않아요)."""
    git("fetch", "-q", "origin", "main")
    r = git("show", "origin/main:state/tg_offset.json")
    if r.returncode != 0:
        return None
    try:
        return int(json.loads(r.stdout).get("next", 0))
    except Exception:
        return None


def ours(up, chat):
    """정해 둔 사람이 보낸 것(버튼·글·사진)인지."""
    cb = up.get("callback_query")
    if cb:
        return str((cb.get("from") or {}).get("id")) == chat
    return str(((up.get("message") or {}).get("chat") or {}).get("id")) == chat


def photos_busy():
    r = subprocess.run(["gh", "run", "list", "--workflow", "photos.yml", "--limit", "5", "--json", "status"],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"photos 상태를 못 읽었어요: {r.stderr[:200]}")
        return True  # 모르면 부르지 않고 다음에 다시 봐요
    return any(x.get("status") != "completed" for x in json.loads(r.stdout or "[]"))


def call_photos():
    r = subprocess.run(["gh", "workflow", "run", "photos.yml", "--ref", "main"], cwd=ROOT, capture_output=True, text=True)
    print(f"{datetime.now(KST):%H:%M:%S} photos 부름: {'됨' if r.returncode == 0 else r.stderr[:200]}")
    if r.returncode != 0:
        return False
    time.sleep(15)  # 목록에 나타날 때까지
    until = time.time() + PHOTOS_WAIT
    while time.time() < until and photos_busy():
        time.sleep(15)
    return True


def send_test(token, chat):
    sent = datetime.now(KST).strftime("%H:%M")
    rid = (json.loads((ROOT / "requests" / "buttons-test.json").read_text(encoding="utf-8")) or {}).get("rid") \
        if (ROOT / "requests" / "buttons-test.json").exists() else None
    if rid:  # 실제 고치기 시험: 그 영상에 [고쳐서 다시]·답장을 받는 메시지(아침에 받은 영상을 고쳐요)
        sys.path.insert(0, str(ROOT / "video"))
        try:
            from publish import LABELS
            name = LABELS.get(rid[11:], (rid[11:],))[0]
        except Exception:
            name = rid
        kb = {"inline_keyboard": [[{"text": "🛠 고쳐서 다시", "callback_data": f"j:fix:{rid}"},
                                   {"text": "이대로 둘게요", "callback_data": f"j:fine:{rid}"}]]}
        api(token, "sendMessage", chat_id=chat, reply_markup=json.dumps(kb, ensure_ascii=False),
            text=f"🧪 실제 고치기 시험 · {name} ({rid})\n이 메시지에 고칠 점을 답장으로 적어 주세요. 그대로 고쳐서 '승인 전 시안'으로 다시 보내요.\n"
                 "(답장 없이 [고쳐서 다시]만 누르면 검수 까닭이 없어 그대로 둘 수 있어요.) 네이버·인스타 어디에도 올리지 않아요.")
        return
    kb = {"inline_keyboard": [[{"text": "✅ 연결 확인", "callback_data": f"j:ping:{sent}"}],
                              [{"text": "🛠 고치기 루틴도 불러 보기", "callback_data": f"j:pingfix:{sent}"}]]}
    api(token, "sendMessage", chat_id=chat, reply_markup=json.dumps(kb, ensure_ascii=False),
        text=f"🧪 텔레그램 버튼 연결 시험 ({sent})\n[연결 확인]을 누르면 1~3분 안에 답이 와요. 아무것도 바꾸지 않아요.\n"
             "[고치기 루틴도 불러 보기]는 고치기 루틴을 실제로 불러요(열린 고칠 요청이 없으면 아무것도 바꾸지 않고 끝나요).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=3)
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("텔레그램 설정이 없어 지키지 않아요.")
        return
    if a.test:
        send_test(token, chat)
    end = time.time() + a.hours * 3600
    calls = 0
    print(f"{datetime.now(KST):%H:%M} 부터 {a.hours}시간 지켜봐요")
    while time.time() < end and calls < MAX_CALLS:
        offset = saved_offset()
        if offset is not None:
            try:
                ups = api(token, "getUpdates", offset=offset, timeout=0, allowed_updates='["message","callback_query"]')
            except Exception as e:  # 409(다른 곳에서 받는 중) 등은 다음에 다시
                print(f"텔레그램을 못 봤어요: {type(e).__name__}")
                ups = []
            new = [u for u in ups if u["update_id"] >= offset and ours(u, chat)]
            if new and not photos_busy():
                print(f"새로 온 것 {len(new)}개")
                if call_photos():
                    calls += 1
        time.sleep(STEP)
    print(f"{datetime.now(KST):%H:%M} 지키기 끝 (photos {calls}번 부름)")


if __name__ == "__main__":
    main()
