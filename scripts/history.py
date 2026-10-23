# -*- coding: utf-8 -*-
"""지난 콘텐츠와 겹치는지, 날짜가 맞는지 봐요. (2026-10-23 3단계)
읽기만 하고 아무것도 쓰지 않아요. 저장소 안의 지난 설계도·글·블로그 초안을 이 컴퓨터에서 읽어 겹치는 것만 짧게 알려 줘요.

  python3 scripts/history.py file videos/2026-10-23/8-trend.json [--fetch]   설계도 하나를 지난 콘텐츠와 견주고 날짜를 봐요
  python3 scripts/history.py check "고디바 모찌 새벽 줄" [--date 2026-10-23] [--url 주소 …]   쓰기 전에 후보 하나를 견줘요

- 견주는 곳: videos/*/*.json(카드는 장마다), items/*/*.json(소식 글), blog/*.json(블로그 초안). 형식이 달라도 같은 소재면 잡아요.
  보냈는지는 state/sent_videos.json, state/sent.json, state/blog_posted.json 으로 표시해요.
- 겹침 판단: 같은 기사 주소, 같은 음식·제품 이름(뜻이 같은 말은 SYNONYMS 로 묶음), 같은 일(줄 서기·품절 등, CONCEPTS),
  같은 숫자. 여러 콘텐츠에 흔한 말(가을, 저녁 등)은 덜 셉니다.
- 같은 소재인데 지난번에 없던 숫자가 있으면 '후속 가능'으로, 새 숫자도 새 이름도 없으면 '반복 의심'으로 알려 줘요.
  설계도의 followup 칸({"of": "2026-10-16/8-trend#3", "new": "무엇이 새로운지"})에 적은 것은 후속편으로 봐요.
- 날짜: 설계도의 dates 칸(PROMPT.md "날짜 구분")을 보고, 출처 기사가 오래됐는지, 출시 전인데 나왔다고 썼는지,
  끝난 행사인지, 통계 기준 해가 다른데 '올해'라고 썼는지 알려 줘요. --fetch 를 주면 dates 에 없는 출처의 발행일을 기사에서 읽어 와요.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAYS = 60  # 이만큼 지난 콘텐츠까지 견줘요 (쇼츠 60일 규칙과 같게)
DATES_FROM = "2026-10-24"  # dates 칸 규칙이 처음 쓰이는 날. 그 전 설계도는 dates 가 없어도 알리지 않아요(지난 기록은 고치거나 채우지 않음)

# 뜻이 같은 이름. 앞의 말로 모아 셉니다. 새로 겹친 말을 찾으면 여기에 더해요.
SYNONYMS = {
    "찹쌀떡": ["모찌", "모찌떡", "다이후쿠", "찹쌀모찌"],
    "떡볶이": ["떡뽁이", "떡볶기"],
    "치킨": ["통닭", "후라이드치킨", "프라이드치킨"],
    "삼겹살": ["오겹살"],
    "짜장면": ["자장면"],
    "꽃게": ["숫꽃게", "수꽃게", "암꽃게"],
    "버거": ["햄버거"],
}
# 같은 '일'을 가리키는 말
CONCEPTS = {
    "줄서기": ["줄 서", "줄서", "줄을 서", "오픈런", "대기줄", "웨이팅", "줄이 섰", "줄이 서"],
    "품절": ["품절", "완판", "동나"],
    "출시": ["출시", "나와요", "나왔", "선보", "내놓"],
    "값오름": ["올랐", "인상", "오른다", "↑"],
    "값내림": ["내렸", "인하", "떨어졌", "↓"],
}
STOP = set("""요즘 오늘 이번 지난 올해 작년 우리 여러분 정말 진짜 그냥 이거 그거 저거 무엇 어디 언제 얼마 때문 사람 사람들
먹고갈지도 먹거리 음식 메뉴 소식 뉴스 카드 영상 쇼츠 이야기 정리 댓글 여러분은 알려 주세요 있어요 했어요 해요 돼요 나요 거예요
가장 많이 조금 아주 너무 다시 함께 같이 하나 두 세 네 다섯 처음 마지막 지금 이제 벌써 아직 바로 그래서 그런데 하지만
or OR 먹고갈지 갈까 먹지 보고 가지 오늘의
TOP 저녁 저녁메뉴 저녁메뉴추천 오늘뭐먹지 저녁뭐먹지 메뉴추천 불금 월요일 화요일 수요일 목요일 금요일 토요일 일요일 주말 평일
상황 실화 왔어 골라서 거예 장바구니물가 장바구니물 먹거리뉴스 오늘의뉴스 카드뉴스
얼마나 나왔나 골라 추천 당기 생각나 지역 따라 사정 기간 까닭 비용 물량 정부 무게 여행 떠나 협업 원대 이달 산지 숫자 하나씩
이유 이름 누적 판매 매출 출시 신상 신제품 인기 화제 유행 가격 값 기준 자료 발표 조사 보도 기사 사진 출처 됐어 됐다 됐대 했다 한다""".split())
JOSA = re.compile(r"(으로|에서|까지|부터|이에요|예요|이랑|랑|하고|에게|한테|처럼|보다|만큼|이나|이면|으로는|에는|에선|은|는|이|가|을|를|에|의|도|로|와|과|요|만)$")
VERB = re.compile(r"(려고|었어|았어|였어|했어|졌어|봤어|랐어|렸어|됐어|줄게|할게|볼게|을까|어요|아요|다며|대요|래요|해요|네요|세요|죠|는데|어서|아서|으면|거든|셔|보면|하면)$")  # 말끝은 이름이 아니에요
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(만\s*개|만\s*명|만\s*원|억\s*원|천\s*원|개|%|원|kg|명|배|곳|위|건|잔|봉)")
NEW_WORDS = re.compile(r"나왔|출시됐|출시했|선보였|팔리고|판매 중|판매하고|팔렸")  # "나와요"는 앞으로도 뜻해 빼요
SOON_WORDS = re.compile(r"예정|나온다|나올|부터|출시 전|곧")
SYN = {v.lower(): k for k, vs in SYNONYMS.items() for v in vs + [k]}


def words(text):
    """글에서 이름이 될 만한 낱말(두 글자 이상, 조사 떼고, 뜻이 같은 말은 하나로)."""
    out = set()
    for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", text or ""):
        w = JOSA.sub("", w) if re.search(r"[가-힣]", w) else w
        if len(w) < 2 or w in STOP or w[0].isdigit() or VERB.search(w):
            continue
        out.add(SYN.get(w.lower(), w))
    for v, k in SYN.items():  # 붙여 쓴 말 속의 이름도 (고디바모찌 → 찹쌀떡)
        if len(v) >= 2 and v in (text or "").lower():
            out.add(k)
    return out


def concepts(text):
    return {k for k, vs in CONCEPTS.items() if any(v in (text or "") for v in vs)}


def numbers(text):
    return {(re.sub(r"[,\s]", "", a) + re.sub(r"\s", "", b)) for a, b in NUM.findall(text or "")}


def marked(text):
    """[[ ]] 로 강조한 말 — 그 콘텐츠의 주인공일 때가 많아요."""
    return set().union(*[words(m) for m in re.findall(r"\[\[(.+?)\]\]", text or "")] or [set()])


def short_url(u):
    u = u.get("url", "") if isinstance(u, dict) else u
    u = re.sub(r"^https?://(www\.|m\.)?", "", (u or "").strip()).split("#")[0]
    return u.rstrip("/").split("?")[0] if "idxno=" not in u and "id=" not in u else u.rstrip("/")


def flat(x):
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(flat(i) for i in x)
    if isinstance(x, dict):  # 화면에 나오는 글 칸만 (anim·layout 같은 설정 값은 빼요)
        return " ".join(flat(v) for k, v in x.items() if k in TEXT_KEYS or isinstance(v, (list, dict)) and k not in SKIP_KEYS)
    return ""


TEXT_KEYS = set("""title summary headline say line chip fact why note items label kicker sub head points ask name text big ribbon
k v q item caption_line menu food dish""".split())
SKIP_KEYS = set("photo photos crop pos fit credit credits music thumb_photo inset base marks anim layout meta".split())


def unit(uid, day, kind, label, key_text, body_text, urls, sent):
    keys = words(key_text) | marked(body_text)
    return {"id": uid, "date": day, "kind": kind, "label": label.replace("\n", " ").replace("[[", "").replace("]]", "")[:60],
            "keys": keys, "words": keys | words(body_text), "concepts": concepts(body_text + " " + key_text),
            "numbers": numbers(body_text), "urls": {short_url(u) for u in urls if u}, "sent": sent}


def units_of_spec(spec, day, name, sent):
    """설계도 하나를 견줄 덩어리로. 여러 소식을 담는 카드(소식·유행)는 장마다 따로, 나머지는 통째로."""
    head = " ".join(flat(spec.get(k)) for k in ("subject", "yt_keyword", "yt_related", "tags", "yt_tags"))
    urls = spec.get("sources") or []
    kind = spec.get("kind") or spec.get("format") or name
    out = []
    cards = spec.get("cards") or []
    if cards and spec.get("format") == "cards" and spec.get("mode") not in ("story",) and kind in ("소식", "유행"):
        for i, c in enumerate(cards, 1):
            if c.get("type") == "summary":
                continue
            text = flat({k: c.get(k) for k in ("headline", "fact", "why", "note", "say", "rows", "ribbon", "src", "big")})
            out.append(unit(f"{day}/{name}#{i}", day, kind, c.get("headline") or text, flat([c.get("headline"), c.get("fact"), c.get("name")]), text,
                            c.get("sources") or [], sent))
        return out
    body = flat({k: spec.get(k) for k in ("title", "summary", "headline", "cover", "cards", "scenes", "lines", "top", "slides")})
    out.append(unit(f"{day}/{name}", day, kind, spec.get("title") or spec.get("subject") or name, head, body, urls, sent))
    return out


def load_history(before, skip=None):
    """before 날짜보다 앞선 DAYS 일 안의 콘텐츠 덩어리 목록."""
    sent_v = set(json.loads((ROOT / "state/sent_videos.json").read_text(encoding="utf-8"))) if (ROOT / "state/sent_videos.json").exists() else set()
    sent_i = set(json.loads((ROOT / "state/sent.json").read_text(encoding="utf-8"))) if (ROOT / "state/sent.json").exists() else set()
    posted = {e["id"] for e in json.loads((ROOT / "state/blog_posted.json").read_text(encoding="utf-8"))} if (ROOT / "state/blog_posted.json").exists() else set()
    lo = date.fromordinal(before.toordinal() - DAYS)
    units = []

    def inside(day):
        try:
            d = date.fromisoformat(day)
        except ValueError:
            return False
        return lo <= d < before

    for p in sorted((ROOT / "videos").glob("*/*.json")):
        day = p.parent.name
        if not inside(day) or (skip and p.resolve() == skip):
            continue
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        units += units_of_spec(spec, day, p.stem, f"{day}-{p.stem}" in sent_v)
    for p in sorted((ROOT / "items").glob("*/*.json")):
        day = p.parent.name
        if not inside(day):
            continue
        it = json.loads(p.read_text(encoding="utf-8"))
        text = flat({k: it.get(k) for k in ("title", "summary", "facts", "angle")})
        units.append(unit(f"{day}/items/{p.stem}", day, "소식 글", it.get("title", p.stem), flat([it.get("subject"), it.get("region")]),
                          text, it.get("sources") or [], it.get("id") in sent_i))
    for p in sorted((ROOT / "blog").glob("*.json")):
        b = json.loads(p.read_text(encoding="utf-8"))
        day = b.get("date", p.stem[:10])
        if not inside(day):
            continue
        text = flat([b.get("title"), [x.get("text") for x in b.get("blocks", []) if isinstance(x, dict) and x.get("type") in ("p", "h2", "h3")][:6]])
        units.append(unit(f"{day}/blog/{p.stem}", day, "블로그", b.get("title", p.stem), flat([b.get("subject"), b.get("keyword"), b.get("tags")]),
                          text, [], b.get("id") in posted))
    return units


def score(a, b, df):
    """겹친 정도와 까닭. 흔한 말은 덜 셉니다."""
    def w(x):  # 지난 콘텐츠 여러 곳에 나온 말일수록 덜 셉니다. 전체에서 차지하는 비율로 봐요(같은 소재를 자주 되풀이할수록 덜 잡히지 않게)
        n, total = df.get(x, 0), max(df.get("__total__", 1), 1)
        return 0 if n > max(6, total * 0.08) else 0.5 if n > max(2, total * 0.04) else 1

    why, s = [], 0.0
    shared_url = a["urls"] & b["urls"]
    if shared_url:
        s += 5
        why.append("같은 기사")
    keys = {x for x in a["keys"] & b["keys"] if w(x)}  # 둘 다 주인공으로 내세운 이름(태그·핵심 키워드·주제·[[ ]])
    ks = sum(3 * w(x) for x in keys)
    others = {x for x in (a["words"] & b["words"]) - keys if w(x)}
    os_ = sum(w(x) for x in others)
    con = a["concepts"] & b["concepts"] - {"출시"}
    s += ks + min(os_, 3) + (2 * len(con) if keys else 0)
    nums = {n for n in a["numbers"] & b["numbers"] if not n.endswith("위")}  # '1위' 같은 순위는 흔해서 빼요
    if nums and keys:
        s += 2
    names = sorted(x for x in keys if w(x)) + sorted(x for x in others if w(x))[:3]
    if names:
        why.append("같은 말: " + ", ".join(names[:6]))
    if con:
        why.append("같은 일: " + ", ".join(sorted(con)))
    if nums:
        why.append("같은 숫자: " + ", ".join(sorted(nums)))
    return s, why, keys


def same_monthly_set(a, b):
    """'2026-10-15/1-check' 와 '2026-10-12/1-monthly' 처럼 같은 달의 달마다 만드는 제철 묶음인지."""
    ma, mb = re.match(r"(\d{4}-\d{2})-\d{2}/1-", a), re.match(r"(\d{4}-\d{2})-\d{2}/1-", b)
    return bool(ma and mb and ma.group(1) == mb.group(1))


def compare(cands, history, followup=None):
    df = {"__total__": len(history)}
    for u in history:
        for x in u["words"]:
            df[x] = df.get(x, 0) + 1
    lines = []
    for c in cands:
        hits = []
        for h in history:
            if same_monthly_set(c["id"], h["id"]):
                continue  # 매달 1일에 함께 만드는 이달의 제철 묶음(1-*)끼리는 일부러 같은 소재를 다뤄요
            dinner = c["kind"] == "저녁" or h["kind"] == "저녁"
            if dinner and c["kind"] != h["kind"]:
                continue  # 저녁 추천은 정보가 아니라 고르기라 다른 콘텐츠와 견주지 않아요
            s, why, keys = score(c, h, df)
            if dinner:
                keys = keys - {"맥주", "소주", "막걸리", "하이볼", "와인", "사이다", "콜라"}  # 곁들이는 술은 메뉴가 아니에요
            if dinner and (len(keys) < 3 or (date.fromisoformat(c["date"]) - date.fromisoformat(h["date"])).days > 7):
                continue  # 저녁끼리는 7일 안에 메뉴가 셋 넘게 겹칠 때만 (dinner.md: 4개가 똑같이 겹치지 않게)
            if s >= 6 and (keys or "같은 기사" in why):
                hits.append((s, h, why))
        hits.sort(key=lambda x: -x[0])
        for s, h, why in hits[:3]:
            ago = (date.fromisoformat(c["date"]) - date.fromisoformat(h["date"])).days
            new_nums = c["numbers"] - h["numbers"]
            ofs = (followup or {}).get("of") or []
            ofs = ofs if isinstance(ofs, list) else [ofs]  # 여러 지난 콘텐츠의 후속일 수 있어요
            fu = any(h["id"] == o or ("#" not in str(o) and h["id"].startswith(str(o))) for o in ofs)
            if fu:
                verdict = f"후속편으로 적어 둠 ({followup.get('new', '무엇이 새로운지 비어 있음')})"
            elif new_nums and set(c["concepts"] & h["concepts"]) - {"출시", "값오름", "값내림"} and s >= 6:
                verdict = ("같은 메시지 반복 의심 — 지난번과 같은 일을 같은 말로 전해요. 새 숫자(" + ", ".join(sorted(new_nums)) +
                           ")가 진짜 새 사실이면 그 숫자를 앞세운 후속편으로 쓰고 followup 칸에 적고, 아니면 소재를 바꿔 주세요")
            elif new_nums:
                verdict = "후속 가능 — 지난번에 없던 숫자: " + ", ".join(sorted(new_nums)) + " (followup 칸에 무엇이 새로운지 적어 주세요)"
            else:
                verdict = "반복 의심 — 새 숫자·새 사실이 안 보여요. 소재를 바꾸거나 새로 확인된 사실을 더해 주세요"
            lines.append(f"  이력: {c['label'][:30]} ↔ {h['id']} '{h['label'][:30]}' ({ago}일 전, {h['kind']}, {'보냄' if h['sent'] else '안 보냄'}, 점수 {s:g})"
                         f" · {' · '.join(why)} → {verdict}")
    return lines


# ---------- 날짜 ----------

def to_date(x):
    if not x:
        return None
    m = re.search(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", str(x))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def fetch_dates(url):
    """기사 페이지에서 발행일·수정일 (news.py 와 같은 방법)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import news
    raw = news.get(news.original_url(url), headers=news.BROWSER, timeout=30)
    page = news._decode(raw)
    return {"url": url, "published": (news._meta(page, "article:published_time") or news._meta(page, "og:regDate") or news._meta(page, "pubdate"))[:16],
            "modified": news._meta(page, "article:modified_time")[:16]}


def date_lines(spec, day, fetch=False):
    """dates 칸을 보고 날짜가 어긋난 곳을 알려 줘요. 소식·유행 카드는 장마다 dates 를 따로 적을 수 있어요."""
    out = []
    today = date.fromisoformat(day)
    kind = spec.get("kind", "")
    newsy = kind in ("소식", "유행") or "이슈" in flat(spec.get("kicker"))
    blocks = [("", spec.get("dates") or {}, flat({k: spec.get(k) for k in ("title", "summary", "headline", "cover", "scenes", "lines", "thumb")}), spec.get("sources") or [])]
    for i, c in enumerate(spec.get("cards") or [], 1):
        if c.get("dates"):
            blocks.append((f"{i}장 ", c["dates"], flat({k: c.get(k) for k in ("headline", "fact", "why", "say", "note")}), []))
    everything = json.dumps(spec, ensure_ascii=False)
    new_rule = day >= DATES_FROM  # 새 콘텐츠만 빠진 날짜를 알려요. 지난 콘텐츠는 실제로 어긋난 것만
    if new_rule and not spec.get("dates") and not any(b[1] for b in blocks[1:]):
        out.append("날짜: dates 칸이 없어요. 출처 기사 발행일·출시일·행사 기간·통계 기준·확인일을 적어 주세요(PROMPT.md \"날짜 구분\").")
    elif new_rule:
        dated = {s.get("url") for b in blocks for s in (b[1].get("sources") or [])}
        missing = [u for u in (spec.get("sources") or []) if isinstance(u, str) and u not in dated]
        if missing and not fetch:
            out.append(f"날짜: 출처 {len(missing)}곳의 기사 발행일이 dates.sources 에 없어요(추정하지 말고 기사에서 확인해 적어 주세요). 예: {missing[0][:70]}")
    for where, d, text, urls in blocks:
        srcs = list(d.get("sources") or [])
        known = {s.get("url") for s in srcs}
        if fetch:
            for u in urls:
                if u not in known:
                    try:
                        srcs.append(fetch_dates(u))
                    except Exception as e:
                        out.append(f"날짜: {where}출처 발행일을 못 읽었어요 ({str(e)[:60]}): {u}")
        for s in srcs:
            p = to_date(s.get("published"))
            if not p:
                continue
            age = (today - p).days
            m = to_date(s.get("modified"))
            note = f" (수정 {m.isoformat()})" if m and m != p else ""
            shown = f"{p.month}월 {p.day}일" in everything or f"{p.month}.{p.day}" in everything
            if age > 3 and newsy and shown:
                out.append(f"날짜: {where}출처가 {age}일 전({p.isoformat()}) 기사인데 날짜를 밝혀 뒀어요. 지금도 맞는지(판매 중·값)만 다시 확인해 주세요.")
            elif age > 3 and newsy:
                out.append(f"날짜: {where}출처가 {age}일 전({p.isoformat()}{note}) 기사예요. 오늘 소식처럼 쓰지 말고 날짜를 밝히거나 새 기사로 확인해 주세요: {s.get('url', '')[:70]}")
            elif age > 7:
                out.append(f"날짜: {where}출처가 {age}일 전({p.isoformat()}{note}) 기사예요. '요즘'·'최근'으로 쓸 때는 지금도 맞는지 다시 확인해 주세요: {s.get('url', '')[:70]}")
        rel = d.get("released")
        rel_day = to_date(rel.get("date") if isinstance(rel, dict) else rel)
        if rel_day and rel_day > today:
            if NEW_WORDS.search(text) and not SOON_WORDS.search(text):
                out.append(f"날짜: {where}출시일이 {rel_day.isoformat()}(아직 전)인데 이미 나온 것처럼 썼어요. '○월 ○일 나와요'·'출시 예정'으로 써 주세요.")
            elif f"{rel_day.month}월 {rel_day.day}일" not in text and f"{rel_day.month}.{rel_day.day}" not in text:
                out.append(f"날짜: {where}출시 전({rel_day.isoformat()})이에요. 화면에 출시 날짜를 밝혀 주세요.")
        ev = d.get("event") or {}
        end = to_date(ev.get("end") if isinstance(ev, dict) else None)
        if end and end < today:
            out.append(f"날짜: {where}행사가 {end.isoformat()}에 끝났어요. 끝난 행사는 소개하지 않아요.")
        sp = str(d.get("stat_period") or "")
        sy = re.search(r"(\d{4})", sp)
        if sy and int(sy.group(1)) != today.year and "올해" in text:
            out.append(f"날짜: {where}통계 기준이 {sp}인데 글에 '올해'라고 썼어요. 기준 해를 밝혀 주세요.")
        if new_rule and not d.get("checked") and d:
            out.append(f"날짜: {where}확인일(checked)이 없어요.")
    return out


# ---------- 실행 ----------

def report_file(path, fetch=False):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    day = path.parent.name if re.match(r"\d{4}-\d{2}-\d{2}$", path.parent.name) else date.today().isoformat()
    history = load_history(date.fromisoformat(day), skip=path)
    lines = compare(units_of_spec(spec, day, path.stem, False), history, spec.get("followup"))
    return lines + ["  " + x for x in date_lines(spec, day, fetch)]


def print_report(path, fetch=False):
    """build.py 가 설계도를 검사할 때 함께 불러요. 알림만 하고 막지는 않아요."""
    for line in report_file(path, fetch):
        print(line)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file"); f.add_argument("path"); f.add_argument("--fetch", action="store_true")
    c = sub.add_parser("check"); c.add_argument("text"); c.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d")); c.add_argument("--url", nargs="*", default=[])
    a = ap.parse_args()
    if a.cmd == "file":
        lines = report_file(a.path, a.fetch)
    else:
        cand = unit("후보", a.date, "후보", a.text, a.text, a.text, a.url, False)
        lines = compare([cand], load_history(date.fromisoformat(a.date)))
    print("\n".join(lines) if lines else "  이력: 겹치는 지난 콘텐츠가 없어요.")


if __name__ == "__main__":
    main()
