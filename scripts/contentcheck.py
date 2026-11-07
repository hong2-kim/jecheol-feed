# -*- coding: utf-8 -*-
"""사진이 글과 같은 대상을 보여 주는지, 사진을 써도 되는지, 지역 이름·범위가 맞는지 봐요. (2026-10-23 4단계)
읽기만 하고 아무것도 쓰지 않아요. 사진 속 내용을 컴퓨터가 알아보지는 못해요. 설계도에 적힌 shows·match·rights·region 칸과
사진 주소, 잘라 쓴 좌표, 글을 견줘 "사람이 다시 볼 곳"을 알려 줘요.

  python3 scripts/contentcheck.py videos/2026-10-23/4-find.json

설계도에 적는 칸 (PROMPT.md "사진은 내용을 정한 뒤에"):
- 사진마다 `shows`: 사진을 직접 열어 보고 적은, 실제로 찍힌 것("맘스터치 2차 쿵파오싸이버거", "백설기", "인천종합어시장 꽃게 좌판")
           `match`: 정확(글이 말하는 바로 그 음식·상품) / 같은 종류(같은 음식이지만 그 상품·그 가게 것은 아님) / 분위기(장소·풍경)
           2026-11-07부터: 특정 상품을 말하는 장면(그 회사 상품을 다루는 쇼츠의 모든 문장, 브랜드 이름이 든 카드)은 `정확` 만.
           음식 일반을 말하는 문장·장은 그 문장에 "general": true 를 적고 같은 종류 참고 사진을 쓸 수 있어요.
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
PHOTO_KEYS = {"photo", "photo2", "photos", "photo_top", "photo_bottom", "inset", "logo", "video"}
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

    def walk(o, where, ctx, gen=False, about=""):
        if isinstance(o, dict):
            own = text_of(o)
            here = (own + " " + ctx).strip() if own else ctx
            gen = gen or o.get("general") is True  # 그 상품이 아니라 음식 일반을 말하는 문장·장 (2026-11-06)
            about = str(o.get("about") or about)  # 이 문장·장이 설명하는 대상 (2026-11-06 장면별 판단)
            for k, v in o.items():
                if k in PHOTO_KEYS:
                    for i, p in enumerate(v if isinstance(v, list) else [v]):
                        if isinstance(p, dict) and isinstance(p.get("url"), str):
                            extra = {"_general": True} if gen else {}
                            if p.get("about") or about:
                                extra["_about"] = str(p.get("about") or about)  # 사진마다 적은 about 이 먼저(비교 장면의 두 장)
                            out.append((f"{where}.{k}" + (f"[{i}]" if isinstance(v, list) else ""), here, {**p, **extra}))
                        elif isinstance(p, dict):
                            walk(p, f"{where}.{k}", here, gen, about)
                elif k == "grid" and isinstance(v, list) and isinstance(o.get("hl"), int):
                    # 저녁 2×2: 그 문장이 말하는 음식은 밝힌 칸(hl, 0부터) 하나예요. 나머지 칸은 그 문장과 견주지 않아요 (2026-10-24)
                    for i, c in enumerate(v):
                        walk(c, f"{where}.{k}[{i + 1}]", here if i == o["hl"] else "", gen, about)
                elif isinstance(v, (dict, list)) and k not in ("meta", "dates", "region", "followup", "credits", "sources"):
                    walk(v, f"{where}.{k}", here, gen, about)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{i + 1}]", ctx, gen, about)

    for key in ("thumb", "cover", "scenes", "lines", "cards", "top", "slides", "base"):
        if spec.get(key) is not None:
            walk(spec[key], key, "")
    return out


GENERIC = set("""먹고갈지도 신상 신제품 제품 상품 출시 후속 후속작 리뉴얼 한정 누적 판매 매출 편의점 디저트 간식 음식 브랜드 이번 새로
요즘 유행 가격 할인 캠페인 행사 응모 경품 팔린 팔렸대 넘게""".split())
# 문장이 '그 상품' 이야기라는 단서. 이런 말이 있는데 general 로 적으면 막아요.
# 브랜드 이름만으로는 막지 않아요("GS25 군고구마 매출"은 음식 일반일 수 있어요).
PRODUCT_CUES = re.compile(r"신제품|신상품|후속|출시|리뉴얼|재출시|팔렸|판매량|누적 판매|이 제품|이 상품|새로 나온|새로 낸|한정판|패키지|포장")


def name_words(text):
    return re.findall(r"[가-힣A-Za-z]{2,}", str(text or ""))


def product_of(spec):
    """콘텐츠가 한 회사 상품을 다루는지(내레이션·발견형·해설 쇼츠). {"brands", "heads", "specific", "names"} 또는 None.
    heads: 상품 이름 끝말('츄러스'·'도시락'), specific: 그 상품만의 이름 낱말('쫀득'·'롱롱'·'혜자로운'), names: 상품 이름들.
    상품 이름은 설계도 "products"(적으면 먼저), dates.released.name, 제목·썸네일 [[ ]], 주제에서 모아요.
    장면이 이 상품을 말하는지는 장면마다 따로 봐요(scene_of, 2026-11-06 사용자: 제목에 브랜드가 있다고 모든 장면을 막지 않아요).
    소식이 여럿인 카드 뉴스는 장마다 글로 보니 여기서는 빼요."""
    if spec.get("format") == "cards" or spec.get("cards"):
        return None
    head = " ".join(str(spec.get(k) or "") for k in ("subject", "title", "yt_keyword", "headline"))
    brands = brands_in(head)
    if not brands:
        return None
    released = (spec.get("dates") or {}).get("released")
    names = [str(x) for x in spec.get("products") or []]
    if isinstance(released, dict) and released.get("name"):
        names.append(str(released["name"]))
    names += re.findall(r"\[\[(.+?)\]\]", " ".join(str(t or "") for t in (spec.get("headline"), (spec.get("thumb") or {}).get("head"))))
    heads, specific = set(), set()
    for m in names:
        ws = [w for w in name_words(m) if w not in brands]
        if ws:
            heads.add(ws[-1])  # '초코 쫀득 츄러스' → '츄러스' (우리말 이름은 끝말이 그 물건이에요)
            specific |= set(ws[:-1])
    specific |= {w for w in name_words(spec.get("subject")) if w not in brands}
    specific -= heads | GENERIC | brands | PLACES
    heads -= GENERIC
    return {"brands": brands, "heads": heads, "specific": specific, "names": names}


def scene_of(text, p, prod):
    """이 사진 자리가 무엇을 설명하는지: ("상품", 대상) / ("일반", 대상) / ("모름", "") / ("어긋남", 까닭).
    문장·사진에 적은 about(대상)·general 을 먼저 보고, 없으면 문장으로 봐요. general·일반 대상인데 문장이 그 상품 이야기면 '어긋남'."""
    about, general = p.get("_about", ""), bool(p.get("_general"))
    own = sorted(w for w in prod["specific"] if w in text)
    cue = PRODUCT_CUES.search(text)
    this = next((f"이 {h}" for h in prod["heads"] if f"이 {h}" in text), "")
    if about and not general and (brands_in(about) or any(w in about for w in prod["specific"])):
        return "상품", about
    if general or about:
        if own or cue or this:
            return "어긋남", f"general·일반 대상으로 적었지만 문장은 그 상품 이야기예요('{(own or [cue.group(0) if cue else this])[0]}')"
        return "일반", about or "음식 일반"
    if brands_in(text) & prod["brands"] or own or cue or this:
        return "상품", ""
    return "모름", ""


def marked_names(text):
    """[[ ]] 로 강조한 이름(숫자 빼고). 그 자리의 주인공이에요."""
    out = set()
    for m in re.findall(r"\[\[(.+?)\]\]", text or ""):
        out |= words(m)
    return out


def brands_in(text):
    found = {b for b in BRANDS if re.search(rf"(?<![A-Za-z가-힣]){re.escape(b)}", text or "")}
    return {b for b in found if not any(b != o and b in o for o in found)}  # '이마트24' 가 있으면 '이마트' 는 따로 세지 않아요


STOCK = re.compile(r"unsplash\.com|pexels\.com|pixabay\.com")  # 무료 사진 사이트 (2026-11-07)


def host_kind(url, rights, terms=None, today="9999-12-31", platforms=("instagram", "youtube")):
    """사진 출처 갈래와 판단. (갈래, 문제 여부, 설명). 문제 여부가 참이면 조건이 확인되기 전에는 게시용으로 쓰지 않아요.
    2026-10-23 사용자가 정함: "공식 사진은 사용 조건을 확인한 후 활용한다". 판단 순서: 사진마다 적은 terms → sources.json 의 photo_rights → 주소 갈래."""
    r = rights or ""
    if AI.search(r):
        return "AI 생성 그림", True, "AI 로 만든 그림은 실제 음식·제품 사진처럼 쓰지 않아요(사용 불가)"
    if isinstance(terms, dict) and terms.get("ok") and terms.get("url") and terms.get("checked"):
        return "이용 조건 확인한 사진", False, ""
    host = url.split("/")[2] if "://" in url else url.split(":")[0] + ":"
    if url.startswith("vault:press/"):
        # 보관함 press/ 는 바깥 사진을 옮겨 둔 곳이라 보관함 자체가 근거가 아니에요. 원본 페이지(terms.url)의 출처 조건으로 봐요 (2026-11-07)
        src = (terms or {}).get("url") if isinstance(terms, dict) else ""
        if not src:
            return "보관함에 옮긴 바깥 사진", True, "원본 페이지와 이용 조건(terms: url·checked·scope·ok)이 없어요. 원본 조건을 확인해 적어 주세요(확인 필요)"
        url, host = src, (src.split("/")[2] if "://" in src else src)
    entry = rights_entry(url, host)
    if entry:
        status = entry.get("status")
        if status == "사용 가능":
            uses = entry.get("uses") or {}
            no = [pf for pf in platforms if uses.get(pf) in ("미확인", "불가")]
            if no:  # 출처는 사용 가능이어도 이 쓰임(인스타·유튜브·블로그)이 허용되는지 모르면
                return entry["name"], True, f"{entry['name']} 사진을 {'·'.join(no)}에 써도 되는지 확인하지 못했어요(확인 필요)"
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


# 2026-11-06 사용자: 특정 제품을 말하는 장면은 그 제품의 실제 사진만. '참고 사진' 딱지를 달아도 비슷한 다른 음식 사진으로 대신하지 않아요.
# 음식 일반을 말하는 문장·장에 "general": true 를 적으면 그곳만 같은 종류 참고 사진을 쓸 수 있어요.
EXACT_FROM = "2026-11-07"


def festival_scene(spec, where, text):
    """축제를 소개하는 장면인지 (2026-11-06). 카드는 태그가 '축제'인 장, 다른 꼴은 설계도 dates.event 축제 이름이 문장에 나올 때만.
    '축제와 지역 농산물을 엮은 도시락'처럼 축제라는 말만 나오는 문장은 빼요."""
    m = re.match(r"cards\[(\d+)\]", where)
    if m and isinstance(spec.get("cards"), list) and 1 <= int(m.group(1)) <= len(spec["cards"]):
        return (spec["cards"][int(m.group(1)) - 1].get("tag") or "") == "축제"  # cards[N] 은 1부터 세요(gate.py HELD_AT 과 같음)
    if where.startswith("cover"):
        return False
    name = str(((spec.get("dates") or {}).get("event") or {}).get("name") or "")
    words = [w for w in re.split(r"[\s·]+", re.sub(r"제?\d+회|\d{4}", " ", name)) if len(w) >= 2 and w != "축제"]
    return bool(words) and "축제" in name and all(w in text for w in words)


def photo_lines(spec, day, platforms=("instagram", "youtube")):
    new_rule = day >= DATES_FROM
    exact_rule = day >= EXACT_FROM
    prod = product_of(spec) if exact_rule else None
    abouts = {}  # 상품 대상(about)마다 그 대상만의 낱말 — 비교 장면에서 서로 다른 제품 사진인지 봐요
    if prod:
        for _, _, q in items_of(spec):
            a_ = q.get("_about", "")
            if a_ and not q.get("_general") and (brands_in(a_) or any(w in a_ for w in prod["specific"])):
                abouts[a_] = set(name_words(a_)) - prod["brands"] - GENERIC
    # 그 콘텐츠가 이름으로 내세운 음식·상품(태그·유튜브 태그·핵심 키워드·주제). 글에 이 이름이 나오면 사진도 그것이어야 해요
    curated = words(" ".join(json.dumps(spec.get(k) or "", ensure_ascii=False) for k in ("tags", "yt_tags", "yt_keyword", "yt_related", "subject")))
    curated -= {"먹고갈지도", "수출", "출시", "협업", "신메뉴", "신상", "제철", "가을", "겨울", "여름", "봄", "디저트", "간식", "음식", "맛집",
                "먹방", "추천", "가격", "할인", "편의점", "먹스타그램", "요즘", "유행"} | PLACES  # 나라·지역 이름은 사진에 찍힐 대상이 아니에요(지역 사진은 region 으로 봐요)
    out, seen_crop, by_url = [], {}, {}
    items = items_of(spec)
    # 같은 사진(주소·자르기가 같음)을 여러 자리에 다시 쓰면 shows·match·rights 는 한 곳에만 적어도 돼요(저녁 4칸이 문장마다 되풀이돼요, 2026-10-24)
    noted = {}
    for _, _, p in items:
        for k in ("shows", "match", "rights"):
            if p.get(k):
                noted.setdefault((p["url"], tuple(p.get("crop") or ())), {}).setdefault(k, p[k])
    for where, text, p in items:
        p = {**p, **{k: v for k, v in noted.get((p["url"], tuple(p.get("crop") or ())), {}).items() if not p.get(k)}}
        url = p["url"]
        shows, match, rights = p.get("shows", ""), p.get("match", ""), p.get("rights", "")
        # 1) 출처와 쓸 수 있는지
        kind, bad, why = host_kind(url, rights, p.get("terms"), day, platforms)
        if bad or why:  # 사용 불가 → 차단, 확인 필요 → 확인 (5단계 gate.py 가 이 등급으로 발송을 정해요)
            out.append(("사진 권리", f"{where}: {kind} — {why}", "차단" if "(사용 불가)" in why else "확인" if bad else "참고"))
        # 2) 한 사진을 좌표로 여러 번 잘라 씀(맘스터치 사례)
        crop = tuple(p.get("crop") or ())
        by_url.setdefault(url, set()).add(crop)
        if crop:
            seen_crop.setdefault((url, crop), []).append((where, words(text), shows))
        # 3) 사진이 글과 같은 대상인지 (shows·match 가 있어야 볼 수 있어요)
        if new_rule and not shows:
            out.append(("사진 일치", f"{where}: shows(사진에 실제로 찍힌 것)가 없어요. 사진을 열어 보고 적어 주세요", "확인"))
        if new_rule and match not in MATCH:
            out.append(("사진 일치", f"{where}: match 를 정확/같은 종류/분위기 가운데 하나로 적어 주세요", "확인"))
        if shows and match != "분위기":
            want = {w for w in words(text) if w in curated}
            have = words(shows) | {SYN.get(w.lower(), w) for w in words(shows)}
            seen_in = lambda w: w in have or any(w in h or h in w for h in have)
            miss = sorted(w for w in want if not seen_in(w))
            # 2026-11-06 사용자: '참고 사진' 딱지로 다른 대상 사진을 대신 쓰지 않아요. 이미 만든(11-07 전) 설계도는 예전처럼 참고로 낮춰요(다시 만들 때 보류 알림이 가지 않게)
            labeled = not exact_rule and match == "같은 종류" and "참고" in str(p.get("ref") or "")
            star = {w for w in marked_names(text) if w in curated}  # [[ ]] 로 내세운 이름은 꼭 사진에 있어야 해요
            # 글에 나온 이름 가운데 사진에 하나도 없거나, [[ ]] 로 내세운 이름이 없을 때만 (재료 이름까지 다 찍혀야 하는 것은 아니에요)
            if miss and (len(miss) == len(want) or any(not seen_in(w) for w in star)):
                out.append(("사진 일치", f"{where}: 글에 나온 이름 '{'·'.join(miss)}'이(가) 사진(shows: {shows[:30]})에 없어요. 그 대상이 찍힌 사진으로 바꾸거나 사진 없는 장으로", "확인" if match == "정확" else "참고" if labeled else "차단"))
        said, seen_ = set(re.findall(r"(\d+)차", text)), set(re.findall(r"(\d+)차", shows))
        if said and seen_ and not said & seen_:  # 1차 협업 이야기에 2차 신제품 사진 (맘스터치 사례)
            out.append(("사진 일치", f"{where}: 글은 {'·'.join(sorted(said))}차인데 사진은 {'·'.join(sorted(seen_))}차 제품이에요", "차단"))
        general = bool(p.get("_general"))
        kind_ = None
        if prod and shows and not where.startswith("cover"):
            # 장면별 판단 (2026-11-06 사용자): 제품을 소개하는 장면은 그 제품 사진, 후속 제품 비교는 각각의 실제 제품 사진,
            # 음식 일반(츄러스의 역사 등)은 참고 사진 가능. 제품 장면에 다른 제품 사진 + '참고 사진' 딱지는 안 돼요.
            kind_, target = scene_of(text, p, prod)
            if kind_ == "어긋남":
                out.append(("사진 일치", f"{where}: {target}. 그 상품 장면이면 실제 제품 사진을 쓰고 general·일반 about 을 지워 주세요", "차단"))
            elif kind_ in ("상품", "모름") and match == "같은 종류":
                if kind_ == "상품":
                    msg = (f"{where}: 이 장면이 설명하는 대상({target or '·'.join(sorted(prod['brands'])) + ' 상품'})과 달리 사진은 비슷한 다른 음식이에요(shows: {shows[:30]}). "
                           "'참고 사진' 딱지를 달아도 쓰지 않아요. PROMPT.md \"제품 사진 찾는 차례\"(photos.py product)로 그 제품의 실제 사진을 찾아 주세요")
                else:
                    msg = (f"{where}: 이 콘텐츠는 {'·'.join(sorted(prod['brands']))} 상품을 다루는데 이 장면이 무엇을 설명하는지 알 수 없어요(shows: {shows[:30]}). "
                           "문장에 \"about\" 을 적어 주세요: 그 상품이면 \"about\": \"브랜드 제품명\"(실제 제품 사진), 음식 일반이면 \"general\": true(참고 사진 가능)")
                out.append(("사진 일치", msg, "차단"))
            elif kind_ in ("상품", "모름") and match == "분위기" and any(h in shows for h in prod["heads"]):
                hit = next(h for h in prod["heads"] if h in shows)
                out.append(("사진 일치", f"{where}: match 를 분위기로 적었지만 사진에 '{hit}'이(가) 찍혀 있어요(shows: {shows[:30]}). 그 상품이 아니면 같은 종류 사진이라 "
                                         "그 상품 장면에 쓰지 않아요. 실제 제품 사진이나 그 회사 매장·행사 사진으로 바꿔 주세요", "차단"))
            elif kind_ == "상품" and match == "정확":
                # 실제 그 제품인지: 사진에서 알아본 것(브랜드·제품명·포장 글자)을 shows 에 적어요. 비교 장면이면 그 대상만의 이름이 사진에 있어야 해요
                if target in abouts and len(abouts) > 1:
                    own = abouts[target] - set().union(*[v for k_, v in abouts.items() if k_ != target])
                    if own and not any(w in shows for w in own):
                        out.append(("사진 일치", f"{where}: 이 장면은 '{target}' 인데 사진(shows: {shows[:30]})에 '{'·'.join(sorted(own))}' 가 없어요. "
                                                 "비교하는 다른 제품 사진이 아닌지 열어 보고 shows 에 적어 주세요", "차단"))
                known = prod["brands"] | prod["specific"] | prod["heads"] | (abouts.get(target) or set())
                if not any(w in shows for w in known):
                    out.append(("사진 일치", f"{where}: 실제 제품 사진(match 정확)이면 사진에서 무엇으로 알아봤는지(브랜드·제품명·포장 글자·생김새) shows 에 적어 주세요(shows: {shows[:30]})", "차단"))
        for b in sorted(brands_in(text)):
            if match == "분위기" or not shows:
                continue
            if kind_ is not None:
                continue  # 위에서 장면별로 봤어요
            if match == "같은 종류" and exact_rule and general and PRODUCT_CUES.search(text):
                out.append(("사진 일치", f"{where}: general(음식 일반)로 적었지만 글은 {b} 상품 이야기예요('{PRODUCT_CUES.search(text).group(0)}'). 그 상품의 실제 사진을 써 주세요", "차단"))
            elif match == "같은 종류" and exact_rule and general:
                continue  # 음식 일반 장("GS25 군고구마 매출 248%"의 군고구마 사진)은 브랜드 이름이 있어도 장면별로 허용해요 (2026-11-06)
            elif match == "같은 종류" and "참고" in str(p.get("ref") or "") and exact_rule and not general:
                out.append(("사진 일치", f"{where}: 글은 {b} 상품을 말하는데 사진은 비슷한 다른 음식이에요(shows: {shows[:30]}). '참고 사진' 딱지를 달아도 그 상품 장면에는 "
                                         f"실제 제품 사진만 써요(2026-11-06). 실제 제품 사진을 찾거나(PROMPT.md \"제품 사진 찾는 차례\"), 못 찾으면 그 장을 보류해요", "차단"))
            elif not exact_rule and match == "같은 종류" and "참고" in str(p.get("ref") or ""):
                out.append(("사진 일치", f"{where}: {b} 상품 글에 같은 종류 참고 사진({shows[:24]}) — 11-07 전 설계도라 알리기만 해요. 새 설계도는 실제 제품 사진만 써요", "참고"))
            elif match != "정확" or b not in shows:
                out.append(("사진 일치", f"{where}: 글은 {b} 상품을 말하는데 사진은 그 상품이 아니에요(match {match or '없음'}, shows: {shows[:30]}). 실제 제품 사진(회사 배포 사진·공식 SNS·이용 허락이나 조건이 확인된 구매 후기 사진)을 찾고, 끝내 없으면 photo_search 를 적어 그 장만 보류해요", "차단"))
        if "참고" in str(p.get("ref") or ""):
            out.append(("사진 표기", f"{where}: '참고 사진' 딱지(ref)는 2026-11-06부터 쓰지 않아요. 사진 성격을 label 에 적어요(예: '2025년 축제 현장 · 울진군', '사진: ○○ 제공')", "참고"))
        if festival_scene(spec, where, text) and "축제" not in shows and not where.startswith("thumb"):
            # 2026-11-06 사용자: 축제 소식은 실제 축제 현장 사진(올해 → 지난해·이전 회차). 생선 말리기·항구·관광지 사진에 표기만 붙여 대신하지 않아요
            out.append(("사진 일치", f"{where}: 축제 소식인데 축제 현장 사진이 아니에요(shows: {shows[:30]}). 같은 축제의 올해·지난해 현장 사진(전경·부스·방문객·판매장·공연·현수막)을 찾고 shows 에 '2024 죽변항 수산물축제 …'처럼 적어요. 못 찾으면 '축제 현장 사진 미확보'로 보고해요", "확인"))
        elif "축제" in shows and not re.search(r"20\d\d", str(p.get("label") or "") + shows):
            out.append(("사진 표기", f"{where}: 축제 현장 사진이면 촬영 연도(확인된 것만)를 label 에 적어요(예: '2024년 축제 현장 · 울진군')", "참고"))
        if STOCK.search(url) and shows:
            # 2026-11-07 사용자: Unsplash 등 무료 사진은 적극 쓰되, 실제 음식·행사와 다른 사진을 그 현장·그 제품 사진처럼 쓰지 않아요
            if festival_scene(spec, where, text) and "축제" in shows:
                out.append(("사진 일치", f"{where}: 무료 사진 사이트(Unsplash·Pexels·Pixabay) 사진을 축제 현장 사진으로 적었어요(shows: {shows[:30]}). 그 축제를 찍은 사진인지 사진 페이지 설명으로 확인되지 않으면 그 축제 현장 사진으로 쓰지 않아요", "확인"))
            elif match == "정확" and (kind_ == "상품" or brands_in(text)):
                out.append(("사진 일치", f"{where}: 무료 사진 사이트 사진을 그 상품의 실제 사진(match 정확)으로 적었어요(shows: {shows[:30]}). 포장·로고로 그 제품임이 보일 때만 정확이에요", "확인"))
    uses = {}
    for where, _, p in items_of(spec):
        if where.startswith(("thumb", "cover")) or ".grid[" in where:  # 썸네일·표지는 본편 사진을 다시 쓰고, 저녁 메뉴 격자는 장마다 같은 판을 보여 줘요
            continue
        uses.setdefault((p["url"], tuple(p.get("crop") or ())), []).append(where)
    for (url, _), places in uses.items():  # 같은 사진이 한 콘텐츠에 또 나오면 보는 사람이 금방 지루해해요(2026-10-24 사용자)
        if len(places) >= 2:
            out.append(("사진 반복", f"같은 사진({url[-45:]})을 {len(places)}곳({', '.join(places[:4])})에 썼어요. 다른 사진(관광공사·위키미디어·오픈버스·뉴스와이어)으로 바꿔 주세요", "참고"))
    for url, crops in by_url.items():
        crops.discard(())
        if len(crops) >= 2:
            noted = all(s for (u, c), lst in seen_crop.items() if u == url for (_, _, s) in lst)
            if not noted:
                out.append(("사진 일치", f"한 사진({url[-45:]})을 좌표로 {len(crops)}번 잘라 썼어요. 여러 제품이 함께 찍힌 사진이면 잘라 낸 조각마다 직접 열어 보고 shows 에 무엇인지 적어 주세요(맘스터치 사례). 어느 것이 어느 제품인지 모르면 통째로 쓰거나 사진 없는 장으로", "확인"))
    for (url, crop), lst in seen_crop.items():
        names = [n for _, n, _ in lst]
        differ = any(len(a & b) * 2 < max(len(a), len(b)) for i, a in enumerate(names) for b in names[i + 1:] if a and b)
        if len(lst) >= 2 and differ:  # 같은 조각을 쓴 자리끼리 글이 반도 안 겹치면 다른 대상을 말하는 것으로 봐요
            places = ", ".join(w for w, _, _ in lst)
            out.append(("사진 일치", f"같은 잘린 조각 {list(crop)}이 서로 다른 대상을 말하는 자리 {places} 에 함께 쓰였어요. 한 조각은 한 대상만 보여 줘요", "차단"))
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
            out.append(("지역", f"'{old}'는 {since}부터 바뀐 이름이에요({now}, 근거: {law}). 지금 이름으로 쓰거나 '옛 {old.split()[-1]}'처럼 밝혀 주세요", "차단"))
    reg = spec.get("region")
    local = spec.get("kind") == "지역"
    if not reg:
        if local and day >= DATES_FROM:
            out.append(("지역", "region 칸이 없어요. 소개한 장소마다 공식 주소·지금 관할(구)·근거, 제목이 말하는 범위(title_scope), 먹거리마다 그 지역과의 관계(why·source)를 적어 주세요", "확인"))
        return out
    places = reg.get("places") or []
    admins = {p.get("admin", "") for p in places if p.get("admin")}
    gus = {re.findall(r"(\S+[구군시])$", a)[0] if re.findall(r"(\S+[구군시])$", a) else a for a in admins}
    scope = reg.get("title_scope", "")
    for p in places:
        if not (p.get("address") and p.get("source")):
            out.append(("지역", f"{p.get('name', '?')}: 공식 주소(address)와 근거(source)가 없어요. 지자체·관광공사·법령 자료로 확인해 주세요", "확인"))
    if scope and gus and not any(g in scope for g in gus) and len(gus) == 1:
        g = next(iter(gus))
        out.append(("지역", f"제목 범위는 '{scope}'인데 소개한 곳 {len(places)}곳이 모두 {g}예요. 제목을 '{scope} {g}'처럼 좁히거나 다른 구의 먹거리도 고르게 다뤄 주세요", "확인"))
    if scope and scope not in head:
        out.append(("지역", f"title_scope '{scope}'가 제목·썸네일에 그대로 없어요. 제목이 실제 범위를 말하는지 확인해 주세요", "참고"))
    for f in reg.get("foods") or []:
        if not (f.get("why") and f.get("source")):
            out.append(("지역", f"{f.get('name', '?')}: 그 지역과 어떤 관계인지(why)와 근거(source)가 없어요. 거기서 판다는 것만으로 대표 음식이라고 쓰지 않아요", "참고"))
    return out


def blog_as_spec(post):
    """블로그 초안을 설계도처럼 봐요: photo 블록마다 바로 앞 문단·제목을 그 사진의 글로 (2026-10-23 5단계)."""
    lines, ctx = [], ""
    for b in post.get("blocks") or []:
        if b.get("type") in ("p", "h2", "h3"):
            ctx = str(b.get("text") or "")
        elif b.get("type") == "photo" and b.get("url"):
            ph = {k: b[k] for k in ("url", "shows", "match", "rights", "terms", "crop") if k in b}
            ph.setdefault("rights", b.get("credit") or "")
            lines.append({"say": (b.get("desc") or "") + " " + ctx, "photo": ph, **({"general": True} if b.get("general") is True else {}),
                          **({"about": b["about"]} if b.get("about") else {})})
    return {"kind": "블로그", "title": post.get("title"), "subject": post.get("subject"), "tags": post.get("tags"),
            "yt_keyword": post.get("keyword"), "lines": lines, "region": post.get("region")}


def findings(path):
    """(갈래, 등급, 내용) 목록. 등급: 차단 / 확인 / 참고. 설계도(videos/날짜/*.json)와 블로그 초안(blog/*.json) 모두."""
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding="utf-8"))
    platforms = ("instagram", "youtube")
    if path.parent.name == "blog" or "blocks" in spec:
        day = spec.get("date") or "9999-12-31"
        spec, platforms = blog_as_spec(spec), ("blog",)
    else:
        day = path.parent.name if re.match(r"\d{4}-\d{2}-\d{2}$", path.parent.name) else "9999-12-31"
    return photo_lines(spec, day, platforms) + region_lines(spec, day)


def report_file(path):
    return [f"  {kind}: {msg}" for kind, msg, _ in findings(path)]


def print_report(path):
    """build.py 가 설계도를 검사할 때 함께 불러요. 알려 주기만 해요. 발송을 막는 것은 scripts/gate.py (5단계)."""
    for line in report_file(path):
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lines = report_file(sys.argv[1])
    print("\n".join(lines) if lines else "  사진·지역: 알릴 것이 없어요.")
