# -*- coding: utf-8 -*-
"""썸네일 머리: 아주 큰 두 줄 제목 + 가는 흰 띠 + 사진 한 장.

2026-10-17 사용자가 정함: 벤치마킹 채널처럼 제목은 크고 한눈에 읽히게, 사진 하나가 중심, 다른 요소는 넣지 않는다.
  위 0~680   어두운 바탕에 두 줄 제목 (첫 줄 흰색, 둘째 줄 강조색, 검은 테두리)
  680~810    흰 띠에 작은 한 줄 (내레이션 쇼츠는 여기에 자막이 나와요)
  810~1920   사진 한 장 (확대 요청이 없으면 잘리지 않게 통째로, 위쪽에 붙여요)
  2026-10-19 5단계: 사진 칸을 맨 아래까지 늘려 아래쪽 어두운 띠(1700~1920)를 없앴어요.
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
# 먹고갈지도 로고 자리 (2026-10-17 사용자: "로고와 글씨는 넣어야 한다, 사람들이 막 쓰면 안 되니까")
#   top: 제목 위에 핀 로고 + 먹고갈지도   stamp: 사진 오른쪽 아래 둥근 로고 도장
#   strip: 흰 띠 왼쪽에 둥근 로고         bar: 사진 아래 이름 띠 + 사진 가운데 옅은 워터마크
#   both: top + stamp
BRAND = "top"
LOGO = HERE / "logo-round.png"  # 프로필 사진(초록 지도)을 둥글게 자른 것
TOP_BIG = 290  # 로고를 제목 위에 둘 때 제목이 시작하는 높이

CSS = """
@font-face { font-family: "Thumb Title"; src: url("THUMB_FONT"); }
.bh { position: absolute; left: 0; right: 0; top: 0; height: 680px; background: var(--bh, #1F2A1A); z-index: 900; overflow: hidden; }
.bh .tag { position: absolute; left: 0; right: 0; top: 104px; display: flex; justify-content: center; align-items: center; gap: 10px;
           font-weight: 900; font-size: 38px; color: #fff; opacity: .9; letter-spacing: -1px; }
.bh .tag svg { width: 30px; height: 38px; }
.bh .tag b { color: #FFB23E; }
.bh .tag.big { top: 182px; gap: 14px; font-size: 56px; opacity: 1; letter-spacing: -1.5px; }
.bh .tag.big svg { width: 50px; height: 62px; }
.bh .tag.big b { color: #FF6B4A; }
.blogo { position: absolute; z-index: 905; border-radius: 50%; border: 6px solid #fff; box-shadow: 0 6px 18px rgba(0,0,0,.45); }
.blogo.stamp { width: 210px; height: 210px; right: 28px; top: 1462px; }
.blogo.strip { width: 112px; height: 112px; left: 24px; top: 689px; border-width: 4px; box-shadow: none; }
.bstrip.logo div { padding-left: 160px; padding-right: 30px; }
.bbar { position: absolute; left: 0; right: 0; top: 1596px; height: 104px; background: rgba(20,28,18,.9); z-index: 904; display: flex; align-items: center;
        justify-content: center; gap: 14px; font-weight: 900; font-size: 54px; color: #fff; letter-spacing: -1.5px; }
.bbar svg { width: 46px; height: 58px; } .bbar b { color: #FF6B4A; }
.bwm { position: absolute; left: -100px; right: -100px; top: 1170px; text-align: center; z-index: 903; font-weight: 900; font-size: 140px;
       color: rgba(255,255,255,.3); transform: rotate(-14deg); letter-spacing: -4px; white-space: nowrap; }
.bh .ln { position: absolute; left: 0; right: 0; text-align: center; white-space: nowrap; font-family: "Thumb Title", "Noto Sans KR", "Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji", sans-serif;
          line-height: 1; letter-spacing: -1px; color: #fff; z-index: 1; filter: drop-shadow(0 8px 0 rgba(0,0,0,.35)); }
/* 테두리는 같은 글을 뒤에 한 벌 더 깔아서 그려요 (글자 위에 바로 그리면 획이 겹친 곳에 검은 줄이 생겨요) */
.bh .ln::before { content: attr(data-t); position: absolute; left: 0; right: 0; top: 0; z-index: -1; color: #000; -webkit-text-stroke: 12px #000; }
.bh .ln.l2, .bh .ln .am { color: var(--hc, #FFB23E); }
.bh .ln .emo { font-family: "Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji", sans-serif; display: inline-block; width: 1em; font-size: .92em; }
.bh .ln.l2 .am { color: #fff; }
.bstrip { position: absolute; left: 0; right: 0; top: 680px; height: 130px; background: #fff; display: flex; align-items: center; justify-content: center; z-index: 901; }
.bstrip div { font-weight: 900; font-size: 58px; letter-spacing: -2px; color: #111; text-align: center; padding: 0 40px; white-space: nowrap; }
.bstrip .am { color: #D8432B; }
.bpic { position: absolute; left: 0; right: 0; top: 810px; height: 1110px; overflow: hidden; background: #0E0B09; }
.bpic img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; object-position: 50% 0; }
.bpic img.bg, .bpic.cover img { object-fit: cover; }
/* 흰 바탕 상품 사진은 위에 붙이면 아래가 텅 비어 보여서 가운데에 둬요 (2026-10-21 빅아치) */
.bpic.pack { background: #fff; } .bpic.pack img { padding: 30px 56px; object-position: 50% 50%; }
.tref { position: absolute; right: 24px; top: 832px; z-index: 903; padding: 8px 22px 12px; border-radius: 12px; background: rgba(10,8,6,.74); color: #fff; font-weight: 800; font-size: 40px; letter-spacing: -1px; white-space: nowrap; }
.bback { position: absolute; left: 0; right: 0; top: 1700px; bottom: 0; overflow: hidden; }
/* 사진 아래 목록 (thumb.list). 사진은 띠 바로 아래에 통째로 붙고, 남은 아래 칸에 소식 목록이 들어가요 (2026-10-21 빅아치 소식 카드) */
.blist { position: absolute; left: 0; right: 0; bottom: 0; z-index: 902; background: #1F2A1A; display: flex; align-items: center; padding: 0 70px; }
.blist ul { width: 100%; list-style: none; }
.blist li { position: relative; padding: 16px 0 18px 40px; border-top: 2px solid rgba(255,255,255,.2); font-weight: 800; letter-spacing: -2px; color: #fff; white-space: nowrap; }
.blist li:first-child { border-top: 0; }
.blist li::before { content: ""; position: absolute; left: 2px; top: 50%; width: 16px; height: 16px; margin-top: -7px; border-radius: 50%; background: #FFB23E; }
.blist .am { color: #FFB23E; }
.blist .btag { display: inline-block; margin-bottom: 12px; padding: 6px 22px 10px; border-radius: 10px; background: #FFB23E; color: #17130F; font-weight: 900; font-size: 44px; letter-spacing: -1px; }
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


EMOJI = __import__("re").compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


def width(line, size):
    """제목 한 줄 폭. 이모지(🤤 등)는 제목 글꼴에 없어서 글자 하나(1em)로 쳐요(2026-11-13)."""
    t = line.replace("[[", "").replace("]]", "")
    emo = len([c for c in EMOJI.findall(t) if c not in "\uFE0F\u200D"])
    return (_font().getlength(EMOJI.sub("", t)) + 100 * emo) * size / 100


PIN_BOWL = ('<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="#D8432B"/>'
            '<circle cx="100" cy="92" r="62" fill="#FFF8EC"/><path d="M60 96h80c0 26-17 40-40 40S60 122 60 96z" fill="#D8432B"/>'
            '<rect x="54" y="90" width="92" height="10" rx="5" fill="#D8432B"/>'
            '<path d="M82 52c-7 7 7 12 0 22M100 48c-7 7 7 12 0 22M118 52c-7 7 7 12 0 22" stroke="#D8432B" stroke-width="7" fill="none" stroke-linecap="round"/></svg>')


def brand_name(name):
    """핀 로고(김 나는 그릇) + 먹고(흰색)갈지도(빨강)."""
    import build as B
    return f'{PIN_BOWL}<span>{B.esc(name[:2])}<b>{B.esc(name[2:])}</b></span>'


def sizes(lines, top=TOP):
    """줄마다 폭에 꽉 차는 글자 크기. 두 줄을 합쳐 제목 칸 높이를 넘지 않게 맞춰요."""
    cap = 230 if len(lines) == 1 else 190
    out = [min(cap, int(ROOM / max(width(l, 100) / 100, 1))) for l in lines]
    gap = 26 * (len(lines) - 1)
    room = BOTTOM - top - gap
    if sum(out) > room:
        out = [int(s * room / sum(out)) for s in out]
    return out


def head_html(text, name="먹고갈지도", hc=AC, bg=BG, brand=None):
    import build as B
    brand = brand or BRAND
    top = TOP_BIG if brand in ("top", "both") else TOP
    lines = [l for l in text.split("\n") if l.strip()][:2]
    ss = sizes(lines, top)
    y = top + (BOTTOM - top - sum(ss) - 26 * (len(ss) - 1)) / 2
    out = [f'<div class="bh" style="--hc:{hc};--bh:{bg}"><div class="tag{" big" if brand in ("top", "both") else ""}">{brand_name(name)}</div>']
    for i, (l, s) in enumerate(zip(lines, ss)):
        two = i == 1 and "[[" not in text  # [[ ]] 가 없으면 둘째 줄 전체가 강조색
        plain = B.esc(l.replace("[[", "").replace("]]", ""))
        body = B.rich(l)
        if EMOJI.search(plain):  # 이모지는 검은 테두리 층에서 빼고(같은 폭의 빈칸), 그림 글자 그대로 둬요
            plain = EMOJI.sub(lambda m: "" if m.group() in "\uFE0F\u200D" else "\u2003", plain)
            body = EMOJI.sub(lambda m: m.group() if m.group() in "\uFE0F\u200D" else f'<span class="emo">{m.group()}</span>', body)
        out.append(f'<div class="ln{" l2" if two else ""}" data-t="{plain}" style="top:{y:.0f}px;font-size:{s}px">{body}</div>')
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


STRIP_MIN, STRIP_MAX = 58, 74  # 흰 띠 글자 크기. 짧으면 크게 (2026-10-19 5단계: 띠 글이 작아 잘 안 읽혔어요)


def strip_size(sub):
    """흰 띠 한 줄이 띠 폭(1000px)에 들어가는 가장 큰 글자 크기. 짧을수록 커져요."""
    import build as B
    n = B.units(sub or "") or 1
    return max(STRIP_MIN, min(STRIP_MAX, int(1000 / n / 1.02)))


PIC_W, PIC_H = 1080, 1110  # 사진 칸 (거의 정사각형)


def photo_share(spec):
    """사진 칸(1080x1110) 가운데 사진이 실제로 차는 몫 (0~1). 나머지는 같은 사진을 흐리게 깐 빈자리예요.
    잘리지 않게 넣으면 칸과 모양이 다를수록 작아져요: 정사각 97%, 3:4 세로 77%, 4:3 가로 73%, 2:3 세로 69%, 3:2 가로 65%, 16:9 가로 55%.
    꽉 채우면(fit cover) 100%."""
    import build as B
    _, _, photo = parts(spec)
    if not photo or B.zoomed(photo):
        return 1.0
    B.fetch_photo(photo)
    w, h = B.SIZES[B.photo_key(photo)]
    k = min(PIC_W / w, PIC_H / h)
    return (w * k) * (h * k) / (PIC_W * PIC_H)


# ── 저녁 추천 썸네일: 메뉴 4가지를 한 화면 2×2 로 (2026-11-13 사용자: 추천 음식 4가지가 반드시 한 화면에 모두 보이게) ──
# 사진 칸(810~1920)을 영상의 4칸과 같은 차례·같은 사진으로 나눠요. 칸마다 같은 사진을 흐리게 깔고, 그 위에 사진을 통째로(contain) 두되
# TGRID_ZOOM 배까지만 키워요(가로·세로 모두 원본의 TGRID_KEEP 이상이 보여야 해요 → 주요 음식이 잘리지 않게).
TGRID_ZOOM = 1.1
TGRID_KEEP = 0.85
TGRID_CELL = ((1080 - 6) / 2, (1110 - 6) / 2)
TGRID_CSS = (".tgrid { position: absolute; left: 0; right: 0; top: 810px; height: 1110px; display: flex; flex-wrap: wrap; gap: 6px; background: #0E0B09; }"
             ".tgrid .c { position: relative; flex: 0 0 calc(50% - 3px); height: calc(50% - 3px); overflow: hidden; background: #0E0B09; }"
             ".tgrid .c img { position: absolute; inset: 0; width: 100%; height: 100%; }"
             ".tgrid .c img.bg { object-fit: cover; }"
             ".tgrid .c img.fg { object-fit: contain; }")


def grid_of(spec):
    """저녁 추천의 4칸 [칸 dict…] (영상에서 처음 나오는 2×2). 저녁 추천이 아니거나 없으면 None."""
    if spec.get("kind") != "저녁" or spec.get("layout") != "rec":
        return None
    for l in spec.get("lines") or []:
        sh = l.get("show") if isinstance(l.get("show"), dict) else {}
        if sh.get("grid") and sh.get("dir") == "2x2":
            return sh["grid"]
    return None


def grid_zoom(B, photo):
    """칸 안에서 사진을 키우는 배수(통째로=1). 칸을 꽉 채우는 배수와 TGRID_ZOOM 중 작은 것."""
    w, h = B.SIZES[B.photo_key(photo)]
    cw, ch = TGRID_CELL
    cover = max(cw / w, ch / h) / min(cw / w, ch / h)
    return min(TGRID_ZOOM, cover)


def grid_html(B, grid):
    cells = []
    for c in grid:
        p = (c or {}).get("photo")
        if not p:
            cells.append('<div class="c empty"></div>')
            continue
        src, pos = B.fetch_photo(p)
        z = grid_zoom(B, p)
        cells.append(f'<div class="c"><img class="bg" src="{B.backdrop(p)}">'
                     f'<img class="fg" src="{src}" data-z="{z:.3f}" style="transform:scale({z:.3f});transform-origin:{pos}"></div>')
    return f'<div class="tgrid">{"".join(cells)}</div><style>{TGRID_CSS}</style>'


def grid_problems(spec):
    """설계도만 보고: 4칸·2×2·빈칸 없음 (꼭 고칠 것). 메뉴와 사진이 맞는지는 rec.dinner_photo_problems 가 봐요."""
    if spec.get("kind") != "저녁" or spec.get("layout") != "rec":
        return []
    g = grid_of(spec)
    if not g:
        return ['썸네일에 쓸 2×2 4칸이 없어요(첫 4칸 장면에 "dir": "2x2"). 추천 음식 4가지가 썸네일 한 화면에 모두 보여야 해요.']
    out = []
    if len(g) != 4:
        out.append(f"4칸이어야 하는데 {len(g)}칸이에요.")
    for k, c in enumerate(g):
        if not ((c or {}).get("photo") or {}).get("url"):
            out.append(f"{k + 1}번 칸에 사진이 없어요(빈칸). 그 메뉴 사진을 찾거나, 없으면 메뉴를 다시 골라요.")
    return out


# 다 그린 썸네일을 열어 봐요: 4칸, 사진이 다 열렸는지, 칸마다 원본이 얼마나 보이는지, 칸이 비어 보이지 않는지
GRID_JS = """() => [...document.querySelectorAll('.tgrid .c')].map(c => {
  const i = c.querySelector('img.fg'); const r = c.getBoundingClientRect();
  if (!i) return {empty: true, x: r.left, y: r.top, w: r.width, h: r.height};
  const z = parseFloat(i.dataset.z || '1'), nw = i.naturalWidth, nh = i.naturalHeight;
  const s = Math.min(r.width / nw, r.height / nh) * z;
  const dw = Math.min(r.width, nw * s), dh = Math.min(r.height, nh * s);  // 칸 안에 실제로 보이는 사진 자리(가운데 기준)
  return {empty: false, ok: i.complete && nw > 0, keep_x: Math.min(1, r.width / (nw * s)), keep_y: Math.min(1, r.height / (nh * s)),
          x: r.left, y: r.top, w: r.width, h: r.height, px: r.left + (r.width - dw) / 2, py: r.top + (r.height - dh) / 2, pw: dw, ph: dh};
})"""


def grid_check(page, shot):
    """썸네일 그림(shot)과 열린 페이지로 4칸을 확인해요. (문제 목록(비면 통과), 칸별 값)"""
    from PIL import Image, ImageStat
    cells = page.evaluate(GRID_JS)
    out = []
    if len(cells) != 4:
        out.append(f"썸네일 4칸 검사: 칸이 {len(cells)}개예요(4개여야 해요).")
    with Image.open(shot) as im:
        g = im.convert("L")
        for k, c in enumerate(cells):
            x, y, w, h = (c["px"], c["py"], c["pw"], c["ph"]) if "pw" in c else (c["x"], c["y"], c["w"], c["h"])  # 흐린 바탕 말고 사진 자리만 재요
            box = tuple(int(v) for v in (x + 10, y + 10, x + w - 10, y + h - 10))
            c["stdev"] = round(ImageStat.Stat(g.crop(box)).stddev[0], 1)
            if c.get("empty") or not c.get("ok"):
                out.append(f"썸네일 4칸 검사: {k + 1}번 칸에 사진이 없거나 열리지 않았어요.")
            elif min(c["keep_x"], c["keep_y"]) < TGRID_KEEP:
                out.append(f"썸네일 4칸 검사: {k + 1}번 칸 사진이 많이 잘려요(원본의 가로 {c['keep_x']:.0%}·세로 {c['keep_y']:.0%}만 보여요).")
            if c["stdev"] < 12:
                out.append(f"썸네일 4칸 검사: {k + 1}번 칸이 거의 한 색이에요(빈칸처럼 보여요).")
    return out, cells


def body(spec):
    """썸네일 한 장면(머리 + 띠 + 사진). 저녁 추천은 사진 자리에 메뉴 4칸(2×2)."""
    import build as B
    head, sub, photo = parts(spec)
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
    t = spec.get("thumb") or {}
    ref = ref_tag(photo)
    if t.get("list"):
        return (list_html(B, photo, t["list"], t.get("list_tag", "")) + ref
                + f'<div class="bstrip{" logo" if BRAND == "strip" else ""}"><div style="font-size:{strip_size(sub)}px">{B.rich(sub)}</div></div>'
                + brand_marks(name) + head_html(head, name, t.get("color", AC)))
    g = grid_of(spec)
    if g:
        return (grid_html(B, g)
                + f'<div class="bstrip{" logo" if BRAND == "strip" else ""}"><div style="font-size:{strip_size(sub)}px">{B.rich(sub)}</div></div>'
                + brand_marks(name) + head_html(head, name, t.get("color", AC)))
    return (f'<div class="bback"><img src="{B.backdrop(photo)}"></div>{photo_html(B, photo)}{ref}'
            + f'<div class="bstrip{" logo" if BRAND == "strip" else ""}"><div style="font-size:{strip_size(sub)}px">{B.rich(sub)}</div></div>'
            + brand_marks(name) + head_html(head, name, t.get("color", AC)))


def ref_tag(photo):
    """사진 오른쪽 위 작은 표기. 사진에 적은 "label"(사진 성격·출처·촬영 연도)을 그대로 보여 줘요 (2026-11-06 사용자).
    label 이 없으면 붙이지 않아요. 예전의 '참고 사진' 딱지("ref")는 더 쓰지 않아요."""
    if not isinstance(photo, dict) or not str(photo.get("label") or "").strip():
        return ""
    import build as B
    return f'<div class="tref">{B.esc(str(photo["label"]).strip())}</div>'


def list_html(B, photo, items, tag=""):
    """사진을 흰 띠 바로 아래에 통째로(잘리지 않게) 붙이고, 남은 아래 칸에 목록을 넣어요. 소식 카드 첫 장의 목록과 같은 모양이에요.
    "thumb": {"head": …, "sub": …, "photo": …, "list": ["[[빅아치]] 프랑스 1위였다?", …]}"""
    from PIL import Image
    import voice
    pack = voice.is_pack(B, photo)
    src = B.pack_photo(photo) if pack else B.fetch_photo(photo)[0]
    path = B.CACHE / (B.photo_key(photo) + ("-pack.jpg" if pack else "-g2.jpg"))
    with Image.open(path) as im:
        w, h = im.size
    padx, pady = (56, 30) if pack else (0, 0)
    room = 1920 - 810 - (80 if tag else 0) - 113 * len(items) - 30  # 목록이 세 줄 이상이면 마지막 줄이 화면 밖으로 밀려요 (2026-11-03 빼빼로 소식 3)
    pic_h = min(round((PIC_W - 2 * padx) * h / w) + 2 * pady, 760, room)  # 목록 칸이 너무 좁아지지 않게 사진 칸은 760까지
    size = min(min(B.fit_size(line, 64, 900) for line in items), 64)
    rows = "".join(f'<li style="font-size:{size}px">{B.rich(line)}</li>' for line in items)
    pic = (f'<div class="bpic{" pack" if pack else ""}" style="height:{pic_h}px">'
           + (f'<img src="{src}">' if pack else f'<img class="bg" src="{B.backdrop(photo)}"><img src="{src}" style="object-position:50% 50%">')
           + '</div>')
    label = f'<span class="btag">{B.esc(tag)}</span>' if tag else ""
    return pic + f'<div class="blist" style="top:{810 + pic_h}px"><div style="width:100%">{label}<ul>{rows}</ul></div></div>'


def brand_marks(name, brand=None):
    """사진·띠 위에 얹는 로고. (BRAND 가 top 이면 제목 위에 있어서 여기선 없어요)"""
    brand = brand or BRAND
    if brand in ("stamp", "both"):
        return f'<img class="blogo stamp" src="{LOGO.as_uri()}">'
    if brand == "strip":
        return f'<img class="blogo strip" src="{LOGO.as_uri()}">'
    if brand == "bar":
        return f'<div class="bwm">{name} · {name}</div><div class="bbar">{brand_name(name)}</div>'
    return ""


# 저녁 추천(layout rec)은 2026-10-20 확정한 시안의 썸네일 모양을 그대로 써요: 사진 칸 810~1700, 흰 띠 글자 58px.
# 썸네일이 곧 영상 첫 화면이라 영상(rec.py)과 같은 모양이어야 해요. 다른 쇼츠는 5단계에서 넓힌 모양 그대로예요.
KEEP_CSS = (".rkeep .bpic { height: 890px; } .rkeep .bpic img { object-position: 50% 50%; } "
            ".rkeep .bstrip div { font-size: 58px !important; }")


def page(spec):
    """썸네일 그림 한 장을 찍을 HTML."""
    style = ((HERE / "base.css").read_text(encoding="utf-8") + css() + KEEP_CSS).replace("FONT_DIR", (HERE / "fonts").as_uri()) + spec.get("css", "")  # build.build_html 과 같은 한 편 전용 배치
    keep = " rkeep" if spec.get("layout") == "rec" else ""
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<style>{style}</style></head><body><section class="scene first{keep}" style="visibility:visible">{body(spec)}</section></body></html>')


def has(spec):
    head, _, photo = parts(spec)
    return bool(head and (photo or grid_of(spec)))


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
    if t.get("photo"):
        share = photo_share(spec)
        if share < 0.72:  # 3:2 가로·2:3 세로 사진은 사진 칸의 3분의 1이 흐린 빈자리예요
            out.append(f"thumb.photo 가 사진 칸(거의 정사각형)과 모양이 달라 칸의 {share:.0%}만 사진이고 나머지는 흐린 빈자리예요. "
                       "음식이 가운데 크게 있는 사진이면 \"fit\": \"cover\" 를 적어 꽉 채우고, 아니면 정사각형·3:4 세로 사진으로 바꿔 주세요.")
    return out
