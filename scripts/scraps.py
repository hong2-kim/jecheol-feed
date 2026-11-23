# -*- coding: utf-8 -*-
"""사진으로 모으는 트렌드 소재 (2026-11-23 사용자: "발견하는 대로 사진만 보내고 설계도를 확인할게").

사용자가 편의점 신상·마트 먹거리·축제 포스터를 찍어 텔레그램으로 보내면
  1) photos 작업(fetch_photos.py)이 사진을 바로 보관하고 ideas/scraps.json 의 photos 에 "new" 로 적어요.
  2) Claude(고치기 루틴이 있으면 바로, 없으면 다음 아침 매일 실행)가 rules/scrap.md 대로 사진을 읽어
     소재(topics)로 등록·조사하고, 묶음·단독 쇼츠가 되면 검수용 설계도 plans/날짜-이름.json 을 만들어요.
  3) plans.yml 작업이 설계도의 썸네일 시안을 그려 텔레그램으로 보내요. [이대로 만들기]를 누르기 전에는 영상을 만들지 않아요.

  python scripts/scraps.py list                 새 사진·소재·설계도 상태 (Claude 가 처음에 봐요)
  python scripts/scraps.py check [plans/x.json]  설계도·소재 기록 검사 (파일을 안 주면 검토 중인 설계도 모두)
  python scripts/scraps.py send                  아직 안 보낸 설계도를 텔레그램으로 (plans.yml 이 불러요)

소재 기록 ideas/scraps.json
  photos: [{id, file, at, date, note, batch, status: new|read|skip|dinner, topic, why}]
  topics: [{id: "S1", name, kind, flow, read: {product|brand|event|price|place|date: {v, sure: 확인|추정}},
            keywords, photos: [id…], from: user|trend, added, status, research, covered, plan, updated}]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KST, ROOT, log_error, read_json, write_json  # noqa: E402

SCRAPS = ROOT / "ideas" / "scraps.json"
PLANS = ROOT / "plans"
SENT = ROOT / "state" / "plans_sent.json"
FIRE = ROOT / "state" / "scrap_fire.json"
BATCH_SEC = 5 * 60      # 이만큼 안에 이어 보낸 사진은 같은 소재일 수 있다고 묶어 둬요(패키지·가격표). 마지막 판단은 Claude 가 사진을 보고 해요.
SETTLE_SEC = 8 * 60     # 마지막 사진 뒤 이만큼 지나면 조사를 불러요(이어 보내는 중에 부르지 않게)
DINNER_WORDS = ("저녁", "#저녁")  # 글이 이 말로 시작하면 예전처럼 저녁 메뉴 사진으로 받아요
TOPIC_STATUS = ("new", "researched", "wait", "bundle", "solo", "planned", "made", "dropped")
PLAN_STATUS = ("review", "approved", "fix", "dropped", "made")
SURE = ("확인", "추정")


def load():
    d = read_json(SCRAPS, None) or {}
    d.setdefault("photos", [])
    d.setdefault("topics", [])
    return d


def save(d):
    write_json(SCRAPS, d)


def now_ts():
    return int(time.time())


# ── photos 작업에서 부르는 것 ─────────────────────────────────────────────

def is_dinner(note):
    return (note or "").strip().startswith(DINNER_WORDS)


def strip_dinner(note):
    """'저녁 춘천 닭갈비' → '춘천 닭갈비' (plan.py 가 첫 낱말을 음식 이름으로 봐요)."""
    note = (note or "").strip()
    for w in sorted(DINNER_WORDS, key=len, reverse=True):
        if note.startswith(w):
            return note[len(w):].lstrip(" :,·-")
    return note


def add_photo(entry):
    """보관한 사진 한 장을 새 소재 사진으로 적어요. 바로 앞 사진과 BATCH_SEC 안이면 같은 묶음(batch)이에요."""
    d = load()
    if any(p["id"] == entry["id"] for p in d["photos"]):
        return None
    last = max(d["photos"], key=lambda p: p.get("at", 0), default=None)
    at = entry.get("at", 0)
    batch = last["batch"] if last and abs(at - last.get("at", 0)) <= BATCH_SEC else f"b{at}"
    rec = {"id": entry["id"], "type": entry.get("type", "photo"), "file": entry["file"], "thumb": entry.get("thumb"),
           "at": at, "date": entry.get("date"), "note": entry.get("note", ""), "batch": batch, "status": "new", "topic": None}
    d["photos"].append({k: v for k, v in rec.items() if v is not None or k == "topic"})
    save(d)
    return rec


def set_note(photo_id, note):
    d = load()
    for p in d["photos"]:
        if p["id"] == photo_id:
            p["note"] = note
            save(d)
            return True
    return False


def to_dinner(photo_id):
    """[저녁 메뉴 사진이에요] 버튼: 소재에서 빼고 예전처럼 저녁 메뉴 영상 첫 장면에 쓰게 해요."""
    d = load()
    p = next((p for p in d["photos"] if p["id"] == photo_id), None)
    if not p:
        return False
    p["status"], p["why"] = "dinner", "사용자가 저녁 메뉴 사진이라고 함"
    for t in d["topics"]:
        if photo_id in t.get("photos", []):
            t["photos"].remove(photo_id)
            if not t["photos"] and t.get("from") == "user" and t.get("status") not in ("made",):
                t["status"], t["why"] = "dropped", "사진이 저녁 메뉴로 옮겨짐"
    save(d)
    return True


def new_photos(d=None):
    d = d or load()
    return [p for p in d["photos"] if p.get("status") == "new"]


def plan_files(status=None):
    out = []
    for path in sorted(PLANS.glob("*.json")):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if status is None or plan.get("status") in status:
            out.append((path, plan))
    return out


def work_waiting():
    """Claude 가 할 일: (새 사진 수, 만들기·고치기를 기다리는 설계도 [이름…])."""
    return len(new_photos()), [p.name for p, plan in plan_files(("approved", "fix"))]


def want_research(now=None):
    """새 사진이 다 들어온 뒤(마지막 사진에서 SETTLE_SEC 지남) 아직 조사를 부르지 않았으면 True 를 돌려주고 기록해요."""
    now = now or now_ts()
    fresh = new_photos()
    if not fresh:
        return False
    newest = max(p.get("at", 0) for p in fresh)
    fire = read_json(FIRE, {}) or {}
    if newest <= fire.get("upto", 0) or now - newest < SETTLE_SEC:
        return False
    write_json(FIRE, {"upto": newest, "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M")})
    return True


def receipt(saved_ids, routine_ok):
    """받은 사진 알림 글."""
    d = load()
    recs = [p for p in d["photos"] if p["id"] in saved_ids]
    batches = {p["batch"] for p in recs}
    lines = [f"📸 소재 사진 {len(recs)}장 받았어요" + (f" (한 번에 보낸 묶음 {len(batches)}개)" if len(recs) > 1 else "") + "."]
    lines.append("제품명·브랜드·행사명을 읽어 소재 후보로 등록하고, 출시일·판매처·일정과 지금 다룰 이유를 조사할게요.")
    lines.append("같은 제품의 패키지·가격표를 따로 보내도 한 소재로 모아요.")
    lines.append("조사는 마지막 사진 뒤 몇 분 기다렸다 바로 시작해요." if routine_ok
                 else "조사는 내일 아침 6시 매일 제작 때 해요(고치기 루틴 바로 연결이 아직이에요).")
    waiting = sum(1 for t in d["topics"] if t.get("from") == "user" and t.get("status") in ("researched", "wait", "bundle"))
    if waiting:
        lines.append(f"지금 쌓인 내가 보낸 소재: {waiting}개 (3개가 모이면 묶음 쇼츠 설계도를 보내요).")
    lines.append("저녁 메뉴로 쓸 사진이면 아래 버튼을 눌러 주세요. 글을 '저녁'으로 시작해 보내도 돼요.")
    return "\n".join(lines)


# ── 검사 ────────────────────────────────────────────────────────────────

def _thumb():
    sys.path.insert(0, str(ROOT / "video"))
    import thumb
    return thumb


def topic_problems(d=None):
    d = d or load()
    out = []
    ids = {t["id"] for t in d["topics"]}
    for p in d["photos"]:
        if p.get("status") == "read" and p.get("topic") not in ids:
            out.append(f"사진 {p['id']}: status read 인데 topic({p.get('topic')})이 소재 목록에 없어요.")
        if p.get("status") == "skip" and not p.get("why"):
            out.append(f"사진 {p['id']}: 소재로 쓰지 않는 까닭(why)을 적어 주세요.")
    for t in d["topics"]:
        tid = t.get("id", "?")
        if t.get("status") not in TOPIC_STATUS:
            out.append(f"소재 {tid}: status 는 {'/'.join(TOPIC_STATUS)} 가운데 하나예요.")
        if not t.get("name"):
            out.append(f"소재 {tid}: name 이 없어요.")
        for k, v in (t.get("read") or {}).items():
            if not isinstance(v, dict) or v.get("sure") not in SURE:
                out.append(f"소재 {tid}: read.{k} 에 sure(확인/추정)를 적어 주세요. 사진·자료로 확인 못 한 것은 '추정'이에요.")
        if t.get("from") == "user" and not t.get("photos"):
            if t.get("status") != "dropped":
                out.append(f"소재 {tid}: 사용자가 보낸 소재인데 사진이 없어요.")
        if t.get("status") in ("researched", "wait", "bundle", "solo", "planned"):
            r = t.get("research") or {}
            if not r.get("why_now"):
                out.append(f"소재 {tid}: research.why_now(지금 다룰 이유)가 없어요. 못 찾았으면 '못 찾음: 까닭'으로 적어요.")
            if not r.get("sources"):
                out.append(f"소재 {tid}: research.sources(기사·공식 발표·후기 주소)가 없어요.")
            if not r.get("checked"):
                out.append(f"소재 {tid}: research.checked(조사한 날)가 없어요.")
    return out


def plan_problems(plan):
    out = []
    pid = plan.get("id", "?")
    need = ["id", "type", "status", "topics", "why_now", "title", "thumb", "hook", "scenes", "need", "sources"]
    for k in need:
        if k not in plan or plan[k] in ("", None):
            out.append(f"{pid}: {k} 칸이 없어요.")
    import re
    if not re.fullmatch(r"[a-z0-9-]{1,40}", str(plan.get("id") or "")):
        out.append(f"{pid}: id 는 영어 소문자·숫자·하이픈만, 40자 안이에요(텔레그램 버튼에 들어가요).")
    if plan.get("type") not in ("bundle", "solo"):
        out.append(f"{pid}: type 은 bundle(묶음) 또는 solo(단독)예요.")
    if plan.get("status") not in PLAN_STATUS:
        out.append(f"{pid}: status 는 {'/'.join(PLAN_STATUS)} 가운데 하나예요.")
    topics = plan.get("topics") or []
    if plan.get("type") == "bundle" and len(topics) != 3:
        out.append(f"{pid}: 묶음 쇼츠는 소재 3개예요(지금 {len(topics)}개).")
    if plan.get("type") == "solo" and len(topics) != 1:
        out.append(f"{pid}: 단독 쇼츠는 소재 1개예요.")
    known = {t["id"]: t for t in load()["topics"]}
    for tid in topics:
        if tid not in known:
            out.append(f"{pid}: 소재 {tid} 가 ideas/scraps.json 에 없어요.")
    t = plan.get("thumb") or {}
    th = _thumb()
    out += [f"{pid}: {x}" for x in th.problems(t.get("head"), "썸네일 큰 문구") + th.next_problems(t)]
    if not t.get("photo"):
        out.append(f"{pid}: thumb.photo(썸네일 메인 사진)가 없어요.")
    if plan.get("type") == "bundle":
        if len(t.get("next") or []) != 2:
            out.append(f'{pid}: 묶음 썸네일은 thumb.next 에 나머지 두 주제 이름을 적어요. 예: ["두바이 초콜릿", "군고구마빵"]')
        it = plan.get("interest") or {}
        if plan.get("from_user"):
            for k in ("period", "rows", "pick", "basis"):
                if not it.get(k):
                    out.append(f"{pid}: 내가 보낸 3개 묶음은 관심도 비교 interest.{k} 가 있어야 해요.")
            if it.get("rows") and len(it["rows"]) != 3:
                out.append(f"{pid}: interest.rows 는 세 주제 모두 적어요.")
            if it.get("pick") and it["pick"] != (plan.get("main") or (topics[:1] or [None])[0]):
                out.append(f"{pid}: 관심도가 가장 높은 주제(interest.pick)가 썸네일 메인(main)이어야 해요.")
    hook = plan.get("hook") or {}
    if isinstance(hook, dict) and not (hook.get("say") or hook.get("show")):
        out.append(f"{pid}: hook(첫 5초)에 say(말)나 show(화면)를 적어 주세요.")
    if len(plan.get("scenes") or []) < 3:
        out.append(f"{pid}: scenes(영상 구성)는 3장면 이상이에요.")
    srcs = plan.get("sources") or []
    if len([s for s in srcs if isinstance(s, dict) and s.get("url")]) < 2:
        out.append(f"{pid}: sources 에 근거 주소가 2개 이상 있어야 해요({{title, url, date}}).")
    for r in plan.get("photos_review") or []:
        if r.get("face") is not False and r.get("use") != "no":
            out.append(f"{pid}: 사진 {r.get('id')} — 얼굴이 보이지 않는지(face: false) 확인해 적어 주세요. 보이면 use: no.")
        if r.get("use") != "no" and (not r.get("shows") or not r.get("match")):
            out.append(f"{pid}: 사진 {r.get('id')} — shows(실제로 보이는 것)·match(같은 상품/같은 종류/다름)를 적어 주세요.")
    used_user = {p for p in (plan.get("user_photos") or [])}
    reviewed = {r.get("id") for r in plan.get("photos_review") or []}
    for p in used_user - reviewed:
        out.append(f"{pid}: 내가 보낸 사진 {p} 을(를) 쓰는데 photos_review 가 없어요(사진 검수 기준).")
    return out


# ── 텔레그램으로 설계도 보내기 (plans.yml) ─────────────────────────────────

def plan_text(plan):
    """설계도를 휴대폰에서 읽기 좋은 글로."""
    known = {t["id"]: t for t in load()["topics"]}
    names = [known.get(t, {}).get("name", t) for t in plan.get("topics") or []]
    t = plan.get("thumb") or {}
    kind = "묶음 쇼츠" + (" (내가 보낸 3개)" if plan.get("from_user") else "") if plan.get("type") == "bundle" else "단독 쇼츠"
    hook = plan.get("hook") or {}
    lines = [f"📝 설계도 확인 · {kind}", f"주제: {' / '.join(names)}", "",
             f"■ 제목: {plan.get('title', '')}",
             f"■ 왜 지금: {plan.get('why_now', '')}",
             f"■ 썸네일 큰 문구: {(t.get('head') or '').replace(chr(10), ' / ').replace('[[', '').replace(']]', '')}"]
    if t.get("next"):
        lines.append(f"■ 썸네일 보조 문구: 뒤에 {'·'.join(t['next'])}도!")
    lines.append(f"■ 첫 5초: {hook.get('say', '') if isinstance(hook, dict) else hook}"
                 + (f" (화면: {hook['show']})" if isinstance(hook, dict) and hook.get("show") else ""))
    lines.append("■ 구성")
    for k, s in enumerate(plan.get("scenes") or [], 1):
        if isinstance(s, dict):
            lines.append(f" {k}) {s.get('t', '')} {s.get('show', '')}" + (f" — \"{s['say']}\"" if s.get("say") else ""))
        else:
            lines.append(f" {k}) {s}")
    it = plan.get("interest") or {}
    if it:
        lines.append(f"■ 관심도 비교 ({it.get('period', '')}): {it.get('basis', '')}")
        for r in it.get("rows") or []:
            lines.append(" · " + r.get("name", r.get("topic", "")) + ": " + ", ".join(f"{k} {v}" for k, v in r.items() if k not in ("name", "topic")))
    if plan.get("need"):
        lines.append("■ 더 확보할 사진·영상")
        lines += [f" · {n}" for n in plan["need"]]
    unsure = plan.get("unsure") or []
    if unsure:
        lines.append("■ 추정(확인 못 함)")
        lines += [f" · {u}" for u in unsure]
    lines.append("■ 근거")
    for k, s in enumerate(plan.get("sources") or [], 1):
        if isinstance(s, dict):
            lines.append(f" {k}. {s.get('title', '')}" + (f" ({s['date']})" if s.get("date") else "") + f"\n    {s.get('url', '')}")
    lines += ["", f"[{plan.get('id')}] 이 메시지에 답장하면 고칠 점으로 받아요. 버튼을 누르기 전에는 영상을 만들지 않아요."]
    return "\n".join(lines)


def buttons(pid):
    return json.dumps({"inline_keyboard": [[{"text": "✅ 이대로 만들기", "callback_data": f"j:pgo:{pid}"[:64]}],
                                           [{"text": "✏️ 고쳐서 다시", "callback_data": f"j:pfix:{pid}"[:64]},
                                            {"text": "🗑 안 만들기", "callback_data": f"j:pno:{pid}"[:64]}]]}, ensure_ascii=False)


def render_thumb(plan, out):
    """설계도의 thumb 으로 썸네일 시안을 그려요(영상과 같은 thumb.py). 못 그리면 None."""
    th = _thumb()
    from playwright.sync_api import sync_playwright
    html = ROOT / "build" / f"plan-{plan['id']}-thumb.html"
    html.parent.mkdir(parents=True, exist_ok=True)
    html.write_text(th.page({"thumb": plan["thumb"]}), encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page(viewport={"width": 1080, "height": 1920})
            pg.goto(html.as_uri())
            pg.evaluate("document.fonts.ready")
            pg.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth > 0)", timeout=30000)
            pg.screenshot(path=str(out), type="jpeg", quality=90)
        finally:
            b.close()
    return out


def send():
    import requests
    from common import note_buttons
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("텔레그램 설정이 없어 설계도를 보내지 않아요.")
        return
    sent = read_json(SENT, {}) or {}

    def tg(method, data, files=None):
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files, timeout=60)
        r.raise_for_status()
        return r.json()["result"]

    notice = topic_notice(sent)
    if notice:
        try:
            tg("sendMessage", {"chat_id": chat, "text": notice[0][:4000], "disable_web_page_preview": "true"})
            sent.update(notice[1])
            write_json(SENT, sent)
        except Exception as e:
            log_error("scraps:notice", f"{type(e).__name__}: {e}")
    for path, plan in plan_files(("review",)):
        pid = plan.get("id") or path.stem
        stamp = plan.get("updated") or plan.get("made_at") or ""
        if sent.get(pid, {}).get("stamp") == stamp:
            continue
        probs = plan_problems(plan)
        try:
            shot = ROOT / "build" / f"plan-{pid}-thumb.jpg"
            try:
                render_thumb(plan, shot)
                with open(shot, "rb") as f:
                    tg("sendPhoto", {"chat_id": chat, "caption": f"썸네일 시안 · {plan.get('title', '')}"[:900]}, {"photo": (shot.name, f, "image/jpeg")})
            except Exception as e:
                log_error("scraps:thumb", f"{pid}: {type(e).__name__}: {e}")
                print(f"썸네일 시안을 못 그렸어요: {pid} — {e}")
            text = plan_text(plan)
            if probs:
                text += "\n\n⚠️ 자동 검사에서 걸린 것 (만들기 전에 고쳐요)\n" + "\n".join("· " + x for x in probs[:6])
            msg = None
            chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)]
            for k, chunk in enumerate(chunks):
                data = {"chat_id": chat, "text": chunk, "disable_web_page_preview": "true"}
                if k == len(chunks) - 1:
                    data["reply_markup"] = buttons(pid)
                    note_buttons(data["reply_markup"])
                msg = tg("sendMessage", data)
            sent[pid] = {"stamp": stamp, "msg": msg and msg.get("message_id"), "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "path": path.relative_to(ROOT).as_posix()}
            write_json(SENT, sent)
            print(f"설계도를 보냈어요: {pid}")
        except Exception as e:
            log_error("scraps:send", f"{pid}: {type(e).__name__}: {e}")
            print(f"설계도를 보내지 못했어요: {pid} — {e}")


STATUS_WORD = {"new": "읽는 중", "researched": "조사 끝", "wait": "묶음 기다림", "bundle": "묶음 기다림", "solo": "단독 후보",
               "planned": "설계도 보냄", "made": "만듦", "dropped": "안 씀"}


def topic_notice(sent):
    """사용자가 보낸 소재 가운데 새로 등록·조사된 것을 한 번에 알려요. (글, 보낸 표시) 또는 None."""
    d = load()
    fresh = [t for t in d["topics"] if t.get("from") == "user" and t.get("status") != "new"
             and sent.get(f"topic:{t['id']}", {}).get("stamp") != t.get("updated")]
    skipped = [p for p in d["photos"] if p.get("status") == "skip" and not sent.get(f"photo:{p['id']}")]
    if not fresh and not skipped:
        return None
    lines = ["🗂 사진 소재 등록·조사 결과"]
    for t in fresh:
        read = t.get("read") or {}
        ok = [f"{k_name(k)} {v.get('v')}" for k, v in read.items() if isinstance(v, dict) and v.get("sure") == "확인"]
        guess = [f"{k_name(k)} {v.get('v')}" for k, v in read.items() if isinstance(v, dict) and v.get("sure") == "추정"]
        r = t.get("research") or {}
        lines += ["", f"■ {t['id']} {t.get('name')} ({t.get('kind', '')}" + (f" · 흐름 {t['flow']}" if t.get("flow") else "") + f") · 사진 {len(t.get('photos') or [])}장"]
        if ok:
            lines.append("  확인: " + ", ".join(ok))
        if guess:
            lines.append("  추정: " + ", ".join(guess))
        if t.get("keywords"):
            lines.append("  키워드: " + ", ".join(t["keywords"][:6]))
        if r.get("why_now"):
            lines.append("  지금 다룰 이유: " + r["why_now"][:200])
        if t.get("covered"):
            lines.append(f"  전에 다룸 → 새 정보: {t['covered'].get('new', '')}")
        lines.append("  상태: " + STATUS_WORD.get(t.get("status"), t.get("status", "")) + (f" ({t['why']})" if t.get("why") else ""))
    for p in skipped:
        lines.append(f"\n· 사진 {p['id']}: 소재로 안 씀 — {p.get('why', '')}")
    waiting = [t for t in d["topics"] if t.get("from") == "user" and t.get("status") in ("researched", "wait", "bundle") and not t.get("plan")]
    lines.append(f"\n내가 보낸 소재 중 묶음 기다리는 것: {len(waiting)}개" + (" (3개가 모이면 묶음 쇼츠 설계도를 보내요)" if len(waiting) < 3 else ""))
    mark = {f"topic:{t['id']}": {"stamp": t.get("updated")} for t in fresh}
    mark.update({f"photo:{p['id']}": {"stamp": "skip"} for p in skipped})
    return "\n".join(lines), mark


def k_name(k):
    return {"product": "제품명", "brand": "브랜드", "event": "행사", "price": "가격", "place": "장소", "date": "날짜"}.get(k, k)


def plan_by_msg(msg_id):
    for pid, v in (read_json(SENT, {}) or {}).items():
        if v.get("msg") == msg_id:
            return pid
    return None


def plan_path(pid):
    v = (read_json(SENT, {}) or {}).get(pid) or {}
    if v.get("path") and (ROOT / v["path"]).exists():
        return ROOT / v["path"]
    for path, plan in plan_files():
        if plan.get("id") == pid or path.stem == pid:
            return path
    return None


# ── Claude 가 보는 목록 ──────────────────────────────────────────────────

def listing():
    d = load()
    fresh = new_photos(d)
    print(f"새 사진 {len(fresh)}장 (status new)")
    for b in sorted({p['batch'] for p in fresh}):
        group = [p for p in fresh if p["batch"] == b]
        print(f"  묶음 {b} — {len(group)}장 (이어 보낸 사진: 같은 상품의 패키지·가격표일 수 있어요)")
        for p in group:
            when = datetime.fromtimestamp(p.get("at", 0), KST).strftime("%m-%d %H:%M")
            print(f"    · {p['id']} {when} 글: {p.get('note') or '(없음)'}\n      {p.get('thumb') or p['file']}")
    act = [t for t in d["topics"] if t.get("status") not in ("made", "dropped")]
    print(f"\n진행 중인 소재 {len(act)}개")
    for t in act:
        print(f"  · {t['id']} [{t.get('status')}] {t.get('name')} · 흐름 {t.get('flow', '-')} · {t.get('from')} · 사진 {len(t.get('photos') or [])}장"
              + (f" · 조사 {t['research'].get('checked')}" if t.get("research") else ""))
    user_ready = [t for t in act if t.get("from") == "user" and t.get("status") in ("researched", "wait", "bundle") and not t.get("plan")]
    if len(user_ready) >= 3:
        print(f"\n→ 내가 보낸 소재가 {len(user_ready)}개 모였어요. 먼저 받은 3개로 묶음 쇼츠 설계도를 만들어요(rules/scrap.md 4).")
    for path, plan in plan_files(("review", "approved", "fix")):
        print(f"\n설계도 {path.name}: {plan.get('status')}" + (f" · 고칠 점: {plan.get('fix_note')}" if plan.get("fix_note") else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "check", "send"])
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if a.cmd == "list":
        listing()
    elif a.cmd == "send":
        send()
    else:
        probs = topic_problems()
        targets = [(Path(f), json.loads(Path(f).read_text(encoding="utf-8"))) for f in a.files] or plan_files(("review",))
        for path, plan in targets:
            probs += plan_problems(plan)
        for p in probs:
            print("꼭 고쳐 주세요: " + p)
        print(f"소재·설계도 검사: {'통과' if not probs else f'{len(probs)}건'}")
        sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
