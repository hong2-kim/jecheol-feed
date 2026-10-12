# -*- coding: utf-8 -*-
"""텔레그램 봇 대화방에 보낸 사진과 동영상을 받고, 올렸어·삭제 확인 같은 말도 처리해요. (말은 cleanup.py 참고)

  python scripts/fetch_photos.py
- 받은 파일은 incoming 폴더에 두고, 작업 파일이 깃허브 릴리스 "myphotos" 에 올려요.
  (저장소 안에 넣으면 나중에 지워도 기록에 남아 용량이 줄지 않아서, 지울 수 있는 곳에 따로 둬요)
- 파일마다 이름, 고유 번호, 지문(sha256), 함께 적은 글을 myphotos/index.json 에 적어요.
  이 기록은 파일을 지운 뒤에도 남겨서, 같은 파일을 다시 받아도 또 쓰지 않아요.
- TELEGRAM_CHAT_ID 로 정해 둔 사람이 보낸 것만 받아요.
- 텔레그램은 받은 것을 하루만 보관하니, 이 스크립트는 몇 시간마다 돌아야 해요.
필요한 값(환경 변수): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

import cleanup
from common import KST, ROOT, log_error, read_json, write_json

INCOMING = ROOT / "incoming"
INDEX = ROOT / "myphotos" / "index.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "hong2-kim/jecheol-feed")
BASE = f"https://github.com/{REPO}/releases/download/myphotos/"
MAX_BYTES = 20 * 1000 * 1000  # 봇이 내려받을 수 있는 크기 한도


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=40) as res:
        return json.loads(res.read())["result"]


def download(token, file_id):
    info = api(token, "getFile", file_id=file_id)
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", timeout=180) as res:
        return res.read()


def media(msg):
    """메시지에서 사진이나 동영상을 찾아요. 없으면 None."""
    if msg.get("photo"):
        best = msg["photo"][-1]  # 가장 큰 것
        return {"type": "photo", "ext": ".jpg", "tg": best}
    doc = msg.get("document") or {}
    mime = doc.get("mime_type") or ""
    ext = os.path.splitext(doc.get("file_name") or "")[1].lower()
    if mime.startswith("image/"):
        return {"type": "photo", "ext": ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg", "tg": doc}
    video = msg.get("video") or msg.get("animation") or (doc if mime.startswith("video/") else None)
    if video:
        return {"type": "video", "ext": ext if ext in (".mp4", ".mov") else ".mp4", "tg": video}
    return None


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("텔레그램 설정이 없어 사진 받기는 건너뛰어요.")
        return
    state = ROOT / "state" / "tg_offset.json"
    offset = (read_json(state, {}) or {}).get("next", 0)
    updates = api(token, "getUpdates", offset=offset, timeout=0, allowed_updates='["message"]')
    index = read_json(INDEX, []) or []
    known = {e.get("tg_unique") for e in index} | {e.get("sha256") for e in index}
    captions, saved, again, too_big, answers = {}, [], 0, 0, []
    loose, named = [], []  # 따로 보낸 글 (받은 시각, 글), 그 글로 이름을 채운 항목
    for up in updates:  # 여러 개를 한꺼번에 보내면 글은 첫 번째에만 붙어요
        msg = up.get("message") or {}
        if msg.get("media_group_id") and msg.get("caption"):
            captions[msg["media_group_id"]] = msg["caption"]
    for up in updates:
        offset = max(offset, up["update_id"] + 1)
        msg = up.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != chat:
            continue
        found = media(msg)
        if not found:
            if msg.get("text"):  # 올렸어, 삭제 확인 같은 말
                try:
                    answer = cleanup.handle(msg["text"])
                except Exception as e:
                    log_error("cleanup", f"{type(e).__name__}: {e}")
                    answer = ["처리하다가 문제가 생겼어요. 아무것도 지우지 않았어요."]
                if answer:
                    answers.append("\n".join(answer))
                elif answer is None:  # 명령이 아닌 글은 방금 보낸 사진·동영상의 이름일 수 있어요
                    loose.append((msg.get("date", 0), msg["text"].strip()))
            continue
        tg = found["tg"]
        if tg.get("file_size", 0) > MAX_BYTES:
            too_big += 1
            continue
        if tg.get("file_unique_id") in known:
            again += 1
            continue
        try:
            data = download(token, tg["file_id"])
        except Exception as e:
            log_error("fetch_photos", type(e).__name__)  # 주소에 토큰이 들어 있어 오류 글은 남기지 않아요
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in known:
            again += 1
            continue
        day = datetime.fromtimestamp(msg.get("date", 0), KST).strftime("%Y-%m-%d")
        name = f"{day}-{up['update_id']}{found['ext']}"
        INCOMING.mkdir(exist_ok=True)
        (INCOMING / name).write_bytes(data)
        note = (msg.get("caption") or captions.get(msg.get("media_group_id")) or "").strip()
        entry = {"id": name, "type": found["type"], "file": BASE + name, "note": note, "date": day, "used": [],
                 "tg_unique": tg.get("file_unique_id"), "sha256": digest, "bytes": len(data), "msg_id": msg.get("message_id"),
                 "at": msg.get("date", 0)}
        if found["type"] == "video":
            entry["seconds"] = tg.get("duration")
            thumb = tg.get("thumbnail") or tg.get("thumb")
            if thumb:  # 어떤 영상인지 볼 수 있게 작은 미리보기 그림도 같이 둬요
                try:
                    (INCOMING / f"{name}.thumb.jpg").write_bytes(download(token, thumb["file_id"]))
                    entry["thumb"] = BASE + f"{name}.thumb.jpg"
                except Exception as e:
                    log_error("fetch_photos:thumb", type(e).__name__)
        index.append(entry)
        known |= {entry["tg_unique"], digest}
        saved.append(entry)
    # 이름 없이 온 사진·동영상에, 앞뒤 10분 안에 따로 보낸 글을 이름으로 붙여요.
    for at, text in loose:
        blank = [e for e in index if not e.get("note") and not e.get("used") and not e.get("deleted") and abs(e.get("at", 0) - at) <= 600]
        if blank:
            target = min(blank, key=lambda e: abs(e.get("at", 0) - at))
            target["note"] = text[:200]
            named.append(target)
    write_json(state, {"next": offset})
    if saved or named:
        write_json(INDEX, index)
    late = [e for e in named if all(e is not s for s in saved)]  # 전에 받은 것에 이름만 나중에 온 경우
    saved = [("동영상 " if e["type"] == "video" else "사진 ") + (e.get("note") or "(이름 없음)") for e in saved]
    lines = []
    if saved:
        lines.append(f"{len(saved)}개 받았어요:\n" + "\n".join("· " + s for s in saved[:10]))
        if any("(이름 없음)" in s for s in saved):
            lines.append("음식 이름을 알려 주세요. 지금 이 대화방에 이름만 보내도 돼요. (예: 닭갈비, 춘천)")
        lines.append("다음 영상을 만들 때 먼저 써요.")
    if late:
        lines.append("이름을 적어 뒀어요: " + ", ".join(e["note"] for e in late))
    if again:
        lines.append(f"{again}개는 전에 받은 것과 같은 파일이라 다시 받지 않았어요.")
    if too_big:
        lines.append(f"{too_big}개는 20MB가 넘어 받지 못했어요. 동영상은 10초 안쪽으로 짧게 보내 주세요.")
    if lines:
        api(token, "sendMessage", chat_id=chat, text="\n".join(lines))
    for answer in answers:
        api(token, "sendMessage", chat_id=chat, text=answer[:4000])
    try:  # 올린 지 7일이 지난 것이 새로 생기면 지울 목록을 먼저 보여 줘요
        offer = cleanup.propose()
    except Exception as e:
        log_error("cleanup:propose", f"{type(e).__name__}: {e}")
        offer = []
    if offer:
        api(token, "sendMessage", chat_id=chat, text="\n".join(offer)[:4000])
    print(f"받은 것 {len(saved)}개, 같은 파일 {again}개, 너무 큰 것 {too_big}개")


def main():
    try:
        run()
    except Exception as e:
        log_error("fetch_photos", type(e).__name__)
        sys.exit(f"사진 받기 실패: {type(e).__name__}")


if __name__ == "__main__":
    main()
