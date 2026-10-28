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
        beside = HERE.parent.parent / "jecheol-photos" / url[len("vault:"):]  # 매일 실행(클라우드): 보관함이 옆 폴더에 받아져 있어요
        if beside.exists():
            return beside.read_bytes()
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
ORIG = {}  # 사진 주소 -> 키우기 전 원래 크기 (잘라 쓴 사진은 잘라 낸 조각의 크기). 흐린 사진을 찾을 때 써요.


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


def photo_key(photo):
    """사진마다 저장할 이름. 같은 주소라도 잘라 쓰는 곳(crop)이 다르면 다른 사진이에요."""
    if isinstance(photo, str):
        photo = {"url": photo}
    raw = photo["url"] + (f'#crop={",".join(str(v) for v in photo["crop"])}' if photo.get("crop") else "")
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def fetch_photo(photo):
    """사진을 내려받아 보정한 뒤 JPEG로 저장하고 (파일 주소, 위치)를 돌려줘요.
    "crop": [왼, 위, 오른, 아래] (원본 픽셀)을 적으면 그 부분만 잘라 써요. 상품 봉지 사진에서 조리된 음식만 쓸 때처럼요."""
    if isinstance(photo, str):
        photo = {"url": photo}
    url = photo["url"]
    CACHE.mkdir(parents=True, exist_ok=True)
    key = photo_key(photo)
    path = CACHE / (key + "-g2.jpg")
    if not path.exists():
        data = read_source(url)
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if image.mode in ("RGBA", "LA", "P"):  # 바탕이 투명한 로고는 흰 바탕에 얹어요 (검게 나오지 않게)
            image = image.convert("RGBA")
            white = Image.new("RGBA", image.size, "white")
            white.alpha_composite(image)
            image = white
        image = image.convert("RGB")
        if photo.get("crop"):
            image = image.crop(tuple(photo["crop"]))
            (CACHE / (key + ".orig")).write_text("%d %d" % image.size)  # 키우기 전 조각 크기
            if min(image.size) < 900:  # 잘라 낸 조각이 작으면 키워요 (grade 가 한 번 더 선명하게 해요)
                k = 900 / min(image.size)
                image = image.resize((round(image.width * k), round(image.height * k)), Image.LANCZOS)
        if min(image.size) < 500:
            raise ValueError(f"사진이 너무 작아요 ({image.size[0]}x{image.size[1]}): {url}")
        if not (CACHE / (key + ".orig")).exists():
            (CACHE / (key + ".orig")).write_text("%d %d" % image.size)
        grade(image).save(path, "JPEG", quality=92)
    if key not in SIZES:
        with Image.open(path) as im:
            SIZES[key] = im.size
    if key not in ORIG and (CACHE / (key + ".orig")).exists():
        ORIG[key] = tuple(int(v) for v in (CACHE / (key + ".orig")).read_text().split())
    return path.as_uri(), photo.get("pos", "50% 50%")


def pack_photo(photo):
    """상품 사진(회사가 나눠 준 포장 사진)은 자르지 않고 통째로 보여 줘요. 둘레의 흰 여백만 잘라 내요."""
    url = photo["url"] if isinstance(photo, dict) else photo
    fetch_photo(photo)
    key = photo_key(photo)
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
    path = CACHE / (photo_key(photo) + "-blur.jpg")
    if not path.exists():
        with Image.open(CACHE / (photo_key(photo) + "-g2.jpg")) as im:
            small = im.convert("RGB").resize((108, 192), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7))
            ImageEnhance.Brightness(small).enhance(0.5).save(path, "JPEG", quality=88)
    return path.as_uri()


def is_tall(photo):
    url = photo["url"] if isinstance(photo, dict) else photo
    fetch_photo(photo)
    w, h = SIZES[photo_key(photo)]
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
    if not s.get("photo"):  # 맞는 사진이 없는 장면은 다른 음식 사진 대신 지도 바탕에 글만 (2026-10-23 6단계, PROMPT.md "사진은 내용을 정한 뒤에")
        return NEWS_MAP, BLANK, True
    return img(s["photo"]), backdrop(s["photo"]), is_tall(s["photo"])


BLANK = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"  # 사진 없는 장면의 흐린 바탕 자리(투명 1px)


def zoomed(photo):
    """설계도에 "fit": "cover" 를 적은 사진만 화면을 꽉 채우게 잘라요."""
    return isinstance(photo, dict) and photo.get("fit") == "cover"


def keep_whole(photo):
    """원본 전체가 중요한 사진: 상품 포장·포스터·안내문처럼 디자인된 그림. 잘리지 않게 통째로 둬요.
    설계도 사진에 "fit": "contain"(또는 "whole"·"pack")이나 "kind": "poster"·"pack" 을 적어요.
    (2026-10-17 "확대 요청이 없으면 안 잘리게" 규칙은 이런 사진에만 남기고, 음식 사진은 2026-10-28 사용자 승인으로 크게 보여 줘요)"""
    return isinstance(photo, dict) and (photo.get("fit") in ("contain", "whole", "pack") or photo.get("kind") in ("poster", "pack"))


def fills(photo):
    """가로 음식 사진을 세로 화면에 크게(칸을 꽉 채워, 가장자리만 자연스럽게 잘려요). 핵심이 가장자리에 있으면 "pos" 로 옮겨요."""
    return bool(photo) and not zoomed(photo) and not keep_whole(photo)


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
    tag, back, tall = moving(s, s["dur"])
    fill = not s.get("video") and not tall and fills(s.get("photo"))  # 가로 음식 사진: 위쪽 큰 칸을 꽉 채워요 (2026-10-28)
    whole = not s.get("video") and not zoomed(s.get("photo")) and not fill
    parts = [(f'<div class="back"><img src="{back}"></div>' if whole or fill else "")
             + f'<div class="pic{" whole" if whole else " fill" if fill else ""}">{tag}</div>', '<div class="mid">']
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
    inset = ""
    if s.get("inset"):  # 장소 사진 위에 음식 사진 한 장을 작게 겹쳐요 (2026-10-22 차이나타운 + 짜장면)
        src, pos = fetch_photo(s["inset"])
        inset = f'<div class="inset a rise" style="--dl:.3s;--d:.3s"><img src="{src}" style="object-position:{pos}"></div>'
    return "card", (
        f'<div class="back"><img src="{back}"></div>'
        f'<div class="pic {"tall" if tall else "wide"}{"" if s.get("video") or zoomed(s.get("photo")) else " fill" if not tall and fills(s.get("photo")) else " whole"}">{tag}</div>{inset}<div class="shade"></div>'
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
    """시안 A. 순위 하나. 사진을 화면 가득 깔고 큰 순위 숫자, 메뉴 이름, 상황 한 줄.

    {"type": "rank", "no": 5, "name": "곱창", "line": "불판 앞에 앉으면 끝", "photo": {...}}
    사진은 세로로 잘라도 불판·접시가 통째로 보이는 것만 써요. 천천히 7%만 다가가요.
    술(drink)은 2026-10-18 사용자가 빼자고 해서 화면에 넣지 않아요.
    "vs" 를 적으면 먹는 방식이 갈리는 메뉴(부먹·찍먹 등)를 사진 두 장을 살짝 겹쳐 보여 주고 물어봐요(scene_vs).
    """
    if s.get("vs"):
        return scene_vs(s, i, ctx)
    total = ctx.get("ranks", 5)
    if s.get("video"):  # 사용자가 보낸 동영상은 그대로 움직이게 둬요
        pic = f'<div class="pic">{moving(s, s["dur"])[0]}</div>'
    elif not zoomed(s["photo"]):
        # 가로 사진은 잘라서 꽉 채우지 않고 통째로 보여 줘요(멀리서 본 느낌). 빈 곳은 같은 사진을 흐리게 깔아요. (2026-10-15 사용자: 너무 확대돼 보임)
        src, pos = fetch_photo(s["photo"])
        pic = (f'<div class="pic"><img src="{backdrop(s["photo"])}"></div>'
               f'<div class="pic rk-wide{" rk-tall" if is_tall(s["photo"]) else ""}"><img class="kb a" src="{src}" style="--d:{s["dur"]}s"></div>')
    else:
        src, pos = fetch_photo(s["photo"])
        pic = f'<div class="pic"><img class="kb a" src="{src}" style="object-position:{pos};--d:{s["dur"]}s"></div>'
    name = (f'<div class="rk-name">{rise("", s["name"], .2, tag="b")}'
            + (rise("say", s["line"], .5) if s.get("line") else "") + "</div>")
    no = f'<div class="rk-no a pop" style="--d:.4s">{int(s["no"])}<small>위</small></div>'
    return "rank", pic + '<div class="rk-shade"></div>' + rank_top(ctx, total - int(s["no"]) + 1) + no + name


def scene_vs(s, i, ctx):
    """먹는 방식이 갈리는 메뉴를 사진 두 장으로. 두 장이 살짝 겹쳐 기울어 있고, 가운데 VS, 아래에 "여러분은 무슨 파?" 물음.
    (2026-10-18 사용자: 1위 돈까스에 소스가 없다, 부먹·찍먹 사진 두 장이 살짝 겹치고 "여러분은 무슨 파세요?" 물어보자)

    {"type": "rank", "no": 1, "name": "돈까스", "line": "…", "photo": <부먹 사진, 흐린 바탕용>,
     "vs": {"a": {"photo": {...}, "label": "부먹"}, "b": {"photo": {...}, "label": "찍먹"}, "ask": "여러분은
[[부먹파]]? [[찍먹파]]?"}}
    """
    total = ctx.get("ranks", 5)
    vs = s["vs"]
    cards = ""
    for k, side in enumerate(("a", "b")):
        src, pos = fetch_photo(vs[side]["photo"])
        cards += (f'<div class="vs-card vs-{side} a rise" style="--dl:{.05 + k * .12}s;--d:.35s">'
                  f'<img src="{src}" style="object-position:{vs[side]["photo"].get("pos", pos) if isinstance(vs[side]["photo"], dict) else pos}">'
                  f'<span class="vs-lab">{esc(vs[side]["label"])}</span></div>')
    back = backdrop(vs["a"]["photo"])
    no = f'<div class="rk-no vs-no a pop" style="--d:.4s">{int(s["no"])}<small>위</small></div>'
    name = (f'<div class="rk-name vs-name">{rise("", s["name"], .2, tag="b")}'
            + (rise("say", s["line"], .45) if s.get("line") else "") + "</div>")
    ask = rise("vs-ask", vs.get("ask", "여러분은 무슨 파예요?"), .6) + rise("vs-sub", vs.get("sub", "댓글로 알려 주세요"), .75)
    return "rank vs", (f'<div class="pic"><img src="{back}"></div><div class="rk-shade"></div>' + rank_top(ctx, total - int(s["no"]) + 1)
                       + cards + '<div class="vs-mark a pop" style="--dl:.3s;--d:.3s">VS</div>' + no + name + ask)


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


def scene_lineup(s, i, ctx):
    """참가 업체 김밥을 사진 타일로 2~4개씩. 사진 아래에 지역·업체 이름과 김밥 이름. 타일이 차례로 올라와요.
    (2026-10-26 사용자: 김천김밥축제 쇼츠가 글자 위주라 어떤 김밥인지 모르겠다, 업체 사진을 3~4개씩 나눠 보여 주자)

    {"type": "lineup", "kicker", "title", "items": [{"photo", "region", "shop", "menu", "badge"}], "note"}
    업체 이름과 사진은 꼭 같은 집 같은 김밥이어야 해요. 같은 종류 사진으로 대신하지 않아요.
    """
    items, dur = s["items"], s["dur"]
    t0 = .35
    seg = min(.45, (dur * .55 - t0) / len(items))
    cells = ""
    for k, it in enumerate(items):
        badge = f'<span class="badge">{esc(it["badge"])}</span>' if it.get("badge") else ""
        where = " · ".join(v for v in (it.get("region"), it.get("shop")) if v)
        cells += (f'<div class="it a tile" style="--dl:{round(t0 + k * seg, 2)}s;--d:.4s"><div class="ph">{img(it["photo"])}{badge}</div>'
                  f'<div class="rg">{esc(where)}</div><div class="mn">{rich(it["menu"])}</div></div>')
    head = f'<div class="head">{rise("kicker", s.get("kicker", ""), .1)}{rise("title", s["title"], .3)}</div>'
    note = rise("note", s["note"], .6) if s.get("note") else ""
    return f'lineup n{len(items)}', f'{head}<div class="grid">{cells}</div>{note}'


def scene_winners(s, i, ctx):
    """끝 장면. 역대 우승작 사진 세 장을 모으고 가운데에 다음 축제를 묻는 말. 올해 것(마지막)이 가장 크게.
    (2026-10-26 사용자: 1·2·3회 우승작을 한 화면에 모으고 "다음엔 대체 무슨 김밥이 나올까?")

    {"type": "winners", "kicker", "title", "items": [{"photo", "no", "name"}, …3개]}
    """
    pics = ""
    for k, it in enumerate(s["items"][:3]):
        pics += (f'<div class="w w{k + 1} a tile" style="--dl:{.1 + k * .3:.2f}s;--d:.4s">{img(it["photo"])}'
                 f'<div class="lb"><span>{esc(it["no"])}</span><b>{rich(it["name"])}</b></div></div>')
    kicker = f'<i>{rich(s["kicker"])}</i>' if s.get("kicker") else ""
    q = f'<div class="q a hold" style="--dl:1s;--d:.45s">{kicker}<b>{rich(s["title"])}</b></div>'
    return "winners", pics + q


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
          "check": scene_check, "sheet": scene_sheet, "rank": scene_rank, "tease": scene_tease,
          "lineup": scene_lineup, "winners": scene_winners}

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


# 영상 전체 길이(초). 2026-10-19 사용자가 10~15초 일괄 제한을 없애고 갈래마다 정하기로 했어요.
# 짧으면 SHORTEST 까지 늘이고, 갈래의 상한을 넘으면 줄여요. 상한은 채울 목표가 아니에요 (PROMPT.md "영상 길이").
SHORTEST, LONGEST = 10.0, 20.0  # 일반 정보형
LONGEST_SKIT = 25.0  # TOP 5 와 발견형은 앞에 상황극 첫마디가 붙어요
SQUEEZE = 1.0  # 마지막으로 fit 이 장면 길이를 줄인 비율 (1.0 = 줄이지 않음)


def longest(spec):
    if spec.get("format") == "voice":  # 내레이션 쇼츠는 읽는 시간만큼 (59초까지)
        return 59.0
    if spec.get("longest"):  # 사용자가 장면을 더 넣어 달라고 한 영상만 (2026-10-26 김천김밥축제 업체·우승작)
        return float(spec["longest"])
    skit =spec.get("kind") == "발견" or any(s["type"] == "rank" for s in spec.get("scenes", []))
    return LONGEST_SKIT if skit else LONGEST


def fit(scenes, tail, top=LONGEST):
    """장면 길이를 고르게 늘이거나 줄여서 전체가 10초~갈래의 상한(longest) 안에 들게 해요."""
    for s in scenes:
        s.setdefault("dur", 2.4)
    global SQUEEZE
    body = sum(s["dur"] for s in scenes)
    target = min(max(body, SHORTEST - tail), top - tail)
    SQUEEZE = min(1.0, target / body)  # 상한 때문에 줄인 비율. 장면을 빼지는 않고 고르게 빨라져요 (아래 __main__ 이 알려 줘요)
    if abs(target - body) > 0.01:
        for s in scenes:
            s["dur"] = round(s["dur"] * target / body, 2)
    if min(s["dur"] for s in scenes if s["type"] != "tease") < 1.2:  # "1위는?" 같은 멈춤 장면은 짧아도 돼요
        raise ValueError(f"장면이 {len(scenes)}개라 {top:.0f}초 안에 다 보여 줄 수 없어요. 장면을 줄여 주세요.")


# 먹고갈지도만의 노래(video/brand_music.py 로 만든 것). 영상 갈래마다 어울리는 곡을 골라요. (2026-10-16 사용자가 넣으라고 함)
# 설계도에 "music": "none" 을 적으면 노래 없이, "brand-walk" 처럼 적으면 그 곡으로 만들어요.
# 2026-10-16 사용자가 정함: 저녁 TOP 5는 궁금한 느낌(궁금궁금), 발견형도 비슷한 결(살금살금).
SONGS = {"제철": "brand-picnic", "유행": "brand-munch", "저녁": "brand-curious", "지역": "brand-market",
         "이야기": "brand-night", "소식": "brand-walk", "발견": "brand-sneak", "세계": "brand-walk", "해외": "brand-walk"}


# 유튜브 오디오 보관함 곡 (2026-10-17 사용자가 골라 줌, 39곡). 곡 파일은 비공개 보관함 music/ 에 있고 목록은 video/music.json.
# 영상 갈래마다 분위기 묶음에서 날짜로 돌려 가며 골라요. 같은 날 같은 묶음을 쓰는 영상끼리는 SLOT 만큼 떨어진 곡을 써요.
LIBRARY = json.loads((HERE / "music.json").read_text(encoding="utf-8"))
MOODS = {"저녁": "궁금", "발견": "궁금", "해설": "궁금", "소식": "밝음", "유행": "밝음",
         "제철": "따뜻", "지역": "따뜻", "이야기": "따뜻", "세계": "따뜻", "해외": "따뜻"}
SLOT = {"3-dinner": 0, "4-find": 6, "10-voice": 3, "2-news": 0, "8-trend": 7, "1-monthly": 0, "1-check": 4, "1-sheet": 8,
        "5-world": 2, "6-story": 0, "7-local": 3, "9-abroad": 6}


def pick_track(spec):
    """그날 쓸 오디오 보관함 곡의 키. 설계도에 "music" 을 적었거나 날짜를 모르면 None (먹고갈지도 노래를 써요)."""
    name = spec.get("music")
    if name:
        return name[4:] if name.startswith("lib:") else None
    pool = LIBRARY["pools"].get(MOODS.get(spec.get("kind", ""), "따뜻"))
    day = spec.get("_day")
    if not pool or not day:
        return None
    from datetime import date
    return pool[(date.fromisoformat(day).toordinal() + SLOT.get(spec.get("_name", ""), 0)) % len(pool)]


def track_info(spec):
    """그 영상에 깔리는 곡 정보(title, artist, license, credit). 먹고갈지도 노래면 None."""
    key = pick_track(spec)
    return {"key": key, **LIBRARY["tracks"][key]} if key in LIBRARY["tracks"] else None


def music_line(spec):
    """CC 곡이면 게시글·설명에 꼭 넣을 출처 줄. 아니면 빈 글."""
    t = track_info(spec)
    return f"🎵 {t['credit']}" if t and t.get("credit") else ""


def song(spec):
    key = pick_track(spec)
    if key:
        return f"lib:{key}"
    name = spec.get("music") or SONGS.get(spec.get("kind", ""), "brand-walk")
    return "none" if name == "none" else f"file:{name}"


def build_html(spec):
    """설계도를 한 장짜리 HTML로 만들어요. (HTML, 길이)"""
    if spec.get("format") == "voice":
        import voice
        return voice.build_voice(spec)
    accent = spec.get("accent") or ACCENTS.get(spec.get("kind", ""), "#FFB23E")
    scenes = spec["scenes"]
    ctx = {"cards": sum(1 for s in scenes if s["type"] == "card"), "card_no": 0, "brand": spec.get("brand"),
           "ranks": sum(1 for s in scenes if s["type"] == "rank") or 5, "top": spec.get("top"), "rank_note": spec.get("rank_note")}
    meta = {"music": song(spec), "sfx": [], "ambience": []}  # 먹고갈지도 노래를 조용히 깔아요. 효과음은 넣지 않아요.
    import thumb
    css = (HERE / "base.css").read_text(encoding="utf-8") + thumb.css()
    css = css.replace("FONT_DIR", (HERE / "fonts").as_uri())
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">', f"<style>{css}</style></head>",
           f'<body style="--ac:{accent}">']
    # "thumb" 이 있으면 맨 앞 0.9초를 썸네일 화면(큰 두 줄 제목 + 사진 한 장)으로 보여 줘요. (2026-10-17 사용자가 정함, thumb.py)
    front = thumb.has(spec)
    # 맨 끝에는 늘 계정 이름 장면이 붙어요. 사진 출처는 몇 줄이든 게시글에 적고 이 장면에는 넣지 않아요.
    # (2026-10-22 사용자: "맨 뒷장에 출처 안 남기게". 로고만 가운데에)
    lines = []
    # 체크·한 장 정리는 끝 장면을 따로 붙이지 않아요. 같은 장면 뒤에 지도를 옅게 깔고 아래에 이름을 넣어요. (2026-10-15 사용자가 정함)
    inline = all(s["type"] in INLINE_BRAND for s in scenes)
    tail = 0 if inline else (min(3.0, 2.0 + .25 * max(0, len(lines) - 2)) if lines else 1.5)
    fit(scenes, tail, longest(spec) - (thumb.THUMB_SEC if front else 0))
    frames = [("thumb", thumb.body(spec), thumb.THUMB_SEC)] if front else []
    for i, s in enumerate(scenes):
        kind, body = SCENES[s["type"]](s, i, ctx)
        if inline:
            theme = spec.get("theme") or INLINE_BRAND[s["type"]]
            body = brand_map(theme) + body + brand_foot(theme, lines)
            kind += f" th-{theme}"
        frames.append((kind, body, s["dur"]))
    if not inline:
        frames.append(("outro", scene_outro(lines), tail))
    order = ([{"type": "thumb", "in": "zoom"}] if front else []) + scenes
    how = [None] + [transition(spec.get("kind", ""), frames, i, order) for i in range(1, len(frames))]
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
# 이야기 카드 ("mode": "story", 2026-10-18 사용자가 정함): 이슈 하나를 여러 장으로 풀어요.
#   첫 장(물음 하나) → 답·근거(비교 compare, 막대 chart, 사진·큰 숫자) → 까닭 → 정리(summary)
# type 이 없는 카드는 예전과 똑같이 그려요.
STORY_MIN, STORY_MAX = 3, 6
STORY_PILL, STORY_LABEL = "이슈", "오늘의 먹거리 이슈"
CARD_TYPES = ("compare", "chart", "summary", "hero")


def is_cards(spec):
    """그림 여러 장으로 올리는 것. 카드 뉴스와 넘겨 보는 해설(steps.py)이에요."""
    return spec.get("format") in ("cards", "steps")


def series(spec):
    return SERIES.get(spec.get("kind"), NEWS_SERIES)


def is_story(spec):
    return spec.get("mode") == "story"


# TOP5형 카드 ("mode": "top5", 2026-10-19 5단계): 음식 다섯 가지를 한 장씩. 장마다 실제 사진을 크게, 음식 이름·핵심 한 줄.
#   "rank_type": "추천"(기본) — 우리가 고른 추천이에요. 순위처럼 보이지 않게 "추천 1~5"로 차례대로 적고 "N위·순위·랭킹"을 쓰지 않아요.
#   "rank_type": "자료" — 판매량·조사 같은 실제 순위 자료가 있을 때만. "rank_src"(자료 이름 · 날짜)를 꼭 적고 5위부터 1위까지 거꾸로 세요.
#   (2026-10-19 사용자가 정함: "실제 순위 데이터가 아닌 추천형이라면 순위 근거가 있는 것처럼 표현하지 않는다")
TOP5_PILL = {"추천": "추천 5", "자료": "TOP 5"}
TOP5_LABEL = {"추천": "오늘의 추천 5", "자료": "오늘의 TOP 5"}
RANK_WORDS = re.compile(r"\d\s?위|순위|랭킹|1등|인정\?|가장 많이 팔린|제일 잘 팔린")
DATED = re.compile(r"\d+월|\d{4}|\d+주|\d+일")


def is_top5(spec):
    return spec.get("mode") == "top5"


def rank_type(spec):
    return "자료" if spec.get("rank_type") == "자료" else "추천"


def top5_problems(spec, must, should):
    """TOP5형 카드에서 고칠 곳."""
    cards = spec.get("cards") or []
    kind = rank_type(spec)
    if len(cards) != 5:
        must.append(f"TOP5형은 카드가 꼭 5장이에요. 지금 {len(cards)}장이에요.")
    cover = spec.get("cover") or {}
    if not cover.get("title"):
        must.append("첫 장(cover)에 title 을 적어 주세요.")
    elif max(units(line) for line in cover["title"].split("\n")) > 11:
        should.append("첫 장: title 이 길어 글자가 작아져요. 한 줄에 10자 안쪽으로 줄여 주세요.")
    nos = [c.get("no") for c in cards]
    if kind == "자료":
        if nos != [5, 4, 3, 2, 1][:len(cards)] or set(nos) != set(range(1, len(cards) + 1)):
            must.append("자료 순위 TOP5는 5위부터 1위까지 차례로 놓고, 장마다 no(순위 숫자)를 적어 주세요.")
        if not spec.get("rank_src") or not DATED.search(str(spec["rank_src"])):
            must.append("rank_type 이 자료인데 rank_src(순위를 낸 자료 이름 · 날짜)가 없어요. 실제 순위 자료가 없으면 rank_type 을 추천으로 바꿔 주세요.")
        first = next((c for c in cards if c.get("no") == 1), None)
        if first and cover.get("photo") and photo_key(first.get("photo") or {"url": ""}) == photo_key(cover["photo"]):
            must.append("첫 장 사진이 1위 사진과 같아요. 답이 미리 보이니 다른 순위 사진을 써 주세요.")
    else:
        if nos != list(range(1, len(cards) + 1)):
            must.append("추천 TOP5는 순위가 아니라 추천 다섯 가지예요. no 를 1부터 5까지 차례로 적어 주세요(거꾸로 세지 않아요).")
        if not spec.get("rank_note"):
            should.append("rank_note 에 무엇을 기준으로 고른 추천인지 한 줄 적어 주세요(예: 요일과 날씨에 맞춘 먹고갈지도 추천이에요).")
        for where, text in shown_texts(spec) + [("게시글", spec.get("caption") or ""), ("제목", spec.get("title") or ""),
                                                ("유튜브 제목", spec.get("yt_title") or "")]:
            hit = RANK_WORDS.search(str(text).replace("[[", "").replace("]]", ""))
            if hit:
                must.append(f"{where}: '{hit.group()}' — 추천형인데 순위 자료가 있는 것처럼 보여요. '추천', '골라 봤어요', '마지막 추천'처럼 써 주세요.")
    for n, c in enumerate(cards, 1):
        for key, label in (("name", "음식 이름"), ("line", "핵심 한 줄"), ("photo", "실제 사진")):
            if not c.get(key):
                must.append(f"카드 {n}: {label}({key})이 없어요.")
        if c.get("name") and units(str(c["name"])) > 9:
            should.append(f"카드 {n}: 음식 이름은 8자 안쪽이 크게 보여요.")
        if c.get("line") and units(str(c["line"])) > 19:
            must.append(f"카드 {n}: 핵심 한 줄이 길어요. 18자 안쪽으로 줄여 주세요.")
        if c.get("fact") and units(str(c["fact"])) > 20:
            should.append(f"카드 {n}: 핵심 숫자 줄이 길어요. 20자 안쪽으로 줄여 주세요.")


def why_lines(card):
    why = card.get("why") or []
    return [why] if isinstance(why, str) else list(why)


def card_problems(spec):
    """카드 뉴스 설계도에서 고칠 곳을 찾아요. (꼭 고칠 것, 고치면 좋은 것)"""
    must, should = news_problems(spec), []  # 소식 단위(news)가 있으면 장과 게시글이 맞는지 (2026-10-28)
    cards = spec.get("cards") or []
    if is_top5(spec):
        top5_problems(spec, must, should)
        return must, should
    story = is_story(spec)
    lo, hi = (STORY_MIN, STORY_MAX) if story else (CARD_MIN, CARD_MAX)
    if not lo <= len(cards) <= hi:
        must.append(f"카드가 {len(cards)}장이에요. {lo}~{hi}장으로 맞춰 주세요.")
    cover = spec.get("cover") or {}
    if story:  # 이야기 카드: 첫 장은 물음 하나. items(목록)는 없어도 돼요
        if not cover.get("title"):
            must.append("첫 장(cover)에 title(물음 하나)을 적어 주세요.")
        else:
            if len(cover["title"].split("\n")) > 3:
                must.append("첫 장: title 은 세 줄까지예요.")
            if max(units(line) for line in cover["title"].split("\n")) > 11:
                should.append("첫 장: title 이 길어 글자가 작아져요. 한 줄에 10자 안쪽으로 줄여 주세요.")
        if len(cover.get("items") or []) > 3:
            should.append("첫 장: 이야기 카드의 items 는 3줄까지만 보여요. 물음 하나에 집중해 주세요.")
        if any(units(line) > 17 for line in cover.get("items") or []):
            should.append("첫 장: items 한 줄이 길어 글자가 작아져요. 16자 안쪽으로 줄여 주세요.")
        if units(str(cover.get("label") or "")) > 13:
            should.append("첫 장: label 이 길어요. 12자 안쪽으로 줄여 주세요.")
        if units(str(spec.get("pill") or "")) > 5:
            should.append("pill(계정 옆 이름표)이 길어요. 4자 안쪽으로 줄여 주세요.")
        if cards and cards[-1].get("type") != "summary":
            should.append("이야기 카드는 마지막 장을 정리(type summary)로 끝내 주세요.")
        # 실사 사진이 든 장이 사진 없는 장보다 적지 않은지는 사진을 받은 뒤 card_photo_problems 가 봐요 (2026-10-19 5단계)
    elif not cover.get("title") or not cover.get("items"):
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
        kind = c.get("type")
        if kind is not None and kind not in CARD_TYPES:
            must.append(f"카드 {n}: 모르는 꼴(type '{kind}')이에요. 빼거나 {', '.join(CARD_TYPES)} 가운데 하나로 적어 주세요.")
            continue
        need = (("tag", "분류"), ("headline", "한 줄 소식")) + (() if kind == "summary" else (("src", "자료 이름"),) if kind == "hero"
                                                                else (("why", "까닭"), ("src", "자료 이름")))
        for key, name in need:
            if not c.get(key):
                must.append(f"카드 {n}: {name}({key})이 없어요.")
        if kind:
            typed_problems(c, n, must, should)
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
        if not kind and not c.get("photo") and not c.get("flow"):  # 2026-10-28 사용자: 사진 없이 글자만 큰 장 금지(말차 오레오 사례)
            tried = [k for k in PHOTO_STEPS if (c.get("photo_search") or {}).get(k)]
            if story:
                should.append(f"카드 {n}: 사진 없는 숫자 장이에요. 그 음식 사진이 있으면 photo 에 적어 주세요.")
            elif len(tried) == len(PHOTO_STEPS):  # 복구 절차를 다 거쳤으면 이 장(소식)은 제작 때 보류돼요
                should.append(f"카드 {n}: 사진 없는 소식 장이라 이 소식은 보류돼요(복구 시도 기록 있음). 나머지 소식은 그대로 나가요.")
            else:
                must.append(f"카드 {n}: 사진 없는 소식 장이에요. 글자만 큰 장으로 대신하지 말고 복구 절차를 차례로 해 주세요: "
                            "① 그 제품·음식의 실제 사진 더 찾기 ② 제조사 보도자료·미디어센터 ③ 쓸 수 있는 다른 실제 사진·시각 자료(막대·비교 장) "
                            "④ 레이아웃 바꾸기. 다 해도 없으면 photo_search 에 exact·press·other·layout 마다 해 본 것을 적어요(그 소식만 보류돼요).")
        must.extend(density_problems(c, n))
        if story and kind != "summary":  # 장마다 앞 장에서 이어지는 물음 (2026-10-19 5단계)
            q = str(c.get("q") or "")
            if not q:
                should.append(f"카드 {n}: q(이 장이 답하는 물음)가 없어요. 앞 장 끝에 '다음 · 물음'으로 보여 줘서 넘기게 해요.")
            elif units(q) > Q_MAX:
                should.append(f"카드 {n}: q 가 길어요. {Q_MAX - 1}자 안쪽으로 줄여 주세요.")
    if "출처" not in (spec.get("caption") or ""):
        must.append("게시글(caption) 끝에 '출처: 기관·매체 이름(날짜)' 줄을 적어 주세요. 카드에는 출처 장이 없어요.")
    return must, should


# 한 장에 들어가는 글의 양 (2026-10-19 5단계: "카드마다 정보가 너무 많거나 글자가 작아지지 않게")
#   글이 길면 fit_size 가 글자를 줄이는데, 휴대폰에서 읽히는 선 아래로 줄면 꼭 고치게 해요.
HL_SIZE, WHY_SIZE, FACT_SIZE = 98, 48, 56  # 기본 글자 크기 (cards.css 와 news_card 가 같은 값을 써요)
HL_MIN, WHY_MIN, FACT_MIN = 82, 40, 46     # 이보다 작아지면 꼭 고쳐요
CARD_TEXT_MAX = 68                           # 한 장의 글(한 줄 소식 + 핵심 숫자 + 까닭) 칸 수 합
Q_MAX = 15                                   # 이야기 카드의 물음(q) 한 줄


def density_problems(c, n):
    """한 장의 글이 너무 많거나 글자가 너무 작아지는지. (꼭 고칠 것 목록)"""
    out = []
    head = str(c.get("headline") or "")
    if head and fit_size(head, HL_SIZE, 950) < HL_MIN:
        out.append(f"카드 {n}: 한 줄 소식이 길어 글자가 {fit_size(head, HL_SIZE, 950)}px 로 작아져요. 한 줄 12자 안쪽으로 줄여 주세요.")
    why = why_lines(c)
    if why and min(fit_size(line, WHY_SIZE, 915) for line in why) < WHY_MIN:
        out.append(f"카드 {n}: 까닭 줄이 길어 글자가 작아져요. 한 줄 20자 안쪽으로 줄이고 나머지는 게시글에 써 주세요.")
    if c.get("fact") and fit_size(str(c["fact"]), FACT_SIZE, 950) < FACT_MIN:
        out.append(f"카드 {n}: 핵심 숫자 줄이 길어 글자가 작아져요. 숫자 하나만 남겨 주세요.")
    if c.get("type") != "summary":
        total = sum(units(line) for line in head.split("\n")) + units(str(c.get("fact") or "")) + sum(units(line) for line in why)
        if total > CARD_TEXT_MAX:
            out.append(f"카드 {n}: 한 장에 글이 많아요(약 {total:.1f}칸, {CARD_TEXT_MAX}칸까지). 까닭을 한 줄로 줄이거나 다음 장으로 나눠 주세요.")
    return out


def shown_texts(spec):
    """카드와 썸네일에 보이는 글 전부: [(어디, 글), …]. 숫자 표기를 견줄 때 써요."""
    out = []
    t = spec.get("thumb") or {}
    out += [("썸네일", t.get("head")), ("썸네일", t.get("sub"))]
    cv = spec.get("cover") or {}
    out += [("첫 장", cv.get("title"))] + [("첫 장", i) for i in cv.get("items") or []]
    for n, c in enumerate(spec.get("cards") or [], 1):
        w = f"카드 {n}"
        out += [(w, c.get(k)) for k in ("q", "headline", "fact", "big", "name", "line", "ask", "note")]
        out += [(w, x) for x in why_lines(c) + list(c.get("points") or [])]
        for s in c.get("sides") or []:
            out += [(w, s.get(k)) for k in ("label", "value", "note")]
    return [(w, str(x)) for w, x in out if x]


PCT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
MAN_WON = re.compile(r"\d+만\s?\d[\d,]*\s?원")       # 2만269원, 1만 3800원
SIGNED = re.compile(r"(?<![\w\d])[+\-−]\d+(?:\.\d+)?\s*%")  # -10.3%, +32.5%


def number_problems(spec):
    """제목·썸네일·본문의 숫자 표기가 같은지 (2026-10-19 5단계: "제목과 본문의 숫자 표기를 통일").
    - 같은 숫자를 32% 와 32.5% 처럼 다르게 쓰면 꼭 고쳐요. 자료에 적힌 값(소수 첫째 자리까지) 하나로 씁니다.
    - 값은 20,269원처럼 쉼표로, 오르내림은 32.5% ↑ / 10.3% ↓ 처럼 숫자 뒤 화살표로 써요(문장에서는 올랐어요·내렸어요).
    (꼭 고칠 것, 고치면 좋은 것)"""
    must, should = [], []
    texts = shown_texts(spec) + [(k, str(spec.get(f) or "")) for k, f in
                                 (("게시글", "caption"), ("제목", "title"), ("유튜브 제목", "yt_title"), ("유튜브 설명 첫 줄", "yt_lead"))]
    seen = {}
    for where, text in texts:
        for v in PCT.findall(text.replace("[[", "").replace("]]", "")):
            seen.setdefault(v, set()).add(where)
    vals = sorted(seen, key=float)
    for a in vals:
        for b in vals:
            if "." not in a and "." in b and int(a) in (int(float(b)), round(float(b))):  # 32 와 32.5, 47 과 46.8
                must.append(f"같은 숫자를 {a}%({', '.join(sorted(seen[a]))})와 {b}%({', '.join(sorted(seen[b]))})로 다르게 썼어요. "
                            f"자료에 적힌 {b}% 하나로 맞춰 주세요.")
    for where, text in texts:
        plain = text.replace("[[", "").replace("]]", "")
        if MAN_WON.search(plain):
            should.append(f"{where}: '{MAN_WON.search(plain).group()}' → 카드에는 20,269원처럼 쉼표로 써 주세요.")
        if SIGNED.search(plain):
            should.append(f"{where}: '{SIGNED.search(plain).group()}' → 부호 대신 10.3% ↓, 32.5% ↑ 처럼 숫자 뒤 화살표로 써 주세요.")
    return list(dict.fromkeys(must)), list(dict.fromkeys(should))


WON = re.compile(r"\d[\d,]*\s?원")
CHANGE = re.compile(r"\d+(?:\.\d+)?\s*%\s*[↑↓]|\d+(?:\.\d+)?\s*%\s*(?:올|내|뛰|떨어|싸|비싸|늘|줄|하락|상승|증가|감소)")
BASIS = re.compile(r"작년|지난해|전년|직전|지난주|전주|평년|지난달|전월|한 달|이달 초|일주일|같은 기간|같은 날|대비|보다|\d+월 \d+주|\d+월(?:에는|엔|에|보다)")


def basis_problems(spec):
    """값·오르내림 숫자에 기준 기간과 출처가 있는지 (2026-10-19 5단계: "가격·증감률의 기준 기간과 출처 확인").
    - 값(원)이나 % 가 있는 장은 src 에 자료 이름과 날짜(기준일)가 있어야 해요.
    - 오르내림(32.5% ↑, 10% 내렸어요)이 있는 장은 무엇과 견준 것인지(작년 같은 날, 직전 주…)가 그 장 글이나 basis 칸에 있어야 해요.
    정리 장(summary)은 앞 장의 기준을 따르니 보지 않아요. (꼭 고칠 것 목록)"""
    out = []
    for n, c in enumerate(spec.get("cards") or [], 1):
        if c.get("type") == "summary":
            continue
        texts = [str(c.get(k) or "") for k in ("headline", "fact", "big", "line", "basis")] + why_lines(c)
        texts += [str(s.get(k) or "") for s in c.get("sides") or [] for k in ("label", "value", "note")]
        texts += [str(b.get("label") or "") for b in (c.get("chart") or {}).get("bars") or []] + [str((c.get("chart") or {}).get("note") or "")]
        plain = " ".join(texts).replace("[[", "").replace("]]", "")
        has_num = bool(PCT.search(plain) or WON.search(plain) or c.get("type") == "chart")
        if has_num:
            src = str(c.get("src") or (spec.get("rank_src") if is_top5(spec) else "") or "")
            if not src:
                out.append(f"카드 {n}: 값·% 가 있는데 src(자료 이름 · 기준 날짜)가 없어요.")
            elif not DATED.search(src):
                out.append(f"카드 {n}: src '{src}' 에 기준 날짜가 없어요. 'aT 농산물유통정보 · 10월 16일'처럼 언제 값인지 적어 주세요.")
        if CHANGE.search(plain) and not BASIS.search(plain):
            out.append(f"카드 {n}: 오르내림 숫자가 무엇과 견준 것인지 없어요. 글에 '작년보다'를 넣거나 basis 칸에 '작년 같은 날 대비'처럼 적어 주세요.")
    return out


MIN_PHOTO = 600  # 원래 사진(잘라 쓴 조각)의 짧은 변. 이보다 작으면 키워도 흐려요


def page_photos(spec):
    """장마다 쓰는 실제 사진 목록: [(장 이름, 사진), …]. 첫 장, 사진 카드, 비교 칸, 흐름(flow)의 음식 사진까지요."""
    out = []
    if (spec.get("cover") or {}).get("photo"):
        out.append(("첫 장", spec["cover"]["photo"]))
    for n, c in enumerate(spec.get("cards") or [], 1):
        if c.get("photo"):
            out.append((f"카드 {n}", c["photo"]))
        if c.get("photo2"):
            out.append((f"카드 {n}", c["photo2"]))
        for s in c.get("sides") or []:
            if s.get("photo"):
                out.append((f"카드 {n}", s["photo"]))
        if c.get("flow"):
            out.append((f"카드 {n}", c["flow"]["photo"]))
    return out


def card_photo_problems(spec):
    """사진이 받아진 뒤에 보는 것: 흐린 사진, 한 장 돌려쓰기, 실사 사진이 모자란지. (꼭 고칠 것, 고치면 좋은 것)
    2026-10-19 5단계: "실사 사진을 먼저 쓰고, 사진이 부족하면 억지로 만들지 않는다"."""
    must, should = [], []
    if spec.get("format") != "cards":
        return must, should
    photos = page_photos(spec)
    for where, p in photos:
        fetch_photo(p)
        size = ORIG.get(photo_key(p))
        if size and min(size) < MIN_PHOTO:
            must.append(f"{where}: 사진이 작아요({size[0]}x{size[1]}). 키우면 흐려 보여요. 더 큰 사진으로 바꾸거나 사진 없이(big) 만들어 주세요.")
    seen, urls = {}, {}
    for where, p in photos:
        p = {"url": p} if isinstance(p, str) else p
        seen.setdefault(photo_key(p), []).append(where)
        urls.setdefault(p["url"], set()).add(photo_key(p))
    for places in seen.values():
        if len(set(places)) > 1 and not (len(places) == 2 and places[0] == "첫 장"):
            should.append(f"같은 사진이 {', '.join(places)}에 나와요. 장마다 다른 사진을 써 주세요.")
    for url, keys in urls.items():
        if len(keys) >= 3:
            must.append(f"사진 한 장을 {len(keys)}번 잘라 쓰고 있어요. 서로 다른 실제 사진을 찾고, 없으면 그 장을 빼 주세요.")
    if not (spec.get("cover") or {}).get("photo"):
        must.append("첫 장에 실제 사진이 없어요. 첫 장 제목에 쓴 음식의 사진을 넣어 주세요.")
    distinct = {p["url"] if isinstance(p, dict) else p for _, p in photos}
    pages = [spec.get("cover") or {}] + [c for c in spec.get("cards") or [] if c.get("type") != "summary"]
    shown = sum(bool(p.get("photo") or p.get("flow") or any(s.get("photo") for s in p.get("sides") or [])) for p in pages)
    if len(distinct) < 2 or shown < len(pages) - shown:
        # 2026-10-23 5단계: 사진이 없다는 이유로 소식을 버리지 않아요(이용 조건이 확인된 사진만 쓰니 사진 없는 장이 늘 수 있어요). 알림으로만 둬요
        should.append(f"실제 사진이 {len(distinct)}장, 사진 든 장이 {shown}/{len(pages)}장이에요. 다른 음식 사진으로 채우지 말고, "
                      "사진 없는 장은 확인된 숫자·날짜로 또렷하게 만들어 주세요. 그 음식이 찍힌 쓸 수 있는 사진이 있으면 넣어 주세요.")
    return must, should


def typed_problems(c, n, must, should):
    """이야기 카드의 비교(compare)·막대(chart)·정리(summary) 장을 살펴요."""
    if c["type"] == "hero":
        if not c.get("photo"):
            must.append(f"카드 {n}: 큰 제목 장(hero)에 사진(photo)이 없어요.")
        if not c.get("say") and not c.get("lines"):
            should.append(f"카드 {n}: 큰 제목 장(hero)에 가운데 한마디(say)가 없어요. 무엇이 몇 월 며칠에 어떻게 되는지 두 줄로 적어 주세요.")
        if len(hero_lines(c.get("headline", ""))) > 2 or any(len(str(x).split("\n")) > 2 for x in [c.get("say", "")] + [l.get("say", "") for l in c.get("lines") or []]):
            should.append(f"카드 {n}: 큰 제목 장의 headline·say 는 두 줄까지예요. 길면 사진이 작아져 그린 뒤 검수에 걸려요.")
        if len(c.get("rows") or []) > HERO_ROWS_MAX:
            should.append(f"카드 {n}: 정보 줄(rows)은 {HERO_ROWS_MAX}줄까지만 보여요. 핵심만 남기고 나머지는 다음 장으로 옮겨 주세요.")
        if c.get("more") and (len(hero_more(c)) != 2 or c.get("photo2")):
            should.append(f"카드 {n}: B안(more)은 정확·같은 종류 사진이 꼭 2장일 때만 쓰여요(분위기 사진은 빠져요). 아니면 A안(사진 한 장)으로 나가요.")
        for line in c.get("lines") or []:
            for row in str(line.get("say") or "").split("\n"):
                if units(row) > HERO_SAY_MAX:
                    should.append(f"카드 {n}: 내레이션 자막 한 줄이 길어요({row}). {HERO_SAY_MAX}칸 안쪽에서 줄을 바꿔 주세요.")
        return
    if c["type"] == "compare":
        sides = c.get("sides") or []
        if len(sides) != 2:
            must.append(f"카드 {n}: 비교(compare)는 sides 가 꼭 2개예요.")
        for s in sides:
            if not s.get("label") or not s.get("value"):
                must.append(f"카드 {n}: 비교 칸마다 label(무엇)과 value(값)를 적어 주세요.")
            elif units(str(s["label"])) > 9 or units(str(s["value"])) > 9:
                should.append(f"카드 {n}: 비교 칸의 label·value 는 8자 안쪽이 좋아요. 글자가 작아져요.")
    elif c["type"] == "chart":
        bars = (c.get("chart") or {}).get("bars") or []
        if not 2 <= len(bars) <= 6:
            must.append(f"카드 {n}: 막대(chart)는 bars 가 2~6개예요.")
        for b in bars:
            if not b.get("label") or isinstance(b.get("value"), bool) or not isinstance(b.get("value"), (int, float)) or b["value"] < 0:
                must.append(f"카드 {n}: 막대마다 label 과 0 이상의 숫자 value 를 적어 주세요. (값은 확인한 자료의 숫자만)")
                break
        if any(units(str(b.get("label", ""))) > 7 for b in bars):
            should.append(f"카드 {n}: 막대 이름(label)은 6자 안쪽이 좋아요.")
    elif c["type"] == "summary":
        points = c.get("points") or []
        if not 1 <= len(points) <= 3:
            must.append(f"카드 {n}: 정리(summary)는 points 가 1~3줄이에요.")
        if any(units(str(p)) > 22 for p in points):
            should.append(f"카드 {n}: 정리 한 줄이 길어 글자가 작아져요. 22자 안쪽으로 줄여 주세요.")


WEEKLY_CTA = "늙크크 안 되게, 매주 금요일 유행 업데이트"  # 트렌드 카드 첫 장 아래 한마디 (2026-10-16 사용자가 정한 느낌)


def news_cover(cover, total, when, name, pill, label, weekly=False, story=False, first_q=None, foot_note=None):
    """첫 장. 오늘 소식들을 궁금하게 던져요. 답은 다음 장부터 나와요.
    weekly(트렌드 카드)면 이름표에 "10월 3주차 유행 업데이트"를 크게 쓰고, 아래에 매주 온다는 한마디를 붙여요.
    story(이야기 카드)면 이름표는 cover.label(없으면 "오늘의 먹거리 이슈")이고, items 목록은 있을 때만 보여요."""
    if cover.get("photo"):
        src, pos = fetch_photo(cover["photo"])
        top = f'<div class="ph"><img src="{src}" style="object-position:{pos}"></div>{ref_label(cover["photo"]).replace("ref", "ref ph-ref", 1)}'
    else:
        top = f'<div class="ph">{NEWS_MAP}</div>'
    items = (cover.get("items") or [])[:3] if story else cover["items"]
    size = min((fit_size(line, 58, 880) for line in items), default=58)
    rows = "".join(f'<li style="font-size:{size}px">{rich(line)}</li>' for line in items)
    if story:
        tag = esc(cover.get("label") or STORY_LABEL)
    else:
        tag = esc(when) + " 유행 업데이트" if weekly else f"{label} {total}"
    listing = f'<ul class="list">{rows}</ul>' if rows or not story else ""
    return (
        f'<section class="nc cv" id="c1">{top}'
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><span class="tag{" wk" if weekly else ""}">{tag}</span>'
        f'<div class="hl" style="font-size:{fit_size(cover["title"], 122, 950)}px">{rich(cover["title"])}</div>'
        f'{listing}</div>'
        + (f'<div class="foot"><span class="cta">{WEEKLY_CTA}</span><b class="go">밀어서 →</b></div></section>' if weekly
           else f'<div class="foot"><span>{esc(foot_note or "")}</span><b class="go go-q">{rich(first_q)} 밀어서 →</b></div></section>' if first_q
           else '<div class="foot"><span></span><b class="go">밀어서 확인하기 →</b></div></section>')
    )


SPARK = ('<svg class="spark" viewBox="0 0 120 120"><g stroke="currentColor" stroke-width="9" stroke-linecap="round" fill="none">'
         '<path d="M60 8v30"/><path d="M60 82v30"/><path d="M8 60h30"/><path d="M82 60h30"/></g></svg>')


RUNNER = ('<svg class="runner" viewBox="0 0 120 100"><g fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round">'
          '<path d="M6 40h18M2 56h16M10 72h14" stroke-width="6" opacity=".55"/>'
          '<path d="M74 28 62 56"/><path d="M71 34 54 40 46 52"/><path d="M71 34 84 46 96 42"/>'
          '<path d="M62 56 76 70 72 92"/><path d="M62 56 52 74 36 76"/></g>'
          '<circle cx="80" cy="14" r="10" fill="currentColor"/></svg>')
# 장바구니: 편의점·마트에서 많이 팔린 소식에 써요 (뛰는 사람은 줄 서기·오픈런 소식에)
BASKET = ('<svg class="runner" viewBox="0 0 120 100"><g fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round" stroke-linejoin="round">'
          '<path d="M6 50h14M2 64h12" stroke-width="6" opacity=".55"/>'
          '<path d="M26 22h12l10 46h50l10-34H44"/><path d="M58 44h40" opacity=".6"/></g>'
          '<circle cx="54" cy="84" r="8" fill="currentColor"/><circle cx="92" cy="84" r="8" fill="currentColor"/></svg>')


def flow_html(f):
    """카드 위쪽에 [파는 곳 로고] → [뛰는 사람] → [그 음식 사진] 을 한 줄로 놓아요.
    f = {"logo": 사진, "logo_label": "고디바 롯데월드몰", "run_label": "새벽 4~5시", "photo": 사진, "photo_label": "초콜릿 모찌"}
    "mid": "basket" 이면 가운데가 장바구니(많이 팔린 소식), 없으면 뛰는 사람(줄 서기 소식). "badge" 는 음식 사진 위 숫자 딱지."""
    logo, _ = fetch_photo(f["logo"])
    food, pos = fetch_photo(f["photo"])
    item = lambda cls, inner, label: f'<div class="fl-it {cls}">{inner}<span>{esc(label)}</span></div>' if label else f'<div class="fl-it {cls}">{inner}</div>'
    return ('<div class="flow">'
            + item("logo", f'<div class="tile{" logo-fit" if f.get("logo_fit") else ""}"><img src="{logo}"></div>', f.get("logo_label"))
            + item("run", BASKET if f.get("mid") == "basket" else RUNNER, f.get("run_label"))
            + item("food", f'<div class="tile big"><img src="{food}" style="object-position:{pos}">'
                   + (f'<b class="badge">{rich(f["badge"])}</b>' if f.get("badge") else "") + '</div>', f.get("photo_label"))
            + "</div>")


def number(v):
    """막대 옆에 적는 값: 12321 -> 12,321 / 12.50 -> 12.5"""
    return f"{v:,}" if isinstance(v, int) else f"{v:,.1f}".rstrip("0").rstrip(".")


def compare_html(c):
    """두 가지를 나란히: [무엇·사진·값·한마디] VS [무엇·사진·값·한마디]. "arrow": true 면 가운데가 → (전후 비교)."""
    sides = c["sides"]
    hi = c.get("hi", 1)  # 강조할 칸 (기본은 오른쪽)
    size = min(fit_size(str(s["value"]), 104, 390) for s in sides)

    def side(s, i):
        pic = ""
        if s.get("photo"):
            src, pos = fetch_photo(s["photo"])
            pic = f'<img src="{src}" style="object-position:{pos}">{ref_label(s["photo"]).replace("ref", "ref cm-ref", 1)}'
        note = f'<i class="cm-n">{rich(s["note"])}</i>' if s.get("note") else ""
        return (f'<div class="cm-it{" hi" if i == hi else ""}"><span class="cm-lb">{rich(s["label"])}</span>{pic}'
                f'<b class="cm-v" style="font-size:{size}px">{rich(s["value"])}</b>{note}</div>')
    mid = "→" if c.get("arrow") else "VS"
    return f'<div class="cmp">{side(sides[0], 0)}<div class="cm-mid">{mid}</div>{side(sides[1], 1)}</div>'


def chart_html(c):
    """가로 막대 2~6개. 값은 확인한 자료의 숫자 그대로. "hi" 로 강조할 막대(기본은 마지막)를 골라요."""
    ch = c["chart"]
    bars = ch["bars"]
    top = max(b["value"] for b in bars) or 1
    hi = ch.get("hi", len(bars) - 1)
    unit = esc(ch.get("unit", ""))
    rows = "".join(
        f'<div class="ch-row{" hi" if i == hi else ""}"><span class="ch-lb">{rich(b["label"])}</span>'
        f'<div class="ch-bar"><i style="width:{max(3, round(b["value"] / top * 100))}%"></i></div>'
        f'<b class="ch-v">{number(b["value"])}{unit}</b></div>'
        for i, b in enumerate(bars))
    note = f'<div class="ch-note">{rich(ch["note"])}</div>' if ch.get("note") else ""
    return f'<div class="chart">{note}{rows}</div>'


def summary_card(c, n, total, when, name, pill, story=False):
    """마지막 정리 장: 한 줄 결론 + 알아 둘 것 1~3줄 + (있으면) 댓글 물음.
    "photo" 가 있으면 지도 대신 그 사진을 위쪽에 흐리게 깔아요(이야기의 첫 음식으로 돌아와 마무리)."""
    points = c.get("points") or []
    size = min((fit_size(str(p), 52, 900) for p in points), default=52)
    rows = "".join(f'<li style="font-size:{size}px">{rich(p)}</li>' for p in points)
    ask = f'<div class="ask">{rich(c["ask"])}</div>' if c.get("ask") else ""
    foot = f'자료 {esc(c["src"])}' if c.get("src") else ""
    if c.get("photo"):
        src, pos = fetch_photo(c["photo"])
        back = f'<div class="ph dim"><img src="{src}" style="object-position:{pos}"></div>'
    else:
        back = f'<div class="ph">{NEWS_MAP}</div>'
    if story:
        dots = "".join(f'<i class="{"on" if i == n else ""}"></i>' for i in range(1, total + 1))
        return (
            f'<section class="nc sm st" id="c{n + 1}">{back}'
            f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
            f'<div class="txt"><span class="tag">{esc(c["tag"])}</span>'
            f'<div class="hl" style="font-size:{fit_size(c["headline"], 98, 950)}px">{rich(c["headline"])}</div>'
            f'<ul class="list">{rows}</ul>{ask}</div>'
            f'<div class="next"><span></span><span class="dots">{dots}</span></div>'
            f'<div class="foot"><span>{foot}</span><b></b></div></section>'
        )
    return (
        f'<section class="nc sm" id="c{n + 1}"><div class="ph">{NEWS_MAP}</div>'
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><span class="tag">{esc(c["tag"])}</span>'
        f'<div class="hl" style="font-size:{fit_size(c["headline"], 98, 950)}px">{rich(c["headline"])}</div>'
        f'<ul class="list">{rows}</ul>{ask}</div>'
        f'<div class="foot"><span>{foot}</span><b>{n} / {total}</b></div></section>'
    )


def story_bits(c, nxt, n, total):
    """이야기 카드에서 장을 잇는 것 (2026-10-19 5단계): 이 장이 답하는 물음(q), 진행 점, 다음 장 예고.
    (물음 줄 HTML, 다음 장 예고 HTML)"""
    q = f'<span class="q">{rich(c["q"])}</span>' if c.get("q") else ""
    dots = "".join(f'<i class="{"on" if i == n else ""}"></i>' for i in range(1, total + 1))
    teaser = f'<span class="nx-q">다음 · {rich(nxt["q"])}</span>' if nxt and nxt.get("q") else (
        '<span class="nx-q">다음 · 정리</span>' if nxt else "")
    return q, f'<div class="next">{teaser}<span class="dots">{dots}</span></div>'


HERO_SAY_MAX = 18  # 큰 제목 장 가운데 자막 한 줄 칸 수
HERO_ROOM = 1000   # 큰 제목 한 줄이 차지하는 폭 (화면 양 끝에서 40px 안쪽)
# 사진 중심 (2026-10-28 사용자: 제목만 크고 사진이 작은 장 금지). 제목은 눈길을 끌 만큼만, 사진은 양옆 끝까지 크게, 설명은 아래 짧게.
HERO_HEAD_CAP = 100      # 큰 제목 글자 크기 상한 (예전 170~230)
HERO_ONE_LINE = 92       # 두 줄 제목을 한 줄로 이어도 이 크기 이상이면 한 줄로 써요
HERO_TOP = 122           # 제목이 시작하는 곳 (로고·날짜 줄 아래)
HERO_ROW, HERO_ROWS_MAX = 64, 2  # 아래 정보 줄 높이, 줄 수 상한 (더 많으면 다음 장으로)
HERO_SAY_LINE = 66       # 한마디 한 줄 높이 (글자 50px)
HERO_FOOT = 1296         # 맨 아래 자료 줄 위쪽 끝
HERO_MORE_SPLIT = 0.62   # 사진이 석 장이면 큰 사진이 사진 칸 높이의 이만큼, 나머지는 같은 크기 두 칸


def hero_head(line, cap=HERO_HEAD_CAP):
    """큰 제목 한 줄. 화면 양 끝에 맞게 글자 크기를 정하고(상한 cap), 검은 테두리를 뒤에 한 벌 깔아요."""
    import thumb
    size = min(cap, int(160 * HERO_ROOM / max(1.0, thumb.width(line, 160))))
    plain = line.replace("[[", "").replace("]]", "")
    return size, f'<span data-t="{esc(plain)}">{rich(line)}</span>'


def hero_lines(headline):
    """제목 줄들. 한 줄로 이어도 충분히 크면 줄바꿈을 없애요 (불필요한 줄바꿈 줄이기)."""
    lines = [x for x in str(headline).split("\n") if x.strip()]
    if len(lines) > 1:
        one = " ".join(lines)
        if hero_head(one)[0] >= HERO_ONE_LINE:
            return [one]
    return lines


def ref_label(p):
    """그 상품·그 대상이 아닌 사진(match 가 같은 종류·분위기)에 붙이는 '참고 사진' 딱지 (2026-10-28 사용자: 대체 사진은 참고 사진임을 분명히).
    ref 를 적으면 그 말로 써요. 예: 참고 사진 · 실제 제품 아님"""
    if not isinstance(p, dict) or p.get("match", "정확") == "정확":
        return ""
    return f'<span class="ref">{esc(p.get("ref") or "참고 사진")}</span>'


def hero_more(c):
    """큰 사진 아래 같은 크기 두 칸(B안)에 넣을 사진. 내용과 바로 이어지지 않는 분위기 사진은 빼요 (2026-10-28 사용자)."""
    return [p for p in (c.get("more") or []) if p.get("match") in ("정확", "같은 종류")][:2]


def hero_photos(c, box):
    """사진 칸. A안: 한 장을 양옆 끝까지 꽉 채워요(자연스럽게 잘라요, 위치는 pos). 기본이에요.
    두 장(photo2)은 나란히, B안(more 에 정확·같은 종류 사진 2장)은 큰 사진 + 같은 크기 두 칸. more 가 모자라면 A안으로 돌아가요."""
    top, height = box
    def cell(p, style):
        if p.get("fit") == "pack":  # 상품 포장 사진: 자르지 않고 흰 판에 통째로 크게 (흰 바탕이 사진의 일부예요)
            return f'<div class="pk" style="{style}"><img src="{pack_photo(p)}">{ref_label(p)}</div>'
        src, pos = fetch_photo(p)
        return f'<div style="{style}"><img src="{src}" style="object-position:{pos}">{ref_label(p)}</div>'
    more = hero_more(c)
    pics = [c["photo"]] + ([c["photo2"]] if c.get("photo2") else []) + (more if len(more) == 2 and not c.get("photo2") else [])
    gap = 10
    if len(pics) == 1:
        cells = cell(pics[0], f"left:0;top:0;width:1080px;height:{height}px")
    elif len(pics) == 2:
        w = (1080 - gap) // 2
        cells = "".join(cell(p, f"left:{k * (w + gap)}px;top:0;width:{w}px;height:{height}px") for k, p in enumerate(pics))
    else:
        main = round(height * HERO_MORE_SPLIT)
        w, h = (1080 - gap) // 2, height - main - gap
        cells = cell(pics[0], f"left:0;top:0;width:1080px;height:{main}px") + "".join(
            cell(p, f"left:{k * (w + gap)}px;top:{main + gap}px;width:{w}px;height:{h}px") for k, p in enumerate(pics[1:3]))
    return f'<div class="hpics" style="top:{top}px;height:{height}px">{cells}</div>'


HERO_SCALE = 176  # 비교 그림 띠 높이


def scale_html(sc, top):
    """두 가지 크기·두께를 나란히 그린 띠 (2026-10-28 말차 오레오: 기존 오레오보다 약 40% 얇아요).
    {"title": "두께 비교", "note": "[[약 40%]] 얇아요", "src": "회사 발표", "shape": "sandwich" 또는 "bar",
     "items": [{"label": "기존 오레오 샌드", "value": 100}, {"label": "오레오 씬즈", "value": 60, "hl": true}]}
    값은 확인한 자료의 비율만 써요. 비율 그림이라 사진처럼 보이지 않게 단순하게 그려요."""
    items = sc.get("items") or []
    top_v = max((float(i["value"]) for i in items), default=1) or 1
    cells = ""
    for i in items:
        h = max(12, round(96 * float(i["value"]) / top_v))
        body = (f'<span class="sw" style="height:{h}px"><i></i><i></i><i></i></span>' if sc.get("shape", "sandwich") == "sandwich"
                else f'<span class="sb" style="height:{h}px"></span>')
        cells += f'<div class="sc-it{" hi" if i.get("hl") else ""}">{body}<b>{rich(i["label"])}</b></div>'
    head = (f'<div class="sc-hd"><em>{rich(sc.get("title", ""))}</em><strong>{rich(sc.get("note", ""))}</strong>'
            f'<small>{esc(sc.get("src", ""))}</small></div>')
    return f'<div class="hscale" style="top:{top}px;height:{HERO_SCALE}px">{head}{cells}</div>'


def hero_card(c, n, total, when, name, pill, say=None):
    """큰 제목 장. 2026-10-28 사용자가 사진 중심으로 다시 정함 (예전: 2026-10-21 빅아치 시안, 화면 양 끝까지 큰 두 줄 제목).
    위: 로고·날짜 + 짧은 제목(상한 HERO_HEAD_CAP) + 밑줄
    가운데: 양옆 끝까지 큰 사진 (photo2 가 있으면 두 장 나란히, more 가 있으면 큰 사진 + 같은 크기 두 칸). ribbon 은 사진 왼쪽 위 딱지.
    아래: 한마디(say, 내레이션 lines 가 있으면 쇼츠에서 한 줄씩 바뀌어요) → 정보 줄(rows, 2줄까지) → 자료 줄 (또는 날짜 띠 date)."""
    if say is None:
        say = c.get("say") or ((c.get("lines") or [{}])[0]).get("say", "")
    rows = (c.get("rows") or [])[:HERO_ROWS_MAX]
    heads, top = "", HERO_TOP
    lines = hero_lines(c["headline"])
    for line in lines:
        size, body = hero_head(line, HERO_HEAD_CAP if len(lines) <= 2 and not c.get("compact") else 84)  # compact: 검수에 걸려 자동으로 줄인 장  # 세 줄이면 더 작게 (제목 높이 검수에 걸리지 않게)
        heads += f'<div class="ht" style="top:{top}px;font-size:{size}px">{body}</div>'
        top += round(size * 1.08)
    say_n = max(1, max((len(str(x.get("say", "")).split("\n")) for x in c.get("lines") or [{"say": say}]), default=1))
    rows_top = HERO_FOOT - (HERO_ROW * len(rows) + 14 if rows else 0) - (96 if c.get("date") else 0)
    bottom = rows_top - (HERO_SCALE + 10 if c.get("scale") else 0)
    say_top = bottom - HERO_SAY_LINE * say_n - 12
    pic_top = top + 40
    photo = hero_photos(c, (pic_top, say_top - 22 - pic_top))
    rib = f'<div class="hrib" style="top:{pic_top + 26}px">{rich(c["ribbon"])}</div>' if c.get("ribbon") else ""
    date = f'<div class="hdate">{rich(c["date"])}</div>' if c.get("date") else ""
    items = "".join(f'<li><span><b>{esc(r["k"])}</b>{rich(r["v"])}</span></li>' for r in rows)
    extra = f'<ul class="hrows" style="top:{rows_top + 4}px">{items}</ul>' if rows else ""
    if c.get("scale"):
        extra += scale_html(c["scale"], bottom + 4)
    if not c.get("date"):
        extra += f'<div class="foot"><span>자료 {esc(c["src"])}</span><b>{n} / {total}</b></div>'
    if c.get("price"):  # 값표: 사진 오른쪽 위 (2026-10-21 사용자)
        cells = "".join(f'<div><span>{esc(r["k"])}</span><b>{rich(r["v"])}</b></div>' for r in c["price"])
        head = f'<em>{esc(c["price_title"])}</em>' if c.get("price_title") else ""  # 확정 전 값이면 "예상 가격"처럼 적어요
        note = f'<i>{esc(c["price_note"])}</i>' if c.get("price_note") else ""
        extra += f'<div class="hprice" style="top:{pic_top + 20}px">{head}{cells}{note}</div>'
    return (
        f'<section class="nc hero" id="c{n + 1}">{photo}'
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'{heads}<div class="hline" style="top:{top + 4}px"></div>{rib}'
        f'<div class="hsay" style="top:{say_top}px;height:{HERO_SAY_LINE * say_n + 8}px"><div>{rich(say)}</div></div>{date}{extra}</section>'
    )


# 그린 뒤 검수 (2026-10-28 사용자: 제목이 지나치게 크거나 사진이 작거나 여백이 크면 걸러 주세요)
# 카드마다 제목 높이, 사진이 실제로 보이는 넓이, 사진 칸 안 빈 여백(통째로 넣어 남은 곳), 사진·글 없이 비어 있는 가로 띠를 재요.
TEXT_SEL = (".ht", ".hsay > div", ".hrows li", ".hrib", ".hl", ".fact", ".bs", ".why > div", ".bignum", ".tag", ".foot span", ".foot b",
            ".when", ".brand span", ".cm-lb", ".cm-v", ".cm-n", ".ch-lb", ".list li", ".ref", ".note", ".q", ".nx-q", ".ask", ".ln",
            ".hprice span", ".hprice b", ".hprice em", ".hprice i", ".sc-hd em", ".sc-hd strong", ".sc-hd small", ".sc-it b")  # 겹침·잘림을 재는 글자 칸
LAYOUT_PROBE = r"""() => [...document.querySelectorAll('section.nc')].map(sec => {
  const S = sec.getBoundingClientRect(), A = S.width * S.height;
  const cut = (a, b) => ({left: Math.max(a.left, b.left), top: Math.max(a.top, b.top), right: Math.min(a.right, b.right), bottom: Math.min(a.bottom, b.bottom)});
  const area = r => Math.max(0, r.right - r.left) * Math.max(0, r.bottom - r.top);
  let photo = 0, spare = 0;
  for (const im of sec.querySelectorAll('img')) {
    if (im.classList.contains('bg') || !im.naturalWidth) continue;
    let r = cut(im.getBoundingClientRect(), S);
    if (im.parentElement !== sec) r = cut(r, im.parentElement.getBoundingClientRect());
    const box = area(r);
    if (box < 2000) continue;
    if (im.closest('.pk')) photo += box;  // 상품 포장 사진: 흰 판까지 사진이에요
    else if (getComputedStyle(im).objectFit === 'contain') {
      const b = im.getBoundingClientRect(), k = Math.min(b.width / im.naturalWidth, b.height / im.naturalHeight);
      const seen = Math.min(box, im.naturalWidth * k * im.naturalHeight * k);
      photo += seen; spare += box - seen;
    } else photo += box;
  }
  const tight = e => { const r = document.createRange(); r.selectNodeContents(e); return r.getBoundingClientRect(); };
  const texts = [...sec.querySelectorAll(TEXT_SEL)].filter(e => e.innerText.trim() && e.getClientRects().length).map(e => ({e, r: tight(e), t: e.innerText.trim().replace(/\s+/g, ' ')}));
  const bad = [];
  for (const x of texts) {
    if (x.r.left < S.left - 2 || x.r.right > S.right + 2 || x.r.top < S.top - 2 || x.r.bottom > S.bottom + 2) bad.push('화면 밖으로 잘림: ' + x.t.slice(0, 20));
    else if (getComputedStyle(x.e).whiteSpace === 'nowrap' && x.e.scrollWidth > x.e.clientWidth + 3) bad.push('칸을 넘침: ' + x.t.slice(0, 20));
  }
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i], b = texts[j];
    if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
    const o = area(cut(a.r, b.r));
    if (o > 0.12 * Math.min(area(a.r), area(b.r)) && o > 150) bad.push('글자가 겹침: ' + a.t.slice(0, 12) + ' / ' + b.t.slice(0, 12));
  }
  const small = texts.map(x => ({t: x.t, f: parseFloat(getComputedStyle(x.e).fontSize)})).sort((a, b) => a.f - b.f)[0] || {t: '', f: 99};
  const word = texts.filter(x => x.t.replace(/[\s\[\]]/g, '').length <= 4).map(x => ({t: x.t, h: (x.r.bottom - x.r.top) / S.height})).sort((a, b) => b.h - a.h)[0] || {t: '', h: 0};
  const heads = [...sec.querySelectorAll(sec.classList.contains('hero') ? '.ht' : '.hl')].map(e => e.getBoundingClientRect());
  const title = heads.length ? Math.max(...heads.map(r => r.bottom)) - Math.min(...heads.map(r => r.top)) : 0;
  return {id: sec.id, title: title / S.height, photo: photo / A, spare: spare / A, text: bad, word: word.t, word_h: word.h, small: small.t, small_px: small.f};
})""".replace("TEXT_SEL", repr(",".join(TEXT_SEL)))
MIN_TEXT_PX = 26  # 카드 글자 최소 크기 (2026-10-28 사용자: 휴대폰에서 실제로 읽히게)
HERO_LIMITS = {"title": 0.22, "photo": 0.40, "spare": 0.06, "empty": 110}  # 제목 높이·사진 넓이·빈 여백 비율, 빈 가로 띠(px)


def empty_band(jpg):
    """그림에서 아무것도 없는(어두운 한 가지 색) 가장 긴 가로 띠의 높이(px). 맨 위 로고 줄과 맨 아래 자료 줄 자리는 빼요.
    상품 사진의 흰 판처럼 밝은 바탕은 사진의 일부라 세지 않아요."""
    with Image.open(jpg) as im:
        g = im.convert("L").resize((270, im.height // 2))
    rows = [g.crop((0, y, 270, y + 1)) for y in range(g.height)]
    flat = [max(r.getextrema()) - min(r.getextrema()) < 14 and max(r.getextrema()) < 110 for r in rows]
    best = run = 0
    for y, f in enumerate(flat):
        run = run + 1 if f and 60 < y < g.height - 40 else 0
        best = max(best, run)
    return best * 2


def layout_checks(spec, probe):
    """모든 장: 글자 잘림·겹침(꼭 고칠 것)과 단어 하나가 화면을 크게 차지하는 장(사람이 확인). (꼭, 확인 필요)"""
    must, check = [], []
    for m in probe:
        n = int(m["id"][1:]) - 1
        where = "첫 장" if n == 0 else f"카드 {n}"
        must += [f"{where}: {t}" for t in m.get("text") or []]
        if m.get("small_px", 99) < MIN_TEXT_PX:  # 휴대폰(가로 약 390pt)에서 1080 그림은 0.36배로 보여요. 26px 아래는 9pt 아래라 읽기 어려워요
            must.append(f"{where}: 글자가 너무 작아요({m['small_px']:.0f}px, '{m['small'][:16]}'). {MIN_TEXT_PX}px 이상으로, 긴 출처는 게시글로 옮겨 주세요.")
        if m.get("word_h", 0) > 0.12 and m.get("photo", 0) < 0.3:  # 사진 위에 얹은 큰 숫자는 괜찮아요
            check.append(f"{where}: '{m['word']}' 한 단어가 화면 높이의 {m['word_h']:.0%}를 차지해요. 사진·제목과 합칠 수 있는지 봐 주세요.")
    return must, check


def layout_problems(spec, probe, shots):
    """그린 카드를 재서 고쳐야 할 것을 돌려줘요. 사진 넓이·제목 크기는 큰 제목 장(hero)만 걸러요 (다른 꼴은 꼴별 기준을 따로, docs/card-checks.md)."""
    must = layout_checks(spec, probe)[0]
    for n, c in enumerate(spec.get("cards") or [], 1):
        if c.get("type") != "hero":
            continue
        m = next((x for x in probe if x["id"] == f"c{n + 1}"), None)
        if not m:
            continue
        lim = HERO_LIMITS
        if m["title"] > lim["title"]:
            must.append(f"카드 {n}: 제목이 화면 높이의 {m['title']:.0%}를 차지해요({lim['title']:.0%} 이하로). 제목을 줄여 주세요.")
        if m["photo"] < lim["photo"]:
            must.append(f"카드 {n}: 사진이 화면의 {m['photo']:.0%}만 보여요({lim['photo']:.0%} 이상). 사진을 크게, 글을 줄여 주세요.")
        if m["spare"] > lim["spare"]:
            must.append(f"카드 {n}: 사진 칸에 빈 여백이 {m['spare']:.0%}예요. 사진을 칸에 꽉 채워 주세요.")
        band = empty_band(shots[n]) if n < len(shots) else 0
        if band > lim["empty"]:
            must.append(f"카드 {n}: 비어 있는 가로 띠가 {band}px 있어요({lim['empty']}px 이하로).")
    return must


# 카드 단위 보류 (2026-10-28 사용자: 사진 한 장 문제로 하루 전체가 멈추지 않게, 문제 있는 소식만 빼고 나머지는 그대로)
# 형식·사진 누락 → 보류, 사진 이용 조건 확인 전 → '확인 필요', 사실·사진 일치 차단 → 차단. 빼는 단위는 '소식'이에요:
# 한 소식이 여러 장이면 그 소식의 장을 모두 함께 빼요(일부만 남아 내용이 왜곡되지 않게).
# 첫 소식(표지·썸네일 주제)이 걸리거나 남은 장이 모자라거나 소식을 깔끔히 떼어 낼 수 없으면 지우지 않고 전체를 보류해요.
CARD_AT = re.compile(r"^카드 (\d+):")
CARD_IN = re.compile(r"\bcards\[(\d+)\]")
NEWS_KEYS = ("title", "summary", "line", "list", "caption", "outlets", "tags", "yt_tags", "yt_hashtags", "sources", "credits")


def held_card_no(text):
    """검수 문장이 가리키는 카드 번호(1부터). 카드 하나를 가리키지 않으면 None."""
    m = CARD_AT.match(text) or CARD_IN.search(text)
    return int(m.group(1)) if m else None


def _wordset(text):
    return {w for w in re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text).replace("[[", "").replace("]]", ""))}


def news_units(spec):
    """소식 단위 목록(설계도의 "news"). 소식마다 제목·요약·게시글 문단·썸네일 한 줄·태그·출처를 따로 가져요 (2026-10-28 사용자)."""
    return [u for u in spec.get("news") or [] if isinstance(u, dict)]


def _uniq(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def compose_news(spec):
    """소식 단위로 제목·요약·썸네일 목록·게시글·태그·출처를 다시 짜요. news 칸이 없으면 그대로 돌려줘요.
    게시글 = caption_head \\n {줄들 · 이어 붙임}{caption_line} \\n\\n 1. 문단 \\n\\n 2. 문단 … \\n\\n caption_ask \\n\\n 출처: …"""
    units = news_units(spec)
    if not units:
        return spec
    spec = json.loads(json.dumps(spec, ensure_ascii=False))
    n = len(units)
    lead = units[0].get("lead") or {}  # 맨 앞 소식이 표지·썸네일 주제예요. 첫 소식이 빠지면 다음 소식의 lead 로 바뀌어요
    if lead.get("thumb"):
        spec["thumb"] = dict(spec.get("thumb") or {}, **lead["thumb"])
    if lead.get("cover"):
        spec["cover"] = dict(spec.get("cover") or {}, **lead["cover"])
    for key in ("caption_head", "yt_title", "yt_keyword", "yt_lead"):
        if lead.get(key):
            spec[key] = lead[key]
    if all(u.get("title") for u in units):
        spec["title"] = ", ".join(u["title"] for u in units)
    if all(u.get("summary") for u in units):
        spec["summary"] = " ".join(u["summary"] for u in units)
    th = spec.get("thumb")
    if isinstance(th, dict) and all(u.get("list") for u in units):
        th["list"] = [u["list"] for u in units]
        th["list_tag"] = f"오늘의 먹거리 뉴스 {n}"
    if all(u.get("caption") for u in units):
        head = str(spec.get("caption_head") or "").strip()
        line = " · ".join(u.get("line") or u.get("title", "") for u in units) + str(spec.get("caption_line") or "").replace("{n}", str(n))
        parts = [(head + "\n" + line).strip()] + [f"{i}. {u['caption']}" for i, u in enumerate(units, 1)]
        if spec.get("caption_ask"):
            parts.append(spec["caption_ask"])
        outlets = _uniq([o for u in units for o in u.get("outlets") or []] + list(spec.get("common_outlets") or []))
        if outlets:
            parts.append("출처: " + ", ".join(outlets))
        spec["caption"] = "\n\n".join(parts)
    for key in ("tags", "yt_tags", "yt_hashtags", "yt_related"):
        mine = [t for u in units for t in u.get(key) or []]
        if mine:
            spec[key] = _uniq(mine + list(spec.get("common_" + key) or []))
    for key in ("sources", "credits"):
        mine = [t for u in units for t in u.get(key) or []]
        if mine or any(key in u for u in units):
            spec[key] = _uniq(mine + list(spec.get("common_" + key) or []))
    if spec.get("yt_title"):
        spec["yt_title"] = re.sub(r"(뉴스 ?)\d+", lambda m: f"{m.group(1)}{n}", spec["yt_title"])
    return spec


def news_problems(spec):
    """소식 단위가 있으면 장과 게시글이 맞는지 봐요. (꼭 고칠 것들)"""
    units = news_units(spec)
    if not units:
        return []
    out, ids = [], [u.get("id") for u in units]
    if len(set(ids)) != len(ids) or None in ids:
        out.append("소식(news)마다 서로 다른 id 를 적어 주세요.")
    for u in units:
        miss = [k for k in ("title", "caption", "list", "line") if not u.get(k)]
        if miss:
            out.append(f"소식 {u.get('id')}: {', '.join(miss)} 칸이 비었어요.")
        if not any(c.get("news") == u.get("id") for c in spec.get("cards") or []):
            out.append(f"소식 {u.get('id')}: 이 소식을 보여 주는 장이 없어요.")
    order = []
    for n, c in enumerate(spec.get("cards") or [], 1):
        if c.get("news") not in ids:
            out.append(f"카드 {n}: news 칸에 소식 id 를 적어 주세요({ids}).")
        elif not order or order[-1] != c["news"]:
            order.append(c["news"])
    if len(order) != len(set(order)) or [i for i in ids if i in order] != order:
        out.append("한 소식의 장은 붙여서, 소식 순서대로 놓아 주세요.")
    return out


def _card_news(spec):
    """장마다 소식 id. 소식 단위가 없으면 카드의 "news" 숫자, 그것도 없으면 장 번호를 써요."""
    return [c.get("news") if c.get("news") is not None else f"#{n}" for n, c in enumerate(spec["cards"], 1)]


def _fallback_drop(spec, gone_cards, gone_news_idx):
    """소식 단위가 없는 예전 설계도: 썸네일 목록·게시글 번호 문단을 번호로 빼고, 여러 소식이 섞인 문장이 있으면 지우지 않고 멈춰요.
    (바꿀 칸들, 떼어 내지 못한 까닭 또는 None)"""
    out = {}
    th = spec.get("thumb") or {}
    lst = th.get("list") if isinstance(th.get("list"), list) else []
    if not gone_news_idx:
        return out, None
    paras = str(spec.get("caption", "")).split("\n\n")
    numbered = [i for i, p in enumerate(paras) if re.match(r"^\d+\. ", p)]
    if len(numbered) != len(lst):
        return out, "게시글 번호 문단과 썸네일 목록 수가 달라 소식을 떼어 낼 수 없어요(news 칸으로 소식을 나눠 적어 주세요)"
    gone_text = " ".join([lst[k - 1] for k in gone_news_idx] + [paras[numbered[k - 1]] for k in gone_news_idx]
                         + [str(c.get("headline", "")) for c in gone_cards])
    keep_text = " ".join([x for i, x in enumerate(lst, 1) if i not in gone_news_idx]
                         + [paras[j] for k, j in enumerate(numbered, 1) if k not in gone_news_idx])
    gone_w = _wordset(gone_text) - _wordset(keep_text) - {"뉴스", "먹거리", "오늘의", "오늘", "출시", "할인"}
    keep_w = _wordset(keep_text) - _wordset(gone_text)
    unsafe = []

    def cut(text, seps, where):
        tail = re.search(r"\s*(오늘의 )?먹거리 뉴스 \d+\s*$", text)
        body, end = (text[:tail.start()], tail.group(0)) if tail else (text, "")

        def split(x, rest):  # 굵은 구분(쉼표)부터 나누고, 소식이 섞인 토막만 더 잘게(가운뎃점) 나눠요. 끝까지 섞여 있으면 지우지 않고 멈춰요
            g, k = _wordset(x) & gone_w, _wordset(x) & keep_w
            if not g:
                return x
            if not k:
                return None
            if not rest:
                unsafe.append(f"{where}의 '{x.strip()[:24]}'에 여러 소식이 섞여 있어요")
                return x
            parts = [split(y, rest[1:]) for y in x.split(rest[0])]
            return rest[0].join(y for y in parts if y is not None)
        body = split(body, list(seps)) or ""
        return body.rstrip(" ,·") + end
    for key in ("title", "yt_title"):
        if spec.get(key):
            out[key] = cut(spec[key], (", ",), key)
    if spec.get("summary"):  # 요약은 문장에 소식이 섞여 있으면 지우지 않고, 남은 소식의 썸네일 줄로 새로 써요(다른 소식 내용이 빠지지 않게)
        sents = re.split(r"(?<=[.!?요])\s+", spec["summary"])
        if not any(_wordset(x) & gone_w for x in sents):
            pass
        elif any(_wordset(x) & gone_w and _wordset(x) & keep_w for x in sents):
            out["summary"] = " ".join(re.sub(r"\[\[|\]\]", "", x) for i, x in enumerate(lst, 1) if i not in gone_news_idx)
        else:
            out["summary"] = " ".join(x for x in sents if not _wordset(x) & gone_w)
    keep = [p for i, p in enumerate(paras) if not (i in numbered and numbered.index(i) + 1 in gone_news_idx)]
    k = 0
    for i, p in enumerate(keep):
        if re.match(r"^\d+\. ", p):
            k += 1
            keep[i] = re.sub(r"^\d+\. ", f"{k}. ", p)
    first = keep[0].split("\n")
    keep[0] = "\n".join(cut(x, (", ", " · "), "게시글 첫 줄") for x in first)
    out["caption"] = "\n\n".join(keep)
    left = len(lst) - len(gone_news_idx)
    out["thumb"] = dict(th, list=[x for i, x in enumerate(lst, 1) if i not in gone_news_idx])
    if th.get("list_tag"):
        out["thumb"]["list_tag"] = re.sub(r"\d+", str(left), th["list_tag"])
    for key in ("caption", "yt_title", "title"):
        if out.get(key):
            out[key] = re.sub(r"(뉴스 ?)" + str(len(lst)) + r"(가지)?", lambda m: f"{m.group(1)}{left}{m.group(2) or ''}", out[key])
    return out, ("소식을 깔끔히 떼어 낼 수 없어요: " + " / ".join(unsafe[:2])) if unsafe else None


def drop_cards(spec, nos):
    """nos(1부터) 장이 속한 **소식 전체**를 뺀 설계도. (새 설계도, 떼어 내지 못한 까닭 또는 None)
    소식 단위(news)가 있으면 그 소식의 칸만 빼고 다시 짜요. 없으면 예전 설계도용 방법(_fallback_drop)."""
    spec = json.loads(json.dumps(spec, ensure_ascii=False))
    cards = spec["cards"]
    ids = _card_news(spec)
    gone_ids = {ids[n - 1] for n in nos if 1 <= n <= len(cards)}
    drop = [n for n in range(1, len(cards) + 1) if ids[n - 1] in gone_ids]
    if not drop:
        return spec, None
    gone = [cards[n - 1] for n in drop]
    cover = spec.get("cover") or {}
    if isinstance(cover.get("items"), list) and len(cover["items"]) == len(cards):
        cover["items"] = [x for i, x in enumerate(cover["items"], 1) if i not in drop]
    units = news_units(spec)
    if units:
        spec["news"] = [u for u in units if u.get("id") not in gone_ids]
        spec["cards"] = [c for i, c in enumerate(cards, 1) if i not in drop]
        return compose_news(spec), None
    # 예전 설계도: 카드의 "news" 숫자(썸네일 목록 몇 번째)로 소식을 찾아요. 없으면 장 수와 목록 수가 같을 때만 장 번호로
    lst = ((spec.get("thumb") or {}).get("list")) or []
    if all(isinstance(i, int) for i in gone_ids):
        gone_idx = set(gone_ids)
    elif len(lst) == len(cards):
        gone_idx = set(drop)
    else:
        return spec, "어느 소식인지 몰라 떼어 낼 수 없어요(카드마다 news 칸을 적어 주세요)"
    changed, why = _fallback_drop(spec, gone, gone_idx)
    if why:
        return spec, why
    spec.update(changed)
    spec["cards"] = [c for i, c in enumerate(cards, 1) if i not in drop]
    left = json.dumps({k: v for k, v in spec.items() if k not in ("tags", "yt_tags", "yt_hashtags", "yt_related", "credits", "meta", "dates", "sources", "review")}, ensure_ascii=False)
    gone_src = json.dumps(gone, ensure_ascii=False)
    gone_only = {w for w in _wordset(gone_src) - _wordset(left) - _wordset(left.replace(" ", "")) if len(w) >= 2}
    for key in ("tags", "yt_tags", "yt_hashtags", "yt_related"):
        if isinstance(spec.get(key), list):
            spec[key] = [t for t in spec[key] if str(t).replace(" ", "") in left.replace(" ", "")
                         or not any(w in str(t).replace(" ", "") for w in gone_only)]
    if isinstance(spec.get("credits"), list):
        spec["credits"] = [c for c in spec["credits"] if str(c).replace(" ", "") in left.replace(" ", "")
                           or str(c).replace(" ", "") not in gone_src.replace(" ", "")]
    return spec, None


FIRST_MIN_NEWS = 2  # 첫 소식이 빠진 뒤에도 남아야 하는 소식 수


def first_news_gap(spec, gone_ids):
    """첫 소식이 빠질 때 남은 소식으로 표지·썸네일·제목·요약을 다시 꾸밀 수 없는 까닭. 꾸밀 수 있으면 None (2026-10-28 사용자).
    소식 단위(news)가 있고, 남은 소식이 FIRST_MIN_NEWS 개 이상이고, 새 맨 앞 소식이 lead(썸네일·표지)를 가질 때만."""
    units = [u for u in news_units(spec) if u.get("id") not in gone_ids]
    if not news_units(spec):
        return "예전 설계도(소식 단위 없음)라 표지·썸네일을 다시 꾸밀 수 없어요"
    if len(units) < FIRST_MIN_NEWS:
        return f"남는 소식이 {len(units)}개뿐이에요({FIRST_MIN_NEWS}개부터)"
    lead = units[0].get("lead") or {}
    if not (lead.get("thumb") and lead.get("cover")):
        return f"다음 소식({units[0].get('title', units[0].get('id'))})에 표지·썸네일 자료(lead.thumb·lead.cover)가 없어요"
    return None


PHOTO_STEPS = ("exact", "press", "other", "layout")  # 사진 복구 절차: 실제 사진 → 보도자료·미디어센터 → 다른 사진·시각 자료 → 레이아웃


def photo_gap(c):
    """사진 없는 소식 장인지. 비교·막대·정리처럼 숫자가 주인공인 꼴과 flow 는 빼요."""
    return not c.get("type") and not c.get("photo") and not c.get("flow")


def triage(spec, day=""):
    """보내기 전에 장마다 살펴 문제 있는 소식만 빼요. (고친 설계도, 보류 목록, 전체 보류 까닭 또는 None)
    보류 목록: [{"no": 원래 장 번호, "headline", "grade": 보류|확인 필요|차단, "reasons": [...], "news"}]"""
    if spec.get("format") != "cards" or not spec.get("cards"):
        return spec, [], None
    spec = compose_news(spec)
    held = {}

    def hold(n, grade, why):
        h = held.setdefault(n, {"no": n, "headline": str(spec["cards"][n - 1].get("headline", "")).replace("\n", " "), "grade": grade,
                                "reasons": [], "news": _card_news(spec)[n - 1]})
        rank = {"보류": 1, "확인 필요": 2, "차단": 3}
        if rank[grade] > rank[h["grade"]]:
            h["grade"] = grade
        if why not in h["reasons"]:
            h["reasons"].append(why)

    for n, c in enumerate(spec["cards"], 1):
        if photo_gap(c) and not is_story(spec):
            tried = c.get("photo_search") or {}
            note = " · ".join(f"{k}: {tried[k]}" for k in PHOTO_STEPS if tried.get(k))
            hold(n, "보류", "사진 없는 소식 장" + (f" (복구 시도: {note})" if note else " (복구 절차 기록 없음)"))
    must, _ = card_problems(spec)
    whole = []
    for m in must:
        n = held_card_no(m)
        if n is None:
            whole.append(m)
        elif "사진 없는 소식 장" not in m:
            hold(n, "보류", m)
    try:
        sys.path.insert(0, str(HERE.parent / "scripts"))
        import contentcheck
        for kind, msg, grade in contentcheck.photo_lines(spec, day or "9999-12-31"):
            n = held_card_no(msg)
            if not n or n > len(spec["cards"]):
                continue
            if grade == "차단":
                hold(n, "차단", f"{kind}: {msg}")
            elif grade == "확인" and kind == "사진 권리":
                hold(n, "확인 필요", f"{kind}: {msg}")
    except Exception as e:  # 검사를 못 하면 장을 빼지 않고 보내기 전 검수(gate)에 맡겨요
        print(f"  장별 사진 검사를 하지 못했어요: {e}")
    if whole:
        return spec, list(held.values()), "형식: " + " / ".join(whole[:3])
    if not held:
        return spec, [], None
    ids = _card_news(spec)
    for n in list(held):  # 같은 소식의 다른 장도 함께 빠져요
        for m in range(1, len(ids) + 1):
            if ids[m - 1] == ids[n - 1] and m not in held:
                hold(m, held[n]["grade"], f"같은 소식의 {n}장이 보류돼 함께 빠져요")
    held_list = sorted(held.values(), key=lambda h: h["no"])
    if ids[0] in {h["news"] for h in held_list}:
        why = first_news_gap(spec, {h["news"] for h in held_list})
        if why:
            return spec, held_list, "첫 소식(표지·썸네일 주제)이 걸렸어요: " + " / ".join(held_list[0]["reasons"][:2]) + f" — {why}"
    if is_top5(spec):
        return spec, held_list, "TOP5 는 순위가 이어져 장을 뺄 수 없어요"
    lo = STORY_MIN if is_story(spec) else CARD_MIN
    if len(spec["cards"]) - len(held) < lo:
        return spec, held_list, f"보류하고 나면 {len(spec['cards']) - len(held)}장만 남아요({lo}장부터)"
    out, why = drop_cards(spec, list(held))
    if why:
        return spec, held_list, why
    return out, held_list, None


def layout_triage(spec, bad, held_before=()):
    """그린 뒤 검수에 걸린 장: 큰 제목 장은 한 번 작게(compact) 고쳐 다시 재고, 그래도 안 되면 그 장의 소식만 빼요.
    (새 설계도, 새로 보류한 장 목록, 전체 보류 까닭 또는 None)"""
    by = {}
    for m in bad:
        n = held_card_no(m)
        if n is None:
            return spec, [], "첫 장 검수: " + m
        by.setdefault(n, []).append(m)
    spec = json.loads(json.dumps(spec, ensure_ascii=False))
    drop, held = [], []
    ids = _card_news(spec)
    for n, ms in by.items():
        c = spec["cards"][n - 1]
        if c.get("type") == "hero" and not c.get("compact"):
            c["compact"] = True  # 자동 수정: 제목을 더 작게 해서 다시 재요
            continue
        if ids[n - 1] == ids[0] and first_news_gap(spec, {ids[0]}):
            return spec, [], "첫 소식 장 검수: " + " / ".join(ms[:2]) + " — " + first_news_gap(spec, {ids[0]})
        drop.append(n)
        held.append({"no": n, "headline": str(c.get("headline", "")).replace("\n", " "), "grade": "보류", "reasons": ms, "news": ids[n - 1]})
    if drop:
        gone = {ids[n - 1] for n in drop}
        for m in range(1, len(ids) + 1):
            if ids[m - 1] in gone and m not in drop:
                drop.append(m)
                held.append({"no": m, "headline": str(spec["cards"][m - 1].get("headline", "")).replace("\n", " "), "grade": "보류",
                             "reasons": ["같은 소식의 다른 장이 보류돼 함께 빠져요"], "news": ids[m - 1]})
        lo = STORY_MIN if is_story(spec) else CARD_MIN
        if len(spec["cards"]) - len(drop) < lo:
            return spec, held, f"보류하고 나면 {len(spec['cards']) - len(drop)}장만 남아요"
        spec, why = drop_cards(spec, drop)
        if why:
            return spec, held, why
    return spec, held, None


def news_card(c, n, total, when, name, pill, nxt=None, story=False):
    if c.get("type") == "hero":
        return hero_card(c, n, total, when, name, pill)
    if c.get("type") == "summary":
        return summary_card(c, n, total, when, name, pill, story=story)
    q, nexts = story_bits(c, nxt, n, total) if story else ("", "")
    note = f'<div class="note">{rich(c["note"])}</div>' if c.get("note") else ""  # 사진 위에 붙이는 스티커 한마디
    if c.get("type") == "compare":
        top = f'<div class="ph">{NEWS_MAP}</div>' + compare_html(c)
    elif c.get("type") == "chart":
        top = f'<div class="ph">{NEWS_MAP}</div>' + chart_html(c)
    elif c.get("photo") and c["photo"].get("fit") == "pack":  # 상품 사진은 하얀 사진 카드처럼 살짝 기울여 얹어요
        top = f'<div class="ph">{NEWS_MAP}</div><div class="pack"><img src="{pack_photo(c["photo"])}"></div>{SPARK}'
    elif c.get("flow"):  # 어디서 → 뛰어가서 → 무엇을: 파는 곳 로고, 뛰는 사람, 그 음식 사진 (2026-10-16 사용자가 정함)
        top = f'<div class="ph">{NEWS_MAP}</div>' + flow_html(c["flow"])
    elif c.get("big") and c.get("photo"):  # 숫자 강조 장: 그 음식 사진을 어둡게 깔고 큰 숫자를 얹어요 (2026-10-19 5단계)
        src, pos = fetch_photo(c["photo"])
        top = (f'<div class="ph numbg"><img src="{src}" style="object-position:{pos}"></div>{ref_label(c["photo"]).replace("ref", "ref ph-ref", 1)}'
               f'<div class="bignum" style="font-size:{fit_size(c["big"], 230, 950)}px">{rich(c["big"])}</div>')
    elif c.get("photo"):
        src, pos = fetch_photo(c["photo"])
        top = f'<div class="ph"><img src="{src}" style="object-position:{pos}"></div>{ref_label(c["photo"]).replace("ref", "ref ph-ref", 1)}'
    else:  # 맞는 사진이 없는 소식은 지도 바탕에 큰 숫자를 얹어요
        big = f'<div class="bignum" style="font-size:{fit_size(c["big"], 230, 950)}px">{rich(c["big"])}</div>' if c.get("big") else ""
        top = f'<div class="ph">{NEWS_MAP}</div>{big}'
    fact = f'<div class="fact" style="font-size:{fit_size(c["fact"], FACT_SIZE, 950)}px">{rich(c["fact"])}</div>' if c.get("fact") else ""
    fact += f'<div class="bs">{esc(c["basis"])}</div>' if c.get("basis") else ""  # 숫자의 기준 (작년 같은 날 대비 등)
    why = why_lines(c)
    size = min(fit_size(line, WHY_SIZE, 915) for line in why)
    rows = "".join(f'<div style="font-size:{size}px">{rich(line)}</div>' for line in why)
    return (
        f'<section class="nc{" st" if story else ""}" id="c{n + 1}">{top}{note}'  # c1 은 첫 장(표지)이에요
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><span class="tag">{esc(c["tag"])}</span>{q}'
        f'<div class="hl" style="font-size:{fit_size(c["headline"], HL_SIZE, 950)}px">{rich(c["headline"])}</div>{fact}'
        f'<div class="why">{rows}</div></div>{nexts}'
        f'<div class="foot"><span>자료 {esc(c["src"])}</span><b>{"" if story else f"{n} / {total}"}</b></div></section>'
    )


def top5_card(c, n, total, when, name, pill, kind="추천"):
    """TOP5형 한 장: 위쪽 큰 실제 사진 + (추천 N 또는 N위) + 음식 이름 + 핵심 한 줄 (+ 핵심 숫자, 마지막 장이면 댓글 물음)."""
    src, pos = fetch_photo(c["photo"])
    fact = f'<div class="fact" style="font-size:{fit_size(c["fact"], FACT_SIZE, 950)}px">{rich(c["fact"])}</div>' if c.get("fact") else ""
    fact += f'<div class="bs">{esc(c["basis"])}</div>' if c.get("basis") else ""
    ask = f'<div class="ask">{rich(c["ask"])}</div>' if c.get("ask") else ""
    dots = "".join(f'<i class="{"on" if i == n else ""}"></i>' for i in range(1, total + 1))
    no = int(c["no"])
    if kind == "자료":
        mark, nxt = f'<b>{no}</b>위', ("" if no == 1 else f"다음 · {no - 1}위")
    else:  # 추천: 순위가 아니라 차례 번호예요
        mark, nxt = f'<em>추천</em><b>{no}</b>', ("" if n == total else f"다음 · 추천 {no + 1}")
    return (
        f'<section class="nc rk" id="c{n + 1}">'
        f'<div class="ph"><img src="{src}" style="object-position:{pos}"></div>'
        f'<div class="mast"><div class="brand">{OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="when">{esc(when)}</div></div>'
        f'<div class="txt"><div class="rank">{mark}</div>'
        f'<div class="hl" style="font-size:{fit_size(c["name"], 120, 950)}px">{rich(c["name"])}</div>'
        f'<div class="ln" style="font-size:{fit_size(c["line"], 52, 950)}px">{rich(c["line"])}</div>{fact}{ask}</div>'
        f'<div class="next"><span class="nx-q">{nxt}</span><span class="dots">{dots}</span></div>'
        f'<div class="foot"><span>{esc(("자료 " + c["src"]) if c.get("src") else "")}</span><b></b></div></section>'
    )


def build_cards(spec):
    """카드 뉴스 설계도를 한 쪽짜리 HTML로 만들어요. 카드는 #c1, #c2 … 로 위에서 아래로 놓여요. (HTML, 장수)"""
    if spec.get("format") == "steps":  # 넘겨 보는 해설 (2026-10-18)
        import steps
        return steps.build_steps(spec)
    must, _ = card_problems(spec)
    if must:
        raise ValueError(" / ".join(must))
    pill, label, color = series(spec)
    accent = spec.get("accent") or color
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or ""
    name = f"{esc(name[:2])}<b>{esc(name[2:])}</b>" if name.startswith("먹고") else esc(name)
    css = (HERE / "cards.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    cards = spec["cards"]
    if any(c.get("type") == "hero" for c in cards):  # 큰 제목 장은 썸네일과 같은 제목 글꼴을 써요
        import thumb
        css += thumb.css().replace("FONT_DIR", (HERE / "fonts").as_uri())
    when = spec.get("kicker", "")
    story = is_story(spec)
    if is_top5(spec):  # TOP5형 (2026-10-19 5단계)
        kind = rank_type(spec)
        pill = esc(spec.get("pill") or TOP5_PILL[kind])
        cover = dict(spec["cover"], label=spec["cover"].get("label") or TOP5_LABEL[kind])
        note = f'순위 자료 {spec["rank_src"]}' if kind == "자료" else spec.get("rank_note")
        body = news_cover(cover, len(cards), when, name, pill, label, story=True, first_q="5위부터" if kind == "자료" else "다섯 가지",
                          foot_note=note)
        body += "".join(top5_card(c, n, len(cards), when, name, pill, kind) for n, c in enumerate(cards, 1))
        page = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head><body style="--ac:{accent}">{body}</body></html>'
        return page, len(cards) + 1
    if story:
        pill = esc(spec.get("pill") or STORY_PILL)
    body = news_cover(spec["cover"], len(news_units(spec)) or len(((spec.get("thumb") or {}).get("list")) or []) or len(cards), when, name, pill, label, weekly=spec.get("kind") == "유행", story=story,
                      first_q=cards[0].get("q") if story and cards else None)
    body += "".join(news_card(c, n, len(cards), when, name, pill, cards[n] if n < len(cards) else None, story)
                    for n, c in enumerate(cards, 1))
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
    for big, small in shown:  # 영상 끝 장면에는 출처를 넣지 않아서, 몇 줄이든 게시글에 모두 적어요 (2026-10-22)
        lines.append(f"📷 {big}" + (f" · {small} · 잘라서 보정함" if "CC BY" in big else ""))
    if shown:
        lines.append("")
    if not is_cards(spec) and music_line(spec):  # 인스타 카드에는 음악이 없어요
        lines += [music_line(spec), ""]
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
    "korea.kr": "정책브리핑", "mof.go.kr": "해양수산부", "incheon.go.kr": "인천광역시", "kamis.or.kr": "aT",
    "at.or.kr": "aT", "mafra.go.kr": "농림축산식품부", "mfds.go.kr": "식약처", "open-meteo.com": "Open-Meteo 날씨",
    "visitkorea.or.kr": "한국관광공사", "nongshim.com": "농심", "hongseong.go.kr": "홍성군",
    "kyeongin.com": "경인일보", "tenasia.co.kr": "텐아시아", "mtn.co.kr": "머니투데이방송", "heraldcorp.com": "헤럴드경제",
    "nocutnews.co.kr": "노컷뉴스", "ohmynews.com": "오마이뉴스", "dt.co.kr": "디지털타임스", "etnews.com": "전자신문",
    "insightkorea.co.kr": "인사이트코리아", "hankooki.com": "한국일보", "seoul.co.kr": "서울신문", "kmib.co.kr": "국민일보",
    "kyeonggi.com": "경기일보", "daum.net": "다음 뉴스", "bravo.etoday.co.kr": "브라보마이라이프", "etoday.co.kr": "이투데이",
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
    first = " ".join(str(spec.get("yt_lead") or "").split()) or next((x for x in lines if x), title)  # 설명 첫 줄: 핵심 키워드를 자연스럽게 넣은 한 줄
    # 목록: 설계도에 적은 것 > 카드 > 순위 > 카드 장면 > 체크·표
    points = spec.get("yt_points")
    if not points:
        plain = lambda t: " ".join(str(t).replace("[[", "").replace("]]", "").split())
        scenes = spec.get("scenes") or []
        if spec.get("cards"):
            points = [plain(c.get("headline", "")) for c in spec["cards"]]
        elif any(x["type"] == "rank" for x in scenes):
            ranks = sorted((x for x in scenes if x["type"] == "rank"), key=lambda x: x["no"])
            points = [x["name"] for x in ranks]  # 술은 넣지 않아요 (2026-10-18)
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
        if what and not is_story(spec):  # 이야기 카드는 "N가지" 모음이 아니에요
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
    if "vault:photos/" in json.dumps(spec, ensure_ascii=False):  # 사용자가 직접 찍은 사진(보관함 photos/)일 때만
        shown.append("직접 촬영")
    if shown:
        out.append("📷 사진 출처: " + ", ".join(dict.fromkeys(shown)))
    if music_line(spec):
        out.append(music_line(spec))
    ask = next((x for x in reversed(lines[1:]) if x.endswith("?") or x.endswith("요?") or "댓글" in x), "")
    if ask:
        out.append(ask)
    out.append(" ".join("#" + t for t in youtube_keywords(spec)["hashtags"]))
    return title, "\n".join(out) + "\n"


def _words(xs):
    """띄어쓰기를 고르고, 비거나 겹치는 것(띄어쓰기만 다른 것 포함)을 빼요."""
    out, seen = [], set()
    for x in xs or []:
        x = " ".join(str(x).replace("#", " ").split())
        if x and x.replace(" ", "") not in seen:
            seen.add(x.replace(" ", ""))
            out.append(x)
    return out


def youtube_keywords(spec):
    """유튜브 쇼츠 키워드 묶음 (2026-10-16 사용자가 정함, PROMPT.md "유튜브 키워드").
    keyword(핵심 1개), related(연관 3~6개), tags(업로드 태그 목록), tag_text(태그 칸에 붙여 넣을 글), hashtags(설명 끝 해시태그)"""
    keyword = " ".join(str(spec.get("yt_keyword") or "").split())
    related = _words(spec.get("yt_related"))
    tags = _words(spec.get("yt_tags")) or _words([keyword] + related)
    tags = _words(["먹고갈지도"] + tags)  # 채널 이름은 늘 맨 앞에 (2026-10-16 사용자가 정함)
    tag_text = ""
    for t in tags:  # 유튜브 태그 칸은 모두 합쳐 500자까지라 넘치면 뒤의 것을 버려요
        if len(tag_text) + len(t) + 1 > 450:
            break
        tag_text = f"{tag_text},{t}" if tag_text else t
    if spec.get("yt_hashtags"):
        tags_h = [t.replace(" ", "") for t in _words(spec["yt_hashtags"])][:5]
    else:
        tags_h = hashtags(spec.get("tags"))[:-1][:3]  # 예전 설계도: 인스타 해시태그 앞 3개 (마지막은 계정 이름이라 빼요)
    return {"keyword": keyword, "related": related, "tags": tags, "tag_text": tag_text, "hashtags": tags_h}


def youtube_problems(spec):
    """유튜브 키워드 규칙에 어긋나는 것을 알려 줘요."""
    out = []
    k = youtube_keywords(spec)
    if not k["keyword"]:
        out.append("yt_keyword(핵심 키워드 1개)가 없어요.")
    if not 3 <= len(k["related"]) <= 6:
        out.append(f"yt_related(연관 키워드)가 {len(k['related'])}개예요. 3~6개로 적어 주세요.")
    if not spec.get("yt_tags"):
        out.append("yt_tags(업로드 태그)가 없어요. 핵심·연관 키워드로 대신 채워요.")
    elif len(_words(spec["yt_tags"])) != len(spec["yt_tags"]):
        out.append("yt_tags 에 겹치는 태그가 있어 뺐어요.")
    if not spec.get("yt_hashtags"):
        out.append("yt_hashtags(유튜브 해시태그)가 없어요. 인스타 해시태그 앞 3개를 대신 써요.")
    title = str(spec.get("yt_title") or "").replace(" ", "")
    if k["keyword"] and title and k["keyword"].replace(" ", "") not in title:
        out.append(f"제목(yt_title)에 핵심 키워드 '{k['keyword']}' 가 그대로 들어 있지 않아요. 괜찮은지 한 번 더 보세요.")
    if not spec.get("yt_lead"):
        out.append("yt_lead(설명 첫 줄)가 없어요. 게시글 첫 줄을 대신 써요.")
    return out


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if news_units(spec) and spec.get("format") == "cards":  # 소식 단위로 게시글·제목·목록·태그·출처를 맞춰 설계도에 다시 적어요 (2026-10-28)
        fixed = compose_news(spec)
        if fixed != spec:
            Path(sys.argv[1]).write_text(json.dumps(fixed, ensure_ascii=False, indent=1), encoding="utf-8")
            print("  소식 단위(news)로 제목·요약·게시글·썸네일 목록·태그·출처를 다시 맞춰 설계도에 적었어요.")
            spec = fixed
    try:  # 지난 콘텐츠와 겹치는지, 날짜가 맞는지 (2026-10-23 3단계, scripts/history.py). 알려 주기만 하고 막지는 않아요
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import history
        history.print_report(sys.argv[1])
    except Exception as e:
        print(f"  이력: 확인하지 못했어요 ({e})")
    try:  # 사진이 글과 같은 대상인지, 써도 되는 사진인지, 지역 이름·범위 (2026-10-23 4단계, scripts/contentcheck.py). 알려 주기만 해요
        import contentcheck
        contentcheck.print_report(sys.argv[1])
    except Exception as e:
        print(f"  사진·지역: 확인하지 못했어요 ({e})")
    if is_cards(spec):
        if spec.get("format") == "steps":
            import steps
            must, should = steps.problems(spec)
        else:
            must, should = card_problems(spec)
        for line in must:
            print("  꼭 고쳐 주세요: " + line)
        for line in should:
            print("  " + line)
        if must:
            sys.exit(1)
        _, count = build_cards(spec)  # 사진이 받아지는지도 여기서 확인돼요
        must, should = card_photo_problems(spec)  # 흐린 사진, 한 장 돌려쓰기, 실사 사진 수 (2026-10-19 5단계)
        if spec.get("format") == "cards":
            m2, s2 = number_problems(spec)  # 제목·본문 숫자 표기 (2026-10-19 5단계)
            must, should = must + m2 + basis_problems(spec), should + s2  # 값·증감률의 기준 기간과 출처
        for line in must:
            print("  꼭 고쳐 주세요: " + line)
        for line in should:
            print("  " + line)
        if must:
            sys.exit(1)
        if spec.get("format") == "steps":
            print(f"넘겨 보는 해설 {count}장")
        elif is_story(spec):
            print(f"이야기 카드 {count}장 (첫 장 1 + 이어지는 장 {count - 1})")
        elif is_top5(spec):
            print(f"TOP5형 카드 {count}장 (첫 장 1 + " + ("5위~1위, 순위 자료 " + str(spec.get("rank_src")) if rank_type(spec) == "자료" else "추천 1~5, 순위 아님") + ")")
        else:
            print(f"카드 뉴스 {count}장 (첫 장 1 + 소식 {count - 1})")
        if len(spec.get("tags") or []) != 4:
            print(f"  해시태그를 {len(spec.get('tags') or [])}개 적었어요. 4개만 골라 적어 주세요. (다섯 번째 계정 이름은 자동으로 붙어요)")
        print("  해시태그: " + " ".join("#" + t for t in hashtags(spec.get("tags"))))
        shown = credit_lines(spec)
        print(f"  사진 출처: {len(shown)}줄이 게시글에 자동으로 들어가요." if shown else "  사진 출처: 표시할 것이 없어요.")
        for line in youtube_problems(spec):
            print("  유튜브: " + line)
        import thumb
        for line in thumb.spec_problems(spec):
            print("  썸네일: " + line)
        sys.exit(0)
    if spec.get("format") == "voice":
        import voice
        must, should, guess = voice.problems(spec)
        for line in must:
            print("  꼭 고쳐 주세요: " + line)
        for line in should:
            print("  " + line)
        if must:
            sys.exit(1)
        page, dur, meta = build_html(spec)  # 사진이 받아지는지, 키가 있으면 목소리까지 여기서 확인돼요
        print(f"내레이션 쇼츠 {dur:.1f}초 (문장 {len(spec['lines'])}개, {'목소리로 잰 길이' if meta['voice'] else '어림한 길이'})")
        print("  해시태그: " + " ".join("#" + t for t in hashtags(spec.get("tags"))))
        for line in youtube_problems(spec):
            print("  유튜브: " + line)
        sys.exit(0)
    page, dur, _ = build_html(spec)
    print(f"{dur:.1f}초, 장면 {len(spec['scenes'])}개")
    if SQUEEZE < 0.97:  # 장면은 빠지지 않지만 모두 빨라져 읽기 빠듯할 수 있어요
        print(f"  길이: 적은 길이가 {longest(spec):.0f}초를 넘어 장면이 모두 {round((1 - SQUEEZE) * 100)}% 짧아졌어요. "
              "덜 중요한 장면을 빼서 꼭 필요한 장면이 제 길이로 나오게 해 주세요.")
    elif dur > longest(spec) - 3:  # 상한은 채울 목표가 아니에요 (보통 길이를 넘었을 때만 알려요)
        print(f"  길이: 보통보다 길어요({longest(spec):.0f}초까지 돼요). 없어도 되는 장면이 있으면 빼 주세요.")
    if len(spec.get("tags") or []) != 4:
        print(f"  해시태그를 {len(spec.get('tags') or [])}개 적었어요. 4개만 골라 적어 주세요. (다섯 번째 계정 이름은 자동으로 붙어요)")
    print("  해시태그: " + " ".join("#" + t for t in hashtags(spec.get("tags"))))
    for line in youtube_problems(spec):
        print("  유튜브: " + line)
    import thumb
    for line in thumb.spec_problems(spec):
        print("  썸네일: " + line)
    shown = credit_lines(spec)
    print(f"  사진 출처: {len(shown)}줄이 게시글에 자동으로 들어가요." if shown else "  사진 출처: 표시할 것이 없어요.")
    for big, small in shown:
        if "CC BY" in big and "curid=" not in small:
            print(f"  '{big}' 에 원본 주소가 없어요. photos.py 가 알려 준 credit 을 그대로 적어 주세요.")
    for n, s in enumerate(spec["scenes"], 1):
        if s.get("video"):
            print(f"  장면 {n}: 동영상이에요. 영상을 만들 때 넣어요.")
        elif s["type"] == "card" and not s.get("photo"):
            print(f"  장면 {n}: 사진 없는 장면이에요(지도 바탕에 글). 맞는 사진이 없을 때만 이렇게 써요.")
        elif s["type"] == "card" and not is_tall(s["photo"]):
            print(f"  장면 {n}: 가로 사진이에요. 같은 음식의 세로 사진이 있으면 그걸 쓰면 화면을 꽉 채워요.")
