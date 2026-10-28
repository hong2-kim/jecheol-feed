# -*- coding: utf-8 -*-
"""만든 영상을 공개하고 알려요. 깃허브 자동 작업 안에서 돌아요.

  python video/publish.py 2026-10-12

1. dist/results.json 을 읽어요.
2. 성공한 영상의 내려받기 주소를 state/videos.json 에 적어요. (RSS가 이 파일을 읽어요)
3. 보내기 전 검수(scripts/gate.py): 통과한 것(또는 사용자가 승인한 '확인 필요')만 보내요. 걸린 것은 보내지 않고
   까닭을 state/review.json 에 적고 한 번 알려요. 보낸 것으로 적지 않으니 고쳐서 다시 올리면 다시 검수해 보내요. (2026-10-23 5단계)
4. 텔레그램으로 영상과 게시글용 글을 보내요. 실패한 항목은 이유와 함께 알려요.
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


# 설계도 파일 이름 -> (무슨 영상인지, 언제 나가는지). 텔레그램에서 찾기 쉽게 메시지마다 붙여요.
LABELS = {
    "2-news": ("카드 뉴스", "매일"), "3-dinner": ("저녁 추천", "매일"), "4-find": ("발견형 · 오늘의 한 가지", "매일"),
    "6-story": ("맛의 이야기", "화요일"), "7-local": ("지역의 먹거리", "목요일"), "8-trend": ("요즘 뜨는 메뉴 카드", "금요일"),
    "1-monthly": ("이달의 제철", "달마다"), "5-world": ("세계 축제", "달마다"), "9-abroad": ("해외 먹거리 트렌드", "달마다"),
    "1-check": ("제철 체크 · 몇 개 먹어 봤어요?", "달마다"), "1-sheet": ("제철 한 장 정리", "달마다"),
    "10-voice": ("내레이션 쇼츠", "매일"), "11-steps": ("넘겨 보는 해설", "정보성 주제"),
}


def label(r, where):
    """[인스타 릴스 · 저녁 추천 · 매일] 같은 이름표. where 는 "insta" 또는 "youtube"."""
    stem = r["id"][11:]  # 2026-10-15-3-dinner -> 3-dinner
    what, when = LABELS.get(stem, (r.get("title") or stem, ""))
    if where == "youtube":
        place = "유튜브 쇼츠"
    else:
        place = f"인스타 게시물(사진 {len(r['files'])}장)" if r.get("format") == "cards" else "인스타 릴스"
    return f"[{place} · {what}" + (f" · {when}]" if when else "]")


def send_cards(token, chat, r):
    """카드 뉴스 그림을 한 묶음(앨범)으로 보내요. 올릴 순서대로 놓여요."""
    names = r["files"]
    title = f"{label(r, 'insta')}\n{r.get('title') or r['id']}"
    if len(names) == 1:
        with open(ROOT / "dist" / names[0], "rb") as f:
            tg("sendPhoto", token, data={"chat_id": chat, "caption": title[:900]}, files={"photo": (names[0], f, "image/jpeg")})
        return
    media = [{"type": "photo", "media": f"attach://p{n}"} for n in range(len(names))]
    media[0]["caption"] = title[:900]
    files = {f"p{n}": (name, (ROOT / "dist" / name).read_bytes(), "image/jpeg") for n, name in enumerate(names)}
    tg("sendMediaGroup", token, data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)}, files=files)


def music_note(r, youtube=False):
    """깔린 오디오 보관함 곡 안내. CC 곡이면 출처 줄을 꼭 같이 올려야 한다고 눈에 띄게 적어요. (2026-10-17 사용자가 부탁함)"""
    m = r.get("music")
    if not m:
        return ""
    where = "설명" if youtube else "게시글"
    if m.get("credit"):
        return f"⚠️ CC 필요 — 배경음악 '{m['title']}'({m['artist']})은 출처 표시가 꼭 필요해요. {where} 끝 🎵 줄을 지우지 말고 그대로 올려 주세요.\n\n"
    return f"🎵 배경음악: {m['title']} - {m['artist']} (출처 표시 필요 없음)\n\n"


def keywords_block(r):
    """핵심 키워드, 연관 키워드, 태그(눌러서 복사), 해시태그. 예전 결과에 없으면 비워요. (2026-10-16 사용자가 정함)"""
    out = ""
    if r.get("yt_keyword"):
        out += f"<b>핵심 키워드</b>\n{html.escape(r['yt_keyword'])}\n\n"
    if r.get("yt_related"):
        out += f"<b>연관 키워드</b>\n{html.escape(' · '.join(r['yt_related']))}\n\n"
    if r.get("yt_tags"):
        out += f"<b>태그</b> (눌러서 복사 → 스튜디오 '태그' 칸에 붙여 넣기)\n<code>{html.escape(r['yt_tags'])}</code>\n\n"
    if r.get("pin"):
        out += f"<b>고정 댓글</b> (올린 뒤 첫 댓글로 달고 고정, 눌러서 복사)\n<code>{html.escape(r['pin'])}</code>\n\n"
    if r.get("yt_hashtags"):
        out += f"<b>해시태그</b> (설명 끝에 들어 있어요)\n{html.escape(' '.join('#' + t for t in r['yt_hashtags']))}\n\n"
    return out


def insta_on():
    """인스타용(릴스·카드 게시물과 게시글)도 텔레그램으로 보낼지. config.json 의 telegram_insta.
    (2026-10-22 사용자: "인스타용은 텔레그램에 보낼 때 빼 줘" → false, 유튜브 쇼츠만 가요)"""
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("telegram_insta", True)


def has_youtube(r):
    """유튜브 쇼츠로 보낼 영상이 있는지."""
    video = r.get("short") if r.get("format") == "cards" else r.get("file")
    return bool(r.get("yt_title") and video and (ROOT / "dist" / video).exists())


def send_youtube(token, chat, r, day, alone=False):
    """유튜브 쇼츠에 올릴 제목과 설명을 보내요. 제목과 설명은 눌러서 바로 복사할 수 있게 감싸요.
    영상은 바로 위 인스타 것과 같은 파일이라 다시 보내지 않아요 (2026-10-18 사용자: 같은 영상이 두 번 와서 용량만 차지).
    카드 묶음만 쇼츠용 영상(카드를 넘겨 보는 세로 영상)이 따로 있어서 그것만 보내요.
    인스타용을 보내지 않을 때(alone)는 위에 영상이 없으니 영상도 여기서 보내요."""
    if not has_youtube(r):
        return
    cards = r.get("format") == "cards"
    video = r.get("short") if cards else r["file"]
    tag = label(r, "youtube")
    if cards or alone:
        with open(ROOT / "dist" / video, "rb") as f:
            tg("sendVideo", token, data={"chat_id": chat, "caption": f"{tag}\n{r.get('yt_title') or r.get('title')}"[:900], "supports_streaming": "true",
                                         "width": 1080, "height": 1920}, files={"video": (video, f, "video/mp4")})
    desc = r.get("yt_desc") or ""
    if len(desc) > 3300:  # 텔레그램 글 한 개에 다 들어가게
        desc = desc[:3300].rstrip() + "\n…"
    url = f"https://github.com/{REPO}/releases/download/v{day}/{video}"
    text = (f"<b>{html.escape(tag)}</b>\n{'위 영상' if cards or alone else '바로 위 인스타 영상(같은 파일)'}을 쇼츠로 올려 주세요. 썸네일은 맨 앞(0초) 장면을 고르면 큰 제목 화면이 돼요.\n\n{html.escape(music_note(r, youtube=True))}"
            f"<b>제목</b> (눌러서 복사)\n<code>{html.escape(r['yt_title'])}</code>\n\n"
            + keywords_block(r) +
            f"<b>설명</b> (눌러서 복사)\n<pre>{html.escape(desc)}</pre>\n"
            f"<b>내려받기</b>\n{html.escape(url)}")
    more = "\n\n<b>확인한 자료</b> (설명에는 안 넣어도 돼요)\n" + html.escape("\n".join(r.get("sources") or []))
    if alone and r.get("sources") and len(text) + len(more) <= 4000:  # 인스타 글과 함께 가던 확인한 자료. 글 한 개(4096자)에 들어갈 때만
        text += more
    tg("sendMessage", token, data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})


def send_shorts_only(token, chat, day, todo, bad, sent):
    """인스타용을 빼고 유튜브 쇼츠만 보내요: 첫 안내 → 항목마다 구분 줄, 영상, 제목·설명."""
    if not (todo or bad):
        return
    head = f"{day} 올릴 것이 준비됐어요."
    if todo:
        head += f"\n\n▶ 유튜브 쇼츠 {len(todo)}개\n" + "\n".join(f"{n}. {label(r, 'youtube')[1:-1]}" for n, r in enumerate(todo, 1))
        head += "\n\n영상 바로 아래에 유튜브 제목·설명이 이어져요."
    if bad:
        head += f"\n\n실패 {len(bad)}개: " + "; ".join(f"{b['id']} ({b['error'][:80]})" for b in bad)
    tg("sendMessage", token, data={"chat_id": chat, "text": head})
    for r in todo:
        tg("sendMessage", token, data={"chat_id": chat, "text": f"━━━━ {LABELS.get(r['id'][11:], (r.get('title') or r['id'],))[0]} ━━━━"})
        try:
            send_youtube(token, chat, r, day, alone=True)
            sent.add(r["id"])
        except Exception as e:
            log_error(f"youtube:{r['id']}", e)
            print(f"못 보냈어요: {r['id']} ({e})")


def gate_all(day, results):
    """보내기 전 검수(scripts/gate.py). {id: 검수 결과}. 설계도가 없거나 검수를 못 하면 '확인 필요'로 봐요(통과로 치지 않아요). (2026-10-23 5단계)"""
    import gate
    out = {}
    for r in results:
        if not r.get("ok"):
            continue
        spec = ROOT / "videos" / day / (r["id"][len(day) + 1:] + ".json")
        try:
            out[r["id"]] = gate.evaluate(spec, held=[h["no"] for h in r.get("held") or []])
        except Exception as e:
            log_error(f"gate:{r['id']}", e)
            out[r["id"]] = {"verdict": "확인 필요", "findings": [("검수 오류", "확인", f"검수를 하지 못했어요: {str(e)[:150]}")], "hash": "", "approved": False}
    return out


def gate_reasons(g):
    import gate
    return gate.reasons(g, 12)  # 차단 먼저


def held_cards_notice(token, chat, day, results, review, passed):
    """일부 장만 빼고 보내는 카드 뉴스: 뺀 장과 까닭을 한 번 알리고, 그 장의 사진 검수 시트를 보내요 (2026-10-28 사용자)."""
    import re
    for r in results:
        held = r.get("held") or []
        if not held or r["id"] not in passed:
            continue
        key = ";".join(f"{h['no']}:{h['grade']}" for h in held)
        if (review.get(r["id"]) or {}).get("held_noticed") == key:
            continue
        name = LABELS.get(r['id'][11:], (r.get('title') or r['id'],))[0]
        lines = [f"✂️ {name} — 아래 {len(held)}장은 빼고, 나머지 장만 쪽 번호를 다시 매겨 보내요"]
        for h in held:
            lines.append(f"\n■ {h['no']}장 「{h['headline']}」 — {h['grade']}")
            lines += ["  " + x[:160] for x in h["reasons"][:3]]
        lines.append("\n'확인 필요'는 보고 괜찮으면 Claude 에게 말해 주세요. 그 장을 넣어 다시 만들어요. '차단'·'보류'는 고쳐야 나가요.")
        if token and chat:
            tg("sendMessage", token, data={"chat_id": chat, "text": "\n".join(lines)[:4000], "disable_web_page_preview": "true"})
            try:  # 뺀 장의 사진 자리를 빨간 테두리로 표시한 검수 시트
                import review_sheet
                out = ROOT / "dist" / f"{r['id']}-held.jpg"
                marks = {f"cards[{h['no']}].photo" for h in held}
                review_sheet.spec_sheet(ROOT / "videos" / day / (r["id"][len(day) + 1:] + ".json"), out, marks, "\n".join(lines[:6]).replace("✂️ ", ""))  # 검수 시트 글꼴에는 그림 문자가 없어요
                with open(out, "rb") as f:
                    tg("sendPhoto", token, data={"chat_id": chat, "caption": f"뺀 장 검수 시트 · {name} · 빨간 칸이 뺀 장의 사진"[:900]},
                       files={"photo": (out.name, f, "image/jpeg")})
            except Exception as e:
                log_error(f"review_sheet:held:{r['id']}", e)
        review.setdefault(r["id"], {})["held_noticed"] = key
        review[r["id"]]["held_cards"] = held


def hold_notice(token, chat, day, held, review):
    """보류한 것만 한 번 알려요. 같은 내용(같은 지문·같은 판정)으로 이미 알린 것은 다시 알리지 않아요."""
    import gate
    fresh = [(r, g) for r, g in held if (review.get(r["id"]) or {}).get("noticed") != f"{g['verdict']}:{g['hash']}"]
    if not fresh or not (token and chat):
        return
    lines = [f"🛑 {day} 검수에 걸려 보내지 않은 것 {len(fresh)}개"]
    for r, g in fresh:
        lines.append(f"\n■ {LABELS.get(r['id'][11:], (r.get('title') or r['id'],))[0]} — {g['verdict']}")
        lines += ["  " + x for x in gate.reasons(g)]
    lines.append("\n고친 설계도를 다시 올리면 다시 검수해요. '확인 필요'는 보고 괜찮으면 Claude 에게 \"보내\"라고 하면 승인해 다시 보내요. '차단'은 고쳐야 나가요.")
    tg("sendMessage", token, data={"chat_id": chat, "text": "\n".join(lines)[:4000], "disable_web_page_preview": "true"})
    for r, g in fresh:
        review[r["id"]]["noticed"] = f"{g['verdict']}:{g['hash']}"
        name = LABELS.get(r['id'][11:], (r.get('title') or r['id'],))[0]
        try:  # 문제가 걸린 자리를 빨간 테두리로 표시한 사진 검수 시트(제목·종류·날짜·까닭·출처)
            import re
            import review_sheet
            marks = set(re.findall(r"((?:thumb|cover|scenes|lines|cards|top|slides|base)[\w\[\]\.]*?\.(?:photos?|inset|logo|photo_top|photo_bottom)(?:\[\d+\])?)",
                                   " ".join(m for _, lv, m in g["findings"] if lv != "참고")))
            what = "고쳐야 나가요(차단)" if g["verdict"] == "차단" else "보고 괜찮으면 승인하면 나가요(확인 필요)"
            header = f"{r.get('title') or r['id']}\n{name} · {day} 발행 예정 · {what}\n" + "\n".join(gate.reasons(g, 5))
            out = ROOT / "dist" / f"{r['id']}-photos.jpg"
            review_sheet.spec_sheet(ROOT / "videos" / day / (r["id"][len(day) + 1:] + ".json"), out, marks, header)
            with open(out, "rb") as f:
                tg("sendPhoto", token, data={"chat_id": chat, "caption": f"사진 검수 시트 · {name} ({g['verdict']}) · 빨간 칸이 까닭이 걸린 자리"[:900]},
                   files={"photo": (out.name, f, "image/jpeg")})
        except Exception as e:
            log_error(f"review_sheet:{r['id']}", e)
        try:  # 완성된 결과물을 사람이 볼 수 있게 장면 모음 한 장(scripts/review_sheet.py --media)
            import review_sheet
            files = [ROOT / "dist" / f for f in (r.get("files") or [r["file"]])]
            out = ROOT / "dist" / f"{r['id']}-review.jpg"
            review_sheet.media_sheet([f for f in files if f.exists()], out)
            with open(out, "rb") as f:
                tg("sendPhoto", token, data={"chat_id": chat, "caption": f"검수용 장면 모음 · {r['id']} ({g['verdict']})"}, files={"photo": (out.name, f, "image/jpeg")})
        except Exception as e:
            log_error(f"review_sheet:{r['id']}", e)


def main():
    day = sys.argv[1]
    results = read_json(ROOT / "dist" / "results.json", [])
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # 보내기 전 검수: 통과(또는 사용자가 승인한 확인 필요)만 보내고, 나머지는 보류해 까닭을 state/review.json 에 적어요
    gates = gate_all(day, results)
    review = read_json(ROOT / "state" / "review.json", {}) or {}
    for rid, g in gates.items():
        old = review.get(rid) or {}
        review[rid] = {"verdict": g["verdict"], "hash": g["hash"], "approved": g.get("approved", False),
                       "reasons": gate_reasons(g), "noticed": old.get("noticed"), "held_noticed": old.get("held_noticed")}
    passed = {rid for rid, g in gates.items() if g["verdict"] == "통과"}

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
            if r["id"] not in passed:  # 보류한 것은 RSS·목록에 싣지 않아요(scripts/build_feed.py)
                entry["held"] = gates.get(r["id"], {}).get("verdict", "확인 필요")
            videos.append(entry)
    videos.sort(key=lambda v: v["id"], reverse=True)
    write_json(ROOT / "state" / "videos.json", videos[:400])

    sent = set(read_json(ROOT / "state" / "sent_videos.json", []))
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    held = [(r, gates[r["id"]]) for r in ok if r["id"] not in sent and r["id"] not in passed]
    todo = [r for r in ok if r["id"] not in sent and r["id"] in passed]  # 보류한 것은 보낸 것으로 적지 않아요(고치면 다시 검수)
    for r, g in held:
        print(f"보류: {r['id']} — {g['verdict']}")
    if not (token and chat):
        write_json(ROOT / "state" / "review.json", review)
        print("텔레그램 설정이 없어 알림은 건너뛰어요.")
        return
    try:
        hold_notice(token, chat, day, held, review)
    except Exception as e:
        log_error("telegram:hold", e)
    try:
        held_cards_notice(token, chat, day, ok, review, passed)
    except Exception as e:
        log_error("telegram:held_cards", e)
    write_json(ROOT / "state" / "review.json", review)
    if not insta_on():  # 유튜브 쇼츠만 보내요. 쇼츠가 없는(인스타 전용) 것은 보낸 것으로만 적어 둬요
        sent |= {r["id"] for r in todo if not has_youtube(r)}
        todo = [r for r in todo if has_youtube(r)]
        send_shorts_only(token, chat, day, todo, bad, sent)
        write_json(ROOT / "state" / "sent_videos.json", sorted(sent))
        print(f"보냈어요(유튜브 쇼츠만): {len(todo)}개, 실패 알림 {len(bad)}개")
        return
    if todo or bad:
        head = f"{day} 올릴 것이 준비됐어요."
        if todo:
            head += f"\n\n▶ 인스타 {len(todo)}개\n" + "\n".join(f"{n}. {label(r, 'insta')[1:-1]}" for n, r in enumerate(todo, 1))
            yt = [r for r in todo if r.get("yt_title")]
            if yt:
                head += f"\n\n▶ 유튜브 쇼츠 {len(yt)}개\n" + "\n".join(f"{n}. {label(r, 'youtube')[1:-1]}" for n, r in enumerate(yt, 1))
            head += "\n\n영상은 하나씩만 보내요. 영상 바로 아래에 인스타 글, 그다음 유튜브 제목·설명이 이어져요."
        if bad:
            head += f"\n\n실패 {len(bad)}개: " + "; ".join(f"{b['id']} ({b['error'][:80]})" for b in bad)
        mine = read_json(ROOT / "myphotos" / "index.json", []) or []
        today = plan.used_on(mine, day)
        if today:
            head += "\n\n보내 주신 " + ", ".join(f"'{e.get('note') or '이름 없음'}'" for e in today) + " 을(를) 오늘 영상에 썼어요."
        if plan.waiting(mine):
            head += "\n\n[다음 순서]\n" + "\n".join(plan.lines(mine))
        tg("sendMessage", token, data={"chat_id": chat, "text": head})
    for r in todo:  # 항목마다: 영상(또는 카드) 한 번 → 인스타 글 → 유튜브 제목·설명
        tg("sendMessage", token, data={"chat_id": chat, "text": f"━━━━ {LABELS.get(r['id'][11:], (r.get('title') or r['id'],))[0]} ━━━━"})
        text = (ROOT / "dist" / f"{r['id']}.txt").read_text(encoding="utf-8")
        tag = label(r, "insta")
        try:
            if r.get("format") == "cards":
                send_cards(token, chat, r)
                links = "\n".join(f"https://github.com/{REPO}/releases/download/v{day}/{f}" for f in r["files"])
                body = (f"{tag}\n{r.get('title')}\n위 사진 {len(r['files'])}장을 순서대로 한 게시물에 올려 주세요.\n\n"
                        f"[게시글에 넣을 글]\n{text}\n[원본 그림] 텔레그램 사진은 조금 작아져요. 또렷한 원본은 여기서 받아요\n{links}")
            else:
                with open(ROOT / "dist" / r["file"], "rb") as f:
                    tg("sendVideo", token, data={"chat_id": chat, "caption": f"{tag}\n{r.get('title') or r['id']}"[:900], "supports_streaming": "true",
                                                 "width": 1080, "height": 1920}, files={"video": (r["file"], f, "video/mp4")})
                body = f"{tag}\n{r.get('title')}\n\n{music_note(r)}[게시글에 넣을 글]\n{text}\n[내려받기]\n{r['url']}"
                if r.get("pin"):  # 올린 뒤 고정할 댓글 (2026-10-17)
                    body += f"\n\n[고정 댓글] 올린 뒤 첫 댓글로 달고 고정해 주세요\n{r['pin']}"
            if r.get("sources"):
                body += "\n\n[확인한 자료] 게시글에는 안 넣어도 돼요\n" + "\n".join(r["sources"])
            tg("sendMessage", token, data={"chat_id": chat, "text": body[:4000], "disable_web_page_preview": "true"})
            sent.add(r["id"])
        except Exception as e:
            log_error(f"telegram:{r['id']}", e)
            print(f"못 보냈어요: {r['id']} ({e})")
            continue
        try:  # 유튜브 안내가 안 가도 인스타 안내는 이미 갔으니 보낸 것으로 쳐요
            send_youtube(token, chat, r, day)
        except Exception as e:
            log_error(f"youtube:{r['id']}", e)
            print(f"유튜브 안내를 못 보냈어요: {r['id']} ({e})")
    write_json(ROOT / "state" / "sent_videos.json", sorted(sent))
    print(f"보냈어요: {len(todo)}개, 실패 알림 {len(bad)}개")


if __name__ == "__main__":
    main()
