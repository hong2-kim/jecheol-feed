# -*- coding: utf-8 -*-
"""달마다 만드는 영상(이달의 제철음식, 세계의 음식·술 축제, 해외 먹거리 트렌드)이 나왔는지 확인해요.

  python scripts/check_monthly.py
제철과 세계 축제는 1일, 해외 트렌드는 2일에 나와야 해요. 그날부터 5일까지, 아직 안 나온 것이 있으면 텔레그램으로 알려요.
(깃허브 자동 작업이 매일 오전 8시에 돌려요. 그날 영상은 보통 6시 반쯤 만들어져요)
필요한 값(환경 변수): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import sys
from datetime import datetime

from common import KST, ROOT, log_error, read_json
from notify_telegram import api

# 파일 이름 끝: (이름, 나오는 날)
WANT = {"1-monthly": ("이달의 제철음식", 1), "5-world": ("세계의 음식·술 축제", 1), "9-abroad": ("해외 먹거리 트렌드", 2)}


def missing(now):
    """이번 달에 아직 영상으로 나오지 않은 것의 이름."""
    month = now.strftime("%Y-%m")
    videos = [v for v in (read_json(ROOT / "state" / "videos.json", []) or []) if str(v.get("id", "")).startswith(month)]
    return [name for key, (name, day) in WANT.items()
            if now.day >= day and not any(str(v["id"]).endswith(key) for v in videos)]


def main():
    now = datetime.now(KST)
    left = missing(now)
    if not left:
        print("달마다 만드는 영상이 이번 달에 모두 나왔어요.")
        return
    print("아직 안 나온 영상:", ", ".join(left))
    if now.day > 5:  # 달 초에만 알려요. 그 뒤로는 날마다 알리지 않아요.
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        print("텔레그램 설정이 없어 알림은 건너뛰어요.")
        return
    text = (f"⚠️ {now.month}월 영상이 아직 안 나왔어요: {', '.join(left)}\n"
            "달 초(1일, 2일)에 나와야 하는 영상이에요. 오늘 아침 실행에서 만들지 못했어요. 내일 아침에 다시 만들어요.")
    try:
        api(token, "sendMessage", chat_id=chat_id, text=text)
    except Exception as e:
        log_error("check_monthly", e)
        sys.exit(f"알림 실패: {e}")


if __name__ == "__main__":
    main()
