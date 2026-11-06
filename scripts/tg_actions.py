# -*- coding: utf-8 -*-
"""텔레그램 버튼·답장을 실제 작업으로 옮겨요. scripts/fetch_photos.py 가 10분마다 받아서 불러요. (2026-11-06 사용자)
사람이 PC 앞에서 Claude 에게 "보내", "고쳐"라고 하지 않아도, 텔레그램에서 누르거나 답장하면 이어져요.

버튼(callback_data = j:할일:영상id, video/publish.py 가 붙여요)
  ok    승인: 승인 전 시안을 '올릴 것'으로. 검수 승인(차단이면 강제 통과)을 설계도에 적고, RSS·목록에 넣어요(시안은 이미 받았으니 다시 보내지 않아요)
  no    이번엔 빼기: 다시 묻지 않아요
  keep  뺀 장도 넣기: 뺀 장을 넣고 그 영상만 다시 만들어 보내요(produce 작업을 불러요)
  fine  이대로: 버튼만 치워요
  fix   고쳐서 다시: requests/fix-영상id.json 을 남겨요. 고치기 루틴이 있으면 바로, 없으면 다음 아침 매일 실행이 고쳐요
  rerun 그날 치를 못 만들었을 때 지금 다시 만들기(j:rerun:날짜). 고치기 루틴이 있으면 바로, 없으면 다음 아침
  ping / pingfix  연결 확인(buttons.yml 시험이 보내요). ping 은 아무것도 바꾸지 않고, pingfix 는 고치기 루틴만 불러 봐요
버튼은 scripts/watch_buttons.py(buttons.yml)가 알림을 보낸 뒤 3시간 동안 지켜보다가 누르면 photos 작업을 바로 불러요.
답장: 시안·뺀 장 알림 메시지에 답장하면 그 글을 고칠 점(note)으로 fix 를 해요.

깃허브 작업을 불러야 하는 일은 build/dispatch.json 에 적어 두고, photos 작업이 기록을 올린 뒤에 불러요.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
DISPATCH = ROOT / "build" / "dispatch.json"


def _read(path, default):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path, data, indent=2):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")


def spec_path(rid):
    """영상 id(2026-11-06-2-news) 또는 블로그 초안 id(blog-2026-11-06-이름)의 설계도."""
    if rid.startswith("blog-"):
        return ROOT / "blog" / (rid[5:] + ".json")
    return ROOT / "videos" / rid[:10] / (rid[11:] + ".json")


def blog_decide(rid, what):
    """블로그 초안에 대한 결정. 이 컴퓨터의 13시 발행(scripts/auto-publish.mts)이 기다리며 읽어요."""
    path = ROOT / "state" / "blog_decisions.json"
    d = _read(path, {})
    d[rid[5:]] = {"decision": what, "at": now()}
    _write(path, d)


def name_of(rid):
    if rid.startswith("blog-"):
        return "블로그 초안 " + rid[5:]
    try:  # video/publish.py 를 불러오면 requests 가 필요해서(photos 작업엔 없음) LABELS 칸만 읽어요
        import ast
        tree = ast.parse((ROOT / "video" / "publish.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "LABELS")
        return ast.literal_eval(node.value).get(rid[11:], (rid[11:],))[0]
    except Exception:
        return rid[11:]


def set_review(rid, **fields):
    """설계도의 review 칸에 적어요. 지금 내용의 지문(hash)을 같이 적어서, 내용을 고치면 승인이 풀려요(scripts/gate.py)."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import gate
    path = spec_path(rid)
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec.setdefault("review", {}).update(fields, hash=gate.content_hash(spec))
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return spec


def queue(workflow, **inputs):
    jobs = _read(DISPATCH, [])
    job = {"workflow": workflow, "inputs": inputs}
    if job in jobs:  # 같은 일은 한 번만 불러요
        return
    jobs.append(job)
    _write(DISPATCH, jobs)


def now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def close_fix(rid, why):
    """승인하거나 뺐으면 열려 있는 고치기 요청은 닫아요."""
    path = ROOT / "requests" / f"fix-{rid}.json"
    req = _read(path, None)
    if req and req.get("status") == "open":
        req.update(status=why, closed=now())
        _write(path, req)


def approve(rid):
    close_fix(rid, "approved")
    review = _read(ROOT / "state" / "review.json", {})
    r = review.get(rid) or {}
    block = r.get("verdict") == "차단"
    set_review(rid, approved=now(), note="텔레그램 승인 버튼", **({"force": True} if block else {}))
    r.update(verdict="통과", approved=True, dropped=False)
    review[rid] = r
    _write(ROOT / "state" / "review.json", review)
    if rid.startswith("blog-"):
        blog_decide(rid, "approve")
        return (f"✅ 승인했어요 · {name_of(rid)}\n컴퓨터가 기다리고 있으면(13시 발행 뒤 3시간까지) 곧 네이버에 올라가요. 아니면 다음 발행 때 올라가요."
                + ("\n(검수 '차단'이었지만 직접 고르신 대로 씁니다)" if block else ""))
    sent = set(_read(ROOT / "state" / "sent_videos.json", []))  # 시안을 이미 받았으니 다시 보내지 않아요
    _write(ROOT / "state" / "sent_videos.json", sorted(sent | {rid}))
    videos = _read(ROOT / "state" / "videos.json", [])
    for v in videos:
        if v["id"] == rid:
            v.pop("held", None)
    _write(ROOT / "state" / "videos.json", videos)
    return f"✅ 승인했어요 · {name_of(rid)}\n받은 시안 그대로 올리면 돼요. RSS·올릴 것 목록에도 넣었어요." + ("\n(검수 '차단'이었지만 직접 고르신 대로 씁니다)" if block else "")


def drop(rid):
    close_fix(rid, "dropped")
    review = _read(ROOT / "state" / "review.json", {})
    review.setdefault(rid, {})["dropped"] = now()
    _write(ROOT / "state" / "review.json", review)
    if rid.startswith("blog-"):
        blog_decide(rid, "skip")
        return f"🗑 이 블로그 초안은 올리지 않을게요 · {rid[5:]}"
    return f"🗑 이번엔 빼기로 했어요 · {name_of(rid)}\n올릴 것·RSS에 넣지 않고, 다시 묻지 않아요."


def keep_cards(rid):
    review = _read(ROOT / "state" / "review.json", {})
    held = (review.get(rid) or {}).get("held_cards") or []
    nos = sorted({h["no"] for h in held if h.get("no")})
    if not nos:
        return f"{name_of(rid)}: 뺀 장 기록이 없어서 그대로 둬요."
    set_review(rid, keep_cards=nos, approved=now(), note="텔레그램 '뺀 장도 넣기' 버튼")
    sent = set(_read(ROOT / "state" / "sent_videos.json", []))
    _write(ROOT / "state" / "sent_videos.json", sorted(sent - {rid}))
    review[rid]["held_noticed"] = None
    _write(ROOT / "state" / "review.json", review)
    queue("produce.yml", day=rid[:10], only=rid[11:])
    return f"➕ {', '.join(map(str, nos))}장을 넣어 {name_of(rid)} 을(를) 다시 만들고 있어요. 10~20분 뒤에 새로 와요."


def fix(rid, note=""):
    review = _read(ROOT / "state" / "review.json", {})
    r = review.get(rid) or {}
    old = _read(ROOT / "requests" / f"fix-{rid}.json", None)
    if old and old.get("status") == "open" and old.get("note") and note and note not in old["note"]:
        note = old["note"] + "\n" + note  # 아직 안 고친 요청에 답장을 더 하면 고칠 점을 이어 붙여요
    elif old and old.get("status") == "open" and not note:
        note = old.get("note", "")
    req = {"rid": rid, "spec": spec_path(rid).relative_to(ROOT).as_posix(), "status": "open", "at": now(),
           "reasons": r.get("reasons") or [], "held_cards": r.get("held_cards") or [], "note": note[:800]}
    _write(ROOT / "requests" / f"fix-{rid}.json", req)
    r["fix"] = now()
    review[rid] = r
    _write(ROOT / "state" / "review.json", review)
    if rid.startswith("blog-"):
        blog_decide(rid, "fix")
    else:
        sent = set(_read(ROOT / "state" / "sent_videos.json", []))  # 고친 것은 다시 보내야 해요
        _write(ROOT / "state" / "sent_videos.json", sorted(sent - {rid}))
    queue("fix", rid=rid)
    when = ("지금 고치기 시작해요. 20~40분 뒤 고친 시안이 와요." if routine_ready()
            else "지금 바로는 못 불러서 내일 아침 매일 제작 때 먼저 고쳐요. " + routine_missing())
    return f"🛠 {name_of(rid)} 고쳐서 다시 만들게요." + (f"\n반영할 점: {note[:200]}" if note else "") + f"\n{when}"


def rerun(day):
    queue("fix", rid=f"rerun:{day}")
    return (f"🔁 {day} 치를 지금 다시 만들게요. 30~60분 뒤 텔레그램으로 와요." if routine_ready()
            else f"{day} 치를 지금 바로는 만들지 못해요. 내일 아침에는 평소대로 만들어요. " + routine_missing())


def routine_ready():
    return not routine_missing()


def routine_missing():
    """고치기 루틴을 바로 못 부르는 까닭: 깃허브 작업에 안 보이는 Secret 이름(값은 적지 않아요). 다 있으면 빈 글."""
    gone = [k for k in ("FIX_ROUTINE_URL", "FIX_ROUTINE_TOKEN") if not os.environ.get(k, "").strip()]
    return (f"(깃허브 작업에 Secret {'·'.join(gone)} 이(가) 안 보여요. 저장소 Settings → Secrets and variables → Actions 의 "
            "'Repository secrets' 에 이 이름 그대로 있어야 해요)") if gone else ""


def ping(sent):
    """연결 확인 버튼(buttons.yml 시험이 보내요). 아무것도 바꾸지 않아요."""
    return (f"✅ 버튼이 이어졌어요 · 보낸 때 {sent} → 처리 {now()}\n"
            + ("고치기 루틴 바로 연결: 됨 (Secrets 있음)" if routine_ready()
               else "고치기 루틴 바로 연결: 아직 → [고쳐서 다시]는 다음 날 아침에 처리돼요 " + routine_missing()))


def ping_fix(sent):
    """고치기 루틴을 실제로 불러 봐요. 열린 요청이 없으면 루틴은 아무것도 하지 않고 끝나요."""
    if not routine_ready():
        return "고치기 루틴 바로 연결이 아직이라 부르지 않았어요. " + routine_missing()
    queue("fix", rid="ping")
    return "🛠 고치기 루틴을 불러 볼게요. 1~2분 안에 부른 결과가 와요."


ACTIONS = {"ping": ping, "pingfix": ping_fix, "rerun": rerun, "ok": approve, "no": drop, "keep": keep_cards, "fix": fix, "fine": lambda rid: f"알겠어요. {name_of(rid)} 은(는) 이대로 둘게요."}


def handle_callback(data):
    """버튼 하나를 처리하고 답할 글을 돌려줘요. 우리 버튼이 아니면 None."""
    parts = (data or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "j" or parts[1] not in ACTIONS:
        return None
    rid = parts[2]
    if parts[1] in ("rerun", "ping", "pingfix"):  # 설계도가 없는 버튼
        return ACTIONS[parts[1]](rid)
    if not spec_path(rid).exists():
        return f"설계도가 없어요: {rid}"
    return ACTIONS[parts[1]](rid)


def handle_reply(msg):
    """시안·뺀 장 알림에 단 답장이면 고칠 점으로 처리해요. 아니면 None."""
    to = (msg.get("reply_to_message") or {}).get("message_id")
    if not to or not msg.get("text"):
        return None
    review = _read(ROOT / "state" / "review.json", {})
    rid = next((k for k, v in review.items() if v.get("ask_msg") == to), None)
    if not rid:  # 기록에 없으면 답장한 봇 메시지의 버튼이나 글 속 영상 id 에서 읽어요(시험 메시지 등).
        import re  # 텔레그램은 답장에 원래 메시지의 버튼을 안 붙여 줄 때가 있어서 글도 봐요
        to_msg = msg.get("reply_to_message") or {}
        rows = (to_msg.get("reply_markup") or {}).get("inline_keyboard") or []
        rid = next((b["callback_data"][6:] for row in rows for b in row if str(b.get("callback_data", "")).startswith("j:fix:")), None)
        if not rid and (to_msg.get("from") or {}).get("is_bot"):
            m = re.search(r"\b(\d{4}-\d{2}-\d{2}-\d+-[a-z]+)\b", to_msg.get("text") or to_msg.get("caption") or "")
            rid = m.group(1) if m else None
    if not rid or not spec_path(rid).exists():
        return None
    return fix(rid, msg["text"].strip())


def fire_fix(rid):
    """고치기 루틴을 바로 불러요(FIX_ROUTINE_URL·FIX_ROUTINE_TOKEN 이 있을 때만)."""
    url, token = os.environ.get("FIX_ROUTINE_URL", "").strip(), os.environ.get("FIX_ROUTINE_TOKEN", "").strip()
    if not (url and token):
        return False
    if rid.startswith("rerun:"):
        text = f"작업: 오늘 치 만들기\n{rid[6:]} 치를 매일 실행과 똑같이 만들어 주세요."
    elif rid == "ping":
        text = "작업: 고치기\n(텔레그램 연결 확인으로 불렀어요. 열린 요청이 없으면 아무것도 바꾸지 말고 끝내요.)"
    else:
        text = f"작업: 고치기\nrequests/fix-{rid}.json 을 고쳐 주세요."
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
        "anthropic-beta": "experimental-cc-routine-2026-04-01", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        out = json.loads(res.read() or b"{}")
    return out.get("claude_code_session_url") or True


def tell(text):
    """작업 결과를 텔레그램으로 알려요(설정이 없으면 화면에만)."""
    print(text)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        try:
            from notify_telegram import api
            api(token, "sendMessage", chat_id=chat, text=text[:4000], disable_web_page_preview="true")
        except Exception as e:
            print(f"텔레그램으로 알리지 못했어요: {type(e).__name__}")


def run_dispatch():
    """photos 작업이 기록을 올린 뒤 불러요: 쌓아 둔 깃허브 작업 부르기와 고치기 루틴 부르기.
    못 부르면 조용히 넘기지 않고 텔레그램으로 알려요(고칠 요청은 남아 있어 다음 아침 매일 실행이 처리해요)."""
    import subprocess
    import urllib.error
    jobs = _read(DISPATCH, [])
    for job in jobs:
        rid = job["inputs"].get("rid", "")
        try:
            if job["workflow"] == "fix":
                fired = fire_fix(rid)
                if fired and rid == "ping":
                    tell("✅ 고치기 루틴을 불렀어요(연결 시험). 열린 요청이 없으면 루틴은 아무것도 바꾸지 않고 끝나요."
                         + (f"\n{fired}" if isinstance(fired, str) else ""))
            else:
                args = ["gh", "workflow", "run", job["workflow"], "--ref", "main"]
                for k, v in job["inputs"].items():
                    args += ["-f", f"{k}={v}"]
                subprocess.run(args, check=True)
        except Exception as e:
            why = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
            print(f"작업을 부르지 못했어요: {job} ({e})")
            if job["workflow"] == "fix":
                tell(f"⚠️ 고치기 루틴을 바로 부르지 못했어요 ({why}).\n"
                     + ("연결 시험이라 바뀐 것은 없어요." if rid == "ping" else
                        "요청은 남아 있어서 내일 아침 매일 제작 때 먼저 처리해요." if not rid.startswith("rerun:") else
                        "내일 아침에는 평소대로 만들어요.")
                     + ("\n열쇠(FIX_ROUTINE_TOKEN)가 틀렸거나 만료됐을 수 있어요. claude.ai 루틴 화면에서 새로 만들어 Secrets 에 넣으면 돼요."
                        if why in ("HTTP 401", "HTTP 403") else ""))
            else:
                tell(f"⚠️ {job['workflow']} 작업을 부르지 못했어요 ({why}). 다음 정기 실행 때 이어서 해요.")
    if DISPATCH.exists():
        DISPATCH.unlink()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["dispatch"]:
        run_dispatch()
