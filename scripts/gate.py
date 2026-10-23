# -*- coding: utf-8 -*-
"""보내기 전 검수: 통과 / 확인 필요 / 차단. (2026-10-23 5단계)
새 검사를 따로 만들지 않고 이미 있는 검사를 모아 등급을 매겨요.
  - 형식: video/build.py 의 "꼭 고쳐 주세요"(카드·내레이션·해설), 블로그는 scripts/build_blog.py 의 check
  - 중복·날짜: scripts/history.py
  - 사진·권리·지역: scripts/contentcheck.py
  - 실제 사진을 열어 봤는지: scripts/review_sheet.py 가 만든 검수 시트의 지문(review.photo_sheet)

  python3 scripts/gate.py videos/2026-10-24/2-news.json      판정과 까닭 (끝 코드 0 통과, 1 확인 필요, 2 차단)
  python3 scripts/gate.py blog/2026-10-24-이름.json --json
  python3 scripts/gate.py approve videos/2026-10-24/4-find.json "사용자가 대화에서 '보내'"   확인 필요를 사람이 보고 승인했을 때만
  python3 scripts/gate.py status 2026-10-24                  그날 보류한 것과 지금 상태(고쳤는지·승인했는지)

- 차단: 고치기 전에는 보내지 않아요(잘못된 상품 사진, 사용 불가 사진, 출시일·행사 오류, 바뀐 행정구역 이름, 형식 오류).
- 확인 필요: 사람이 보고 승인해야 보내요(사진을 실제로 확인한 기록이 없음, 이용 조건 확인 전 사진, 같은 메시지 반복 의심 등).
- 승인(review.approved)은 승인한 때의 내용 지문(review.hash)과 지금 내용이 같을 때만 통해요. 고치면 다시 검수해요.
- 읽기만 하고, approve 명령만 그 설계도의 review 칸을 써요.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "video"))
import contentcheck  # noqa: E402
import history  # noqa: E402

KST = timezone(timedelta(hours=9))
# history.py 가 내는 줄을 등급으로. 위에서부터 처음 맞는 것
HISTORY_LEVELS = [
    ("후속편으로 적어 둠", "참고"), ("후속 가능", "참고"), ("반복 의심", "확인"),
    ("이미 나온 것처럼", "차단"), ("끝났어요", "차단"), ("오늘 소식처럼 쓰지 말고", "확인"), ("통계 기준이", "확인"),
]


def content_hash(spec):
    """review 칸을 뺀 내용의 지문. 승인한 뒤 내용이 바뀌면 달라져요."""
    body = {k: v for k, v in spec.items() if k != "review"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def is_blog(path, spec):
    return path.parent.name == "blog" or "blocks" in spec


def day_of(path, spec):
    if is_blog(path, spec):
        return spec.get("date") or "9999-12-31"
    return path.parent.name if re.match(r"\d{4}-\d{2}-\d{2}$", path.parent.name) else "9999-12-31"


def form_findings(path, spec):
    """이미 있는 형식 검사의 "꼭 고쳐 주세요" (사진을 내려받지 않는 것만)."""
    out = []
    if is_blog(path, spec):
        import build_blog
        out += [("형식", "차단", m) for m in build_blog.check(spec, path.stem)]
        return out
    import build
    if build.is_cards(spec):
        if spec.get("format") == "steps":
            import steps
            must, _ = steps.problems(spec)
        else:
            must, _ = build.card_problems(spec)
            if spec.get("format") == "cards":
                must = must + build.number_problems(spec)[0] + build.basis_problems(spec)
    elif spec.get("format") == "voice":
        import voice
        must = voice.problems(spec)[0]
    else:
        must = []
    return [("형식", "차단", m) for m in must]


def history_findings(path, spec):
    if is_blog(path, spec):  # 블로그 초안을 지난 콘텐츠와 견줘요(설계도와 같은 도구)
        day = day_of(path, spec)
        text = " ".join(str(b.get("text") or "") for b in spec.get("blocks") or [] if b.get("type") in ("p", "h2", "h3"))
        u = history.unit("이 초안", day, "블로그", spec.get("title") or "", " ".join([str(spec.get("subject")), str(spec.get("keyword")), " ".join(spec.get("tags") or [])]),
                         (spec.get("title") or "") + " " + text, [], False)
        lines = history.compare([u], history.load_history(datetime.fromisoformat(day).date()))
    else:
        lines = history.report_file(path)
    out = []
    for line in lines:
        level = next((lv for key, lv in HISTORY_LEVELS if key in line), "참고")
        out.append(("이력" if "이력:" in line else "날짜", level, line.strip()))
    return out


def photo_sheet_finding(path, spec):
    """새 규칙 날짜부터: 검수 시트로 실제 사진(잘라 낸 조각까지)을 열어 봤는지. shows 만 믿지 않아요."""
    if day_of(path, spec) < history.DATES_FROM:
        return []
    import review_sheet
    want = review_sheet.sheet_hash(spec)
    if not want:
        return []
    got = (spec.get("review") or {}).get("photo_sheet")
    if got != want:
        why = "검수 시트를 만든 뒤 사진이 바뀌었어요" if got else "실제 사진 검수 시트를 열어 본 기록(review.photo_sheet)이 없어요"
        return [("사진 확인", "확인", f"{why}. python3 scripts/review_sheet.py {path.as_posix()} 시트.jpg 로 만들어 열어 보고, 나온 지문을 review.photo_sheet 에 적어 주세요")]
    return []


def evaluate(path):
    """{"verdict": 통과|확인 필요|차단, "findings": [(갈래, 등급, 내용)], "hash", "approved", "forced"}"""
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    found = []
    for part in (form_findings, history_findings, photo_sheet_finding):
        try:
            found += part(path, spec)
        except Exception as e:  # 검사를 못 하면 통과로 치지 않아요
            found.append(("검수 오류", "확인", f"{part.__name__} 를 하지 못했어요: {str(e)[:150]}"))
    try:
        found += [(a, lv, m) for a, m, lv in contentcheck.findings(path)]
    except Exception as e:
        found.append(("검수 오류", "확인", f"contentcheck 를 하지 못했어요: {str(e)[:150]}"))
    h = content_hash(spec)
    review = spec.get("review") or {}
    approved = bool(review.get("approved")) and review.get("hash") == h
    forced = bool(review.get("force")) and review.get("hash") == h
    blocks = [f for f in found if f[1] == "차단"]
    checks = [f for f in found if f[1] == "확인"]
    if blocks and not forced:
        verdict = "차단"
    elif (checks or blocks) and not (approved or forced):
        verdict = "확인 필요"
    else:
        verdict = "통과"
    return {"verdict": verdict, "findings": found, "hash": h, "approved": approved, "forced": forced}


def reasons(result, n=4):
    """사람에게 보여 줄 까닭 몇 줄(차단 먼저)."""
    order = {"차단": 0, "확인": 1, "참고": 2}
    fs = sorted([f for f in result["findings"] if f[1] != "참고"], key=lambda f: order[f[1]])
    lines = [f"[{lv}] {area}: {msg[:140]}" for area, lv, msg in fs[:n]]
    if len(fs) > n:
        lines.append(f"…그 밖에 {len(fs) - n}건")
    return lines


def approve(path, note):
    """사용자가 '확인 필요'를 보고 승인했을 때만 써요. 지금 내용의 지문을 함께 적어서, 고치면 승인이 풀려요."""
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec.setdefault("review", {}).update({"approved": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "note": note, "hash": content_hash(spec)})
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return spec["review"]


def status(day):
    """그날 보류한 것과 지금 상태(state/review.json + 설계도를 지금 다시 검수). 운영자가 무엇을 봐야 하는지 한눈에."""
    review = json.loads((ROOT / "state" / "review.json").read_text(encoding="utf-8")) if (ROOT / "state" / "review.json").exists() else {}
    rows = []
    for rid, v in sorted(review.items()):
        if not rid.startswith(day):
            continue
        spec = ROOT / "videos" / day / (rid[len(day) + 1:] + ".json")
        now = evaluate(spec) if spec.exists() else None
        changed = now and now["hash"] != v.get("hash")
        state = ("보냄" if v["verdict"] == "통과" else "보류") + (" · 고친 뒤 아직 다시 보내기 전" if changed else "")
        rows.append(f"{rid[len(day) + 1:]:10} 그때 {v['verdict']:5} → 지금 {now['verdict'] if now else '설계도 없음':5} "
                    f"{'(사람 승인됨)' if now and now['approved'] else ''} [{state}]")
        if now and now["verdict"] != "통과":
            rows += ["    " + x for x in reasons(now, 3)]
    return rows or [f"{day} 검수 기록이 없어요."]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args and args[0] == "status":  # python3 scripts/gate.py status 2026-10-24
        print("\n".join(status(args[1])))
        return
    if args and args[0] == "approve":
        print(json.dumps(approve(args[1], " ".join(args[2:]) or "사용자 승인"), ensure_ascii=False))
        return
    as_json = "--json" in args
    path = [a for a in args if not a.startswith("--")][0]
    r = evaluate(path)
    if as_json:
        print(json.dumps({"verdict": r["verdict"], "hash": r["hash"], "reasons": reasons(r, 6)}, ensure_ascii=False))
    else:
        print(f"검수: {r['verdict']}" + (" (사용자 승인)" if r["approved"] else "") + (" (강제 통과)" if r["forced"] else ""))
        for area, lv, msg in r["findings"]:
            print(f"  [{lv}] {area}: {msg}")
    sys.exit({"통과": 0, "확인 필요": 1, "차단": 2}[r["verdict"]])


if __name__ == "__main__":
    main()
