# -*- coding: utf-8 -*-
"""어떤 주제·제목·형식이 반응을 얻었는지 게시물마다 한 줄로 모아 보여 줘요. 읽기만 해요. (2026-10-18 사용자가 정한 설계)

  python scripts/reaction_log.py
  python scripts/reaction_log.py --from 2026-10-15 --to 2026-10-18
  python scripts/reaction_log.py --csv C:/Users/User/Desktop/반응기록.csv   (저장소 밖 경로만)
  python scripts/reaction_log.py --json                                  (시험용: 기계가 읽는 꼴)

읽는 것: videos/날짜/*.json(설계도), state/videos.json(만든 결과), state/yt_stats.json(유튜브 공개 숫자),
        git 기록(그날 숫자를 언제 모았는지), state/yt_links.json(수동 연결표, 있을 때만).
쓰는 것: 없음. --csv 를 주면 저장소 밖의 그 파일 하나만 써요. 네트워크를 쓰지 않아요.

규칙
- 유튜브 영상과 설계도 잇기: 수동 연결표 > 제목 완전 일치(후보 하나) > 비슷한 제목(0.8 이상, 올린 날이 만든 날~2일 뒤, 후보 하나).
  그 밖은 "미연결"이고 반응 값을 설계도에 붙이지 않아요.
- 24시간 값은 올린 뒤 20~28시간, 72시간 값은 66~78시간에 실제로 찍힌 기록만 써요. 없으면 "미확인"이에요.
  가까운 값으로 채우거나 사이를 어림하지 않아요.
- 비교는 같은 날·같은 형식·같은 창끼리만 하고, 3개 미만이면 보류해요.
- 기록 시각: ytstats 작업 커밋(이름 jecheol-feed, 메시지 "유튜브 조회수 기록")의 작성 시각을 써요.
  작성·커밋 시각이 5분 넘게 벌어지거나, 다른 커밋이거나, 기록 속 가장 새 영상보다 앞서면 그날은 미확인이에요.
  ytstats.yml 의 이름·메시지를 바꾸면 아래 COLLECTOR 도 같이 바꿔야 해요(안 바꾸면 그 뒤 기록이 모두 미확인).
"""
import argparse
import csv
import difflib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from common import KST, ROOT

WINDOWS = {"24h": (20.0, 28.0), "72h": (66.0, 78.0)}
SIMILAR = 0.8          # 비슷한 제목으로 볼 유사도
DAYS_AFTER = 2         # 만든 날부터 며칠 뒤에 올린 것까지 같은 게시물 후보로 보나
MIN_GROUP = 3          # 같은 날·같은 형식 비교에 필요한 수
MIN_PAIRS, LEAN = 8, 0.75  # 특징별 짝 비교: 짝이 이만큼 있고 한쪽이 이 비율 넘게 이겨야 결론을 내요
LIKE_MIN_VIEWS = 50    # 좋아요율은 조회 50회부터
# 제목 꼴. 사람이 판단하지 않고 이 규칙으로만 붙여요.
FEATURES = {
    "물음": lambda t: "?" in t,
    "숫자": lambda t: any(c.isdigit() for c in t),
    "ㅋㅋ": lambda t: "ㅋ" in t,
    "상황극": lambda t: any(w in t for w in ("친구", "다며", "길래", "했는데")),
}
WEEK = "월화수목금토일"


def iso(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def kst(dt, fmt="%m-%d %H:%M"):
    return dt.astimezone(KST).strftime(fmt)


def norm(title):
    """유튜브 제목 다듬기: 띄어쓰기를 고르고 100자에서 자르는 것까지 build.youtube_text 와 같게 해요."""
    t = " ".join(str(title or "").split())
    return t[:99].rstrip() + "…" if len(t) > 100 else t


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


# ytstats 작업(.github/workflows/ytstats.yml)이 커밋할 때 쓰는 이름과 메시지. 이 둘이 맞는 커밋만 "수집 기록"으로 봐요.
# ⚠ ytstats.yml 의 git config user.name 이나 git commit -m 메시지를 바꾸면 여기도 같이 바꿔야 해요.
#   안 바꾸면 그 뒤 기록은 모두 "ytstats 작업 커밋이 아니에요"로 기록 시각을 믿지 못해 24h·72h 가 전부 미확인이 돼요.
#   (틀린 값이 조용히 들어가는 것보다 낫지만, 측정이 멈춘 것처럼 보여요.)
#   예전 메시지로 남은 기록까지 인정하려면 메시지를 바꾸는 대신 여기에 예전 것을 함께 받아 주도록 고쳐요.
# 이름·메시지는 누구나 똑같이 쓸 수 있어서 인증이 아니에요. 실수로 섞인 커밋(다른 작업, 손으로 한 커밋)을 거르는 장치예요.
COLLECTOR = ("jecheol-feed", "유튜브 조회수 기록")
# 작성 시각과 커밋 시각이 이보다 벌어지면 그날 기록 시각을 믿지 않아요(미확인).
# 근거(2026-10-18 확인): GitHub 실행 기록으로 본 정상 수집 4건은 수집~커밋이 최대 37초였고 작성=커밋 시각이었어요.
#   이력을 다시 쓰면(rebase·cherry-pick·amend) 보통 몇 시간씩 벌어져요. 5분은 그 사이의 안전 기준이에요.
# 한계: 모든 정상 상황을 보장하는 값은 아니에요. GitHub 가 느려 pull --rebase 가 5분 넘게 걸리면 정상 기록도 미확인이 되고,
#   5분 안에 다시 쓴 이력은 걸러지지 않아요. 그래서 가장 새 영상보다 앞선 시각인지도 함께 봐요(build).
MAX_SKEW_MIN = 5


def snapshot_times(root, ledger):
    """날짜 칸마다 숫자를 모은 시각과, 믿지 못하는 날의 까닭. ({날짜: 시각}, {날짜: 까닭})
    그 칸이 마지막으로 바뀐 커밋의 작성 시각(author)을 쓰되, 아래를 모두 지킬 때만 믿어요.
    - ytstats 작업이 만든 커밋(이름 jecheol-feed, 메시지 "유튜브 조회수 기록")
    - 작성 시각과 커밋 시각이 5분 안 (다시 쓴 커밋·amend 를 걸러요)
    - 지금 파일의 그 칸이 그 커밋 내용과 같음 (커밋 안 된 수정을 걸러요)"""
    log = git(root, "log", "--format=%H%x1f%aI%x1f%cI%x1f%an%x1f%s", "--", "state/yt_stats.json")
    if not log:
        return {}, {}
    last, seen = {}, {}
    for line in reversed(log.strip().splitlines()):
        sha, authored, committed, name, subject = line.split("\x1f")
        text = git(root, "show", f"{sha}:state/yt_stats.json")
        if text is None:
            continue
        for day, entry in (json.loads(text).get("days") or {}).items():
            if seen.get(day) != entry:
                last[day] = (iso(authored), iso(committed), name, subject)
            seen[day] = entry
    taken, doubt = {}, {}
    for day, (authored, committed, name, subject) in last.items():
        if seen.get(day) != (ledger.get("days") or {}).get(day):
            doubt[day] = "커밋 안 된 수정이 있어요"
        elif (name, subject) != COLLECTOR:
            doubt[day] = f"ytstats 작업 커밋이 아니에요 ({name} · {subject})"
        elif abs((committed - authored).total_seconds()) > MAX_SKEW_MIN * 60:
            gap = int(abs((committed - authored).total_seconds()))
            doubt[day] = f"작성 시각과 커밋 시각이 {gap // 60}분 {gap % 60}초 벌어졌어요(기준 {MAX_SKEW_MIN}분)"
        else:
            taken[day] = authored
    return taken, doubt


def load_specs(root):
    specs = {}
    for path in sorted((root / "videos").glob("*/*.json")):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        sid = f"{path.parent.name}-{path.stem}"
        specs[sid] = {"id": sid, "date": path.parent.name, "spec": s,
                      "titles": [t for t in (norm(s.get("yt_title")), norm(s.get("title"))) if t]}
    return specs


def format_group(s):
    f = s.get("format")
    if f == "cards":
        return "이야기 카드" if s.get("mode") == "story" else "트렌드 카드" if s.get("kind") == "유행" else "모음 카드"
    if f == "steps":
        return "넘겨 보는 해설"
    if f == "voice":
        return "내레이션"
    return f"영상({s.get('kind') or '?'})"


def link(videos, specs, manual):
    """유튜브 영상 id -> (설계도 id 또는 None, 상태, 까닭)"""
    out, ignore = {}, set(manual.get("ignore") or [])

    def in_range(sid, v):  # 만든 날 ~ 2일 뒤에 올린 것만 같은 게시물 후보예요
        made_on = datetime.strptime(specs[sid]["date"], "%Y-%m-%d").date()
        return made_on <= v["at"].astimezone(KST).date() <= made_on + timedelta(days=DAYS_AFTER)

    exact, exact_far = {}, {}
    for vid, v in videos.items():
        same = [sid for sid, sp in specs.items() if v["title"] in sp["titles"]]
        exact[vid] = [sid for sid in same if in_range(sid, v)]
        exact_far[vid] = [sid for sid in same if not in_range(sid, v)]
    title_count = {}
    for v in videos.values():
        title_count[v["title"]] = title_count.get(v["title"], 0) + 1
    taken = {}
    for vid, v in videos.items():  # 1) 수동 2) 완전 일치
        if vid in ignore:
            out[vid] = (None, "제외", "수동 연결표에서 뺐어요")
        elif vid in (manual.get("links") or {}):
            sid = manual["links"][vid]
            note = "" if sid in specs else " (설계도를 못 찾았어요)"
            if exact[vid] and exact[vid] != [sid]:
                note += f" (주의: 제목은 {', '.join(exact[vid])} 와 같아요)"
            out[vid] = (sid if sid in specs else None, "수동" if sid in specs else "미연결", "수동 연결표" + note)
        elif title_count[v["title"]] > 1:
            out[vid] = (None, "미연결", "같은 제목 영상이 여러 개예요")
        elif len(exact[vid]) > 1:
            out[vid] = (None, "미연결", "같은 제목 설계도가 여러 개예요: " + ", ".join(exact[vid]))
        elif exact[vid]:
            sp = specs[exact[vid][0]]["spec"]
            which = "계획한 유튜브 제목" if norm(sp.get("yt_title")) == v["title"] else "설계도 title(인스타 제목)"
            out[vid] = (exact[vid][0], "정확", f"{which}과 같아요")
        elif exact_far[vid]:
            out[vid] = (None, "미연결", "제목은 같지만 올린 날이 설계도 날짜 범위 밖이에요: " + ", ".join(exact_far[vid]))
        if out.get(vid) and out[vid][0]:
            taken[out[vid][0]] = vid
    for vid, v in videos.items():  # 3) 비슷한 제목
        if vid in out:
            continue
        scored = sorted(((max(difflib.SequenceMatcher(None, v["title"], t).ratio() for t in sp["titles"]), sid)
                         for sid, sp in specs.items() if sp["titles"]), reverse=True)
        near = [(r, sid) for r, sid in scored if r >= SIMILAR and in_range(sid, v)]
        best = ", ".join(f"{sid}({r:.2f})" for r, sid in scored[:2]) or "없음"
        if len(near) == 1 and near[0][1] not in taken:
            out[vid] = (near[0][1], "유사", f"제목 유사도 {near[0][0]:.2f}")
            taken[near[0][1]] = vid
        elif len(near) > 1:
            out[vid] = (None, "미연결", "비슷한 설계도가 여럿이에요: " + ", ".join(f"{sid}({r:.2f})" for r, sid in near))
        elif near:
            out[vid] = (None, "미연결", f"비슷한 설계도 {near[0][1]} 는 이미 다른 영상과 이어졌어요")
        elif scored and scored[0][0] >= SIMILAR:
            out[vid] = (None, "미연결", f"올린 날이 설계도 날짜 범위 밖이에요 (가장 비슷한 것 {best})")
        else:
            out[vid] = (None, "미연결", f"제목이 많이 달라요 (가장 비슷한 것 {best})")
    return out


def window_value(obs, lo, hi):
    """창 안에 실제로 찍힌 기록 하나. 없으면 (None, 까닭)."""
    known = [o for o in obs if o["age"] is not None]
    hit = [o for o in known if lo <= o["age"] <= hi]
    if hit:
        return min(hit, key=lambda o: abs(o["age"] - (lo + hi) / 2)), ""
    unknown = len(obs) - len(known)
    tail = f", 기록 시각 모르는 관측 {unknown}개" if unknown else ""
    if not known:
        return None, f"미확인(기록 시각 모름, 관측 {unknown}개)"
    last = max(o["age"] for o in known)
    if last < lo:
        return None, f"미확인(나이 부족, 마지막 관측 {last:.1f}h{tail})"
    return None, "미확인(창 밖, 관측 " + ", ".join(f"{o['age']:.1f}h" for o in sorted(known, key=lambda o: o["age"])) + tail + ")"


def build(root, date_from=None, date_to=None):
    ledger = read(root / "state" / "yt_stats.json", {}) or {}
    days = ledger.get("days") or {}
    times, doubt = snapshot_times(root, ledger)
    for day, t0 in list(times.items()):  # 기록에 든 가장 새 영상보다 먼저 모았을 수는 없어요
        newest = max((iso(v["at"]) for v in (days.get(day, {}).get("videos") or {}).values()), default=None)
        if newest and t0 < newest:
            doubt[day] = f"기록 시각({kst(t0)})이 기록에 든 가장 새 영상({kst(newest)})보다 앞서요"
            del times[day]
    specs = load_specs(root)
    made = {e["id"]: e for e in read(root / "state" / "videos.json", []) or []}
    manual = read(root / "state" / "yt_links.json", {}) or {}
    videos = {}
    for day in sorted(days):
        for vid, v in (days[day].get("videos") or {}).items():
            videos[vid] = {"title": norm(v["t"]), "at": iso(v["at"])}
    if date_from or date_to:
        videos = {vid: v for vid, v in videos.items()
                  if (not date_from or kst(v["at"], "%Y-%m-%d") >= date_from) and (not date_to or kst(v["at"], "%Y-%m-%d") <= date_to)}
    links = link(videos, specs, manual)
    rows, unlinked = [], []
    for vid, v in sorted(videos.items(), key=lambda x: x[1]["at"]):
        obs = []
        for day in sorted(days):
            x = (days[day].get("videos") or {}).get(vid)
            if not x:
                continue
            t = times.get(day)
            age = round((t - v["at"]).total_seconds() / 3600, 1) if t else None
            if age is not None and age < 0:
                continue
            obs.append({"day": day, "taken": kst(t) if t else None, "age": age, "v": x.get("v"), "l": x.get("l"), "c": x.get("c")})
        sid, state, why = links[vid]
        base = {"yt_id": vid, "yt_title": v["title"], "uploaded": kst(v["at"], "%Y-%m-%d %H:%M"),
                "weekday": WEEK[v["at"].astimezone(KST).weekday()], "link": state, "link_why": why}
        if not sid:
            unlinked.append(base)
            continue
        s = specs[sid]["spec"]
        meta = s.get("meta") or {}
        r = dict(base, spec=sid, subject=s.get("subject") or "미기록", kind=s.get("kind") or "미기록", format=format_group(s),
                 cards=len(made.get(sid, {}).get("files") or []) or None, seconds=made.get(sid, {}).get("seconds"),
                 features=[k for k, f in FEATURES.items() if f(v["title"])], planned_title=norm(s.get("yt_title") or s.get("title")),
                 angle=meta.get("angle") or "미기록", target=meta.get("target") or "미기록",
                 fallback=(meta["fallback"] or "없음(이슈)") if "fallback" in meta else "미기록",
                 total_checked=meta.get("total_checked", "미기록"), total_with_guess=meta.get("total_with_guess", "미기록"),
                 click=meta.get("click") or "미기록", exclude=meta.get("exclude") or "미기록",
                 saves="미확인(연동 필요)", shares="미확인(연동 필요)", instagram="미확인(연동 필요)", observations=obs)
        for name, (lo, hi) in WINDOWS.items():
            o, missing = window_value(obs, lo, hi)
            if o:
                rate = f"{o['l'] / o['v'] * 100:.1f}%" if o["v"] and o["v"] >= LIKE_MIN_VIEWS else f"미확인(조회 {LIKE_MIN_VIEWS} 미만)"
                r[name] = {"views": o["v"], "likes": o["l"], "comments": o["c"], "like_rate": rate, "taken": o["taken"], "age": o["age"]}
            else:
                r[name] = missing
        rows.append(r)
    groups = []
    for name in WINDOWS:
        bucket = {}
        for r in rows:
            if isinstance(r[name], dict):
                bucket.setdefault((r["uploaded"][:10], r["format"]), []).append(r)
        for (day, fmt), rs in sorted(bucket.items()):
            med = statistics.median(x[name]["views"] for x in rs)
            members = [{"spec": x["spec"], "views": x[name]["views"], "x_median": round(x[name]["views"] / med, 2) if med else None, "features": x["features"]}
                       for x in sorted(rs, key=lambda x: -x[name]["views"])]
            groups.append({"window": name, "day": day, "format": fmt, "n": len(rs), "verdict": "비교" if len(rs) >= MIN_GROUP else f"비교 보류({MIN_GROUP}개 미만)", "members": members})
    features = []
    for feat in FEATURES:
        wins = pairs = 0
        for g in groups:
            yes = [m for m in g["members"] if feat in m["features"]]
            no = [m for m in g["members"] if feat not in m["features"]]
            for a in yes:
                for b in no:
                    pairs += 1
                    wins += a["views"] > b["views"]
        lean = wins / pairs if pairs else None
        verdict = (f"결론 보류(짝 {pairs}개, {MIN_PAIRS}개 미만)" if pairs < MIN_PAIRS else
                   f"'{feat}' 쪽이 높았어요" if lean >= LEAN else f"'{feat}' 아닌 쪽이 높았어요" if lean <= 1 - LEAN else "뚜렷한 차이 없음")
        features.append({"feature": feat, "pairs": pairs, "wins": wins, "verdict": verdict})
    status = {"snapshot_times": {d: kst(t) for d, t in sorted(times.items())},
              "snapshot_unknown": sorted(set(days) - set(times)),
              "snapshot_doubt": doubt,
              "windows": {k: f"{lo:g}~{hi:g}시간" for k, (lo, hi) in WINDOWS.items()},
              "links": {k: sum(1 for x in links.values() if x[1] == k) for k in ("정확", "유사", "수동", "미연결", "제외")},
              "manual_table": "있음" if (root / "state" / "yt_links.json").exists() else "없음",
              "missing": {name: sum(1 for r in rows if not isinstance(r[name], dict)) for name in WINDOWS}}
    return {"status": status, "rows": rows, "unlinked": unlinked, "groups": groups, "features": features}


def cell(x):
    if isinstance(x, dict):
        return f"{x['views']:,} · 좋아요 {x['likes']} · 댓글 {x['comments']} (관측 {x['taken']} · {x['age']:.1f}h)"
    return x


def show(res):
    st = res["status"]
    print("[자료 상태]")
    print("기록 시각(ytstats 커밋 작성 시각, 한국): " + (" · ".join(f"{d[5:]} → {t}" for d, t in st["snapshot_times"].items()) or "없음"))
    if st["snapshot_unknown"]:
        print("기록 시각을 모르는 날: " + ", ".join(f"{d}({st['snapshot_doubt'].get(d, '기록 없음')})" for d in st["snapshot_unknown"]))
    print(f"창: 24h {st['windows']['24h']}, 72h {st['windows']['72h']} · 수동 연결표 {st['manual_table']}")
    print("연결: " + " · ".join(f"{k} {v}" for k, v in st["links"].items()) + f" · 미확인 24h {st['missing']['24h']}개, 72h {st['missing']['72h']}개")
    print("\n[게시물]")
    for r in res["rows"]:
        print(f"- {r['uploaded']}({r['weekday']}) {r['spec']} · {r['format']} · {r['subject']} · 연결 {r['link']}({r['link_why']})")
        print(f"    제목: {r['yt_title']}  [꼴: {', '.join(r['features']) or '없음'}]")
        print(f"    24h: {cell(r['24h'])}")
        print(f"    72h: {cell(r['72h'])}")
        print(f"    각도 {r['angle']} · 타깃 {r['target']} · 점수 {r['total_checked']}/{r['total_with_guess']} · 저장·공유 {r['saves']}")
    print("\n[미연결: 반응 값을 설계도에 붙이지 않았어요]")
    for u in res["unlinked"] or [{"uploaded": "", "yt_title": "없음", "link_why": ""}]:
        print(f"- {u['uploaded']} {u['yt_title']}  → {u['link_why']}")
    print("\n[같은 날·같은 형식 비교]")
    for g in res["groups"] or []:
        names = ", ".join(f"{m['spec']} {m['views']:,}회(중앙값의 {m['x_median']}배)" for m in g["members"])
        print(f"- {g['day']} · {g['window']} · {g['format']} n={g['n']}: {g['verdict']} — {names}")
    if not res["groups"]:
        print("- 창 안에 값이 있는 게시물이 없어요")
    print("\n[제목 꼴별 짝 비교 (같은 날·같은 형식 짝만)]")
    for f in res["features"]:
        print(f"- {f['feature']}: 짝 {f['pairs']}개, 이긴 짝 {f['wins']}개 → {f['verdict']}")


def write_csv(res, path, root):
    path = Path(path).resolve()
    if path == root.resolve() or root.resolve() in path.parents:
        sys.exit(f"CSV 는 저장소 밖에만 써요: {path}")
    cols = ["uploaded", "weekday", "spec", "link", "format", "subject", "kind", "yt_title", "features", "angle", "target",
            "total_checked", "total_with_guess", "24h_views", "24h_likes", "24h_comments", "24h_taken", "24h_age",
            "72h_views", "72h_likes", "72h_comments", "72h_taken", "72h_age", "saves", "shares"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in res["rows"]:
            out = dict(r, features=" ".join(r["features"]))
            for name in WINDOWS:
                x = r[name]
                for k in ("views", "likes", "comments", "taken", "age"):
                    out[f"{name}_{k}"] = x[k] if isinstance(x, dict) else (x if k == "views" else "")
            w.writerow([out.get(c, "") for c in cols])
    print(f"CSV 를 썼어요: {path}", file=sys.stderr)  # --json 출력이 섞이지 않게 표준 오류로


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--csv")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", help="다른 저장소 폴더를 읽을 때(시험용)")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else ROOT
    res = build(root, a.date_from, a.date_to)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        show(res)
    if a.csv:
        write_csv(res, a.csv, root)


if __name__ == "__main__":
    main()
