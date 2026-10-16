# -*- coding: utf-8 -*-
"""영상 설계도(videos/날짜/이름.json)를 화면(HTML)으로 바꿔요.

설계도는 장면(scenes)의 목록이에요. 장면 종류는 네 가지예요.
  cover  사진을 화면 가득 어둡게 깔고 큰 제목      (첫 장면, 마지막 장면)
  card   사진을 화면 가득, 아래에 장소·제목·한두 줄   (소식, 메뉴, 음식 한 가지)
  duo    위아래 사진 두 장, 가운데에 번호·이름·설명  (장소 소개, 사진 비교)
  info   위에 사진, 아래에 큰 날짜나 숫자           (축제 일정)
사진은 주소(url)로 적고, 만들 때 내려받아요. cover 와 card 는 photo 대신 video 로 동영상도 넣을 수 있어요.
"""
import hashlib
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from common import hashtags  # noqa: E402

CACHE = HERE.parent / "build" / "photos"
ACCENTS = {"제철": "#FFB23E", "소식": "#4FC3C8", "저녁": "#FF7A6B", "추가": "#B79CFF", "세계": "#8FD694", "해외": "#7FB8FF"}
UA = {"User-Agent": "jecheol-feed/1.0 (https://github.com/hong2-kim/jecheol-feed)"}


def esc(text):
    return html.escape(str(text))


def rich(text):
    """[[글]] 로 감싼 부분은 강조색으로 보여 줘요."""
    return esc(text).replace("[[", '<span class="am">').replace("]]", "</span>")


VAULT = "hong2-kim/jecheol-photos"  # 사용자 사진 비공개 보관함. 설계도에는 "vault:photos/…jpg" 로 적어요.


def read_source(url, timeout=60):
    """사진·동영상 파일을 읽어요. 인터넷 주소, 저장소 안 경로, 비공개 보관함(vault:) 모두 돼요."""
    if url.startswith("vault:"):
        import os
        local = os.environ.get("VAULT_DIR", "").strip()  # 이 컴퓨터에서 만들 때: 받아 둔 보관함 폴더
        if local and (Path(local) / url[len("vault:"):]).exists():
            return (Path(local) / url[len("vault:"):]).read_bytes()
        token = os.environ.get("PHOTOS_TOKEN", "").strip()
        if not token:
            raise RuntimeError("PHOTOS_TOKEN 이 없어 비공개 보관함 사진을 읽을 수 없어요")
        path = urllib.parse.quote(url[len("vault:"):])
        req = urllib.request.Request(f"https://api.github.com/repos/{VAULT}/contents/{path}",
                                     headers={**UA, "Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"})
        return urllib.request.urlopen(req, timeout=timeout).read()
    if url.startswith("http"):
        safe = urllib.parse.quote(url, safe=":/?&=%+,;@()")
        return urllib.request.urlopen(urllib.request.Request(safe, headers=UA), timeout=timeout).read()
    return (HERE.parent / url).read_bytes()  # 사용자가 보낸 사진. 저장소 안의 경로예요 (myphotos/이름.jpg)


SIZES = {}  # 사진 주소 -> (가로, 세로)


def grade(image):
    """작은 사진은 선명하게 키우고 색과 윤기를 조금 살려요. 사진 속 내용은 바꾸지 않아요."""
    w, h = image.size
    if max(w, h) < 1900:
        k = 1900 / max(w, h)
        image = image.resize((round(w * k), round(h * k)), Image.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=2.2, percent=70, threshold=2))
    image.thumbnail((2200, 2200))
    image = ImageEnhance.Color(image).enhance(1.14)
    return ImageEnhance.Contrast(image).enhance(1.06)


def fetch_photo(photo):
    """사진을 내려받아 보정한 뒤 JPEG로 저장하고 (파일 주소, 위치)를 돌려줘요."""
    if isinstance(photo, str):
        photo = {"url": photo}
    url = photo["url"]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + "-g2.jpg")
    if not path.exists():
        data = read_source(url)
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        if min(image.size) < 500:
            raise ValueError(f"사진이 너무 작아요 ({image.size[0]}x{image.size[1]}): {url}")
        grade(image).save(path, "JPEG", quality=92)
    if url not in SIZES:
        with Image.open(path) as im:
            SIZES[url] = im.size
    return path.as_uri(), photo.get("pos", "50% 50%")


def pack_photo(photo):
    """상품 사진(회사가 나눠 준 포장 사진)은 자르지 않고 통째로 보여 줘요. 둘레의 흰 여백만 잘라 내요."""
    url = photo["url"] if isinstance(photo, dict) else photo
    fetch_photo(photo)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = CACHE / (key + "-pack.jpg")
    if not path.exists():
        with Image.open(CACHE / (key + "-g2.jpg")) as im:
            im = im.convert("RGB")
            ink = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L").point(lambda v: 255 if v > 18 else 0)
            box = ink.getbbox() or (0, 0, *im.size)
            pad = round(max(im.size) * 0.02)
            box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width), min(box[3] + pad, im.height))
            im.crop(box).save(path, "JPEG", quality=92)
    return path.as_uri()


def backdrop(photo):
    """같은 사진을 흐리고 어둡게 만든 바탕. 가로 사진 아래쪽 빈 곳을 채워요."""
    url = photo["url"] if isinstance(photo, dict) else photo
    src, _ = fetch_photo(photo)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + "-blur.jpg")
    if not path.exists():
        with Image.open(CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + "-g2.jpg")) as im:
            small = im.convert("RGB").resize((108, 192), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7))
            ImageEnhance.Brightness(small).enhance(0.5).save(path, "JPEG", quality=88)
    return path.as_uri()


def is_tall(photo):
    url = photo["url"] if isinstance(photo, dict) else photo
    fetch_photo(photo)
    w, h = SIZES[url]
    return h >= w * 1.15


EXTRACT = False  # 영상을 실제로 만들 때만 True. 설계도 확인만 할 때는 동영상을 풀지 않아요.
FPS = 30


def clip(video, dur):
    """동영상을 내려받아 장면 길이만큼 낱장으로 풀어요. (첫 장 주소, 낱장 폴더 주소, 장수, 세로인지)"""
    import subprocess

    import imageio_ffmpeg

    if isinstance(video, str):
        video = {"url": video}
    url, start = video["url"], float(video.get("from", 0))
    key = hashlib.sha1(f"{url}|{start}|{dur}".encode()).hexdigest()[:16]
    folder = CACHE.parent / "frames" / key
    if not (folder / "00001.jpg").exists():
        folder.mkdir(parents=True, exist_ok=True)
        src = CACHE.parent / "clips" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".mp4")
        if not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(read_source(url, timeout=180))
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        first = folder / "first.jpg"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(start), "-i", str(src), "-frames:v", "1", "-q:v", "3", str(first)], check=True)
        with Image.open(first) as im:
            w, h = im.size
        scale = "scale=1080:-2" if h >= w else "scale=-2:1080"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(start), "-i", str(src), "-t", f"{dur + 0.7:.2f}", "-an",
                        "-vf", f"fps={FPS},{scale}", "-q:v", "3", str(folder / "%05d.jpg")], check=True)
    count = len(list(folder.glob("[0-9]*.jpg")))
    if count == 0:
        raise ValueError(f"동영상에서 화면을 꺼내지 못했어요: {url}")
    with Image.open(folder / "00001.jpg") as im:
        w, h = im.size
    return (folder / "00001.jpg").as_uri(), folder.as_uri(), count, h >= w * 1.15


def moving(s, dur):
    """장면의 바탕. 동영상이 있으면 동영상, 없으면 사진. (HTML, 흐린 바탕 주소, 세로인지)"""
    if s.get("video") and EXTRACT:
        first, folder, count, tall = clip(s["video"], dur)
        pos = s["video"].get("pos", "50% 50%") if isinstance(s["video"], dict) else "50% 50%"
        tag = f'<img class="vf" src="{first}" data-frames="{folder}" data-n="{count}" data-fps="{FPS}" style="object-position:{pos}">'
        return tag, first, tall
    if s.get("video"):  # 설계도 확인만 할 때는 동영상을 풀지 않아요
        return "", "", True
    return img(s["photo"]), backdrop(s["photo"]), is_tall(s["photo"])


def img(photo):
    """사진 한 장. 장면이 넘어가기 전까지는 움직이지 않고 그대로 있어요."""
    src, pos = fetch_photo(photo)
    return f'<img src="{src}" style="object-position:{pos}">'


def rise(cls, text, delay, tag="div", style=""):
    """글 한 덩이. 장면이 들어오는 동안 차례로 자리 잡고(0.5초 안), 그 뒤로는 움직이지 않아요."""
    delay = round(min(delay, .6) * .35, 2)
    return f'<{tag} class="{cls} a rise" style="--dl:{delay}s;--d:.3s;{style}">{rich(text)}</{tag}>'


def units(line):
    """글 한 줄이 차지하는 칸 수. (한글 1, 띄어쓰기 0.3, 영문·숫자·기호 0.55 칸으로 어림해요)"""
    line = line.replace("[[", "").replace("]]", "")
    return sum(.3 if c == " " else .55 if ord(c) < 128 else 1 for c in line)


def fit_size(text, size, room=930):
    """가장 긴 줄이 화면 폭을 넘지 않게 글자 크기를 줄여요."""
    longest = max(units(line) for line in text.split("\n")) or 1
    return min(size, int(room / longest / .95))


def scene_cover(s, i, ctx):
    parts = [f'<div class="pic">{moving(s, s["dur"])[0]}</div>', '<div class="mid">']
    if s.get("kicker"):
        parts.append(rise("kicker", s["kicker"], .15))
    parts.append(rise("title", s["title"], .4, style=f'font-size:{fit_size(s["title"], s.get("size", 128))}px'))
    if s.get("line"):
        parts.append(rise("line", s["line"], .75))
    parts.append("</div>")
    if s.get("bright") or s.get("video"):  # 직접 찍은 사진·동영상은 어둡게 덮지 않고 그대로 보여 줘요
        parts.insert(1, '<div class="veil"></div>')
        return "cover bright", "".join(parts)
    return "cover", "".join(parts)


def scene_card(s, i, ctx):
    """사진이나 동영상을 화면 가득 깔고 글은 아래쪽에 얹어요. 세로면 전체, 가로면 위 3/4 을 채워요."""
    tag, back, tall = moving(s, s["dur"])
    chip = rise("chip", s["chip"], .2) if s.get("chip") else ""
    return "card", (
        f'<div class="back"><img src="{back}"></div>'
        f'<div class="pic {"tall" if tall else "wide"}">{tag}</div><div class="shade"></div>'
        f'<div class="txt">{chip}{rise("hd", s["headline"], .32)}{rise("ln", s.get("line", ""), .6)}</div>'
    )


def scene_duo(s, i, ctx):
    parts = [f'<div class="pic">{img(s["photo_top"])}</div>',
             f'<div class="pic bot">{img(s["photo_bottom"])}</div>']
    if s.get("title"):
        parts.append('<div class="seam"></div><div class="mid">')
        if s.get("no"):
            parts.append(rise("no", s["no"], .2))
        parts.append(rise("big", s["title"], .3, style=f'font-size:{s.get("size", 116)}px'))
        if s.get("sub"):
            parts.append(rise("sub", s["sub"], .6))
        parts.append("</div>")
    if s.get("chip_top"):
        parts.append(rise("tagchip", s["chip_top"], .45, style="top:300px;"))
    if s.get("chip_bottom"):
        parts.append(rise("tagchip", s["chip_bottom"], 1.9, style="top:1090px;"))
    if s.get("chip_bottom2"):
        parts.append(rise("tagchip hot", s["chip_bottom2"], 2.6, style="top:1190px;"))
    return "duo", "".join(parts)


def scene_info(s, i, ctx):
    bottom = s.get("photo_bottom", s["photo"])
    return "info", (
        f'<div class="pic">{img(s["photo"])}</div><div class="pic bot">{img(bottom)}</div>'
        f'<div class="box">{rise("kicker", s.get("kicker", ""), .3, style="font-size:48px;")}'
        f'{rise("big", s["title"], .5, style="font-size:104px;margin-top:10px;")}'
        f'{rise("huge", s["big"], .9)}{rise("sub", s.get("sub", ""), 1.2, style="margin-top:0;")}</div>'
    )


def rank_top(ctx, done):
    """저녁 TOP 5 의 위쪽 제목과 진행 막대. 모든 장면에 같은 자리에 떠 있어요."""
    top = ctx.get("top") or {}
    total = ctx.get("ranks", 5)
    dots = "".join(f'<span class="{"done" if k < done else ""}"></span>' for k in range(total))
    kicker = f'<span class="k">{esc(top["kicker"])}</span>' if top.get("kicker") else ""
    badge = top.get("badge") or f"TOP {total}"
    title = rich(top.get("title", "오늘 저녁 뭐 먹지?") + "\n[[" + badge + "]]")
    note = f'<div class="rk-note">{esc(ctx["rank_note"])}</div>' if ctx.get("rank_note") else ""
    return f'<div class="rk-top">{kicker}<h3>{title}</h3><div class="dots">{dots}</div></div>{note}'


def scene_rank(s, i, ctx):
    """시안 A. 순위 하나. 사진을 화면 가득 깔고 큰 순위 숫자, 메뉴 이름, 술, 상황 한 줄.

    {"type": "rank", "no": 5, "name": "곱창", "drink": "소주", "line": "불판 앞에 앉으면 끝", "photo": {...}}
    사진은 세로로 잘라도 불판·접시가 통째로 보이는 것만 써요. 천천히 7%만 다가가요.
    """
    total = ctx.get("ranks", 5)
    if s.get("video"):  # 사용자가 보낸 동영상은 그대로 움직이게 둬요
        pic = f'<div class="pic">{moving(s, s["dur"])[0]}</div>'
    elif not is_tall(s["photo"]):
        # 가로 사진은 잘라서 꽉 채우지 않고 통째로 보여 줘요(멀리서 본 느낌). 빈 곳은 같은 사진을 흐리게 깔아요. (2026-10-15 사용자: 너무 확대돼 보임)
        src, pos = fetch_photo(s["photo"])
        pic = (f'<div class="pic"><img src="{backdrop(s["photo"])}"></div>'
               f'<div class="pic rk-wide"><img class="kb a" src="{src}" style="--d:{s["dur"]}s"></div>')
    else:
        src, pos = fetch_photo(s["photo"])
        pic = f'<div class="pic"><img class="kb a" src="{src}" style="object-position:{pos};--d:{s["dur"]}s"></div>'
    name = (f'<div class="rk-name">{rise("", s["name"], .2, tag="b")}'
            + (rise("drink", s["drink"], .35, tag="span") if s.get("drink") else "")
            + (rise("say", s["line"], .5) if s.get("line") else "") + "</div>")
    no = f'<div class="rk-no a pop" style="--d:.4s">{int(s["no"])}<small>위</small></div>'
    return "rank", pic + '<div class="rk-shade"></div>' + rank_top(ctx, total - int(s["no"]) + 1) + no + name


def scene_tease(s, i, ctx):
    """시안 A. 흐린 사진 위에 "1위는?" 한마디. 첫 장면이면 썸네일이 되고, 1위 바로 앞이면 한 번 멈춰 궁금하게 해요."""
    src, pos = fetch_photo(s["photo"])
    done = ctx.get("ranks", 5) - 1 if i else 0
    return "tease", (f'<div class="pic"><img src="{src}" style="object-position:{pos}"></div><div class="rk-shade"></div>'
                     + rank_top(ctx, done) + f'<div class="big-q a pop" style="--d:.4s">{rich(s.get("text", "1위는?"))}</div>')


def scene_check(s, i, ctx):
    """시안 B. "몇 개 먹어 봤어요?" 동그란 사진 3~6개에 차례로 체크가 켜지고, 그때마다 한 줄 정보가 바뀌어요.

    첫 화면(썸네일)에서 제목과 사진이 다 보이고, 체크는 장면 길이에 맞춰 고르게 켜져요. 끝에는 댓글을 부르는 말.
    {"type": "check", "kicker", "title", "items": [{"name", "photo", "line"}], "end", "end_sub"}
    """
    items, dur = s["items"], s["dur"]
    n = len(items)
    t0 = round(dur * .14, 2)
    seg = (dur * .8 - t0) / n
    at = [round(t0 + k * seg, 2) for k in range(n)]
    cells = "".join(
        f'<div class="it"><div class="c">{img(it["photo"])}<div class="on a" style="--dl:{at[k]}s;--d:.3s"></div></div>'
        f'<b>{esc(it["name"])}</b><div class="ck a" style="--dl:{at[k]}s;--d:.35s">{k + 1}</div></div>'
        for k, it in enumerate(items))
    cnt = f'<span class="out1 a" style="--d:{t0}s">0 / {n}</span>' + "".join(
        f'<span class="{"hold" if k == n - 1 else "flash"} a" style="--dl:{at[k]}s;--d:{.3 if k == n - 1 else round(seg, 2)}s">{k + 1} / {n}</span>'
        for k in range(n))
    say = "".join(
        f'<div class="flash a" style="--dl:{at[k]}s;--d:{round(seg, 2)}s">{esc(it["name"])} · {rich(it.get("line", ""))}</div>'
        for k, it in enumerate(items))
    end_at = round(dur * .82, 2)
    say += (f'<div class="end hold a" style="--dl:{end_at}s;--d:.4s"><b>{esc(s.get("end", "댓글에 숫자만 남겨 주세요"))}</b>'
            f'<span>{esc(s.get("end_sub", "저장해 두고 하나씩 깨 보기"))}</span></div>')
    head = f'<div class="head">{rise("kicker", s.get("kicker", ""), .1)}{rise("title", s["title"], .3)}</div>'
    # 위쪽 "0 / 5" 세기는 빼고, 동그라미마다 체크 대신 차례 번호(1~5)가 켜져요 (2026-10-15 사용자가 정함: 체크가 잘 안 보임)
    return "check", f'{head}<div class="grid">{cells}</div><div class="say">{say}</div>'


def scene_sheet(s, i, ctx):
    """시안 C. 저장하고 싶어지는 표 한 장. 줄이 하나씩 밝아지며 눈길을 이끌어요.

    {"type": "sheet", "kicker", "title", "cols": [3개], "rows": [{"name", "sub", "photo", "when", "good"}], "note", "save"}
    표는 쇼츠 오른쪽 단추 자리(화면 오른쪽 15%)에 걸리지 않게 왼쪽으로 붙여요.
    """
    rows, dur = s["rows"], s["dur"]
    t0 = .6
    seg = (dur - t0 - .3) / len(rows)
    cols = s.get("cols") or ["이름", "언제가 제일", "몸에 좋은 것"]
    head = "".join(f"<th>{esc(c)}</th>" for c in [""] + cols)
    body = ""
    for k, r in enumerate(rows):
        hl = f'<span class="hl flash a" style="--dl:{round(t0 + k * seg, 2)}s;--d:{round(seg, 2)}s"></span>'
        good = f'<td class="good">{hl}{rich(r.get("good", ""))}</td>'
        body += (f'<tr><td>{hl}<div class="th">{img(r["photo"])}</div></td>'
                 f'<td>{hl}<b>{esc(r["name"])}</b><i>{esc(r.get("sub", ""))}</i></td>'
                 f'<td>{hl}{rich(r.get("when", ""))}</td>{good}</tr>')
    note = f'<div class="note">{esc(s["note"])}</div>' if s.get("note") else ""
    # 저장 안내: 배경 띠 없이 책갈피 그림과 글로만 (2026-10-15). save_style 은 icon(기본) 또는 line
    mark = ('<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4.5L6 21z" fill="none" stroke="currentColor" stroke-width="2.4" '
            'stroke-linejoin="round"/></svg>')
    save = f'<div class="save {s.get("save_style", "icon")}">{mark}<span>{rich(s.get("save", "장 볼 때 꺼내 보게 [[저장]]해 두세요"))}</span></div>'
    table = (f'<table><colgroup><col class="c1"><col class="c2"><col><col class="c4"></colgroup>'
             f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')
    title = f'<div class="head">{rise("kicker", s.get("kicker", ""), .1)}{rise("title", s["title"], .3)}</div>'
    return "sheet", title + f'<div class="box">{table}{note}{save}</div>'


CREDIT = re.compile(r"^(?P<who>.+?)\s*\((?P<lic>[^()]*)\)(?:\s*·\s*(?P<link>.+))?$")
FREE = ("CC0", "Public domain", "PDM")


def credit_lines(spec):
    """영상 끝에 꼭 적어야 하는 사진 출처만 골라요. [(큰 글, 작은 글)]

    - 한국관광공사 사진(공공누리 1유형): 출처 표시가 조건이라 그대로 적어요.
    - CC BY 사진: 저작자, 라이선스, 원본 주소를 적어요.
    - CC0·퍼블릭 도메인 사진, 직접 찍은 것: 표시할 의무가 없어 적지 않아요.
    """
    out = []
    for credit in spec.get("credits") or []:
        credit = " ".join(str(credit).split())
        m = CREDIT.match(credit)
        if not credit or (m and m["lic"].startswith(FREE)):
            continue
        if m and m["lic"].startswith("CC BY"):
            link = m["link"] or ""
            out.append((f'{m["who"]} · {m["lic"]}', link if "." in link else "Wikimedia Commons"))
        else:
            out.append((credit, ""))
    return out


# 끝 장면의 바탕. 인스타 프로필 사진(insta-profile/make.py 의 밤 지도)과 같은 색과 모양이에요.
OUTRO_MAP = """<svg class="map" viewBox="0 0 1080 1920">
<rect width="1080" height="1920" fill="#17130F"/>
<path d="M-40 1610C180 1550 300 1710 520 1670S900 1550 1120 1630V1960H-40z" fill="#0F1A22"/>
<path d="M700 -20h260v330H640z" fill="#1B2418"/><path d="M-20 250h230l-60 300H-20z" fill="#1B2418"/><path d="M850 1060h270v300H790z" fill="#1B2418"/>
<g fill="none" stroke="#2B251E" stroke-linecap="round">
<path d="M-40 640L1120 500" stroke-width="46"/><path d="M330 -40L500 1960" stroke-width="46"/>
<path d="M-40 1040L1120 960" stroke-width="26"/><path d="M780 -40L880 1960" stroke-width="26"/>
<path d="M-40 300L1120 170" stroke-width="16"/><path d="M120 -40L220 1960" stroke-width="16"/>
<path d="M560 -40L690 1960" stroke-width="16"/><path d="M-40 1400L1120 1440" stroke-width="16"/><path d="M-40 840L1120 770" stroke-width="16"/>
</g>
<rect width="1080" height="1920" fill="rgba(14,11,9,.42)"/>
<path d="M170 1860C300 1790 250 1700 410 1650S650 1590 610 1500C580 1420 250 1450 170 1340S132 1180 132 ROUTE_END" fill="none" stroke="#FFB23E" stroke-width="12" stroke-linecap="round" stroke-dasharray="2 34" opacity=".85"/></svg>"""
OUTRO_PIN = ('<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="#FFB23E"/>'
             '<circle cx="100" cy="92" r="60" fill="#17130F"/>'
             '<path d="M82 66c-5-7 5-11 0-19M100 62c-5-7 5-12 0-20M118 66c-5-7 5-11 0-19" fill="none" stroke="#FFB23E" stroke-width="6" stroke-linecap="round"/>'
             '<path d="M62 84h76c0 26-16 42-38 42S62 110 62 84z" fill="#FFB23E"/><rect x="55" y="78" width="90" height="9" rx="4.5" fill="#FFB23E"/></svg>')


def scene_outro(lines):
    """맨 끝 장면. 프로필 사진과 같은 지도 위에 계정 이름. 사진 출처가 여러 줄이면 그 아래에 작게(읽을 수 있는 크기로) 모아요.

    점선 길은 화면 아래에서 출발해 이름 옆 핀까지 끊기지 않고 이어져요. (유튜브용 끝 장면과 같은 모양)
    """
    top = 240 if lines else 730  # 이름의 위쪽 위치. 출처 목록이 있으면 위로 올려요
    backdrop_map = OUTRO_MAP.replace("ROUTE_END", str(top + 115 + 42))  # 핀 끝 바로 아래까지
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or ""
    name = f"{esc(name[:2])}<b>{esc(name[2:])}</b>" if name.startswith("먹고") else esc(name)
    rows = "".join(f'<div class="src-l">{esc(big)}' + (f"<span>{esc(small)}</span>" if small else "") + "</div>" for big, small in lines)
    foot = ""
    if any("CC BY" in big for big, _ in lines):  # CC BY 는 고쳐 썼는지와 라이선스 주소도 알려야 해요
        foot = '<div class="src-f">사진은 잘라서 보정했어요 · creativecommons.org/licenses</div>'
    src = f'<div class="src"><div class="src-h">사진 출처</div>{rows}{foot}</div>' if lines else ""
    return f'{backdrop_map}<div class="end" style="top:{top}px"><div class="sig">{OUTRO_PIN}<span>{name}</span></div>{src}</div>'


# 끝 장면 없이 같은 장면에 브랜드를 넣는 장면 종류와 기본 바탕. dark=검정 지도, paper=주황 핀의 종이 지도, green=초록 지도
INLINE_BRAND = {"check": "dark", "sheet": "paper"}
MAP_COLORS = {  # 프로필 사진(insta-profile/make.py)과 같은 색: 땅, 물, 공원, 길, 점선 길, 핀, 핀 안쪽, 이름 앞, 이름 뒤
    "dark":  ("#17130F", "#0F1A22", "#1B2418", "#2B251E", "#FFB23E", "#FFB23E", "#17130F", "#FFFFFF", "#FFB23E"),
    "paper": ("#F3EAD7", "#BFDDE6", "#D3E3B8", "#FFFFFF", "#E0582B", "#E0582B", "#FFFFFF", "#231C15", "#E0582B"),
    "green": ("#DCEBCB", "#A9D5E8", "#BFDCA0", "#FFFDF5", "#D8432B", "#D8432B", "#FFFDF5", "#1F2A1A", "#D8432B"),
}


def brand_map(theme):
    """장면 뒤에 옅게 까는 지도."""
    land, water, park, road, route, *_ = MAP_COLORS[theme]
    return (f'<svg class="bgmap" viewBox="0 0 1080 1920"><rect width="1080" height="1920" fill="{land}"/>'
            f'<path d="M-40 1610C180 1550 300 1710 520 1670S900 1550 1120 1630V1960H-40z" fill="{water}"/>'
            f'<path d="M700 -20h260v330H640z" fill="{park}"/><path d="M-20 250h230l-60 300H-20z" fill="{park}"/><path d="M850 1060h270v300H790z" fill="{park}"/>'
            f'<g fill="none" stroke="{road}" stroke-linecap="round">'
            '<path d="M-40 640L1120 500" stroke-width="46"/><path d="M330 -40L500 1960" stroke-width="46"/>'
            '<path d="M-40 1040L1120 960" stroke-width="26"/><path d="M780 -40L880 1960" stroke-width="26"/>'
            '<path d="M-40 300L1120 170" stroke-width="16"/><path d="M120 -40L220 1960" stroke-width="16"/>'
            '<path d="M560 -40L690 1960" stroke-width="16"/><path d="M-40 1400L1120 1440" stroke-width="16"/><path d="M-40 840L1120 770" stroke-width="16"/></g>'
            # 점선 길은 화면 아래에서 출발해 아래쪽 이름 옆 핀 끝까지 이어져요
            f'<path d="M80 1980C200 1910 430 1890 440 1800S330 1700 302 1678" fill="none" stroke="{route}" stroke-width="19" stroke-linecap="round" stroke-dasharray="2 44"/></svg>')


def brand_foot(theme, lines=()):
    """화면 아래쪽의 핀과 계정 이름. 사진 출처가 여러 줄이면 그 아래에 작게."""
    *_, pin, hole, fg, ac = MAP_COLORS[theme]
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
    name = f"{esc(name[:2])}<b>{esc(name[2:])}</b>" if name.startswith("먹고") else esc(name)
    icon = (f'<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="{pin}"/>'
            f'<circle cx="100" cy="92" r="60" fill="{hole}"/>'
            f'<path d="M82 66c-5-7 5-11 0-19M100 62c-5-7 5-12 0-20M118 66c-5-7 5-11 0-19" fill="none" stroke="{pin}" stroke-width="6" stroke-linecap="round"/>'
            f'<path d="M62 84h76c0 26-16 42-38 42S62 110 62 84z" fill="{pin}"/><rect x="55" y="78" width="90" height="9" rx="4.5" fill="{pin}"/></svg>')
    src = "".join(f'<div>{esc(big)}' + (f" · {esc(small)}" if small else "") + "</div>" for big, small in lines)
    return (f'<div class="brandfoot" style="color:{fg}"><div class="sig2">{icon}<span>{name}</span></div>'
            + (f'<div class="bsrc">사진 {src}</div>' if src else "") + f'<style>.brandfoot .sig2 b{{color:{ac}}}</style></div>')


SCENES = {"cover": scene_cover, "card": scene_card, "duo": scene_duo, "info": scene_info,
          "check": scene_check, "sheet": scene_sheet, "rank": scene_rank, "tease": scene_tease}

# 장면이 넘어가는 방법 (base.css 의 in-이름, out-이름). 영상 종류마다 다르게 섞어요.
TRANSITION = 0.3
EASE = "cubic-bezier(.76,0,.24,1)"
CYCLE = {"저녁": ["push"], "소식": ["deal", "push"], "제철": ["push", "wipe"], "세계": ["wipe", "push"], "해외": ["wipe", "push"]}


def transition(kind, frames, i, scenes):
    """앞 장면에서 i번째 장면으로 넘어가는 방법을 골라요."""
    if frames[i][0] == "outro":
        return "fade"
    if scenes[i].get("in") in ("push", "deal", "wipe", "zoom", "fade"):
        return scenes[i]["in"]
    if i == 1 or frames[i][0].startswith("cover"):  # 첫 장면 다음과 마무리 장면은 앞으로 당겨 들어와요
        return "zoom"
    cycle = CYCLE.get(kind, ["push"])
    return cycle[i % len(cycle)]


SHORTEST, LONGEST = 10.0, 15.0  # 영상 전체 길이(초). 사용자가 정한 범위예요.
LONGEST_RANK = 20.0  # TOP 5 는 앞에 상황극 첫마디가 붙어서 20초까지 돼요 (2026-10-16 사용자가 정함)


def longest(spec):
    return LONGEST_RANK if any(s["type"] == "rank" for s in spec.get("scenes", [])) else LONGEST


def fit(scenes, tail, top=LONGEST):
    """장면 길이를 고르게 늘이거나 줄여서 전체가 10~15초(TOP 5 는 20초) 안에 들게 해요."""
    for s in scenes:
        s.setdefault("dur", 2.4)
    body = sum(s["dur"] for s in scenes)
    target = min(max(body, SHORTEST - tail), top - tail)
    if abs(target - body) > 0.01:
        for s in scenes:
            s["dur"] = round(s["dur"] * target / body, 2)
    if min(s["dur"] for s in scenes if s["type"] != "tease") < 1.2:  # "1위는?" 같은 멈춤 장면은 짧아도 돼요
        raise ValueError(f"장면이 {len(scenes)}개라 {top:.0f}초 안에 다 보여 줄 수 없어요. 장면을 줄여 주세요.")


# 먹고갈지도만의 노래(video/brand_music.py 로 만든 것). 영상 갈래마다 어울리는 곡을 골라요. (2026-10-16 사용자가 넣으라고 함)
# 설계도에 "music": "none" 을 적으면 노래 없이, "brand-walk" 처럼 적으면 그 곡으로 만들어요.
SONGS = {"제철": "brand-picnic", "유행": "brand-picnic", "저녁": "brand-market", "지역": "brand-market",
         "이야기": "brand-night", "소식": "brand-walk", "발견": "brand-walk", "세계": "brand-walk", "해외": "brand-walk"}


def song(spec):
    name = spec.get("music") or SONGS.get(spec.get("kind", ""), "brand-walk")
    return "none" if name == "none" else f"file:{name}"


def build_html(spec):
    """설계도를 한 장짜리 HTML로 만들어요. (HTML, 길이)"""
    accent = spec.get("accent") or ACCENTS.get(spec.get("kind", ""), "#FFB23E")
    scenes = spec["scenes"]
    ctx = {"cards": sum(1 for s in scenes if s["type"] == "card"), "card_no": 0, "brand": spec.get("brand"),
           "ranks": sum(1 for s in scenes if s["type"] == "rank") or 5, "top": spec.get("top"), "rank_note": spec.get("rank_note")}
    meta = {"music": song(spec), "sfx": [], "ambience": []}  # 먹고갈지도 노래를 조용히 깔아요. 효과음은 넣지 않아요.
    css = (HERE / "base.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">', f"<style>{css}</style></head>",
           f'<body style="--ac:{accent}">']
    # 맨 끝에는 늘 계정 이름 장면이 붙어요. 사진 출처가 한 줄이면 게시글에 적고, 여러 줄이면 이 장면에 모아요.
    lines = credit_lines(spec)
    lines = lines if len(lines) > 1 else []
    # 체크·한 장 정리는 끝 장면을 따로 붙이지 않아요. 같은 장면 뒤에 지도를 옅게 깔고 아래에 이름을 넣어요. (2026-10-15 사용자가 정함)
    inline = all(s["type"] in INLINE_BRAND for s in scenes)
    tail = 0 if inline else (min(3.0, 2.0 + .25 * max(0, len(lines) - 2)) if lines else 1.5)
    fit(scenes, tail, longest(spec))
    frames = []
    for i, s in enumerate(scenes):
        kind, body = SCENES[s["type"]](s, i, ctx)
        if inline:
            theme = spec.get("theme") or INLINE_BRAND[s["type"]]
            body = brand_map(theme) + body + brand_foot(theme, lines)
            kind += f" th-{theme}"
        frames.append((kind, body, s["dur"]))
    if not inline:
        frames.append(("outro", scene_outro(lines), tail))
    how = [None] + [transition(spec.get("kind", ""), frames, i, scenes) for i in range(1, len(frames))]
    at = 0.0
    for i, (kind, body, dur) in enumerate(frames):
        last = i == len(frames) - 1
        moves = []
        if i:  # 들어올 때
            moves.append(f"in-{how[i]} {TRANSITION}s {EASE} both")
        if not last:  # 다음 장면이 들어올 때 함께 나가요
            moves.append(f"out-{how[i + 1]} {TRANSITION}s {EASE} {dur}s forwards")
        style = f' style="animation:{", ".join(moves)}"' if moves else ""
        if not i:
            kind += " first"  # 첫 화면이 썸네일이 되므로 글이 처음부터 보이게 해요
        out.append(f'<section class="scene {kind}" data-at="{at:.2f}" data-dur="{dur}" data-out="{0 if last else TRANSITION}"{style}>{body}</section>')
        at += dur
    out.append(f"<script>{(HERE / 'base.js').read_text(encoding='utf-8')}</script></body></html>")
    return "\n".join(out), at, meta


# ── 카드 뉴스 ─────────────────────────────────────────────────────────
# 먹거리 소식은 영상이 아니라 넘겨 보는 카드로 만들어요. 소식 하나가 한 장이에요.
#   위: 계정 이름과 날짜, 사진   가운데: 분류, 한 줄 소식, 핵심 숫자   아래: 까닭(사실 한두 줄), 자료 이름
CARD_MIN, CARD_MAX = 2, 5
CARD_SIZE = {"width": 1080, "height": 1350}
NEWS_MAP = OUTRO_MAP.replace('class="map"', 'preserveAspectRatio="xMidYMin slice"').replace("ROUTE_END", "1100")
# 카드 묶음의 갈래: (계정 이름 옆 이름표, 첫 장에 붙는 말, 강조색). kind 로 골라요.
NEWS_SERIES = ("뉴스", "오늘의 먹거리 뉴스", "#FFB23E")  # 강조색은 프로필 사진의 핀과 같은 색
SERIES = {"유행": ("트렌드", "요즘 뜨는 메뉴", "#FF8FA8")}


def is_cards(spec):
    return spec.get("format") == "cards"


def series(spec):
    return SERIES.get(spec.get("kind"), NEWS_SERIES)


def why_lines(card):
    why = card.get("why") or []
    return [why] if isinstance(why, str) else list(why)


def card_problems(spec):
    """카드 뉴스 설계도에서 고칠 곳을 찾아요. (꼭 고칠 것, 고치면 좋은 것)"""
    must, should = [], []
    cards = spec.get("cards") or []
    if not CARD_MIN <= len(cards) <= CARD_MAX:
        must.append(f"카드가 {len(cards)}장이에요. {CARD_MIN}~{CARD_MAX}장으로 맞춰 주세요.")
    cover = spec.get("cover") or {}
    if not cover.get("title") or not cover.get("items"):
        must.append("첫 장(cover)이 없어요. title(궁금하게 하는 한마디)과 items(소식마다 한 줄)를 적어 주세요.")
    else:
        if len(cover["title"].split("\n")) > 3:
            must.append("첫 장: title 은 세 줄까지예요.")
        if max(units(line) for line in cover["title"].split("\n")) > 11:
            should.append("첫 장: title 이 길어 글자가 작아져요. 한 줄에 10자 안쪽으로 줄여 주세요.")
        if len(cover["items"]) != len(cards):
            should.append(f"첫 장: items 가 {len(cover['items'])}줄인데 소식은 {len(cards)}개예요. 소식마다 한 줄씩 적어 주세요.")
        if any(units(line) > 17 for line in cover["items"]):
            should.append("첫 장: items 한 줄이 길어 글자가 작아져요. 16자 안쪽으로 줄여 주세요.")
    for n, c in enumerate(cards, 1):
        for key, name in (("tag", "분류"), ("headline", "한 줄 소식"), ("why", "까닭"), ("src", "자료 이름")):
            if not c.get(key):
                must.append(f"카드 {n}: {name}({key})이 없어요.")
        head = str(c.get("headline") or "").split("\n")
        if len(head) > 2:
            must.append(f"카드 {n}: 한 줄 소식은 두 줄까지예요.")
        if max(units(line) for line in head) > 13:
            should.append(f"카드 {n}: 한 줄 소식이 길어 글자가 작아져요. 한 줄에 12자 안쪽으로 줄여 주세요.")
        why = why_lines(c)
        if len(why) > 2:
            must.append(f"카드 {n}: 까닭은 두 줄까지예요. 나머지는 게시글에 써 주세요.")
        if any(units(line) > 22 for line in why):
            should.append(f"카드 {n}: 까닭 한 줄이 길어 글자가 작아져요. 22자 안쪽으로 줄여 주세요.")
        if c.get("fact") and units(c["fact"]) > 20:
            should.append(f"카드 {n}: 핵심 숫자 줄이 길어요. 20자 안쪽으로 줄여 주세요.")
        if c.get("note") and units(c["note"]) > 9:
            should.append(f"카드 {n}: 스티커 한마디(note)가 길어요. 8자 안쪽으로 줄여 주세요.")
        if not c.get("photo") and not c.get("big"):
            should.append(f"카드 {n}: 사진이 없어요. 맞는 사진이 없으면 big 에 큰 숫자(예: -9%)를 적어 주세요.")
    if "출처" not in (spec.get("caption") or ""):
        must.append("게시글(caption) 끝에 '출처: 기관·매체 이름(날짜)' 줄을 적어 주세요. 카드에는 출처 장이 없어요.")
    return must, should


def news_cover(cover, total, when, name, pill, label):
    """첫 장. 오늘 소식들을 궁금하게 던져요. 답은 다음 장부터 나와요."""
    if cover.get("photo"):
        src, pos = fetch_photo(cover["photo"])
        top = f'<div class="ph"><img src="{src}" style="object-position:{pos}"></div>'
    else:
        top = f'<div class="ph">{NEWS_MAP}</div>'
    size = min(fit_size(line, 58, 880) for line in cover["items"])
    rows = "".join(f'<li style="font-size:{size}px">{rich(line)}</li>' for line in cover["items"])
    return (
        f'<section class="nc cv" id="c1">{top}'
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><span class="tag">{label} {total}</span>'
        f'<div class="hl" style="font-size:{fit_size(cover["title"], 122, 950)}px">{rich(cover["title"])}</div>'
        f'<ul class="list">{rows}</ul></div>'
        f'<div class="foot"><span></span><b class="go">밀어서 확인하기 →</b></div></section>'
    )


SPARK = ('<svg class="spark" viewBox="0 0 120 120"><g stroke="currentColor" stroke-width="9" stroke-linecap="round" fill="none">'
         '<path d="M60 8v30"/><path d="M60 82v30"/><path d="M8 60h30"/><path d="M82 60h30"/></g></svg>')


def news_card(c, n, total, when, name, pill):
    note = f'<div class="note">{rich(c["note"])}</div>' if c.get("note") else ""  # 사진 위에 붙이는 스티커 한마디
    if c.get("photo") and c["photo"].get("fit") == "pack":  # 상품 사진은 하얀 사진 카드처럼 살짝 기울여 얹어요
        top = f'<div class="ph">{NEWS_MAP}</div><div class="pack"><img src="{pack_photo(c["photo"])}"></div>{SPARK}'
    elif c.get("photo"):
        src, pos = fetch_photo(c["photo"])
        top = f'<div class="ph"><img src="{src}" style="object-position:{pos}"></div>'
    else:  # 맞는 사진이 없는 소식은 지도 바탕에 큰 숫자를 얹어요
        big = f'<div class="bignum" style="font-size:{fit_size(c["big"], 230, 950)}px">{rich(c["big"])}</div>' if c.get("big") else ""
        top = f'<div class="ph">{NEWS_MAP}</div>{big}'
    fact = f'<div class="fact" style="font-size:{fit_size(c["fact"], 56, 950)}px">{rich(c["fact"])}</div>' if c.get("fact") else ""
    why = why_lines(c)
    size = min(fit_size(line, 44, 915) for line in why)
    rows = "".join(f'<div style="font-size:{size}px">{rich(line)}</div>' for line in why)
    return (
        f'<section class="nc" id="c{n + 1}">{top}{note}'  # c1 은 첫 장(표지)이에요
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><span class="tag">{esc(c["tag"])}</span>'
        f'<div class="hl" style="font-size:{fit_size(c["headline"], 98, 950)}px">{rich(c["headline"])}</div>{fact}'
        f'<div class="why">{rows}</div></div>'
        f'<div class="foot"><span>자료 {esc(c["src"])}</span><b>{n} / {total}</b></div></section>'
    )


def build_cards(spec):
    """카드 뉴스 설계도를 한 쪽짜리 HTML로 만들어요. 카드는 #c1, #c2 … 로 위에서 아래로 놓여요. (HTML, 장수)"""
    must, _ = card_problems(spec)
    if must:
        raise ValueError(" / ".join(must))
    pill, label, color = series(spec)
    accent = spec.get("accent") or color
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or ""
    name = f"{esc(name[:2])}<b>{esc(name[2:])}</b>" if name.startswith("먹고") else esc(name)
    css = (HERE / "cards.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    cards = spec["cards"]
    when = spec.get("kicker", "")
    body = news_cover(spec["cover"], len(cards), when, name, pill, label)
    body += "".join(news_card(c, n, len(cards), when, name, pill) for n, c in enumerate(cards, 1))
    page = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head><body style="--ac:{accent}">{body}</body></html>'
    return page, len(cards) + 1


def description(spec):
    """게시글에 넣을 글. 문구, 사진 출처 한 줄, 해시태그.

    사진 출처가 한 줄이면 그대로 짧게 적고, 여러 줄이면 영상 맨 끝 장면에 모았다고만 알려요.
    (한국관광공사 사진은 작가 이름까지가 정해진 표기라서 줄이지 않아요.)
    카드 뉴스에는 끝 장면이 없어서 사진 출처를 모두 게시글에 적어요.
    """
    lines = [spec["caption"].strip(), ""]
    shown = credit_lines(spec)
    if is_cards(spec):
        for big, small in shown:
            lines.append(f"📷 {big}" + (f" · {small} · 잘라서 보정함" if "CC BY" in big else ""))
        if shown:
            lines.append("")
    elif len(shown) == 1:
        big, small = shown[0]
        extra = f" · {small} · 잘라서 보정함" if "CC BY" in big else ""
        lines += [f"📷 {big}{extra}", ""]
    elif shown:
        lines += ["📷 사진 출처는 영상 마지막 장면에 정리했어요.", ""]
    lines.append(" ".join("#" + t for t in hashtags(spec.get("tags"))))
    return "\n".join(lines) + "\n"


BLOG_URL = "https://blog.naver.com/hongbeom_404"


# 출처 주소 -> 매체·기관 이름. 유튜브 설명에는 주소 대신 이름만 짧게 적어요.
OUTLETS = {
    "yna.co.kr": "연합뉴스", "news1.kr": "뉴스1", "newsis.com": "뉴시스", "kbs.co.kr": "KBS", "imbc.com": "MBC", "sbs.co.kr": "SBS",
    "jtbc.co.kr": "JTBC", "ytn.co.kr": "YTN", "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
    "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보", "mk.co.kr": "매일경제", "hankyung.com": "한국경제",
    "mt.co.kr": "머니투데이", "sedaily.com": "서울경제", "fnnews.com": "파이낸셜뉴스", "asiatoday.co.kr": "아시아투데이",
    "segye.com": "세계일보", "edaily.co.kr": "이데일리", "kyongbuk.co.kr": "경북일보", "withbuyer.com": "위드바이어",
    "korea.kr": "정책브리핑", "mof.go.kr": "해양수산부", "incheon.go.kr": "해양수산부 이달의 수산물", "kamis.or.kr": "aT",
    "at.or.kr": "aT", "mafra.go.kr": "농림축산식품부", "mfds.go.kr": "식약처", "open-meteo.com": "Open-Meteo 날씨",
    "visitkorea.or.kr": "한국관광공사", "nongshim.com": "농심", "hongseong.go.kr": "홍성군",
    "kyeongin.com": "경인일보", "tenasia.co.kr": "텐아시아", "mtn.co.kr": "머니투데이방송", "heraldcorp.com": "헤럴드경제",
    "nocutnews.co.kr": "노컷뉴스", "ohmynews.com": "오마이뉴스", "dt.co.kr": "디지털타임스", "etnews.com": "전자신문",
    "insightkorea.co.kr": "인사이트코리아", "hankooki.com": "한국일보", "seoul.co.kr": "서울신문", "kmib.co.kr": "국민일보",
}


def outlet(url):
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    return next((name for dom, name in OUTLETS.items() if host == dom or host.endswith("." + dom)), host)


def youtube_text(spec):
    """유튜브 쇼츠에 넣을 (제목, 설명). 설명은 짧게 (2026-10-15 사용자가 정한 꼴):

    첫 줄(무슨 내용인지) / 둘째 줄(몇 가지인지) / 번호 목록 / ※ 알아 둘 말 / 📌 출처: 이름만 / 📷 사진 출처 / 물음 하나 / 해시태그 3개
    설계도에 yt_title, yt_points(목록), yt_note(※ 줄)를 적으면 그걸 쓰고, 없으면 게시글과 장면에서 뽑아요.
    """
    title = " ".join(str(spec.get("yt_title") or spec.get("title") or "").split())
    if len(title) > 100:
        title = title[:99].rstrip() + "…"
    lines = [x.strip() for x in spec.get("caption", "").strip().splitlines()]
    first = next((x for x in lines if x), title)
    # 목록: 설계도에 적은 것 > 카드 > 순위 > 카드 장면 > 체크·표
    points = spec.get("yt_points")
    if not points:
        plain = lambda t: " ".join(str(t).replace("[[", "").replace("]]", "").split())
        scenes = spec.get("scenes") or []
        if spec.get("cards"):
            points = [plain(c.get("headline", "")) for c in spec["cards"]]
        elif any(x["type"] == "rank" for x in scenes):
            ranks = sorted((x for x in scenes if x["type"] == "rank"), key=lambda x: x["no"])
            points = [f'{x["name"]} · {x.get("drink", "")}'.rstrip(" ·") for x in ranks]
        elif any(x["type"] == "card" for x in scenes):
            points = [plain(x.get("headline", "")) for x in scenes if x["type"] == "card"]
        else:
            for x in scenes:
                if x["type"] in ("check", "sheet"):
                    points = [it["name"] for it in x.get("items") or x.get("rows") or []]
    points = [p for p in (points or []) if p]
    out = [first]
    if len(points) > 1:
        what = {"소식": "오늘의 먹거리 뉴스", "유행": "요즘 뜨는 메뉴", "저녁": "오늘 저녁 메뉴"}.get(spec.get("kind"), "")
        if what:
            out.append(f"{what} {len(points)}가지")
        out.append("")
        out += [f"{i}. {p}" for i, p in enumerate(points, 1)]
    out.append("")
    body = spec.get("caption", "")
    note = spec.get("yt_note")
    if not note and ("값은" in body or "가격" in body or spec.get("kind") in ("소식", "유행")):
        note = "가격은 조사 시점과 판매 조건에 따라 달라질 수 있습니다."
    if not note and "음주" in body:
        note = "술 조합은 추천일 뿐이에요. 지나친 음주는 건강에 해로워요."
    if note:
        out.append(f"※ {note}")
    names = []
    m = re.search(r"출처\s*:\s*(.+)", body)
    if m:  # 게시글 끝의 "출처: 매체(날짜), …" 에서 이름만
        names = [re.sub(r"\(.*?\)", "", x).strip() for x in m.group(1).split(",")]
    names += [outlet(u) for u in spec.get("sources") or []]
    names = [n for n in dict.fromkeys(n for n in names if n and n != "한국관광공사")]
    if names:
        out.append("📌 출처: " + ", ".join(names[:6]))
    shown = []
    for big, small in credit_lines(spec):
        if "한국관광공사" in big:
            shown.append("한국관광공사 포토코리아")
        elif "CC BY" in big:
            shown.append(big + (f" ({small})" if small and "." in small else ""))  # CC BY 는 저작자·라이선스·원본을 줄이지 않아요
        else:
            shown.append(big)
    if "vault:" in json.dumps(spec, ensure_ascii=False):
        shown.append("직접 촬영")
    if shown:
        out.append("📷 사진 출처: " + ", ".join(dict.fromkeys(shown)))
    ask = next((x for x in reversed(lines[1:]) if x.endswith("?") or x.endswith("요?") or "댓글" in x), "")
    if ask:
        out.append(ask)
    tags = hashtags(spec.get("tags"))[:-1][:3]  # 마지막은 계정 이름이라 빼요
    out.append(" ".join("#" + t for t in tags))
    return title, "\n".join(out) + "\n"


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if is_cards(spec):
        must, should = card_problems(spec)
        for line in must:
            print("  꼭 고쳐 주세요: " + line)
        for line in should:
            print("  " + line)
        if must:
            sys.exit(1)
        _, count = build_cards(spec)  # 사진이 받아지는지도 여기서 확인돼요
        print(f"카드 뉴스 {count}장 (첫 장 1 + 소식 {count - 1})")
        if len(spec.get("tags") or []) != 4:
            print(f"  해시태그를 {len(spec.get('tags') or [])}개 적었어요. 4개만 골라 적어 주세요. (다섯 번째 계정 이름은 자동으로 붙어요)")
        print("  해시태그: " + " ".join("#" + t for t in hashtags(spec.get("tags"))))
        shown = credit_lines(spec)
        print(f"  사진 출처: {len(shown)}줄이 게시글에 자동으로 들어가요." if shown else "  사진 출처: 표시할 것이 없어요.")
        sys.exit(0)
    page, dur, _ = build_html(spec)
    print(f"{dur:.1f}초, 장면 {len(spec['scenes'])}개")
    if len(spec.get("tags") or []) != 4:
        print(f"  해시태그를 {len(spec.get('tags') or [])}개 적었어요. 4개만 골라 적어 주세요. (다섯 번째 계정 이름은 자동으로 붙어요)")
    print("  해시태그: " + " ".join("#" + t for t in hashtags(spec.get("tags"))))
    shown = credit_lines(spec)
    where = "게시글에 한 줄로" if len(shown) == 1 else "맨 끝 장면에"
    print(f"  사진 출처: {len(shown)}줄이 {where} 자동으로 들어가요." if shown else "  사진 출처: 표시할 것이 없어요.")
    for big, small in shown:
        if "CC BY" in big and "curid=" not in small:
            print(f"  '{big}' 에 원본 주소가 없어요. photos.py 가 알려 준 credit 을 그대로 적어 주세요.")
    for n, s in enumerate(spec["scenes"], 1):
        if s.get("video"):
            print(f"  장면 {n}: 동영상이에요. 영상을 만들 때 넣어요.")
        elif s["type"] == "card" and not is_tall(s["photo"]):
            print(f"  장면 {n}: 가로 사진이에요. 같은 음식의 세로 사진이 있으면 그걸 쓰면 화면을 꽉 채워요.")
