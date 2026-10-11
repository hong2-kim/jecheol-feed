# -*- coding: utf-8 -*-
"""만든 영상을 공개하고 알려요. 깃허브 자동 작업 안에서 돌아요.

  python video/publish.py 2026-10-12

1. dist/results.json 을 읽어요.
2. 성공한 영상의 내려받기 주소를 state/videos.json 에 적어요. (RSS가 이 파일을 읽어요)
3. 텔레그램으로 영상과 게시글용 글을 보내요. 실패한 항목은 이유와 함께 알려요.
영상 파일 올리기(릴리스)는 작업 파일에서 gh 명령으로 먼저 해 둬요.
"""
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from common import log_error, read_json, write_json  # noqa: E402

ROOT = Path(__file__).parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "hong2-kim/jecheol-feed")


def tg(method, token, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=180, **kw)
    if not r.ok:
        raise RuntimeError(f"텔레그램 {method} 실패: {r.status_code} {r.text[:200]}")
    return r.json()["result"]


def main():
    day = sys.argv[1]
    results = read_json(ROOT / "dist" / "results.json", [])
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    videos = read_json(ROOT / "state" / "videos.json", [])
    for r in results:
        if r["ok"]:
            r["url"] = f"https://github.com/{REPO}/releases/download/v{day}/{r['file']}"
            # 같은 영상을 다시 만들면 제목과 글도 새것으로 바꿔요.
            videos = [v for v in videos if v["id"] != r["id"]]
            videos.append({k: r.get(k) for k in ("id", "date", "kind", "title", "summary", "caption", "tags", "sources", "credits", "url", "seconds", "size_mb")})
    videos.sort(key=lambda v: v["id"], reverse=True)
    write_json(ROOT / "state" / "videos.json", videos[:400])

    if not (token and chat):
        print("텔레그램 설정이 없어 알림은 건너뛰어요.")
        return
    sent = set(read_json(ROOT / "state" / "sent_videos.json", []))
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    todo = [r for r in ok if r["id"] not in sent]
    if todo or bad:
        head = f"{day} 영상 {len(ok)}개가 준비됐어요."
        if bad:
            head += f" 실패 {len(bad)}개: " + "; ".join(f"{b['id']} ({b['error'][:80]})" for b in bad)
        tg("sendMessage", token, data={"chat_id": chat, "text": head})
    for r in todo:
        text = (ROOT / "dist" / r["file"]).with_suffix(".txt").read_text(encoding="utf-8")
        try:
            with open(ROOT / "dist" / r["file"], "rb") as f:
                tg("sendVideo", token, data={"chat_id": chat, "caption": (r.get("title") or r["id"])[:900], "supports_streaming": "true",
                                             "width": 1080, "height": 1920}, files={"video": (r["file"], f, "video/mp4")})
            body = f"{r.get('title')}\n\n[게시글에 넣을 글]\n{text}\n[내려받기]\n{r['url']}"
            if r.get("sources"):
                body += "\n\n[출처]\n" + "\n".join(r["sources"])
            tg("sendMessage", token, data={"chat_id": chat, "text": body[:4000], "disable_web_page_preview": "true"})
            sent.add(r["id"])
        except Exception as e:
            log_error(f"telegram:{r['id']}", e)
            print(f"못 보냈어요: {r['id']} ({e})")
    write_json(ROOT / "state" / "sent_videos.json", sorted(sent))
    print(f"보냈어요: {len(todo)}개, 실패 알림 {len(bad)}개")


if __name__ == "__main__":
    main()
