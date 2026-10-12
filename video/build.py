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
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

HERE = Path(__file__).parent
CACHE = HERE.parent / "build" / "photos"
ACCENTS = {"제철": "#FFB23E", "소식": "#4FC3C8", "저녁": "#FF7A6B", "추가": "#B79CFF", "세계": "#8FD694"}
UA = {"User-Agent": "jecheol-feed/1.0 (https://github.com/hong2-kim/jecheol-feed)"}


def esc(text):
    return html.escape(str(text))


def rich(text):
    """[[글]] 로 감싼 부분은 강조색으로 보여 줘요."""
    return esc(text).replace("[[", '<span class="am">').replace("]]", "</span>")


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
        if url.startswith("http"):
            safe = urllib.parse.quote(url, safe=":/?&=%+,;@()")
            data = urllib.request.urlopen(urllib.request.Request(safe, headers=UA), timeout=60).read()
        else:  # 사용자가 보낸 사진. 저장소 안의 경로예요 (myphotos/이름.jpg)
            data = (HERE.parent / url).read_bytes()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        if min(image.size) < 500:
            raise ValueError(f"사진이 너무 작아요 ({image.size[0]}x{image.size[1]}): {url}")
        grade(image).save(path, "JPEG", quality=92)
    if url not in SIZES:
        with Image.open(path) as im:
            SIZES[url] = im.size
    return path.as_uri(), photo.get("pos", "50% 50%")


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
            if url.startswith("http"):
                safe = urllib.parse.quote(url, safe=":/?&=%+,;@()")
                src.write_bytes(urllib.request.urlopen(urllib.request.Request(safe, headers=UA), timeout=180).read())
            else:
                src.write_bytes((HERE.parent / url).read_bytes())
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


def moving(s, dur, zoom_in=True):
    """장면의 바탕. 동영상이 있으면 동영상, 없으면 사진. (HTML, 흐린 바탕 주소, 세로인지)"""
    if s.get("video") and EXTRACT:
        first, folder, count, tall = clip(s["video"], dur)
        pos = s["video"].get("pos", "50% 50%") if isinstance(s["video"], dict) else "50% 50%"
        tag = f'<img class="vf" src="{first}" data-frames="{folder}" data-n="{count}" data-fps="{FPS}" style="object-position:{pos}">'
        return tag, first, tall
    if s.get("video"):  # 설계도 확인만 할 때는 동영상을 풀지 않아요
        return "", "", True
    return img(s["photo"], dur, zoom_in), backdrop(s["photo"]), is_tall(s["photo"])


def img(photo, dur, zoom_in=True, extra=""):
    src, pos = fetch_photo(photo)
    s0, s1 = ("1.02", "1.12") if zoom_in else ("1.12", "1.02")
    return f'<img class="a kb" src="{src}" style="--d:{dur + .6}s;--s0:{s0};--s1:{s1};object-position:{pos};{extra}">'


def rise(cls, text, delay, tag="div", style=""):
    return f'<{tag} class="{cls} a rise" style="--dl:{delay}s;--d:.45s;{style}">{rich(text)}</{tag}>'


def scene_cover(s, i, ctx):
    parts = [f'<div class="pic">{moving(s, s["dur"], i % 2 == 0)[0]}</div>', '<div class="mid">']
    if s.get("kicker"):
        parts.append(rise("kicker", s["kicker"], .15))
    parts.append(rise("title", s["title"], .4, style=f'font-size:{s.get("size", 128)}px'))
    if s.get("line"):
        parts.append(rise("line", s["line"], .75))
    parts.append("</div>")
    return "cover", "".join(parts)


def scene_card(s, i, ctx):
    """사진이나 동영상을 화면 가득 깔고 글은 아래쪽에 얹어요. 세로면 전체, 가로면 위 3/4 을 채워요."""
    tag, back, tall = moving(s, s["dur"], i % 2 == 0)
    chip = rise("chip", s["chip"], .2) if s.get("chip") else ""
    return "card", (
        f'<div class="back"><img src="{back}"></div>'
        f'<div class="pic {"tall" if tall else "wide"}">{tag}</div><div class="shade"></div>'
        f'<div class="txt">{chip}{rise("hd", s["headline"], .32)}{rise("ln", s.get("line", ""), .6)}</div>'
    )


def scene_duo(s, i, ctx):
    parts = [f'<div class="pic">{img(s["photo_top"], s["dur"], True)}</div>',
             f'<div class="pic bot">{img(s["photo_bottom"], s["dur"], False)}</div>']
    if s.get("title"):
        parts.append('<div class="seam"></div><div class="mid">')
        if s.get("no"):
            parts.append(rise("no", s["no"], .2))
        parts.append(rise("big", s["title"], .3, style=f'font-size:{s.get("size", 116)}px'))
        if s.get("sub"):
            parts.append(rise("sub", s["sub"], .6))
        parts.append("</div>")
    if s.get("chip_top"):
        parts.append(rise("tagchip", s["chip_top"], .45, style="top:150px;"))
    if s.get("chip_bottom"):
        parts.append(rise("tagchip", s["chip_bottom"], 1.9, style="top:1090px;"))
    if s.get("chip_bottom2"):
        parts.append(rise("tagchip hot", s["chip_bottom2"], 2.6, style="top:1190px;"))
    return "duo", "".join(parts)


def scene_info(s, i, ctx):
    bottom = s.get("photo_bottom", s["photo"])
    return "info", (
        f'<div class="pic">{img(s["photo"], s["dur"], False)}</div><div class="pic bot">{img(bottom, s["dur"], True)}</div>'
        f'<div class="box">{rise("kicker", s.get("kicker", ""), .3, style="font-size:48px;")}'
        f'{rise("big", s["title"], .5, style="font-size:104px;margin-top:10px;")}'
        f'{rise("huge", s["big"], .9)}{rise("sub", s.get("sub", ""), 1.2, style="margin-top:0;")}</div>'
    )


def signature():
    """마지막 장면에 넣는 계정 이름. config.json 의 account 를 써요. 지도 핀 모양과 함께 보여 줘요."""
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account")
    if not name:
        return ""
    pin = ('<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="var(--ac)"/>'
           '<circle cx="100" cy="92" r="34" fill="#0E0B09"/></svg>')
    return f'<div class="sig a rise" style="--dl:1s;--d:.45s">{pin}{esc(name)}</div>'


SCENES = {"cover": scene_cover, "card": scene_card, "duo": scene_duo, "info": scene_info}


def build_html(spec):
    """설계도를 한 장짜리 HTML로 만들어요. (HTML, 길이)"""
    accent = spec.get("accent") or ACCENTS.get(spec.get("kind", ""), "#FFB23E")
    scenes = spec["scenes"]
    ctx = {"cards": sum(1 for s in scenes if s["type"] == "card"), "card_no": 0, "brand": spec.get("brand")}
    meta = {"music": "none", "sfx": [], "ambience": []}  # 노래와 효과음은 넣지 않아요. 올릴 때 인스타그램에서 고르면 돼요.
    css = (HERE / "base.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">', f"<style>{css}</style></head>",
           f'<body style="--ac:{accent}">']
    at = 0.0
    for i, s in enumerate(scenes):
        s.setdefault("dur", 4.4)
        kind, body = SCENES[s["type"]](s, i, ctx)
        last = i == len(scenes) - 1
        if last:
            body += signature()
        out.append(f'<section class="scene {kind}{" in-fade" if i else ""}" data-at="{at:.2f}" data-dur="{s["dur"]}" data-out="{0 if last else 0.3}">{body}</section>')
        at += s["dur"]
    out.append(f"<script>{(HERE / 'base.js').read_text(encoding='utf-8')}</script></body></html>")
    return "\n".join(out), at, meta


def description(spec):
    """게시글에 넣을 글. 제목, 핵심 내용, 문구, 해시태그, 사진·음악 표기, 출처."""
    lines = [spec["caption"].strip(), "", " ".join("#" + t for t in spec.get("tags", [])), ""]
    if spec.get("credits"):
        lines.append("사진 " + " / ".join(spec["credits"]))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    page, dur, _ = build_html(spec)
    print(f"{dur:.1f}초, 장면 {len(spec['scenes'])}개")
    for n, s in enumerate(spec["scenes"], 1):
        if s.get("video"):
            print(f"  장면 {n}: 동영상이에요. 영상을 만들 때 넣어요.")
        elif s["type"] == "card" and not is_tall(s["photo"]):
            print(f"  장면 {n}: 가로 사진이에요. 같은 음식의 세로 사진이 있으면 그걸 쓰면 화면을 꽉 채워요.")
