# -*- coding: utf-8 -*-
"""텔레그램 봇 대화방에 보낸 사진과 동영상을 받아요.

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
    captions, saved, again, too_big = {}, [], 0, 0
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
                 "tg_unique": tg.get("file_unique_id"), "sha256": digest, "bytes": len(data), "msg_id": msg.get("message_id")}
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
        saved.append(("동영상 " if found["type"] == "video" else "사진 ") + (note or "(이름 없음)"))
    write_json(state, {"next": offset})
    if saved:
        write_json(INDEX, index)
    lines = []
    if saved:
        lines.append(f"{len(saved)}개 받았어요:\n" + "\n".join("· " + s for s in saved[:10]))
        if any("(이름 없음)" in s for s in saved):
            lines.append("다음부터는 음식 이름을 같이 적어 주세요. (예: 닭갈비, 춘천)")
        lines.append("다음 영상을 만들 때 먼저 써요.")
    if again:
        lines.append(f"{again}개는 전에 받은 것과 같은 파일이라 다시 받지 않았어요.")
    if too_big:
        lines.append(f"{too_big}개는 20MB가 넘어 받지 못했어요. 동영상은 10초 안쪽으로 짧게 보내 주세요.")
    if lines:
        api(token, "sendMessage", chat_id=chat, text="\n".join(lines))
    print(f"받은 것 {len(saved)}개, 같은 파일 {again}개, 너무 큰 것 {too_big}개")


def main():
    try:
        run()
    except Exception as e:
        log_error("fetch_photos", type(e).__name__)
        sys.exit(f"사진 받기 실패: {type(e).__name__}")


if __name__ == "__main__":
    main()
