# -*- coding: utf-8 -*-
"""만든 영상을 공개하고 알려요. 깃허브 자동 작업 안에서 돌아요.

  python video/publish.py 2026-10-12

1. dist/results.json 을 읽어요.
2. 성공한 영상의 내려받기 주소를 state/videos.json 에 적어요. (RSS가 이 파일을 읽어요)
3. 텔레그램으로 영상과 게시글용 글을 보내요. 실패한 항목은 이유와 함께 알려요.
영상 파일 올리기(릴리스)는 작업 파일에서 gh 명령으로 먼저 해 둬요.
"""
import hashlib
import html
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plan  # noqa: E402
from common import log_error, read_json, write_json  # noqa: E402

ROOT = Path(__file__).parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "hong2-kim/jecheol-feed")


def tg(method, token, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=180, **kw)
    if not r.ok:
        raise RuntimeError(f"텔레그램 {method} 실패: {r.status_code} {r.text[:200]}")
    return r.json()["result"]


def card_name(r):
    """카드 묶음을 부르는 이름. 요즘 뜨는 메뉴(kind 유행)는 따로 불러요."""
    return "트렌드 카드" if r.get("kind") == "유행" else "카드 뉴스"


def send_cards(token, chat, r):
    """카드 뉴스 그림을 한 묶음(앨범)으로 보내요. 올릴 순서대로 놓여요."""
    names = r["files"]
    if len(names) == 1:
        with open(ROOT / "dist" / names[0], "rb") as f:
            tg("sendPhoto", token, data={"chat_id": chat, "caption": (r.get("title") or r["id"])[:900]}, files={"photo": (names[0], f, "image/jpeg")})
        return
    media = [{"type": "photo", "media": f"attach://p{n}"} for n in range(len(names))]
    media[0]["caption"] = (r.get("title") or r["id"])[:900]
    files = {f"p{n}": (name, (ROOT / "dist" / name).read_bytes(), "image/jpeg") for n, name in enumerate(names)}
    tg("sendMediaGroup", token, data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)}, files=files)


def send_youtube(token, chat, r, day):
    """유튜브 쇼츠에 올릴 제목과 설명을 보내요. 제목과 설명은 눌러서 바로 복사할 수 있게 감싸요.
    카드 뉴스는 쇼츠용 영상(카드를 넘겨 보는 세로 영상)을 먼저 보내요."""
    if not r.get("yt_title"):
        return
    video = r.get("short") if r.get("format") == "cards" else r["file"]
    if not video or not (ROOT / "dist" / video).exists():
        return
    if r.get("format") == "cards":
        with open(ROOT / "dist" / video, "rb") as f:
            tg("sendVideo", token, data={"chat_id": chat, "caption": f"[유튜브 쇼츠] {r.get('title')}"[:900], "supports_streaming": "true",
                                         "width": 1080, "height": 1920}, files={"video": (video, f, "video/mp4")})
    desc = r.get("yt_desc") or ""
    if len(desc) > 3300:  # 텔레그램 글 한 개에 다 들어가게
        desc = desc[:3300].rstrip() + "\n…"
    url = f"https://github.com/{REPO}/releases/download/v{day}/{video}"
    what = "위 카드 영상" if r.get("format") == "cards" else "위 영상"
    text = (f"<b>[유튜브 쇼츠]</b> {what}을 쇼츠로 올려 주세요.\n\n"
            f"<b>제목</b> (눌러서 복사)\n<code>{html.escape(r['yt_title'])}</code>\n\n"
            f"<b>설명</b> (눌러서 복사)\n<pre>{html.escape(desc)}</pre>\n"
            f"<b>내려받기</b>\n{html.escape(url)}")
    tg("sendMessage", token, data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})


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
            old = next((v for v in videos if v["id"] == r["id"]), {})
            videos = [v for v in videos if v["id"] != r["id"]]
            entry = {k: r.get(k) for k in ("id", "date", "kind", "title", "summary", "caption", "tags", "sources", "credits", "url", "seconds", "size_mb", "yt_title")}
            if r.get("format") == "cards":  # 카드 뉴스는 그림 여러 장이에요. url 은 첫 장이에요.
                entry.update({"format": "cards", "files": r["files"], "urls": [f"https://github.com/{REPO}/releases/download/v{day}/{f}" for f in r["files"]]})
            entry["sha256"] = hashlib.sha256((ROOT / "dist" / r["file"]).read_bytes()).hexdigest()  # 같은 파일인지 알아보는 지문
            entry.update({k: old[k] for k in ("posted", "deleted") if k in old})
            videos.append(entry)
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
        cards = [card_name(r) for r in ok if r.get("format") == "cards"]
        head = f"{day} 영상 {len(ok) - len(cards)}개" + "".join(f", {name} {cards.count(name)}개" for name in dict.fromkeys(cards)) + "가 준비됐어요."
        if bad:
            head += f" 실패 {len(bad)}개: " + "; ".join(f"{b['id']} ({b['error'][:80]})" for b in bad)
        mine = read_json(ROOT / "myphotos" / "index.json", []) or []
        today = plan.used_on(mine, day)
        if today:
            head += "\n\n첫 장면에 보내 주신 " + ", ".join(f"'{e.get('note') or '이름 없음'}'" for e in today) + " 을(를) 썼어요."
        if plan.waiting(mine):
            head += "\n\n[다음 순서]\n" + "\n".join(plan.lines(mine))
        tg("sendMessage", token, data={"chat_id": chat, "text": head})
    for r in todo:
        text = (ROOT / "dist" / f"{r['id']}.txt").read_text(encoding="utf-8")
        try:
            if r.get("format") == "cards":
                send_cards(token, chat, r)
                links = "\n".join(f"https://github.com/{REPO}/releases/download/v{day}/{f}" for f in r["files"])
                body = (f"[{card_name(r)}] {r.get('title')}\n위 사진 {len(r['files'])}장을 순서대로 한 게시물에 올려 주세요.\n\n"
                        f"[게시글에 넣을 글]\n{text}\n[원본 그림] 텔레그램 사진은 조금 작아져요. 또렷한 원본은 여기서 받아요\n{links}")
            else:
                with open(ROOT / "dist" / r["file"], "rb") as f:
                    tg("sendVideo", token, data={"chat_id": chat, "caption": (r.get("title") or r["id"])[:900], "supports_streaming": "true",
                                                 "width": 1080, "height": 1920}, files={"video": (r["file"], f, "video/mp4")})
                body = f"{r.get('title')}\n\n[게시글에 넣을 글]\n{text}\n[내려받기]\n{r['url']}"
            if r.get("sources"):
                body += "\n\n[확인한 자료] 게시글에는 안 넣어도 돼요\n" + "\n".join(r["sources"])
            tg("sendMessage", token, data={"chat_id": chat, "text": body[:4000], "disable_web_page_preview": "true"})
            sent.add(r["id"])
            try:  # 유튜브 안내가 안 가도 인스타 안내는 이미 갔으니 보낸 것으로 쳐요
                send_youtube(token, chat, r, day)
            except Exception as e:
                log_error(f"youtube:{r['id']}", e)
                print(f"유튜브 안내를 못 보냈어요: {r['id']} ({e})")
        except Exception as e:
            log_error(f"telegram:{r['id']}", e)
            print(f"못 보냈어요: {r['id']} ({e})")
    write_json(ROOT / "state" / "sent_videos.json", sorted(sent))
    print(f"보냈어요: {len(todo)}개, 실패 알림 {len(bad)}개")


if __name__ == "__main__":
    main()
