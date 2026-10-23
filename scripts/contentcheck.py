# -*- coding: utf-8 -*-
"""사진이 글과 같은 대상을 보여 주는지, 사진을 써도 되는지, 지역 이름·범위가 맞는지 봐요. (2026-10-23 4단계)
읽기만 하고 아무것도 쓰지 않아요. 사진 속 내용을 컴퓨터가 알아보지는 못해요. 설계도에 적힌 shows·match·rights·region 칸과
사진 주소, 잘라 쓴 좌표, 글을 견줘 "사람이 다시 볼 곳"을 알려 줘요.

  python3 scripts/contentcheck.py videos/2026-10-23/4-find.json

설계도에 적는 칸 (PROMPT.md "사진은 내용을 정한 뒤에"):
- 사진마다 `shows`: 사진을 직접 열어 보고 적은, 실제로 찍힌 것("맘스터치 2차 쿵파오싸이버거", "백설기", "인천종합어시장 꽃게 좌판")
           `match`: 정확(글이 말하는 바로 그 음식·상품) / 같은 종류(같은 음식이지만 그 상품·그 가게 것은 아님) / 분위기(장소·풍경)
           `rights`: 사진을 쓸 수 있는 근거("맘스터치·더시그니처 제공, 재판매 및 DB 금지 · 연합뉴스 배포" 처럼 사진 설명 그대로)
- 지역 콘텐츠는 `region`: {"title_scope": 제목이 말하는 범위, "places": [{"name", "address", "admin", "source"}], "foods": [{"name", "why", "source"}]}
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from history import DATES_FROM, SYN, words  # 같은 낱말 다듬기·같은 말 묶음을 다시 써요

ROOT = Path(__file__).resolve().parent.parent
PHOTO_KEYS = {"photo", "photos", "photo_top", "photo_bottom", "inset", "logo", "video"}
TEXT_KEYS = ("title", "headline", "say", "line", "chip", "fact", "why", "note", "label", "name", "k", "v", "item", "big", "ribbon", "head", "sub", "q")
MATCH = ("정확", "같은 종류", "분위기")

# 사진 주소로 본 출처 갈래 (등록부 sources.json photo_rights 에 없는 주소에 써요)
PRESS = re.compile(r"(yna\.co\.kr|newsis\.com|news1\.kr|mt\.co\.kr|hankyung\.com|chosun|joongang|donga\.com|hani\.co\.kr|khan\.co\.kr|"
                   r"heraldcorp|sedaily|mk\.co\.kr|edaily|fnnews|asiae|etoday|segye\.com|kmib|nocutnews|ytn|sbs\.co\.kr|kbs\.co\.kr|imbc|jtbc|"
                   r"wikitree|pinpointnews|topdaily|insightkorea|hankooki|dailian|newspim|inews24|ajunews|thinkfood|foodbank|foodnews|"
                   r"/news/photo/|news\.)", re.I)
PR_WIRE = re.compile(r"prcdn\.freetls\.fastly\.net|prtimes|newswire", re.I)
SHOP = re.compile(r"011st|coupang|gmarket|auction\.co|ssgcdn|ssg\.com|kurly|cafe24img|naverncp|shop-phinf|shopping\.phinf|smartstore|"
                  r"lotteon|wemakeprice|tmon|11st", re.I)
AI = re.compile(r"AI\s*생성|AI로 (?:만든|생성)|생성형 ?AI|미드저니|midjourney|dall-?e|firefly", re.I)
# 브랜드·회사 이름. 글에 나오면 그 회사 상품 사진(match 정확)이어야 해요
BRANDS = ("CU GS25 세븐일레븐 이마트24 이마트 트레이더스 롯데마트 홈플러스 코스트코 컬리 쿠팡 CJ 비비고 오뚜기 농심 대상 청정원 동원 풀무원 하림 "
          "SPC 파리바게뜨 배스킨라빈스 던킨 맘스터치 롯데리아 맥도날드 버거킹 KFC 스타벅스 투썸 메가커피 빽다방 이디야 노티드 고디바 오리온 "
          "롯데웰푸드 빙그레 해태 삼립 신세계 교촌 BBQ bhc 굽네 노브랜드").split()
PLACES = set("""한국 국내 해외 일본 중국 대만 베트남 태국 미국 영국 프랑스 독일 이탈리아 스페인 홍콩 싱가포르 필리핀 인도
서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주""".split())
# 행정구역이 바뀐 곳: (옛 이름, 시행일, 지금 이름 안내, 근거)
ADMIN_CHANGES = [
    ("인천 중구", "2026-07-01", "중구 내륙은 제물포구, 영종도는 영종구", "인천광역시 제물포구·영종구 및 검단구 설치 등에 관한 법률"),
    ("인천광역시 중구", "2026-07-01", "중구 내륙은 제물포구, 영종도는 영종구", "인천광역시 제물포구·영종구 및 검단구 설치 등에 관한 법률"),
    ("인천 동구", "2026-07-01", "제물포구", "인천광역시 제물포구·영종구 및 검단구 설치 등에 관한 법률"),
    ("인천광역시 동구", "2026-07-01", "제물포구", "인천광역시 제물포구·영종구 및 검단구 설치 등에 관한 법률"),
]


def text_of(d):
    return " ".join(str(d.get(k)) for k in TEXT_KEYS if isinstance(d.get(k), (str, int, float)))


def items_of(spec):
    """(자리 이름, 그 자리의 글, 사진 dict) 목록. 사진은 가장 가까운 글과 묶어요(장면·장·문장, 그 안의 칸)."""
    out = []

    def walk(o, where, ctx):
        if isinstance(o, dict):
            own = text_of(o)
            here = (own + " " + ctx).strip() if own else ctx
            for k, v in o.items():
                if k in PHOTO_KEYS:
                    for i, p in enumerate(v if isinstance(v, list) else [v]):
                        if isinstance(p, dict) and isinstance(p.get("url"), str):
                            out.append((f"{where}.{k}" + (f"[{i}]" if isinstance(v, list) else ""), here, p))
                        elif isinstance(p, dict):
                            walk(p, f"{where}.{k}", here)
                elif isinstance(v, (dict, list)) and k not in ("meta", "dates", "region", "followup", "credits", "sources"):
                    walk(v, f"{where}.{k}", here)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{i + 1}]", ctx)

    for key in ("thumb", "cover", "scenes", "lines", "cards", "top", "slides", "base"):
        if spec.get(key) is not None:
            walk(spec[key], key, "")
    return out


def marked_names(text):
    """[[ ]] 로 강조한 이름(숫자 빼고). 그 자리의 주인공이에요."""
    out = set()
    for m in re.findall(r"\[\[(.+?)\]\]", text or ""):
        out |= words(m)
    return out


def brands_in(text):
    return {b for b in BRANDS if re.search(rf"(?<![A-Za-z가-힣]){re.escape(b)}", text or "")}


def host_kind(url, rights, terms=None, today="9999-12-31"):
    """사진 출처 갈래와 판단. (갈래, 문제 여부, 설명). 문제 여부가 참이면 조건이 확인되기 전에는 게시용으로 쓰지 않아요.
    2026-10-23 사용자가 정함: "공식 사진은 사용 조건을 확인한 후 활용한다". 판단 순서: 사진마다 적은 terms → sources.json 의 photo_rights → 주소 갈래."""
    r = rights or ""
    if AI.search(r):
        return "AI 생성 그림", True, "AI 로 만든 그림은 실제 음식·제품 사진처럼 쓰지 않아요(사용 불가)"
    if isinstance(terms, dict) and terms.get("ok") and terms.get("url") and terms.get("checked"):
        return "이용 조건 확인한 사진", False, ""
    host = url.split("/")[2] if "://" in url else url.split(":")[0] + ":"
    entry = rights_entry(url, host)
    if entry:
        status = entry.get("status")
        if status == "사용 가능":
            stale = stale_check(entry, today)
            return (entry["name"], True, f"이용 조건을 {entry.get('checked')}에 확인했는데 {entry.get('recheck_days')}일이 지났어요. 다시 확인해 주세요(확인 필요)") if stale else (entry["name"], False, "")
        if status == "사용 불가" and not (PRESS.search(url) and re.search(r"제공|사진\s*[=:]", r)):
            return entry["name"], True, f"{entry.get('note') or '이용 허가가 없어요'}(사용 불가)"
    if entry and entry.get("status") == "확인 필요":
        return entry["name"], True, f"{entry['name']} 사진은 이용 조건을 아직 확인하지 않았어요(sources.json photo_rights). 확인 전에는 게시용으로 쓰지 않아요(확인 필요)"
    if SHOP.search(url):
        return "판매 사이트 사진(자사몰·오픈마켓)", True, "판매자·쇼핑몰 상품 사진은 이용 허가가 없어 쓰지 않아요(사용 불가)"
    if PRESS.search(url):
        if re.search(r"제공|사진\s*[=:]", r) and not re.search(r"기자|연합뉴스 ?사진|뉴스1 ?사진", r):
            return ("언론사 서버의 회사 제공 사진", True,
                    f"사진 설명 '{r[:40]}' — 회사 제공이지만 SNS·영상·블로그 재사용 조건을 확인하지 못했어요. 확인 전에는 게시용으로 쓰지 않아요(확인 필요)")
        return "언론사·기자 사진", True, "언론사 서버의 사진인데 회사 제공 근거(rights)가 없어요. 기자·통신사 사진은 쓰지 않아요(사용 불가)"
    if any(host.endswith(c) for c in company_hosts()):
        return "회사 공식 누리집", True, "회사 공식 사진이지만 이용 조건을 확인하지 못했어요. 확인 전에는 게시용으로 쓰지 않아요(확인 필요)"
    if "staticflickr" in host:
        return "플리커", True, "플리커 사진은 사진마다 라이선스를 확인해야 해요(확인 필요)"
    return "출처 불명", True, f"어디 사진인지 모르는 주소예요({host or url[:30]}). 쓰지 않아요(사용 불가)"


_RIGHTS = None


def rights_entry(url, host):
    """sources.json 의 photo_rights 에서 이 사진 주소에 맞는 항목."""
    global _RIGHTS
    if _RIGHTS is None:
        _RIGHTS = json.loads((ROOT / "sources.json").read_text(encoding="utf-8")).get("photo_rights", [])
    for e in _RIGHTS:
        for h in e.get("hosts", []):
            if (h.endswith(":") and url.startswith(h)) or (not h.endswith(":") and ("/" in h and h in url or host.endswith(h))):
                return e
    return None


def stale_check(entry, today):
    """사용 가능으로 적힌 조건도 recheck_days 마다 다시 확인해요(정책이 바뀔 수 있어요)."""
    from datetime import date
    try:
        return (date.fromisoformat(today) - date.fromisoformat(entry.get("checked", ""))).days > int(entry.get("recheck_days") or 90)
    except ValueError:
        return False


_COMPANY = None


def company_hosts():
    global _COMPANY
    if _COMPANY is None:
        cfg = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
        urls = [p["url"] for p in cfg.get("pages", []) if p.get("use") in ("편의점", "식품기업", "프랜차이즈")]
        urls += [r["url"] for r in cfg.get("rss", []) if r.get("group") == "식품기업·프랜차이즈"]
        _COMPANY = {re.sub(r"^www\.", "", u.split("/")[2]) for u in urls}
    return _COMPANY


def photo_lines(spec, day):
    new_rule = day >= DATES_FROM
    # 그 콘텐츠가 이름으로 내세운 음식·상품(태그·유튜브 태그·핵심 키워드·주제). 글에 이 이름이 나오면 사진도 그것이어야 해요
    curated = words(" ".join(json.dumps(spec.get(k) or "", ensure_ascii=False) for k in ("tags", "yt_tags", "yt_keyword", "yt_related", "subject")))
    curated -= {"먹고갈지도", "수출", "출시", "협업", "신메뉴", "신상"} | PLACES  # 나라·지역 이름은 사진에 찍힐 대상이 아니에요(지역 사진은 region 으로 봐요)
    out, seen_crop, by_url = [], {}, {}
    for where, text, p in items_of(spec):
        url = p["url"]
        shows, match, rights = p.get("shows", ""), p.get("match", ""), p.get("rights", "")
        # 1) 출처와 쓸 수 있는지
        kind, bad, why = host_kind(url, rights, p.get("terms"), day)
        if bad or why:
            out.append(("사진 권리", f"{where}: {kind} — {why}", bad))
        # 2) 한 사진을 좌표로 여러 번 잘라 씀(맘스터치 사례)
        crop = tuple(p.get("crop") or ())
        by_url.setdefault(url, set()).add(crop)
        if crop:
            seen_crop.setdefault((url, crop), []).append((where, words(text), shows))
        # 3) 사진이 글과 같은 대상인지 (shows·match 가 있어야 볼 수 있어요)
        if new_rule and not shows:
            out.append(("사진 일치", f"{where}: shows(사진에 실제로 찍힌 것)가 없어요. 사진을 열어 보고 적어 주세요", True))
        if new_rule and match not in MATCH:
            out.append(("사진 일치", f"{where}: match 를 정확/같은 종류/분위기 가운데 하나로 적어 주세요", True))
        if shows and match != "분위기":
            want = {w for w in words(text) if w in curated}
            have = words(shows) | {SYN.get(w.lower(), w) for w in words(shows)}
            miss = sorted(w for w in want if w not in have and not any(w in h or h in w for h in have))
            if miss:
                out.append(("사진 일치", f"{where}: 글에 나온 이름 '{'·'.join(miss)}'이(가) 사진(shows: {shows[:30]})에 없어요. 그 대상이 찍힌 사진으로 바꾸거나 사진 없는 장으로", True))
        said, seen_ = set(re.findall(r"(\d+)차", text)), set(re.findall(r"(\d+)차", shows))
        if said and seen_ and not said & seen_:  # 1차 협업 이야기에 2차 신제품 사진 (맘스터치 사례)
            out.append(("사진 일치", f"{where}: 글은 {'·'.join(sorted(said))}차인데 사진은 {'·'.join(sorted(seen_))}차 제품이에요", True))
        for b in sorted(brands_in(text)):
            if match == "분위기" or not shows:
                continue
            if match != "정확" or b not in shows:
                out.append(("사진 일치", f"{where}: 글은 {b} 상품을 말하는데 사진은 그 상품이 아니에요(match {match or '없음'}, shows: {shows[:30]}). 다른 가게·다른 회사 같은 종류 사진으로 대신하지 않아요", True))
    for url, crops in by_url.items():
        crops.discard(())
        if len(crops) >= 2:
            noted = all(s for (u, c), lst in seen_crop.items() if u == url for (_, _, s) in lst)
            if not noted:
                out.append(("사진 일치", f"한 사진({url[-45:]})을 좌표로 {len(crops)}번 잘라 썼어요. 여러 제품이 함께 찍힌 사진이면 잘라 낸 조각마다 직접 열어 보고 shows 에 무엇인지 적어 주세요(맘스터치 사례). 어느 것이 어느 제품인지 모르면 통째로 쓰거나 사진 없는 장으로", True))
    for (url, crop), lst in seen_crop.items():
        names = [n for _, n, _ in lst]
        differ = any(len(a & b) * 2 < max(len(a), len(b)) for i, a in enumerate(names) for b in names[i + 1:] if a and b)
        if len(lst) >= 2 and differ:  # 같은 조각을 쓴 자리끼리 글이 반도 안 겹치면 다른 대상을 말하는 것으로 봐요
            places = ", ".join(w for w, _, _ in lst)
            out.append(("사진 일치", f"같은 잘린 조각 {list(crop)}이 서로 다른 대상을 말하는 자리 {places} 에 함께 쓰였어요. 한 조각은 한 대상만 보여 줘요", True))
    return out


def region_lines(spec, day):
    out = []
    head = " ".join(str(spec.get(k) or "") for k in ("title", "subject", "yt_title", "yt_keyword", "kicker", "summary"))
    head += " " + json.dumps(spec.get("thumb") or {}, ensure_ascii=False) + " " + json.dumps(spec.get("cover") or {}, ensure_ascii=False)
    for s in spec.get("scenes") or []:
        head += " " + str(s.get("kicker") or "") + " " + str(s.get("title") or "")
    allt = head + " " + str(spec.get("caption") or "")
    for old, since, now, law in ADMIN_CHANGES:
        flat_head = head.replace("\n", " ")
        bare = [m for m in re.finditer(re.escape(old), flat_head)
                if not re.search(r"지금|현재|제물포구|영종구", flat_head[m.end():m.end() + 14]) and not flat_head[max(0, m.start() - 3):m.start()].endswith("옛 ")]
        if day >= since and bare:  # "인천 중구(지금은 제물포구)"·"옛 인천 중구"처럼 밝힌 것은 괜찮아요
            out.append(("지역", f"'{old}'는 {since}부터 바뀐 이름이에요({now}, 근거: {law}). 지금 이름으로 쓰거나 '옛 {old.split()[-1]}'처럼 밝혀 주세요", True))
    reg = spec.get("region")
    local = spec.get("kind") == "지역"
    if not reg:
        if local and day >= DATES_FROM:
            out.append(("지역", "region 칸이 없어요. 소개한 장소마다 공식 주소·지금 관할(구)·근거, 제목이 말하는 범위(title_scope), 먹거리마다 그 지역과의 관계(why·source)를 적어 주세요", True))
        return out
    places = reg.get("places") or []
    admins = {p.get("admin", "") for p in places if p.get("admin")}
    gus = {re.findall(r"(\S+[구군시])$", a)[0] if re.findall(r"(\S+[구군시])$", a) else a for a in admins}
    scope = reg.get("title_scope", "")
    for p in places:
        if not (p.get("address") and p.get("source")):
            out.append(("지역", f"{p.get('name', '?')}: 공식 주소(address)와 근거(source)가 없어요. 지자체·관광공사·법령 자료로 확인해 주세요", True))
    if scope and gus and not any(g in scope for g in gus) and len(gus) == 1:
        g = next(iter(gus))
        out.append(("지역", f"제목 범위는 '{scope}'인데 소개한 곳 {len(places)}곳이 모두 {g}예요. 제목을 '{scope} {g}'처럼 좁히거나 다른 구의 먹거리도 고르게 다뤄 주세요", True))
    if scope and scope not in head:
        out.append(("지역", f"title_scope '{scope}'가 제목·썸네일에 그대로 없어요. 제목이 실제 범위를 말하는지 확인해 주세요", False))
    for f in reg.get("foods") or []:
        if not (f.get("why") and f.get("source")):
            out.append(("지역", f"{f.get('name', '?')}: 그 지역과 어떤 관계인지(why)와 근거(source)가 없어요. 거기서 판다는 것만으로 대표 음식이라고 쓰지 않아요", True))
    return out


def report_file(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    day = path.parent.name if re.match(r"\d{4}-\d{2}-\d{2}$", path.parent.name) else "9999-12-31"
    return [f"  {kind}: {msg}" for kind, msg, _ in photo_lines(spec, day) + region_lines(spec, day)]


def print_report(path):
    """build.py 가 설계도를 검사할 때 함께 불러요. 알려 주기만 하고 막지는 않아요(막는 것은 5단계)."""
    for line in report_file(path):
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lines = report_file(sys.argv[1])
    print("\n".join(lines) if lines else "  사진·지역: 알릴 것이 없어요.")
