# -*- coding: utf-8 -*-
"""썸네일 머리: 아주 큰 두 줄 제목 + 가는 흰 띠 + 사진 한 장.

2026-10-17 사용자가 정함: 벤치마킹 채널처럼 제목은 크고 한눈에 읽히게, 사진 하나가 중심, 다른 요소는 넣지 않는다.
  위 0~680   어두운 바탕에 두 줄 제목 (첫 줄 흰색, 둘째 줄 강조색, 검은 테두리)
  680~810    흰 띠에 작은 한 줄 (내레이션 쇼츠는 여기에 자막이 나와요)
  810~1700   사진 한 장 (확대 요청이 없으면 잘리지 않게 통째로)
유튜브 채널 목록은 위아래를 150px쯤, 인스타 격자(3:4)는 240px쯤 잘라 보여 줘서 제목은 250px 아래에 둬요.

설계도에 이렇게 적어요.
  내레이션 쇼츠: "headline": "식당에서 사 먹으면\\n[[호구 인증 3가지]]"   (영상 내내 위에 있어요)
  그 밖의 쇼츠:  "thumb": {"head": "토요일 저녁\\n[[메뉴 TOP 5]]", "sub": "1위는 의외의 메뉴", "photo": …}
                 → 영상 맨 앞 0.9초가 이 화면이에요. 유튜브에 올릴 때 이 장면을 썸네일로 고르면 돼요.
"""
import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
# 제목 글꼴: 머니그라피체 라운디드(토스). 2026-10-17 사용자가 시안 5개 중에서 고름(블랙한산스는 글자 구분이 안 된다고 함).
# 수정·재배포 금지라 공개 저장소가 아니라 비공개 보관함(fonts/)에 두고, 만들 때 받아 build/fonts/ 에 둬요.
# 보관함을 못 읽으면 저장소에 있는 블랙한산스로 대신해요.
VAULT_FONT = "vault:fonts/Moneygraphy-Rounded.woff2"
FALLBACK_FONT = HERE / "fonts" / "BlackHanSans-Regular.ttf"
ROOM = 990          # 제목 한 줄이 쓸 수 있는 폭
TOP, BOTTOM = 250, 650  # 제목이 들어가는 높이 (목록에서 잘리지 않는 곳)
MAX_LINE = 9        # 한 줄 글자 수(띄어쓰기 포함). 넘으면 글자가 작아져요
BG, AC = "#1F2A1A", "#FFB23E"
THUMB_SEC = 0.9

CSS = """
@font-face { font-family: "Thumb Title"; src: url("THUMB_FONT"); }
.bh { position: absolute; left: 0; right: 0; top: 0; height: 680px; background: var(--bh, #1F2A1A); z-index: 900; overflow: hidden; }
.bh .tag { position: absolute; left: 0; right: 0; top: 104px; display: flex; justify-content: center; align-items: center; gap: 10px;
           font-weight: 900; font-size: 38px; color: #fff; opacity: .9; letter-spacing: -1px; }
.bh .tag svg { width: 30px; height: 38px; }
.bh .tag b { color: #FFB23E; }
.bh .ln { position: absolute; left: 0; right: 0; text-align: center; white-space: nowrap; font-family: "Thumb Title", "Noto Sans KR", sans-serif;
          line-height: 1; letter-spacing: -1px; color: #fff; z-index: 1; filter: drop-shadow(0 8px 0 rgba(0,0,0,.35)); }
/* 테두리는 같은 글을 뒤에 한 벌 더 깔아서 그려요 (글자 위에 바로 그리면 획이 겹친 곳에 검은 줄이 생겨요) */
.bh .ln::before { content: attr(data-t); position: absolute; left: 0; right: 0; top: 0; z-index: -1; color: #000; -webkit-text-stroke: 12px #000; }
.bh .ln.l2, .bh .ln .am { color: var(--hc, #FFB23E); }
.bh .ln.l2 .am { color: #fff; }
.bstrip { position: absolute; left: 0; right: 0; top: 680px; height: 130px; background: #fff; display: flex; align-items: center; justify-content: center; z-index: 901; }
.bstrip div { font-weight: 900; font-size: 58px; letter-spacing: -2px; color: #111; text-align: center; padding: 0 40px; white-space: nowrap; }
.bstrip .am { color: #D8432B; }
.bpic { position: absolute; left: 0; right: 0; top: 810px; height: 890px; overflow: hidden; background: #0E0B09; }
.bpic img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
.bpic img.bg, .bpic.cover img { object-fit: cover; }
.bpic.pack { background: #fff; } .bpic.pack img { padding: 30px 56px; }
.bback { position: absolute; left: 0; right: 0; top: 1700px; bottom: 0; overflow: hidden; }
.bback img { width: 100%; height: 100%; object-fit: cover; filter: brightness(.6); }
"""
PIN = ('<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="#D8432B"/>'
       '<circle cx="100" cy="92" r="60" fill="#fff"/><path d="M62 84h76c0 26-16 42-38 42S62 110 62 84z" fill="#D8432B"/></svg>')


@lru_cache(maxsize=1)
def font_file():
    """제목 글꼴 파일 경로. 비공개 보관함에서 한 번 받아 build/fonts/ 에 둬요."""
    cache = HERE.parent / "build" / "fonts" / VAULT_FONT.rsplit("/", 1)[1]
    if not cache.exists():
        try:
            import build as B
            data = B.read_source(VAULT_FONT)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
        except Exception as e:
            print(f"  썸네일 글꼴을 보관함에서 못 읽어 블랙한산스로 대신해요: {e}")
            return FALLBACK_FONT
    return cache


def css():
    """썸네일 CSS (글꼴 주소를 채운 것). FONT_DIR 은 부르는 쪽에서 채워요."""
    return CSS.replace("THUMB_FONT", font_file().as_uri())


@lru_cache(maxsize=1)
def _font():
    from PIL import ImageFont
    return ImageFont.truetype(str(font_file()), 100)


def width(line, size):
    return _font().getlength(line.replace("[[", "").replace("]]", "")) * size / 100


def sizes(lines):
    """줄마다 폭에 꽉 차는 글자 크기. 두 줄을 합쳐 제목 칸 높이를 넘지 않게 맞춰요."""
    cap = 230 if len(lines) == 1 else 190
    out = [min(cap, int(ROOM / max(width(l, 100) / 100, 1))) for l in lines]
    gap = 26 * (len(lines) - 1)
    room = BOTTOM - TOP - gap
    if sum(out) > room:
        out = [int(s * room / sum(out)) for s in out]
    return out


def head_html(text, name="먹고갈지도", hc=AC, bg=BG):
    import build as B
    lines = [l for l in text.split("\n") if l.strip()][:2]
    ss = sizes(lines)
    y = TOP + (BOTTOM - TOP - sum(ss) - 26 * (len(ss) - 1)) / 2
    out = [f'<div class="bh" style="--hc:{hc};--bh:{bg}"><div class="tag">{PIN}<span>{B.esc(name[:2])}<b>{B.esc(name[2:])}</b></span></div>']
    for i, (l, s) in enumerate(zip(lines, ss)):
        two = i == 1 and "[[" not in text  # [[ ]] 가 없으면 둘째 줄 전체가 강조색
        plain = B.esc(l.replace("[[", "").replace("]]", ""))
        out.append(f'<div class="ln{" l2" if two else ""}" data-t="{plain}" style="top:{y:.0f}px;font-size:{s}px">{B.rich(l)}</div>')
        y += s + 26
    return "".join(out) + "</div>"


def problems(text, where="제목"):
    """썸네일 제목이 크게 보이는지. (보면 좋은 것 목록)"""
    out = []
    lines = [l for l in (text or "").split("\n") if l.strip()]
    if not lines:
        return [f"{where}이 없어요."]
    if len(lines) > 2:
        out.append(f"{where}이 {len(lines)}줄이에요. 두 줄까지만 보여요.")
    for l in lines:
        n = len(l.replace("[[", "").replace("]]", ""))
        if n > MAX_LINE:
            out.append(f"{where} '{l}' 이 {n}글자예요. 한 줄 {MAX_LINE}글자 안이어야 글자가 크게 보여요.")
    return out


def photo_html(B, photo, cls="bpic"):
    import voice
    if voice.is_pack(B, photo):
        return f'<div class="{cls} pack"><img src="{B.pack_photo(photo)}"></div>'
    src, pos = B.fetch_photo(photo)
    if B.zoomed(photo):
        return f'<div class="{cls} cover"><img src="{src}" style="object-position:{pos}"></div>'
    return f'<div class="{cls}"><img class="bg" src="{B.backdrop(photo)}"><img src="{src}"></div>'


def parts(spec):
    """썸네일에 들어갈 (제목, 띠 글, 사진). 내레이션 쇼츠는 headline 과 첫 사진을 써요."""
    t = spec.get("thumb") or {}
    if spec.get("format") == "voice":
        first = spec["lines"][0]
        photo = t.get("photo") or (first.get("photos") or [first.get("photo")])[0]
        return t.get("head") or spec.get("headline", ""), t.get("sub") or "", photo
    return t.get("head", ""), t.get("sub", ""), t.get("photo")


def body(spec):
    """썸네일 한 장면(머리 + 띠 + 사진)."""
    import build as B
    head, sub, photo = parts(spec)
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
    t = spec.get("thumb") or {}
    return (f'<div class="bback"><img src="{B.backdrop(photo)}"></div>{photo_html(B, photo)}'
            + (f'<div class="bstrip"><div>{B.rich(sub)}</div></div>' if sub else '<div class="bstrip"></div>')
            + head_html(head, name, t.get("color", AC)))


def page(spec):
    """썸네일 그림 한 장을 찍을 HTML."""
    style = ((HERE / "base.css").read_text(encoding="utf-8") + css()).replace("FONT_DIR", (HERE / "fonts").as_uri())
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<style>{style}</style></head><body><section class="scene first" style="visibility:visible">{body(spec)}</section></body></html>')


def has(spec):
    head, _, photo = parts(spec)
    return bool(head and photo)


def spec_problems(spec):
    """설계도의 썸네일 칸 확인 (내레이션 쇼츠는 voice.problems 가 headline 을 봐요)."""
    if spec.get("format") == "voice":
        return []
    t = spec.get("thumb")
    if not t:
        return ['thumb 이 없어요. {"head": "두 줄 제목", "sub": "흰 띠 한 줄", "photo": …} 를 적어 주세요. (PROMPT.md "쇼츠 썸네일·제목·주제")']
    out = problems(t.get("head"), "썸네일 제목")
    if not t.get("photo"):
        out.append("thumb.photo 가 없어요. 가장 먹음직스러운 사진 한 장을 적어 주세요.")
    if len((t.get("sub") or "").replace("[[", "").replace("]]", "")) > 16:
        out.append("thumb.sub 가 16자를 넘어요. 짧게 줄여 주세요.")
    return out
