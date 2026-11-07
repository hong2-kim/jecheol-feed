# -*- coding: utf-8 -*-
"""사진 사용 내역 보고. 영상·카드·블로그 결과물과 따로 텔레그램에 보내요. (2026-11-07 사용자가 정함)

  python3 scripts/photo_report.py videos/2026-11-07/4-find.json        보고 글을 미리 봐요(보내지 않아요)
  python3 scripts/photo_report.py blog/2026-11-07-이름.json

알리는 것: 콘텐츠 제목 · 사용한 사진마다 출처와 원본 링크 · 블로그·유튜브·인스타그램 사진을 썼는지 · 이용 허락 확인 여부 ·
추가 확인이 필요한 사진과 그 장면 · 넣지 않은 후보(허락 불명확, photo_candidates) · 사진을 못 구한 장면(photo_missing·photo_search).

설계도에 적는 칸
  사진마다  "page": 원본 페이지(블로그 글·유튜브 영상·인스타 게시물·Unsplash 사진 페이지). 없으면 terms.url, 그다음 사진 주소를 링크로 써요.
            "terms": {"url", "checked", "scope", "ok": true, "permission": "작성자 허락(언제·어떻게)"}  ← 블로그·유튜브·SNS 사진은 이것이 있어야 써요
  설계도에  "photo_candidates": [{"scene": "장면 3 · 축제 먹거리 부스", "from": "네이버 블로그", "page": "원본 링크", "url": "사진 주소", "why": "작성자 허락 없음"}]
            "photo_missing":    [{"scene": "장면 5 · 2025 축제 전경", "tried": "울진군 사진DB·관광공사·Unsplash·블로그 12곳·유튜브 3편"}]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

EXTERNAL = [  # 사용자가 따로 확인하기 쉽게 갈래를 나눠 보여 줘요
    ("블로그", re.compile(r"blog\.naver\.com|blogfiles\.pstatic|postfiles\.pstatic|blogthumb\.pstatic|blogpfthumb|tistory\.com|daumcdn\.net|brunch\.co\.kr")),
    ("유튜브", re.compile(r"youtube\.com|youtu\.be|ytimg\.com")),
    ("인스타그램·SNS", re.compile(r"instagram\.com|cdninstagram\.com|fbcdn\.net|facebook\.com|threads\.net|twitter\.com|twimg\.com|//x\.com")),
]


def external_kind(*urls):
    for name, pat in EXTERNAL:
        if any(pat.search(u or "") for u in urls):
            return name
    return ""


def place(where):
    """설계도 자리 이름을 사람이 읽는 말로: cards[3].photo → 카드 3, scenes[2].photos[1] → 장면 2."""
    m = re.match(r"(thumb|cover|scenes|lines|cards|top|slides|base|blocks)(?:\[(\d+)\])?", where or "")
    if not m:
        return where
    name = {"thumb": "썸네일", "cover": "표지", "scenes": "장면", "lines": "문장", "cards": "카드", "top": "맨 위", "slides": "장",
            "base": "바탕", "blocks": "블로그 사진"}[m.group(1)]
    return f"{name} {m.group(2)}" if m.group(2) else name


def link_of(p):
    t = p.get("terms") if isinstance(p.get("terms"), dict) else {}
    page = p.get("page") or ""
    if not page and t.get("url") and not re.search(r"/license|creativecommons\.org|kogl\.or\.kr", t["url"]):
        page = t["url"]
    u = p.get("url") or ""
    m = re.match(r"(https://commons\.wikimedia\.org/wiki/)Special:FilePath/([^?]+)", u)
    return page or (f"{m.group(1)}File:{m.group(2)}" if m else u)


def collect(spec):
    """(자리, 사진) 목록과 후보·미확보. 같은 사진(주소)은 처음 나온 자리에 묶어요."""
    import contentcheck
    if "blocks" in spec:
        spec = contentcheck.blog_as_spec(spec)
    seen = {}
    for where, _, p in contentcheck.items_of(spec):
        u = p.get("url")
        if u in seen:
            seen[u]["where"].append(place(where))
            continue
        seen[u] = {"where": [place(where)], "p": p}
    return list(seen.values())


def extras(spec):
    """photo_candidates·photo_missing 은 설계도 어디에 적어도(장면·카드 안) 모아요. 카드의 photo_search 도 미확보로 봐요."""
    cands, missing = [], []

    def walk(o, where):
        if isinstance(o, dict):
            for c in o.get("photo_candidates") or []:
                if isinstance(c, dict):
                    cands.append({**c, "scene": c.get("scene") or place(where)})
            for m in o.get("photo_missing") or []:
                if isinstance(m, dict):
                    missing.append({**m, "scene": m.get("scene") or place(where)})
            ps = o.get("photo_search")
            if isinstance(ps, dict) and not o.get("photo") and any(ps.values()):
                missing.append({"scene": place(where), "tried": " · ".join(f"{k}: {v}" for k, v in ps.items() if v)[:220]})
            for k, v in o.items():
                if isinstance(v, (dict, list)) and k not in ("photo_candidates", "photo_missing", "photo_search"):
                    walk(v, f"{where}.{k}" if where else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{i + 1}]")

    walk(spec, "")
    return cands, missing


def report(spec, title="", day="9999-12-31", held=()):
    """보고 글(텔레그램 한 통). held: 결과물에서 뺀 장 [{no, headline, grade, reasons}] (카드 뉴스)."""
    import contentcheck
    rows = collect(spec)
    cands, missing = extras(spec)
    name = str(title or spec.get("title") or "")
    lines = [f"📷 사진 사용 내역 · {name[:70] + ('…' if len(name) > 70 else '')}".strip()]
    ext_used, need = [], []
    for n, r in enumerate(rows, 1):
        p = r["p"]
        t = p.get("terms") if isinstance(p.get("terms"), dict) else {}
        kind, bad, why = contentcheck.host_kind(p["url"], p.get("rights", ""), t, day)
        ext = external_kind(p["url"], p.get("page"), t.get("url"))
        if not bad:
            basis = t.get("permission") or (t.get("scope") or "")[:40] or str(p.get("rights") or "")[:40] or kind
            ok = f"허락 확인: 됨({basis})"
        elif "(사용 불가)" in why:
            ok = "허락 확인: 안 됨(사용 불가)"
        else:
            ok = "허락 확인: 확인 필요"
        src = ext or kind
        if kind == "이용 조건 확인한 사진":  # 사진마다 terms 를 적은 것: 어디 사진인지를 보여 줘요
            ref = link_of(p)  # 보관함에 옮겨 둔 사진이면 원본 페이지(terms.url) 쪽 출처를 보여 줘요
            host = (ref.split("/")[2] if "://" in ref else ref.split("/")[0]).removeprefix("www.")
            src = ext or ((contentcheck.rights_entry(ref, host) or {}).get("name")) or host
        lines.append(f"{n}. {', '.join(r['where'][:3])} — {src} · {ok}\n   {link_of(p)}")
        if ext:
            ext_used.append(f"{ext}({'확인' if not bad else '미확인'})")
        if bad:
            need.append(f"- {', '.join(r['where'][:3])}: {kind} — {why[:120]}\n  {link_of(p)}")
    if not rows:
        lines.append("사용한 사진 없음")
    lines.append("")
    lines.append("블로그·유튜브·인스타그램 사진: " + (f"{len(ext_used)}장 사용 — " + ", ".join(ext_used) if ext_used else "사용 안 함"))
    if need:
        lines += ["", "⚠️ 추가 확인이 필요한 사진", *need]
    for h in held or []:
        missing.append({"scene": f"카드 {h.get('no')}", "tried": f"이 장은 빼고 보냈어요 — {'; '.join((h.get('reasons') or [])[:1])[:160]}"})
    if cands:
        lines += ["", "🔎 넣지 않은 후보(허락 불명확 — 보고 정해 주세요)"]
        for c in cands[:12]:
            lines.append(f"- {c.get('scene')}: {c.get('from') or external_kind(c.get('page'), c.get('url')) or '외부'} — {c.get('why') or '허락 미확인'}\n  {c.get('page') or c.get('url') or ''}")
    if missing:
        lines += ["", "❗ 사진을 못 구한 장면"]
        lines += [f"- {m.get('scene')}: {m.get('tried') or ''}"[:300] for m in missing[:10]]
    if not (need or cands or missing):
        lines += ["", "추가 확인할 사진 없음"]
    return "\n".join(lines)[:4000]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    spec = json.loads(path.read_text(encoding="utf-8"))
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(path))
    print(report(spec, day=m.group(0) if m else "9999-12-31"))


if __name__ == "__main__":
    main()
