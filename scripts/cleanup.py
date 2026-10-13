# -*- coding: utf-8 -*-
"""인스타그램에 올린 영상을 표시하고, 7일 뒤 파일을 지워 저장 공간을 비워요.

텔레그램 봇 대화방에서 이렇게 써요. (정해 둔 사람이 보낸 말만 들어요)
  올렸어            봇이 보낸 영상 가운데 아직 표시 안 한 것을 모두 '올림'으로 표시
  올렸어 1 3        번호를 골라 표시 (번호는 "올릴 것" 이라고 보내면 알려 줘요)
  안올렸어 2        잘못 표시한 것을 되돌리기
  올릴 것           아직 올렸다고 표시하지 않은 영상 목록
  일정              보낸 사진·동영상을 어느 날짜에 쓸지 보기
  삭제 목록         지울 수 있는 파일 목록 다시 보기
  삭제 확인         마지막으로 보여 준 목록을 실제로 지우기
  삭제 취소         이번 목록은 지우지 않기 (7일 뒤 다시 물어봐요)

지우는 것: 올린 지 7일이 지난 완성 영상(릴리스 v날짜)과, 그 영상에만 쓰인 보낸 원본(릴리스 myphotos).
지우지 않는 것: 인스타그램 게시물, 올렸다고 표시하지 않은 영상, 저장소 안의 기록.
남기는 기록: state/posted.json (올린 영상의 이름·주제·지문·쓴 원본). 파일을 지운 뒤에도 남아서 같은 것이 다시 만들어지거나 쓰이지 않아요.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta

import plan
from common import KST, ROOT, log_error, read_json, today_kst, write_json

REPO = os.environ.get("GITHUB_REPOSITORY", "hong2-kim/jecheol-feed")
KEEP_DAYS = 7
VIDEOS = ROOT / "state" / "videos.json"
LEDGER = ROOT / "state" / "posted.json"
STATE = ROOT / "state" / "cleanup.json"
INDEX = ROOT / "myphotos" / "index.json"
MARK = "/releases/download/myphotos/"


def gh(method, path):
    """깃허브에 요청해요. 지울 때는 GITHUB_TOKEN 이 있어야 해요."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jecheol-feed"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=40) as res:
        body = res.read()
    return json.loads(body) if body else None


def assets(tag):
    """릴리스에 있는 파일들. {이름: (번호, 크기)}"""
    try:
        return {a["name"]: (a["id"], a["size"]) for a in gh("GET", f"/releases/tags/{tag}")["assets"]}
    except Exception:
        return {}


def delete_asset(asset_id):
    gh("DELETE", f"/releases/assets/{asset_id}")


def day(text):
    return datetime.strptime(text, "%Y-%m-%d").date()


def originals_of(video_id):
    """그 영상의 설계도를 읽어 (주제, 쓴 원본 이름들)을 돌려줘요."""
    path = ROOT / "videos" / video_id[:10] / f"{video_id[11:]}.json"
    spec = read_json(path, {}) or {}
    found = []
    for scene in (spec.get("scenes") or []) + (spec.get("cards") or []):  # 카드 뉴스는 cards 에 사진이 있어요
        for key in ("photo", "photo_top", "photo_bottom", "video"):
            value = scene.get(key)
            url = value.get("url") if isinstance(value, dict) else value
            if isinstance(url, str) and MARK in url:
                found.append(url.split(MARK, 1)[1])
    return spec.get("subject"), sorted(set(found))


def waiting(videos):
    return sorted((v for v in videos if not v.get("posted") and not v.get("deleted")), key=lambda v: v["id"])


def numbered(items):
    return [f"{n}. {v.get('title') or v['id']} ({v['date']})" for n, v in enumerate(items, 1)]


def picks(text, count):
    nums = [int(n) for n in re.findall(r"\d+", text)]
    return [n for n in nums if 1 <= n <= count]


def to_post():
    items = waiting(read_json(VIDEOS, []) or [])
    if not items:
        return ["아직 올렸다고 표시하지 않은 영상이 없어요."]
    return ["아직 올렸다고 표시하지 않은 영상이에요.", *numbered(items), "", "다 올렸으면 `올렸어`, 일부만 올렸으면 `올렸어 1 3` 처럼 보내 주세요."]


def mark(text):
    videos = read_json(VIDEOS, []) or []
    items = waiting(videos)
    if not items:
        return ["올렸다고 표시할 영상이 없어요. 이미 모두 표시돼 있어요."]
    chosen = [items[n - 1] for n in picks(text, len(items))] or items
    ledger = read_json(LEDGER, []) or []
    today = today_kst()
    for v in chosen:
        v["posted"] = today
        subject, originals = originals_of(v["id"])
        ledger = [e for e in ledger if e["id"] != v["id"]]
        ledger.append({"id": v["id"], "title": v.get("title"), "subject": subject, "made": v["date"], "posted": today,
                       "file": (v.get("files") or [f"{v['id']}.mp4"])[0], "sha256": v.get("sha256"), "originals": originals})
    write_json(VIDEOS, videos)
    write_json(LEDGER, sorted(ledger, key=lambda e: e["id"]))
    state = read_json(STATE, {}) or {}
    state["last_marked"] = [v["id"] for v in chosen]
    write_json(STATE, state)
    when = (day(today) + timedelta(days=KEEP_DAYS)).strftime("%m월 %d일")
    return [f"{len(chosen)}개를 '인스타에 올림'으로 표시했어요.", *numbered(chosen), "",
            f"{KEEP_DAYS}일 뒤({when})에 지울 파일 목록을 보내 드려요. 확인하시기 전에는 아무것도 지우지 않아요.",
            "잘못 표시했으면 `안올렸어 번호` 로 되돌릴 수 있어요."]


def unmark(text):
    state = read_json(STATE, {}) or {}
    last = state.get("last_marked") or []
    videos = read_json(VIDEOS, []) or []
    by_id = {v["id"]: v for v in videos}
    chosen = [last[n - 1] for n in picks(text, len(last))]
    if not chosen:
        return ["되돌릴 번호를 같이 보내 주세요. 예: `안올렸어 2`", *numbered([by_id[i] for i in last if i in by_id])]
    done = []
    for vid in chosen:
        v = by_id.get(vid)
        if v and v.get("posted") and not v.get("deleted"):
            v.pop("posted")
            done.append(v)
    write_json(VIDEOS, videos)
    write_json(LEDGER, [e for e in (read_json(LEDGER, []) or []) if e["id"] not in {v["id"] for v in done} or e.get("deleted")])
    return [f"{len(done)}개를 '아직 안 올림'으로 되돌렸어요.", *numbered(done)]


def eligible():
    """지울 수 있는 파일. 올린 지 7일이 지난 완성 영상과, 그 영상들에만 쓰인 보낸 원본."""
    today = day(today_kst())
    videos = read_json(VIDEOS, []) or []
    old = {v["id"] for v in videos if v.get("posted") and day(v["posted"]) + timedelta(days=KEEP_DAYS) <= today}
    files, cache = [], {}

    def add(kind, tag, name, ref):
        if tag not in cache:
            cache[tag] = assets(tag)
        if name in cache[tag]:
            files.append({"kind": kind, "tag": tag, "name": name, "asset": cache[tag][name][0], "bytes": cache[tag][name][1], "ref": ref})

    for v in videos:
        if v["id"] in old and not v.get("deleted"):
            for name in v.get("files") or [f"{v['id']}.mp4"]:  # 카드 뉴스는 그림 여러 장
                add("완성 영상", "v" + v["date"], name, v["id"])
    for e in read_json(INDEX, []) or []:
        used = [u.replace("/", "-", 1) for u in e.get("used") or []]
        if used and not e.get("deleted") and all(u in old for u in used):
            add("보낸 원본", "myphotos", e["id"], e["id"])
            if e.get("thumb"):
                add("보낸 원본", "myphotos", e["id"] + ".thumb.jpg", e["id"])
    return files


def listing(files):
    total = sum(f["bytes"] for f in files) / 1e6
    lines = [f"지울 수 있는 파일 {len(files)}개 ({total:.1f}MB)예요. 인스타에 올린 지 {KEEP_DAYS}일이 지난 것만 골랐어요.", ""]
    for kind in ("완성 영상", "보낸 원본"):
        group = [f for f in files if f["kind"] == kind]
        if group:
            lines.append(f"[{kind}] 깃허브 보관함")
            lines += [f"· {f['name']} ({f['bytes'] / 1e6:.1f}MB)" for f in group]
    lines += ["", "지우려면 `삭제 확인`, 이번엔 두려면 `삭제 취소` 라고 보내 주세요.",
              "답이 없으면 아무것도 지우지 않아요. 인스타그램 게시물은 건드리지 않고, 다시 쓰지 않도록 기록은 남겨요."]
    return lines


def propose(force=False):
    """지울 것이 새로 생겼으면 목록을 만들어 돌려줘요. 같은 목록을 되풀이해 보내지는 않아요."""
    state = read_json(STATE, {}) or {}
    if not force and state.get("snooze") and day(state["snooze"]) > day(today_kst()):
        return []
    files = eligible()
    names = sorted(f["name"] for f in files)
    if not files:
        return ["지금 지울 수 있는 파일이 없어요."] if force else []
    if not force and names == sorted(f["name"] for f in state.get("pending") or []):
        return []
    state.update({"pending": files, "shown": today_kst()})
    state.pop("snooze", None)
    write_json(STATE, state)
    return listing(files)


def confirm():
    state = read_json(STATE, {}) or {}
    files = state.get("pending") or []
    if not files:
        return ["확인할 삭제 목록이 없어요. `삭제 목록` 이라고 보내면 지금 지울 수 있는 것을 알려 드려요."]
    if not os.environ.get("GITHUB_TOKEN", "").strip():
        return ["지금은 지울 수 없어요. (깃허브 권한이 없어요) 아무것도 지우지 않았어요."]
    done, failed = [], []
    for f in files:
        try:
            delete_asset(f["asset"])
            done.append(f)
        except Exception as e:
            log_error("cleanup:delete", f"{f['name']}: {type(e).__name__}")
            failed.append(f)
    today = today_kst()
    gone = {f["ref"] for f in done}
    videos = read_json(VIDEOS, []) or []
    for v in videos:
        if v["id"] in gone:
            v["deleted"] = today
    write_json(VIDEOS, videos)
    index = read_json(INDEX, []) or []
    for e in index:
        if e["id"] in gone:
            e["deleted"] = today
    write_json(INDEX, index)
    ledger = read_json(LEDGER, []) or []
    for e in ledger:
        if e["id"] in gone:
            e["deleted"] = today
    write_json(LEDGER, ledger)
    state["pending"] = failed
    write_json(STATE, state)
    lines = [f"{len(done)}개를 지웠어요. ({sum(f['bytes'] for f in done) / 1e6:.1f}MB)", *[f"· {f['name']}" for f in done]]
    if failed:
        lines += ["", f"{len(failed)}개는 지우지 못했어요. 다음에 `삭제 확인` 을 다시 보내면 또 시도해요.", *[f"· {f['name']}" for f in failed]]
    lines += ["", "인스타그램 게시물은 그대로예요. 같은 것이 다시 쓰이지 않도록 기록은 남겨 뒀어요."]
    return lines


def cancel():
    state = read_json(STATE, {}) or {}
    state["pending"] = []
    state["snooze"] = (day(today_kst()) + timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    write_json(STATE, state)
    return [f"알겠어요. 아무것도 지우지 않았어요. {KEEP_DAYS}일 뒤에 다시 여쭤볼게요."]


def handle(text):
    """봇 대화방에 온 말 한 줄을 처리해요. 모르는 말이면 None."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    bare = t.replace(" ", "")
    if bare.startswith("삭제확인"):
        return confirm()
    if bare.startswith("삭제취소"):
        return cancel()
    if bare.startswith("삭제목록"):
        return propose(force=True)
    if bare.startswith("안올렸어"):
        return unmark(t)
    if bare.startswith("올렸어"):
        return mark(t)
    if bare.startswith("일정") or bare.startswith("순서"):
        return plan.lines(read_json(INDEX, []) or [])
    if bare.startswith("올릴것"):
        return to_post()
    if bare in ("도움말", "사용법", "/help", "/start"):
        return ["이렇게 보내면 돼요.", "· 사진이나 동영상 + 음식 이름: 다음 영상에 써요", "· 올렸어: 인스타에 올린 영상 표시", "· 올릴 것: 아직 안 올린 영상 보기", "· 일정: 보낸 사진·동영상을 언제 쓸지 보기",
                "· 삭제 목록: 지울 수 있는 파일 보기", "· 삭제 확인 / 삭제 취소"]
    return None
