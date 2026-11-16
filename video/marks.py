"""사진 위 표기 (2026-11-16 사용자가 정함). 카드뉴스·썸네일·내레이션 쇼츠·저녁 추천·순위 릴스가 모두 이 함수로 표기를 정해요.

1. 블로그·인스타그램(그 밖의 SNS 포함)에서 가져온 사진만 → 사진 구석에 아주 작고 흐린 출처 한 줄("출처 네이버 블로그").
2. 축제 사진 → 실제 행사 연도("2024년 축제 현장", "2025년 행사 당시 모습"). 연도를 확인 못 하면 "과거 축제 자료사진".
3. 둘이 겹치면 둘 다(연도는 알아보게, 출처는 작게).
4. 그 밖의 사진에는 화면 출처 문구를 넣지 않아요. 저작자·라이선스·원본 주소는 지금처럼 게시글·유튜브 설명란(credits)에 적어요.

설계도 사진 칸:
  "festival": 2024                                  확인한 행사 연도 → "2024년 축제 현장"
  "festival": {"year": 2025, "kind": "행사 당시 모습"} → "2025년 행사 당시 모습"
  "festival": true (또는 "unknown")                  연도를 확인 못 함 → "과거 축제 자료사진" (추측해서 적지 않아요)
  "sns": "○○님 블로그"                               (선택) 구석 출처 글. 없으면 주소(url·page·terms.url)로 '네이버 블로그'·'인스타그램' 등을 알아봐요.
  "label": 사진 성격(예: "이전 출시 제품 사진")       출처 부분(" · 울진군", "사진: ○○ 제공")은 화면에서 빼요.
"""
import datetime
import html
import re

SNS = [  # scripts/photo_report.py 의 EXTERNAL 과 같은 갈래 (유튜브는 사용자 규칙에 없어 빼요)
    ("네이버 블로그", re.compile(r"blog\.naver\.com|blogfiles\.pstatic|postfiles\.pstatic|blogthumb\.pstatic|blogpfthumb")),
    ("티스토리 블로그", re.compile(r"tistory\.com")),
    ("브런치", re.compile(r"brunch\.co\.kr")),
    ("블로그", re.compile(r"daumcdn\.net|egloos\.com|velog\.io|blogspot\.com|wordpress\.com|medium\.com")),
    ("인스타그램", re.compile(r"instagram\.com|cdninstagram\.com")),
    ("SNS", re.compile(r"fbcdn\.net|facebook\.com|threads\.net|threads\.com|twitter\.com|twimg\.com|//x\.com")),
]
SOURCEY = re.compile(r"^(사진|출처|자료|이미지|제공)\s*[:=]?|^ⓒ|©|제공\s*\)?$|출처")  # 출처만 적은 표기
FEST = re.compile(r"(축제|행사|페스티벌).*(현장|당시|모습)|(현장|당시|모습).*(축제|행사|페스티벌)")
YEAR = re.compile(r"(20\d{2})\s*년")
UNKNOWN = "과거 축제 자료사진"


def _year_ok(y):
    try:
        return 2000 <= int(y) <= datetime.date.today().year
    except (TypeError, ValueError):
        return False


def festival_text(p):
    """축제 사진 표기. festival 칸이 없으면 None."""
    f = p.get("festival")
    if f is None or f is False:
        return None
    kind = "축제 현장"
    if isinstance(f, dict):
        kind = str(f.get("kind") or kind).strip()
        f = f.get("year")
    if not isinstance(f, bool) and _year_ok(f):
        return f"{int(f)}년 {kind}"
    return UNKNOWN


def clean_label(label):
    """예전 label("2025년 축제 현장 · 울진군", "사진: 풀무원 제공", "가리비 사진 · 한국관광공사")에서 출처 부분을 빼요."""
    s = " ".join(str(label or "").split())
    if not s:
        return ""
    head = re.split(r"\s+[·|/]\s+|\s*\|\s*", s)[0].strip()
    if SOURCEY.search(head):
        return ""
    if FEST.search(head):  # 축제 현장 표기: 확인된 연도가 있으면 그대로, 없으면 '과거 축제 자료사진'
        m = YEAR.search(head)
        return head if m and _year_ok(m[1]) else UNKNOWN
    return head


def sns_text(p):
    """블로그·인스타그램 사진이면 구석 출처 글, 아니면 ""."""
    if p.get("own"):  # 사용자가 직접 찍은 사진(인스타 내보내기 보관함 등)은 출처를 적지 않아요
        return ""
    if p.get("sns"):
        s = " ".join(str(p["sns"]).split())
        return s if s.startswith("출처") else f"출처 {s}"
    url = str(p.get("url") or "")
    if url.startswith("vault:") and not url.startswith("vault:press/"):
        return ""
    terms = p.get("terms") if isinstance(p.get("terms"), dict) else {}
    urls = [url, str(p.get("page") or ""), str(terms.get("url") or "")]
    for name, pat in SNS:
        if any(pat.search(u) for u in urls):
            return f"출처 {name}"
    return ""


def marks(p):
    """(보이는 표기, 작은 출처). 없으면 빈 글."""
    if not isinstance(p, dict):
        return "", ""
    label = festival_text(p)
    if label is None:
        label = clean_label(p.get("label"))
    return label, sns_text(p)


def html_of(p, ref_cls="ref", src_cls="psrc", festival_only=False):
    """사진 칸 안에 넣는 HTML. 보이는 표기는 ref_cls, 작은 출처는 src_cls.
    festival_only: 쇼츠·릴스 장면처럼 예전에 표기가 없던 곳은 축제 연도·블로그 출처만 보여요(사진 성격 label 은 새로 띄우지 않아요)."""
    label, src = marks(p)
    if festival_only and not re.search(r"20\d{2}년|" + UNKNOWN, label):
        label = ""
    out = f'<span class="{ref_cls}">{html.escape(label)}</span>' if label else ""
    return out + (f'<span class="{src_cls}">{html.escape(src)}</span>' if src else "")


# 작은 출처의 공통 모양: 아주 작게, 흐리게, 그림자만 살짝 (2026-11-16 사용자: "출처를 표기했다는 정도만")
SRC_LOOK = ("position: absolute; z-index: 4; font-weight: 600; font-size: 19px; letter-spacing: -.3px; white-space: nowrap; "
            "color: rgba(255,255,255,.5); text-shadow: 0 1px 3px rgba(0,0,0,.55); pointer-events: none;")
REF_LOOK = ("position: absolute; z-index: 4; padding: 5px 16px 8px; border-radius: 10px; background: rgba(10,8,6,.66); "
            "color: rgba(255,255,255,.92); font-weight: 700; font-size: 30px; letter-spacing: -.5px; white-space: nowrap;")
