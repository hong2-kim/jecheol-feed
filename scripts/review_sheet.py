# -*- coding: utf-8 -*-
"""실제 사진 검수 시트. (2026-10-23 5단계)
shows 칸에 적은 말만 믿지 않도록, 설계도에 들어간 사진을 잘라 쓴 모양 그대로 받아 그 자리의 글과 나란히 한 장에 모아요.
이 시트를 직접 열어 보고(사람이든 매일 실행의 Claude 든) 사진과 글이 같은 대상인지 확인한 뒤, 나온 지문을 설계도 review.photo_sheet 에 적어요.
지문은 사진 주소와 잘라 쓴 좌표로 만들어서, 사진을 바꾸면 달라져요(그러면 scripts/gate.py 가 다시 '확인 필요'로 봐요).

  python3 scripts/review_sheet.py videos/2026-10-24/4-find.json 시트.jpg          설계도의 사진 + 글
  python3 scripts/review_sheet.py --media dist/2026-10-24-4-find.mp4 시트.jpg       완성된 영상의 장면을 한 줄로 (카드 그림 여러 장도 됨)

컴퓨터가 사진 속을 알아보는 것은 아니에요. 시트를 보고 판단하는 것은 사람(또는 사진을 읽는 Claude)이에요.
"""
import hashlib
import json
import sys
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "video"))
FONT = ROOT / "video" / "fonts" / "NotoSansKR-VF.ttf"


def slots(spec):
    """(자리, 글, 사진) — contentcheck 가 사진과 글을 묶는 방법 그대로."""
    import contentcheck
    if "blocks" in spec:
        spec = contentcheck.blog_as_spec(spec)
    return contentcheck.items_of(spec)


def sheet_hash(spec):
    """사진 주소와 잘라 쓴 좌표의 지문. 사진이 없으면 빈칸."""
    items = [(p.get("url"), list(p.get("crop") or [])) for _, _, p in slots(spec)]
    if not items:
        return ""
    return hashlib.sha256(json.dumps(items, ensure_ascii=False).encode()).hexdigest()[:12]


def font(size):
    try:
        return ImageFont.truetype(str(FONT), size)
    except OSError:
        return ImageFont.load_default()


def tile(img, caption, w=360, h=300, mark=False):
    """사진 한 칸 + 아래 글. mark 면 빨간 테두리(보류 까닭이 걸린 칸)."""
    card = Image.new("RGB", (w, h + 170), "white")
    if img is not None:
        img = img.copy()
        img.thumbnail((w, h))
        card.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
    else:
        ImageDraw.Draw(card).text((20, h // 2), "사진을 받지 못함", fill="red", font=font(22))
    d = ImageDraw.Draw(card)
    if mark:
        d.rectangle([0, 0, w - 1, h + 169], outline=(220, 0, 0), width=6)
    y = h + 6
    for line in caption.split("\n"):
        for part in textwrap.wrap(line, 22) or [""]:
            d.text((8, y), part, fill=(200, 0, 0) if mark and y == h + 6 else "black", font=font(17))
            y += 22
            if y > h + 160:
                return card
    return card


def grid(tiles, cols=4, header=""):
    """칸을 모아 한 장으로. header 가 있으면 맨 위에 제목·종류·날짜·보류 까닭을 적어요."""
    if not tiles:
        tiles = [Image.new("RGB", (400, 100), "white")]
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    lines = [part for line in header.split("\n") for part in (textwrap.wrap(line, 70) or [""])] if header else []
    top = 26 * len(lines) + (16 if lines else 0)
    sheet = Image.new("RGB", (max(w * min(cols, len(tiles)), 900), h * rows + top), (230, 230, 230))
    d = ImageDraw.Draw(sheet)
    for i, line in enumerate(lines):
        d.text((10, 8 + 26 * i), line, fill="black", font=font(20))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * w, top + (i // cols) * h))
    return sheet


def spec_sheet(path, out, mark=(), header=""):
    """설계도의 사진을 잘라 쓴 모양 그대로 + 그 자리 글·shows·출처. mark 에 든 자리(예: 'scenes[3].photo')는 빨간 테두리."""
    import build
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    tiles = []
    for where, text, p in slots(spec):
        try:
            file, _ = build.fetch_photo(p)  # 잘라 쓴 좌표까지 적용된 모양 (file:// 주소로 돌려줘요)
            if file.startswith("file:"):
                file = urllib.request.url2pathname(urllib.parse.urlparse(file).path)
            img = Image.open(file).convert("RGB")
        except Exception:
            img = None
        hit = any(where == m or where.startswith(m) for m in mark)
        cap = (f"{'⚠ ' if hit else ''}{where}\n글: {text.replace(chr(10), ' ')[:60]}\nshows: {p.get('shows', '(없음)')[:40]}"
               f"\n출처·조건: {(p.get('rights') or p.get('url', ''))[:40]}")
        tiles.append(tile(img, cap, mark=hit))
    pick = spec.get("voice_pick") or {}
    if pick and not header:  # 고른 목소리와 까닭을 시트 맨 위에 (2026-10-28)
        header = f"목소리: {pick.get('mode', '')} · {', '.join(pick.get('voices', []))}\n고른 까닭: {pick.get('why', '')}"
    grid(tiles, header=header).save(out, quality=82)
    return sheet_hash(spec), len(tiles)


def media_sheet(files, out, every=2.4):
    """완성된 영상(mp4)은 장면을 일정 간격으로, 카드 그림(jpg)은 그대로 한 줄로."""
    tiles = []
    for f in files:
        f = Path(f)
        if f.suffix.lower() == ".mp4":
            import imageio_ffmpeg
            import subprocess
            import tempfile
            tmp = Path(tempfile.mkdtemp())
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(f), "-vf", f"fps=1/{every}", str(tmp / "f%03d.jpg")], check=True)
            for n, fr in enumerate(sorted(tmp.glob("f*.jpg"))):
                tiles.append(tile(Image.open(fr).convert("RGB"), f"{f.name} {n * every:.0f}초", 270, 480))
        else:
            tiles.append(tile(Image.open(f).convert("RGB"), f.name, 270, 340))
    grid(tiles, cols=8).save(out, quality=80)
    return len(tiles)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a and a[0] == "--media":
        n = media_sheet(a[1:-1], a[-1])
        print(f"완성본 시트 {a[-1]} ({n}칸). 열어 보고 글자 잘림·사진과 자막이 맞는지 확인하세요.")
        return
    h, n = spec_sheet(a[0], a[1])
    print(f"검수 시트 {a[1]} ({n}칸). 직접 열어 보고 칸마다 사진이 글과 같은 대상인지 확인한 뒤 review.photo_sheet 에 적어요: {h}")


if __name__ == "__main__":
    main()
