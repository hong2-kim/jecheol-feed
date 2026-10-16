# -*- coding: utf-8 -*-
"""유튜브 쇼츠 조회수를 하루 한 번 모아 기록하고 텔레그램으로 알려 줘요. (2026-10-16 사용자가 부탁함)
Claude 를 쓰지 않아요. 공개된 숫자(조회수·좋아요·댓글·구독자)만 YouTube Data API 로 읽어요.

  python scripts/yt_stats.py          모아서 state/yt_stats.json 에 적고 텔레그램으로 보내요
  python scripts/yt_stats.py --dry    보내지도 적지도 않고 화면에만 보여 줘요

필요한 값(환경 변수): GOOGLE_TTS_API_KEY (목소리와 같은 키. 구글 클라우드에서 YouTube Data API v3 도 허용해 둠),
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. 채널은 config.json 의 youtube.handle.
"""
import difflib
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from common import KST, ROOT, log_error, read_json, today_kst, write_json

API = "https://www.googleapis.com/youtube/v3/"
LEDGER = ROOT / "state" / "yt_stats.json"
KINDS = {"저녁": "저녁 TOP 5", "발견": "발견형", "소식": "뉴스 카드", "유행": "트렌드", "제철": "제철",
         "지역": "지역", "이야기": "이야기", "세계": "세계 축제", "해외": "해외 트렌드"}


def key():
    k = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    env = ROOT / ".env"  # 이 컴퓨터에서 돌릴 때
    if not k and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_TTS_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"')
    if not k:
        raise RuntimeError("GOOGLE_TTS_API_KEY 가 없어요.")
    return k


def get(path, **params):
    url = API + path + "?" + urllib.parse.urlencode({**params, "key": key()})
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def fetch(handle):
    ch = get("channels", part="statistics,contentDetails", forHandle=handle)["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < 200:
        page = get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50, **({"pageToken": token} if token else {}))
        ids += [x["contentDetails"]["videoId"] for x in page["items"]]
        token = page.get("nextPageToken")
        if not token:
            break
    videos = {}
    for i in range(0, len(ids), 50):
        for v in get("videos", part="snippet,statistics", id=",".join(ids[i:i + 50]))["items"]:
            s = v["statistics"]
            videos[v["id"]] = {"t": v["snippet"]["title"], "at": v["snippet"]["publishedAt"],
                               "v": int(s.get("viewCount", 0)), "l": int(s.get("likeCount", 0)), "c": int(s.get("commentCount", 0))}
    return {"subs": int(ch["statistics"].get("subscriberCount", 0)), "videos": videos}


def guess_kind(title, at, known):
    """유튜브 제목과 올린 날로 우리 영상 종류를 찾아요. 제목을 손으로 바꿔 올린 것도 비슷하면 찾아요."""
    day = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(KST).date()
    best, kind = 0.0, None
    for v in known:
        if not v.get("kind") or abs((datetime.strptime(v["date"], "%Y-%m-%d").date() - day).days) > 3:
            continue
        for name in (v.get("yt_title"), v.get("title"), v.get("summary")):
            if name:
                r = difflib.SequenceMatcher(None, title.replace(" ", ""), str(name).replace(" ", "")).ratio()
                if r > best:
                    best, kind = r, v["kind"]
    if best >= 0.35:
        return kind
    low = title.lower().replace(" ", "")
    if "top5" in low and "저녁" in low:  # 저녁top5 처럼 짧게 바꿔 올린 제목
        return "저녁"
    return None


def report(today, prev, kinds):
    e = html.escape
    vids = sorted(today["videos"].items(), key=lambda x: -x[1]["v"])
    old = (prev or {}).get("videos", {})
    total = sum(v["v"] for _, v in vids)
    lines = [f"<b>📊 유튜브 쇼츠 조회수</b> ({today['date']} 아침)"]
    sub_d = today["subs"] - prev["subs"] if prev else 0
    tot_d = total - sum(v["v"] for v in old.values()) if prev else 0
    lines.append(f"구독자 {today['subs']}명{f' ({sub_d:+d})' if prev else ''} · 전체 조회수 {total:,}{f' ({tot_d:+,})' if prev else ''}")
    lines.append("")
    for n, (vid, v) in enumerate(vids[:12], 1):
        d = f" <i>(+{v['v'] - old[vid]['v']:,})</i>" if vid in old else (" 🆕" if prev else "")
        tag = f"[{KINDS[kinds[vid]]}] " if kinds.get(vid) in KINDS else ""
        lines.append(f"{n}. {tag}{e(v['t'][:34])} — <b>{v['v']:,}</b>{d}")
    if len(vids) > 12:
        lines.append(f"…그 밖 {len(vids) - 12}개")
    groups = {}
    for vid, v in vids:
        if kinds.get(vid) in KINDS:
            groups.setdefault(KINDS[kinds[vid]], []).append(v["v"])
    if len(groups) > 1:
        avg = sorted(((sum(x) / len(x), k, len(x)) for k, x in groups.items()), reverse=True)
        lines += ["", "<b>종류별 평균</b>", " · ".join(f"{k} {a:,.0f} ({c}편)" for a, k, c in avg)]
    if prev:
        grew = sorted(((v["v"] - old[vid]["v"], v["t"]) for vid, v in vids if vid in old), reverse=True)
        if grew and grew[0][0] > 0:
            lines += ["", f"🔥 어제보다 가장 많이 늘어난 것: {e(grew[0][1][:34])} (+{grew[0][0]:,})"]
    return "\n".join(lines)


def main():
    dry = "--dry" in sys.argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    handle = (read_json(ROOT / "config.json", {}).get("youtube") or {}).get("handle", "@meokgomap")
    ledger = read_json(LEDGER, {"days": {}, "kinds": {}})
    date = today_kst()
    try:
        today = {"date": date, **fetch(handle)}
    except Exception as e:
        log_error("yt_stats", e)
        raise
    # 어제(없으면 가장 최근) 기록과 견줘요. 오늘 이미 한 번 돌았으면 그 전 기록과 견줘요.
    before = sorted(d for d in ledger["days"] if d < date)
    prev = ledger["days"][before[-1]] if before else None
    known = read_json(ROOT / "state" / "videos.json", [])
    for vid, v in today["videos"].items():
        if vid not in ledger["kinds"]:
            k = guess_kind(v["t"], v["at"], known)
            if k:
                ledger["kinds"][vid] = k
    text = report(today, prev, ledger["kinds"])
    print(text)
    if dry:
        return
    ledger["days"][date] = {"subs": today["subs"], "videos": today["videos"]}
    write_json(LEDGER, ledger)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30)
        print("텔레그램으로 보냈어요.")
    else:
        print("텔레그램 값이 없어 보내지 않았어요.")


if __name__ == "__main__":
    main()
