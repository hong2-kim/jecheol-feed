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
    import sys
    sys.path.insert(0, str(ROOT / "video"))
    try:
        from publish import LABELS
        return LABELS.get(rid[11:], (rid[11:],))[0]
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
    jobs.append({"workflow": workflow, "inputs": inputs})
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
    soon = bool(os.environ.get("FIX_ROUTINE_URL") and os.environ.get("FIX_ROUTINE_TOKEN"))
    when = "지금 고치기 시작해요. 20~40분 뒤 고친 시안이 와요." if soon else "내일 아침 매일 제작 때 먼저 고쳐서 다시 보내요."
    return f"🛠 {name_of(rid)} 고쳐서 다시 만들게요." + (f"\n반영할 점: {note[:200]}" if note else "") + f"\n{when}"


def rerun(day):
    queue("fix", rid=f"rerun:{day}")
    soon = bool(os.environ.get("FIX_ROUTINE_URL") and os.environ.get("FIX_ROUTINE_TOKEN"))
    return (f"🔁 {day} 치를 지금 다시 만들게요. 30~60분 뒤 텔레그램으로 와요." if soon
            else f"{day} 치를 지금 바로 만들려면 고치기 루틴 연결(한 번만)이 필요해요. 내일 아침에는 평소대로 만들어요.")


ACTIONS = {"rerun": rerun, "ok": approve, "no": drop, "keep": keep_cards, "fix": fix, "fine": lambda rid: f"알겠어요. {name_of(rid)} 은(는) 이대로 둘게요."}


def handle_callback(data):
    """버튼 하나를 처리하고 답할 글을 돌려줘요. 우리 버튼이 아니면 None."""
    parts = (data or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "j" or parts[1] not in ACTIONS:
        return None
    rid = parts[2]
    if parts[1] == "rerun":
        return rerun(rid)
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
    if not rid or not spec_path(rid).exists():
        return None
    return fix(rid, msg["text"].strip())


def fire_fix(rid):
    """고치기 루틴을 바로 불러요(FIX_ROUTINE_URL·FIX_ROUTINE_TOKEN 이 있을 때만)."""
    url, token = os.environ.get("FIX_ROUTINE_URL", "").strip(), os.environ.get("FIX_ROUTINE_TOKEN", "").strip()
    if not (url and token):
        return False
    text = (f"작업: 오늘 치 만들기\n{rid[6:]} 치를 매일 실행과 똑같이 만들어 주세요." if rid.startswith("rerun:")
            else f"작업: 고치기\nrequests/fix-{rid}.json 을 고쳐 주세요.")
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
        "anthropic-beta": "experimental-cc-routine-2026-04-01", "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()
    return True


def run_dispatch():
    """photos 작업이 기록을 올린 뒤 불러요: 쌓아 둔 깃허브 작업 부르기와 고치기 루틴 부르기."""
    import subprocess
    jobs = _read(DISPATCH, [])
    for job in jobs:
        try:
            if job["workflow"] == "fix":
                fire_fix(job["inputs"]["rid"])
            else:
                args = ["gh", "workflow", "run", job["workflow"], "--ref", "main"]
                for k, v in job["inputs"].items():
                    args += ["-f", f"{k}={v}"]
                subprocess.run(args, check=True)
        except Exception as e:
            print(f"작업을 부르지 못했어요: {job} ({e})")
    if DISPATCH.exists():
        DISPATCH.unlink()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["dispatch"]:
        run_dispatch()
