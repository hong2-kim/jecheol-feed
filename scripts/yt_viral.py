# -*- coding: utf-8 -*-
"""요즘 터진 먹거리 쇼츠를 '그 채널 평소보다 몇 배'로 찾아 텔레그램으로 알려 줘요. (2026-11-09 사용자가 부탁함)
Claude 를 쓰지 않아요. 공개된 숫자만 YouTube Data API 로 읽어요(로그인하지 않아요).

  python scripts/yt_viral.py          찾아서 state/yt_viral.json 에 적고 텔레그램으로 보내요
  python scripts/yt_viral.py --dry    보내지도 적지도 않고 화면에만 보여 줘요

왜 '몇 배'인가: 조회수 크기로 줄 세우면 큰 채널만 올라와요. 구독자 200만 채널의 40만 회는 평소 일이고,
평소 3만 회 나오던 채널의 40만 회가 볼 만한 소재예요. 그래서 영상마다 '그 채널 최근 쇼츠 조회수 중앙값'의 몇 배인지 봐요.
(생각은 공개 저장소 Jakeschincariol/youtube-agent-skill 의 yt-viral 에서 가져왔고, 한국어 제목에 맞게 새로 만들었어요.)

어떻게 찾나
1. config.json youtube.viral.queries 낱말마다 최근 hours 시간 안에 올라온 한국 쇼츠를 조회수 순으로 찾아요(검색 1번 = 할당량 100).
2. 찾은 영상의 채널마다 최근 올린 영상 50개를 읽어, hours 보다 오래된 쇼츠(3분 이하)로 중앙값을 내요.
   쇼츠가 4개 안 되면 중앙값이 뜻이 없어서 빼요.
3. 배수가 min_multiple 이상이고 조회수가 min_views 이상인 것만 남기고, 지난 2일 동안 이미 보낸 영상은 빼요.
4. 제목 꼴(숫자·가격·질문·비교 …)은 제목 글자만 보고 나눈 것이에요. 터진 이유라고 단정하지 않아요.

할당량: 하루 1만 중 약 1,200 정도(검색 9번 + 채널 목록). yt_stats.py 와 같은 키(GOOGLE_TTS_API_KEY)를 써요.
"""
import html
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from common import KST, ROOT, log_error, read_json, today_kst, write_json

API = "https://www.googleapis.com/youtube/v3/"
LEDGER = ROOT / "state" / "yt_viral.json"
DEFAULTS = {
    # 우리 쇼츠 주제(편의점 신상·국내외 비교·여행 먹거리·생활 정보·건강식)에 맞춘 낱말. 낱말마다 따로 1·2등을 뽑아요.
    # 한 줄로 줄 세우면 시니어 살림 꿀팁 채널이 다 차지해요(11-09 시험). 낱말 하나 = 할당량 100.
    "queries": ["편의점 신상", "먹방 쇼츠", "음식 꿀팁", "제철 음식", "요즘 유행 음식", "해외 음식", "디저트 신상",
                "여행 먹거리", "다이어트 음식"],
    "per_query": 2,       # 낱말마다 몇 개까지
    "hours": 72,          # 최근 몇 시간 안에 올라온 것
    "min_multiple": 2.0,  # 채널 평소의 몇 배 이상(갓 올린 영상은 조회수가 덜 쌓여 배수가 낮게 나와요)
    "min_views": 10000,   # 너무 작은 숫자는 우연일 수 있어요
    "top": 10,            # 텔레그램에 보여 줄 수
    "max_channels": 120,  # 채널을 너무 많이 읽지 않게(채널 하나 = 할당량 약 2)
    "min_median": 1000,   # 평소 조회수가 이보다 작은 채널은 배수가 쉽게 튀어요
    "min_subs": 5000,     # 구독자가 너무 적은 채널은 빼요(숨긴 채널은 둬요)
    # 한국어 제목을 기계로 찍어 내는 해외 채널(11-09 시험에서 절반 가까이)을 채널 이름으로 빼요
    "skip_channel": r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹìíòóùúý]|vietnam|việt",
}
SHORT_SEC = 180
# 한국어 제목 꼴. 하나의 제목이 여러 꼴에 들 수 있어요.
FORMULAS = [
    ("숫자·순위", r"top\s?\d|best\s?\d|\d+\s?(가지|위|개|곳|종|선|배)|순위|랭킹"),
    ("가격·돈", r"\d[\d,]*\s?(원|만원)|가격|가성비|싸게|최저가|할인|1\+1|값"),
    ("물음", r"\?|왜 |뭐가|어떻게|무엇|진짜일까|맞을까|일까"),
    ("비교", r"\bvs\b|비교|차이|대결|어느 쪽|뭐가 더|말고"),
    ("신상·한정", r"신상|신제품|출시|한정|품절|첫 공개|드디어"),
    ("경고·실수", r"지 ?마(세요|라|요)?|지 ?말|절대|주의|잘못|모르면|큰일|버리지|망하는|제발"),
    ("몰랐던 사실", r"몰랐|비밀|숨은|아무도|사실은|알고 ?보니|이유|정체"),
    ("직접 해 봄", r"먹어 ?봤|해 ?봤|만들어 ?봤|사 ?봤|도전|후기|리뷰|솔직"),
    ("방법·꿀팁", r"레시피|만드는 ?법|꿀팁|황금|방법|하는 ?법|비법|이렇게|이것|넣어 ?보|드세요|해 ?보세요"),
    ("해외·여행", r"일본|미국|중국|대만|태국|베트남|유럽|해외|외국인|여행|현지"),
    ("감탄·강조", r"미쳤|역대급|충격|대박|레전드|난리|실화|ㄷㄷ"),
]


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


def seconds(iso):
    """PT1M5S → 65"""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def clean(title):
    """보여 줄 제목: 해시태그를 빼요."""
    t = re.sub(r"#\S+", "", html.unescape(title)).strip()
    return re.sub(r"\s{2,}", " ", t) or html.unescape(title)


def formulas(title):
    low = clean(title).lower()
    return [name for name, pat in FORMULAS if re.search(pat, low)]


def videos(ids):
    out = {}
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 50):
        for v in get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))["items"]:
            out[v["id"]] = {"t": v["snippet"]["title"], "ch": v["snippet"]["channelId"],
                            "chn": html.unescape(v["snippet"]["channelTitle"]).strip(),
                            "at": v["snippet"]["publishedAt"], "sec": seconds(v["contentDetails"].get("duration")),
                            "v": int(v["statistics"].get("viewCount", 0))}
    return out


def find(cfg, own_channel):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=cfg["hours"])
    found, hit_by = [], {}
    for q in cfg["queries"]:
        res = get("search", part="id", q=q, type="video", videoDuration="short", order="viewCount", regionCode="KR",
                  relevanceLanguage="ko", maxResults=25, publishedAfter=since.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for it in res.get("items", []):
            vid = it["id"].get("videoId")
            if vid:
                found.append(vid)
                hit_by.setdefault(vid, q)
    skip = re.compile(cfg["skip_channel"], re.I) if cfg.get("skip_channel") else None
    cands = {k: v for k, v in videos(found).items() if v["sec"] and v["sec"] <= SHORT_SEC and v["ch"] != own_channel
             and not (skip and skip.search(v["chn"]))}
    # 채널마다 조회수가 가장 큰 후보부터 채널 수를 제한해요
    chans = []
    for v in sorted(cands.values(), key=lambda x: -x["v"]):
        if v["ch"] not in chans:
            chans.append(v["ch"])
    chans = chans[:cfg["max_channels"]]
    uploads, subs = {}, {}
    for i in range(0, len(chans), 50):
        for c in get("channels", part="contentDetails,statistics", id=",".join(chans[i:i + 50]))["items"]:
            uploads[c["id"]] = c["contentDetails"]["relatedPlaylists"]["uploads"]
            subs[c["id"]] = None if c["statistics"].get("hiddenSubscriberCount") else int(c["statistics"].get("subscriberCount", 0))
    recent_ids = {}
    for ch, pl in uploads.items():
        try:
            page = get("playlistItems", part="contentDetails", playlistId=pl, maxResults=50)
            recent_ids[ch] = [x["contentDetails"]["videoId"] for x in page["items"]]
        except Exception:  # 재생목록을 못 읽는 채널은 건너뛰어요
            recent_ids[ch] = []
    info = videos([v for ids in recent_ids.values() for v in ids])
    base, thin = {}, 0
    for ch, ids in recent_ids.items():
        old = [info[v]["v"] for v in ids if v in info and 0 < info[v]["sec"] <= SHORT_SEC
               and datetime.fromisoformat(info[v]["at"].replace("Z", "+00:00")) < since]
        if len(old) >= 4:
            base[ch] = (statistics.median(old), len(old))
        else:
            thin += 1
    rows = []
    for vid, v in cands.items():
        if v["ch"] not in base or base[v["ch"]][0] < cfg["min_median"]:
            continue
        if subs.get(v["ch"]) is not None and subs[v["ch"]] < cfg["min_subs"]:
            continue
        med, n = base[v["ch"]]
        age = (now - datetime.fromisoformat(v["at"].replace("Z", "+00:00"))).total_seconds() / 3600
        rows.append({"id": vid, "title": clean(v["t"]), "channel": v["chn"], "subs": subs.get(v["ch"]), "views": v["v"],
                     "median": int(med), "n": n, "multiple": round(v["v"] / med, 1), "hours": round(age),
                     "formulas": formulas(v["t"]), "query": hit_by.get(vid), "url": f"https://youtube.com/shorts/{vid}"})
    rows.sort(key=lambda r: -r["multiple"])
    return rows, {"searched": len(set(found)), "shorts": len(cands), "channels": len(uploads), "thin": thin}


def man(n):
    return f"{n / 10000:.1f}만" if n >= 10000 else f"{n:,}"


def report(date, picks, stats, cfg):
    e = html.escape
    lines = [f"<b>🔥 요즘 터진 먹거리 쇼츠</b> ({date})",
             f"최근 {cfg['hours']}시간 · 채널 평소보다 {cfg['min_multiple']:g}배 이상 · 조회 {man(cfg['min_views'])} 이상", ""]
    if not picks:
        lines.append("오늘은 기준을 넘은 쇼츠가 없어요.")
    for i, r in enumerate(picks, 1):
        sub = f" · 구독 {man(r['subs'])}" if r.get("subs") else ""
        lines.append(f"{i}. <b>{r['multiple']:g}배</b> {man(r['views'])}회 (평소 {man(r['median'])}) · {r['hours']}시간 전 · [{e(r['query'] or '')}]")
        lines.append(f"   <a href=\"{r['url']}\">{e(r['title'][:44])}</a>")
        lines.append(f"   └ {e(r['channel'][:20])}{sub}" + (f" · 꼴: {', '.join(r['formulas'][:3])}" if r["formulas"] else ""))
    counts = {}
    for r in picks:
        for f in r["formulas"]:
            counts[f] = counts.get(f, 0) + 1
    if counts:
        lines += ["", "<b>제목 꼴</b> " + " · ".join(f"{k} {n}" for k, n in sorted(counts.items(), key=lambda x: -x[1]))]
    lines += ["", f"<i>찾은 쇼츠 {stats['shorts']}개 · 채널 {stats['channels']}곳(쇼츠 4개 안 되는 {stats['thin']}곳 뺌). "
                  "배수는 그 채널 최근 쇼츠 중앙값과 견준 것이고, 꼴은 제목 글자만 보고 나눈 것이라 터진 이유로 단정하지 않아요.</i>"]
    return "\n".join(lines)


def main():
    dry = "--dry" in sys.argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    yt = read_json(ROOT / "config.json", {}).get("youtube") or {}
    cfg = {**DEFAULTS, **(yt.get("viral") or {})}
    if cfg.get("enabled") is False:
        print("youtube.viral.enabled 가 false 라 쉬어요.")
        return
    date = today_kst()
    ledger = read_json(LEDGER, {"days": {}})
    try:
        own = get("channels", part="id", forHandle=yt.get("handle", "@meokgomap"))["items"][0]["id"]
        rows, stats = find(cfg, own)
    except Exception as e:
        log_error("yt_viral", e)
        raise
    recent = {r["id"] for d, day in ledger["days"].items() if d < date and d >= (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
              for r in day.get("picks", [])}
    picks, used, per = [], set(), {}
    for r in rows:  # 배수 큰 차례로, 낱말마다 per_query 개, 한 채널에서 하나만
        if (r["multiple"] >= cfg["min_multiple"] and r["views"] >= cfg["min_views"] and r["id"] not in recent
                and r["channel"] not in used and per.get(r["query"], 0) < cfg["per_query"]):
            picks.append(r)
            used.add(r["channel"])
            per[r["query"]] = per.get(r["query"], 0) + 1
    picks = picks[:cfg["top"]]
    text = report(date, picks, stats, cfg)
    print(text)
    if dry:
        return
    ledger["days"][date] = {"picks": picks, "stats": stats}
    ledger["days"] = dict(sorted(ledger["days"].items())[-30:])  # 30일만 남겨요
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
