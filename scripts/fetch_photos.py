# -*- coding: utf-8 -*-
"""텔레그램 봇 대화방에 보낸 사진을 받아 myphotos 폴더에 저장해요.

  python scripts/fetch_photos.py
- 사진과 함께 적은 글(음식 이름, 가게, 한마디)을 myphotos/index.json 에 같이 적어요.
- TELEGRAM_CHAT_ID 로 정해 둔 사람이 보낸 것만 받아요. 다른 사람이 보낸 것은 무시해요.
- 텔레그램은 받은 것을 하루만 보관하니, 이 스크립트는 몇 시간마다 돌아야 해요.
필요한 값(환경 변수): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

from common import KST, ROOT, log_error, read_json, write_json

FOLDER = ROOT / "myphotos"
MAX_BYTES = 20 * 1000 * 1000  # 봇이 내려받을 수 있는 크기 한도


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=40) as res:
        return json.loads(res.read())["result"]


def picture(msg):
    """메시지에서 사진 파일을 찾아요. (파일 번호, 확장자, 크기) 또는 None"""
    if msg.get("photo"):
        best = msg["photo"][-1]  # 가장 큰 것
        return best["file_id"], ".jpg", best.get("file_size", 0)
    doc = msg.get("document") or {}
    if (doc.get("mime_type") or "").startswith("image/"):
        ext = os.path.splitext(doc.get("file_name") or "")[1].lower() or ".jpg"
        return doc["file_id"], ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg", doc.get("file_size", 0)
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
    index = read_json(FOLDER / "index.json", []) or []
    captions, saved, videos, too_big = {}, [], 0, 0
    for up in updates:  # 여러 장을 한꺼번에 보내면 글은 첫 장에만 붙어요
        msg = up.get("message") or {}
        if msg.get("media_group_id") and msg.get("caption"):
            captions[msg["media_group_id"]] = msg["caption"]
    for up in updates:
        offset = max(offset, up["update_id"] + 1)
        msg = up.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != chat:
            continue
        if msg.get("video") or msg.get("animation") or (msg.get("document") or {}).get("mime_type", "").startswith("video/"):
            videos += 1
            continue
        pic = picture(msg)
        if not pic:
            continue
        file_id, ext, size = pic
        if size > MAX_BYTES:
            too_big += 1
            continue
        try:
            info = api(token, "getFile", file_id=file_id)
            with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", timeout=120) as res:
                data = res.read()
        except Exception as e:
            log_error("fetch_photos", type(e).__name__)  # 주소에 토큰이 들어 있어 오류 글은 남기지 않아요
            continue
        day = datetime.fromtimestamp(msg.get("date", 0), KST).strftime("%Y-%m-%d")
        name = f"{day}-{up['update_id']}{ext}"
        FOLDER.mkdir(exist_ok=True)
        (FOLDER / name).write_bytes(data)
        note = (msg.get("caption") or captions.get(msg.get("media_group_id")) or "").strip()
        index.append({"file": f"myphotos/{name}", "note": note, "date": day, "used": []})
        saved.append(note or "이름 없음")
    write_json(state, {"next": offset})
    if saved:
        write_json(FOLDER / "index.json", index)
    lines = []
    if saved:
        lines.append(f"사진 {len(saved)}장 받았어요: " + ", ".join(saved[:10]))
        if "이름 없음" in saved:
            lines.append("다음부터는 사진에 음식 이름을 같이 적어 주세요. (예: 닭갈비, 춘천)")
        lines.append("다음 영상을 만들 때 이 사진을 먼저 써요.")
    if videos:
        lines.append(f"동영상 {videos}개는 아직 쓸 수 없어요. 사진으로 보내 주세요.")
    if too_big:
        lines.append(f"{too_big}장은 20MB가 넘어 받지 못했어요.")
    if lines:
        api(token, "sendMessage", chat_id=chat, text="\n".join(lines))
    print(f"받은 사진 {len(saved)}장, 동영상 {videos}개, 너무 큰 것 {too_big}개")


def main():
    try:
        run()
    except Exception as e:
        log_error("fetch_photos", type(e).__name__)
        sys.exit(f"사진 받기 실패: {type(e).__name__}")


if __name__ == "__main__":
    main()
