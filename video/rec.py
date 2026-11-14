# -*- coding: utf-8 -*-
"""추천 쇼츠 화면 (설계도 "format": "voice", "layout": "rec"). 2026-10-20 사용자가 정함:
큰 제목은 도입에서만 크게, 그 뒤에는 위쪽에 작게. 음식·행동 장면이 화면 가운데를 차지하고,
설명(순서·가격)은 장면 위에 짧게 얹어요. 자막은 의미 단위("subs")로 나누고, 장면은 대사·자막 조각에 맞춰 바꿔요.

  "intro": 1                      처음 몇 문장을 큰 제목 화면으로 보여 줄지(기본 1)
  "small": "작은 제목"            도입 뒤 위쪽 띠에 보일 제목(없으면 headline 을 한 줄로)
  문장: {"who": "A", "say": "읽을 말", "subs": ["자막 조각", ...], "show": 장면, "shows": [조각마다 장면 또는 null], "sfx": "pop"}
  장면: {"photo": {...}} · {"video": {...}} · {"product": {"img", "name", "price"}} · {"set": {"items": [...], "total", "note"}}
        · {"grid": [{"photo": {...}, "label": "수육"}, ...], "board": {"rows": [[이름, 값], ...], "total": [이름, 값], "note": "..."}}
        어느 장면이든 "tag": ["짧은 설명", ...](장면 위 왼쪽 위), "sfx": "pop"(그 장면이 나올 때)를 적을 수 있어요.
"""
import json
import re
from pathlib import Path

import numpy as np

HEAD_H = 150  # 도입 뒤 위쪽 작은 제목 띠
BOX_TOP, BOX_H = HEAD_H, 1290  # 음식 장면 칸
SUB_Y = 1450  # 자막 띠 가운데
BAND_ROOM = 18.5  # 흰 띠(745) 자막이 58px 로 한 줄에 들어가는 칸 수. 좌우 36px + 안쪽 34px 여백이라 내레이션 쇼츠(19칸)보다 조금 좁아요(2026-11-12 실측)

CSS = """
.rhead { position: absolute; left: 0; right: 0; top: 0; height: 150px; background: #17130F; display: flex; align-items: center; gap: 18px; padding: 0 40px; }
.rhead .rb { flex: none; font-weight: 900; font-size: 34px; color: #FFB23E; letter-spacing: -1px; }
.rhead .rt { font-weight: 900; font-size: 50px; color: #fff; letter-spacing: -2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rbg { position: absolute; left: 0; right: 0; top: 150px; bottom: 0; overflow: hidden; background: #0E0B09; }
.rbg img { width: 100%; height: 100%; object-fit: cover; }
.rbox { position: absolute; left: 0; right: 0; overflow: hidden; }
.rbox img.m { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.rbox.contain img.m { object-fit: contain; }
.rsub { position: absolute; left: 36px; right: 36px; display: flex; align-items: center; justify-content: center; gap: 18px; }
.rsub div { background: #fff; color: #111; font-weight: 900; font-size: 66px; letter-spacing: -2.5px; padding: 10px 34px 18px; border-radius: 22px;
            box-shadow: 0 8px 24px rgba(0,0,0,.35); text-align: center; line-height: 1.12; }
.rsub div .am { color: #D8432B; }
.rsub.flat div { background: none; box-shadow: none; border-radius: 0; padding: 0 0 8px; }
.rsub span.vwho { flex: none; padding: 4px 22px 9px; border-radius: 999px; color: #fff; font-weight: 900; font-size: 40px; letter-spacing: -1px;
                  box-shadow: 0 6px 16px rgba(0,0,0,.35); }
.rtag { position: absolute; left: 36px; display: flex; flex-direction: column; align-items: flex-start; gap: 12px; }
.rtag div { background: rgba(23,19,15,.86); color: #fff; font-weight: 900; font-size: 50px; letter-spacing: -1.5px; padding: 8px 26px 14px; border-radius: 16px;
            animation: rin .22s ease both; }
.rtag div:first-child { background: #D8432B; }
.rtag div:nth-child(2) { animation-delay: .12s; }
.rtag div:nth-child(3) { animation-delay: .24s; }
@keyframes rin { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
.rnote { position: absolute; right: 26px; padding: 6px 18px 9px; border-radius: 12px; background: rgba(0,0,0,.55); color: #fff; font-weight: 700; font-size: 30px; }
.rprod { position: absolute; left: 0; right: 0; background: #fff; }
.rprod img { position: absolute; left: 90px; right: 90px; top: 60px; height: 760px; width: 900px; object-fit: contain; }
.rprod .pn { position: absolute; left: 0; right: 0; top: 860px; text-align: center; font-weight: 900; font-size: 64px; letter-spacing: -2px; color: #1d1a16; }
.rprod .pp { position: absolute; left: 0; right: 0; top: 950px; text-align: center; font-weight: 900; font-size: 120px; letter-spacing: -4px; color: #D8432B;
             font-variant-numeric: tabular-nums; animation: rin .22s ease both; animation-delay: .1s; }
.rsrc { position: absolute; left: 40px; font-weight: 700; font-size: 28px; color: #8a7a64; }
.rset { position: absolute; left: 0; right: 0; background: #fff; }
.rset .items { position: absolute; left: 24px; right: 24px; top: 40px; display: flex; justify-content: space-around; }
.rset .it { width: 330px; display: flex; flex-direction: column; align-items: center; }
.rset .it img { width: 310px; height: 420px; object-fit: contain; }
.rset .it .n { margin-top: 10px; font-weight: 900; font-size: 40px; letter-spacing: -1.5px; color: #1d1a16; text-align: center; }
.rset .it .p { font-weight: 900; font-size: 54px; color: #1d1a16; font-variant-numeric: tabular-nums; }
.rset .tot { position: absolute; left: 60px; right: 60px; top: 700px; display: flex; justify-content: space-between; align-items: baseline; padding: 16px 34px 24px;
             border-radius: 26px; background: #1F2A1A; color: #fff; font-weight: 900; font-size: 64px; animation: rin .25s ease both; animation-delay: .2s; }
.rset .tot b { color: #FFB23E; font-size: 96px; letter-spacing: -3px; }
.rset .nt { position: absolute; left: 60px; right: 60px; top: 870px; text-align: right; font-weight: 900; font-size: 52px; color: #2E6B3A; animation: rin .25s ease both; animation-delay: .35s; }
.rset .items { flex-wrap: wrap; row-gap: 24px; }
.rset.many .it { width: 320px; }
.rset.many .it img { height: 300px; }
.rset.many .it .n { font-size: 36px; }
.rgrid .c.pd { background: #fff; display: flex; flex-direction: column; align-items: center; padding-top: 110px; }
.rgrid .c.pd img { position: static; width: 88%; height: 520px; object-fit: contain; }
.rgrid .c.pd .lp { position: static; margin-top: 30px; background: none; color: #D8432B; font-size: 92px; padding: 0; }
.rgrid.g4 { flex-wrap: wrap; }
.rgrid.g4 .c { flex: 0 0 calc(50% - 3px); height: calc(50% - 3px); }
.rgrid .c.dim img { filter: brightness(.38) saturate(.55); }
.rgrid .c.dim .lb { opacity: .55; }
.rgrid .c.on::after { content: ""; position: absolute; inset: 0; box-shadow: inset 0 0 0 12px #FFB23E; }
.rgrid .c .lb { z-index: 2; }
.rgrid .c.on img { animation: rzoom 2.4s ease-out both; }
.rgrid .c.on .lb { background: #D8432B; font-size: 58px; }
@keyframes rzoom { from { transform: scale(1); } to { transform: scale(1.07); } }
.rgrid .c .pz { position: absolute; inset: 0; animation: rpush var(--pd) ease-out both; animation-delay: var(--po); }
.rgrid .c .pz img.fg { object-fit: contain; }
.rgrid .c.on .pz img { animation: none; }
.rkeep .bpic img { animation: rpush var(--pd) ease-out both; }
@keyframes rpush { from { transform: scale(1); } to { transform: scale(var(--ps)); } }
.rwhite { position: absolute; left: 0; right: 0; bottom: 0; background: #fff; }
.rgrid { position: absolute; left: 0; right: 0; display: flex; gap: 6px; background: #0E0B09; }
.rgrid.col { flex-direction: column; }
.rgrid .c { position: relative; flex: 1; overflow: hidden; }
.rgrid .c img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.rgrid .c .lb { position: absolute; left: 26px; top: 22px; background: rgba(23,19,15,.86); color: #fff; font-weight: 900; font-size: 46px; padding: 6px 22px 12px;
                border-radius: 14px; letter-spacing: -1.5px; }
.rgrid .c .lp { position: absolute; left: 26px; bottom: 24px; background: #fff; color: #D8432B; font-weight: 900; font-size: 64px; padding: 4px 22px 12px;
                border-radius: 14px; letter-spacing: -2px; }
.rboard { position: absolute; left: 50px; right: 50px; background: rgba(23,19,15,.9); border-radius: 30px; padding: 26px 40px 30px; color: #fff;
          animation: rin .25s ease both; }
.rboard .r { display: flex; justify-content: space-between; font-weight: 800; font-size: 50px; padding: 8px 0; letter-spacing: -1.5px;
             animation: rin .22s ease both; }
.rboard .r b { font-variant-numeric: tabular-nums; }
.rboard .t { display: flex; justify-content: space-between; align-items: baseline; margin-top: 12px; padding-top: 16px; border-top: 4px solid #FFB23E;
             font-weight: 900; font-size: 60px; animation: rin .22s ease both; }
.rboard .t b { color: #FFB23E; font-size: 84px; letter-spacing: -3px; }
.rboard .x { margin-top: 10px; font-weight: 800; font-size: 40px; color: #FFD9A0; animation: rin .22s ease both; }
"""

UNITS = ("원", "만", "천", "개", "명", "그램", "킬로", "g", "kg", "분", "인분", "팩", "공기", "%")


def product_img(B, url):
    """회사 상품 이미지(흰 바탕, 작은 것도 있어요)를 흰 바탕에 얹고 여백을 잘라 키워요. 파일 주소."""
    import hashlib
    import io
    from PIL import Image, ImageChops
    path = B.CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + "-prod.png")
    if not path.exists():
        B.CACHE.mkdir(parents=True, exist_ok=True)
        im = Image.open(io.BytesIO(B.read_source(url))).convert("RGBA")
        white = Image.new("RGBA", im.size, "white")
        white.alpha_composite(im)
        im = white.convert("RGB")
        ink = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L").point(lambda v: 255 if v > 18 else 0)
        im = im.crop(ink.getbbox() or (0, 0, *im.size))
        k = 900 / max(im.size)
        if k > 1:  # 작으면 키워요 (회사가 올린 그림이 370px 인 것도 있어요)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im.save(path)
    return path.as_uri()


def _sub_parts(line):
    import voice
    return line.get("subs") or voice.chunks(line["say"])


def _runs(rms, limit, least):
    """조용한 구간 [(가운데 초, 가장 조용한 값)] — rms 가 limit 아래로 least 칸(20ms) 넘게 이어진 곳. 문장 앞뒤는 빼요."""
    out, k, n = [], 0, len(rms)
    while k < n:
        if rms[k] < limit:
            j = k
            while j < n and rms[j] < limit:
                j += 1
            if j - k >= least and k > 0 and j < n:
                out.append(((k + j) / 2 * 0.02, float(rms[k:j].min())))
            k = j
        else:
            k += 1
    return out


def _snap(v, rough, window=0.25, comma=False):
    """자막 조각이 바뀌는 때를 목소리가 쉬는 곳으로 옮겨요. (옮긴 때, 옮긴 거리)
    쉼표로 끝나는 조각은 0.5초 안에서 가장 깊은 쉼, 아니면 가장 가까운 쉼, 그것도 없으면 0.25초 안에서 가장 조용한 곳."""
    sr, f = 44100, 882
    n = len(v) // f
    if n < 5:
        return rough, 0.0
    rms = np.sqrt(np.mean(v[: n * f].reshape(n, f) ** 2, axis=1))
    rms = rms / (rms.max() + 1e-9)
    if comma:  # 쉼표·마침표로 끝나는 조각: 0.5초 안에서 가장 깊게 쉬는 곳(60ms 넘게)
        near = [r for r in _runs(rms, 0.12, 3) if abs(r[0] - rough) <= 0.5]
        if near:
            t = min(near, key=lambda r: (round(r[1], 2), abs(r[0] - rough)))[0]
            return t, t - rough
    near = [r[0] for r in _runs(rms, 0.05, 2) if abs(r[0] - rough) <= 0.5]  # 그 밖에는 가장 가까운 쉼(40ms 넘게)
    if near:
        t = min(near, key=lambda t: abs(t - rough))
        return t, t - rough
    lo, hi = max(0, int((rough - window) / 0.02)), min(n, int((rough + window) / 0.02) + 1)
    if hi - lo < 3:
        return rough, 0.0
    times = (np.arange(lo, hi) + 0.5) * 0.02
    score = rms[lo:hi] + 0.1 * np.abs(times - rough) / window
    t = float(times[int(np.argmin(score))])
    return t, t - rough


def sub_times(line, voice_arr, said, measure=None):
    """문장의 자막 조각마다 (시작, 끝) — 문장 시작에서 잰 초. 그리고 옮긴 거리 목록.
    measure(글)가 있으면 조각마다 따로 읽힌 길이의 비율로 나누고(글자 수보다 정확해요), 목소리가 쉬는 곳에 맞춰요."""
    import voice as V
    from build import units
    parts = _sub_parts(line)
    w = [units(p) + 1 for p in parts]
    audio = [measure(V.spoken({"say": p})) for p in parts] if measure and len(parts) > 1 else []
    if audio and all(a is not None for a in audio):
        w = [len(a) for a in audio]
    edges, moved = [0.0], []
    # 2026-11-08: 조각마다 따로 읽은 소리를 문장 소리에 맞춰(DTW) 다음 조각이 실제로 들리기 시작하는 때를 찾고, 그 0.1초 전 가장 조용한 때에 바꿔요.
    # 맞추지 못하면 예전처럼 길이 비율로 어림해 가까운 쉼으로 옮겨요.
    onsets = V.align_phrases(voice_arr, audio) if voice_arr is not None and audio and all(a is not None for a in audio) else None
    for k in range(1, len(parts)):
        rough = said * sum(w[:k]) / sum(w)
        if onsets and onsets[k - 1] is not None:
            t = V.settle(voice_arr, onsets[k - 1] - V.SUB_LEAD)
            moved.append(t - rough)
        elif voice_arr is not None:  # 따로 읽힌 길이로 어림한 곳에서 가장 가까운 말 사이 쉬는 곳으로
            t, d = _snap(voice_arr, rough, 0.25, comma=bool(re.search(r"[,.?!]\]*$", parts[k - 1].strip())))
            moved.append(d)
        else:
            t = rough
        edges.append(max(edges[-1] + 0.3, t))
    edges.append(said)
    return parts, list(zip(edges[:-1], edges[1:])), moved


def _fit(B, photo):
    """사진을 칸에 꽉 채울지(가로세로가 비슷하면) 통째로 보일지(아주 가로로 길면)."""
    if isinstance(photo, dict) and photo.get("fit") in ("contain", "cover"):
        return photo["fit"]
    B.fetch_photo(photo)
    w, h = B.SIZES[B.photo_key(photo)]
    return "contain" if w / h > 1.3 else "cover"


PUSH_THUMB = 1.12  # 첫 화면(썸네일과 같은 화면) 사진이 끝날 때까지 다가가는 크기


def _cover_scale(B, photo, vis, h):
    """칸 안에 통째로 보이는 크기에서 칸을 꽉 채우는 크기까지 몇 배인지."""
    w_i, h_i = B.SIZES[B.photo_key(photo)]
    n = len(vis["grid"])
    if vis.get("dir") == "2x2":
        cw, ch = (1080 - 6) / 2, (h - 6) / 2
    elif vis.get("dir", "col") == "col":
        cw, ch = 1080, (h - 6 * (n - 1)) / n
    else:
        cw, ch = (1080 - 6 * (n - 1)) / n, h
    return max(cw / w_i, ch / h_i) / min(cw / w_i, ch / h_i)


def vis_html(B, vis, top, h, dur, note):
    """장면 하나의 HTML (칸 위치 top, 높이 h)."""
    out = []
    if vis.get("photo"):
        p = vis["photo"]
        src, pos = B.fetch_photo(p)
        fit = _fit(B, p)
        out.append(f'<div class="rbg" style="top:{top}px"><img src="{B.backdrop(p)}"></div>')  # 칸 아래 빈 곳도 같은 사진을 흐리게
        out.append(f'<div class="rbox{" contain" if fit == "contain" else ""}" style="top:{top}px;height:{h}px"><img class="m" src="{src}" style="object-position:{pos}"></div>')
    elif vis.get("video"):
        v = vis["video"]
        # "zoom": 1.7, "origin": "65% 90%" — 영상 속 행동(팬 등)이 작게 찍혔을 때 그 부분을 키워요
        zoom = f';transform:scale({v["zoom"]});transform-origin:{v.get("origin", "50% 50%")}' if v.get("zoom") else ""
        if B.EXTRACT:
            first, folder, count, _ = B.clip(v, dur)
            out.append(f'<div class="rbg" style="top:{top}px"><img src="{first}" style="filter:blur(28px) brightness(.5);transform:scale(1.15)"></div>'
                       f'<div class="rbox" style="top:{top}px;height:{h}px"><img class="m vf" src="{first}" data-frames="{folder}" '
                       f'data-n="{count}" data-fps="{B.FPS}" style="object-position:{v.get("pos", "50% 50%")}{zoom}"></div>')
        else:
            out.append(f'<div class="rbox" style="top:{top}px;height:{h}px"></div>')
    elif vis.get("product"):
        p = vis["product"]
        out.append(f'<div class="rprod" style="top:{top}px;height:{1920 - top}px"><img src="{product_img(B, p["img"])}">'
                   f'<div class="pn">{B.esc(p["name"])}</div><div class="pp">{B.esc(p["price"])}</div>'
                   + (f'<div class="rsrc" style="top:1120px">{B.esc(p["src"])}</div>' if p.get("src") else "") + "</div>")
    elif vis.get("set"):
        s = vis["set"]
        items = "".join(f'<div class="it"><img src="{product_img(B, it["img"])}"><div class="n">{B.esc(it["name"])}</div>'
                        f'<div class="p">{B.esc(it.get("price", ""))}</div></div>' for it in s["items"])
        tot = f'<div class="tot"><span>{B.esc(s["total"][0])}</span><b>{B.esc(s["total"][1])}</b></div>' if s.get("total") else ""
        nt = f'<div class="nt">{B.esc(s["note"])}</div>' if s.get("note") else ""
        src = f'<div class="rsrc" style="top:1000px">{B.esc(s["src"])}</div>' if s.get("src") else ""
        many = " many" if len(s["items"]) > 3 else ""
        out.append(f'<div class="rset{many}" style="top:{top}px;height:{1920 - top}px"><div class="items">{items}</div>{tot}{nt}{src}</div>')
    elif vis.get("grid"):
        cells = []
        hl = vis.get("hl")  # 2×2 에서 지금 말하는 음식만 밝게(나머지는 어둡게)
        for k, c in enumerate(vis["grid"]):
            if c.get("photo") and vis.get("_push"):  # 통째로 보이다가 천천히 다가가요 (2026-10-21 사용자)
                src, pos = B.fetch_photo(c["photo"])
                off, total = vis["_push"]
                img = (f'<div class="pz" style="--pd:{total:.2f}s;--po:-{off:.2f}s;--ps:{_cover_scale(B, c["photo"], vis, h):.3f}">'
                       f'<img src="{B.backdrop(c["photo"])}"><img class="fg" src="{src}"></div>')
            elif c.get("photo"):
                src, pos = B.fetch_photo(c["photo"])
                img = f'<img src="{src}" style="object-position:{pos}">'
            else:
                img = f'<img src="{product_img(B, c["img"])}" style="object-fit:contain;background:#fff">'
            if not c.get("photo"):  # 상품 칸: 이름표 · 상품 · 값을 위에서 아래로
                img = f'<img src="{product_img(B, c["img"])}">'
            mark = "" if hl is None else (" on" if k == hl else " dim")
            cells.append(f'<div class="c{"" if c.get("photo") else " pd"}{mark}">{img}' + (f'<div class="lb">{B.esc(c["label"])}</div>' if c.get("label") else "")
                         + (f'<div class="lp">{B.esc(c["price"])}</div>' if c.get("price") else "") + "</div>")
        first = vis["grid"][0]
        if first.get("photo"):
            out.append(f'<div class="rbg" style="top:{top}px"><img src="{B.backdrop(first["photo"])}"></div>')
        else:
            out.append(f'<div class="rwhite" style="top:{top}px"></div>')
        kind = {"col": " col", "2x2": " g4"}.get(vis.get("dir", "col"), "")
        out.append(f'<div class="rgrid{kind}" style="top:{top}px;height:{h}px">{"".join(cells)}</div>')
        if vis.get("board"):
            bd = vis["board"]
            rows = "".join(f'<div class="r" style="animation-delay:{0.15 + 0.18 * k:.2f}s"><span>{B.esc(a)}</span><b>{B.esc(b)}</b></div>'
                           for k, (a, b) in enumerate(bd.get("rows", [])))
            last = 0.15 + 0.18 * len(bd.get("rows", []))
            tot = (f'<div class="t" style="animation-delay:{last:.2f}s"><span>{B.esc(bd["total"][0])}</span><b>{B.esc(bd["total"][1])}</b></div>'
                   if bd.get("total") else "")
            x = f'<div class="x" style="animation-delay:{last + 0.2:.2f}s">{B.esc(bd["note"])}</div>' if bd.get("note") else ""
            out.append(f'<div class="rboard" style="top:{top + bd.get("y", 520)}px">{rows}{tot}{x}</div>')
    if vis.get("tag"):
        out.append(f'<div class="rtag" style="top:{top + 34}px">' + "".join(f"<div>{B.rich(t)}</div>" for t in vis["tag"]) + "</div>")
    if note and (vis.get("photo") or vis.get("video") or vis.get("grid")) and not vis.get("own"):
        out.append(f'<div class="rnote" style="top:{top + h - 64}px">{B.esc(note)}</div>')
    return "".join(out)


def build_rec(spec, voices, speech, durs, starts, real):
    """voice.build_voice 가 목소리를 만든 뒤 불러요. (HTML 조각 목록, 장면 바뀌는 때 목록, 효과음, 자막 기록)"""
    import build as B
    import thumb
    import voice as V

    lines = spec["lines"]
    intro = int(spec.get("intro", 1))
    body = sum(durs)
    name = json.loads((V.ROOT / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
    note = spec.get("photo_note", "")
    # 1) 자막 조각과 그때 바뀌는 장면
    events, subs, sfx = [], [], []
    for i, l in enumerate(lines):
        c = V.who_of(spec, l) or spec.get("narrator") or {}

        def measure(text, c=c, l=l):
            v = V.tts(text, c.get("voice"), l.get("rate") or c.get("rate"))
            if v is not None and spec.get("cast") and len(v):  # 문장 소리와 같은 크기로 맞춰요
                v = v * min(V.LOUD / max(1e-9, np.sqrt(np.mean(v ** 2))), 0.98 / max(1e-9, np.abs(v).max()))
            return v
        parts, spans, moved = sub_times(l, voices[i] if real else None, speech[i], measure if real else None)
        shows = l.get("shows") or ([l["show"]] if l.get("show") else [])
        for k, (p, (a, b)) in enumerate(zip(parts, spans)):
            t0 = starts[i] + a
            t1 = starts[i] + (b if k < len(parts) - 1 else durs[i])
            subs.append({"line": i, "k": k, "text": p, "at": t0, "end": t1, "moved": moved[k - 1] if k and moved else 0.0, "who": l.get("who")})
            vis = shows[k] if k < len(shows) else None
            if vis:
                events.append((t0, i, vis))
                if vis.get("sfx"):
                    sfx.append((round(t0, 2), vis["sfx"]))
        if l.get("sfx"):
            sfx.append((round(starts[i], 2), l["sfx"]))
    events.sort(key=lambda e: e[0])
    # 도입이 끝나는 때 새 장면이 없으면, 이어지던 장면을 본문 자리(큰 칸)로 다시 놓아요
    if intro < len(lines) and events and not any(i == intro and abs(t - starts[intro]) < 0.01 for t, i, _ in events):
        before = [e for e in events if e[0] < starts[intro]]
        if before:
            events.append((starts[intro], intro, {k: v for k, v in before[-1][2].items() if k != "sfx"}))
            events.sort(key=lambda e: e[0])
    out = []
    cuts = []
    # 음식 사진 칸은 처음엔 통째로 보이다가 끝날 때까지 천천히 다가가요. 장면이 바뀌어도 이어지게 첫 칸 장면부터 시간을 재요 (2026-10-21 사용자)
    g0 = next((t for t, _, v in events if v.get("grid") and any(c.get("photo") for c in v["grid"])), None)
    for n, (t, i, vis) in enumerate(events):
        end = events[n + 1][0] if n + 1 < len(events) else body
        d = end - t
        if g0 is not None and vis.get("grid") and not spec.get("no_push"):
            vis = {**vis, "_push": (t - g0, body - g0)}
        if vis.get("thumb"):  # 썸네일과 똑같은 첫 화면(큰 제목 + 흰 띠 + 사진). 모양은 thumb.KEEP_CSS(확정 시안)
            push = "" if spec.get("no_push") else f' style="--pd:{d + 0.5:.2f}s;--ps:{PUSH_THUMB}"'
            html = f'<div class="rkeep"{push}>{thumb.body(spec)}</div><style>{thumb.KEEP_CSS}</style>'
        elif i < intro:  # 도입: 예전처럼 큰 제목(0~680) + 자막 띠(680~810) + 그 아래 장면
            strip = '<div class="bstrip"><div></div></div>' if any(v.get("thumb") for _, _, v in events) else ""  # 썸네일의 흰 띠를 그대로
            html = vis_html(B, vis, 810, 1110, d, note) + strip
        else:
            html = vis_html(B, vis, BOX_TOP, BOX_H, d, note)
        fade = float(vis.get("fade", 0.12))  # 이 장면이 나타나는 데 걸리는 초. 앞 장면은 그동안 밑에 남아요
        nxt = float(events[n + 1][2].get("fade", 0)) if n + 1 < len(events) else 0
        anim = f' style="animation:in-fade {fade:.2f}s ease both"' if n else ""
        out.append(f'<section class="scene{" first" if not n else ""}" data-at="{t:.2f}" data-dur="{d:.2f}" data-out="{nxt:.2f}"{anim}>{html}</section>')
        cuts.append({"at": round(t, 2), "dur": round(d, 2), "line": i + 1, "kind": next((k for k in ("photo", "video", "product", "set", "grid", "thumb") if vis.get(k)), "?")})
    # 2) 제목: 도입 동안 크게, 그 뒤엔 위쪽 띠에 작게
    head = spec.get("headline", spec.get("title", ""))
    t_small = starts[intro] if intro < len(lines) else body
    out.append(f'<section class="scene" data-at="0" data-dur="{t_small:.2f}" data-out="0">'
               f'{thumb.head_html(head, name, (spec.get("thumb") or {}).get("color", thumb.AC))}</section>')
    small = spec.get("small") or " ".join(head.replace("[[", "").replace("]]", "").split())
    out.append(f'<section class="scene" data-at="{t_small:.2f}" data-dur="{body - t_small:.2f}" data-out="0">'
               f'<div class="rhead"><span class="rb">{B.esc(name)}</span><span class="rt">{B.esc(small)}</span></div></section>')
    # 3) 자막
    for s in subs:
        if lines[s["line"]].get("nosub"):  # 제목이 곧 그 말일 때(썸네일과 같은 첫 화면) 자막을 따로 띄우지 않아요
            continue
        c = V.who_of(spec, lines[s["line"]])
        # 진행·설명 짝(duo)처럼 cast 에 label 이 없으면 이름표 없이 목소리만 바꿔요 (voice.py 와 같게, 2026-10-28)
        tag = f'<span class="vwho" style="background:{c.get("color", "#333")}">{B.esc(c["label"])}</span>' if c and c.get("label") else ""
        # 745 는 흰 띠 위라서 상자 없이 글자만 (2026-10-21 사용자: 테두리 빼). 띠 자막은 내레이션 쇼츠와 같은 58px(V.BAND_PX, 2026-11-12)
        y = 745 if s["line"] < intro else SUB_Y
        px = V.BAND_PX if y == 745 else V.sub_size(s["text"], 66)  # f-문자열 밖에서 정해요(클라우드 Python 3.11 은 f'' 안의 '' 를 못 읽어요)
        out.append(f'<section class="scene" data-at="{s["at"]:.2f}" data-dur="{max(0.05, s["end"] - s["at"]):.2f}" data-out="0">'
                   f'<div class="rsub{" flat" if y == 745 else ""}" style="top:{y - 60}px;height:120px">{tag}<div style="font-size:{px}px">{B.rich(s["text"])}</div></div></section>')
    return out, cuts, sfx, subs


BROAD = {"찌개", "탕·국", "국수", "전골·샤브", "볶음밥·쌀요리", "덮밥", "회", "국밥", "해물찜", "조개", "굴", "전·부침", "생선구이·조림",
         "소불고기·갈비", "돼지구이", "백반·정식", "도시락", "샐러드·볼", "수프", "죽"}


def _plain_key(s):
    return re.sub(r"[\s·\-()\[\]]", "", s or "")


def dinner_photo_problems(spec):
    """저녁 추천 4칸 사진이 정말 그 메뉴인지 (2026-11-12 사용자: 영어로 찾은 비슷한 다른 음식 사진이 저절로 쓰이지 않게).
    보관함(vault:)·한국관광공사 사진은 예전 그대로 두고, 그 밖의 바깥 사진(Unsplash·Pexels·위키미디어·오픈버스 등)은
    눈으로 확인한 shows 에 그 칸의 메뉴 이름(사전의 aka 도 됨)이 있어야 해요. 없으면 '꼭 고칠 것' → 매일 실행이 고치고,
    그래도 남으면 gate 가 '승인 전 시안'으로 보내요(제작은 멈추지 않아요)."""
    out = []
    lines = spec.get("lines") or []
    grid = next((l["show"]["grid"] for l in lines if isinstance(l.get("show"), dict) and l["show"].get("grid")), None)
    if not grid:
        return out
    picked = (spec.get("menu_pick") or {}).get("menus") or []
    names = {}
    for k in range(len(grid)):
        if k < len(picked):
            names[k] = picked[k]
            continue
        say = next((l.get("say", "") for l in lines if isinstance(l.get("show"), dict) and l["show"].get("hl") == k), "")
        names[k] = re.sub(r"[.!?~]", "", say.split(",")[-1]).strip() if say else ""
    try:
        menu = json.loads((Path(__file__).resolve().parent.parent / "ideas" / "dinner_menu.json").read_text(encoding="utf-8"))["items"]
    except Exception:
        menu = []

    def keys(name):
        n = _plain_key(name)
        out_ = {n} if n else set()
        for x in menu:
            ks = [_plain_key(a) for a in [x["name"], *x.get("aka", [])]]
            if any(kk and kk in n for kk in ks):  # '얼큰한 순대국밥' → 순대국밥·순댓국
                out_.update(kk for kk in ks if kk)
        return out_

    try:  # 보관함 사진마다 사용자가 붙인 메모(note). 보관함이 없는 곳(깃허브 작업)에서는 이 대조만 건너뛰어요
        vault = {"vault:" + x["file"]: x.get("note") or "" for x in json.loads(
            (Path(__file__).resolve().parent.parent.parent / "jecheol-photos" / "index.json").read_text(encoding="utf-8")) if x.get("file")}
    except Exception:
        vault = {}

    def family(text):
        """그 말이 가리키는 메뉴 계열. 사전 이름이 들어 있으면 그 메뉴의 계열, 아니면 이름으로 어림(scripts/dinner_pick.py)."""
        n = _plain_key(text)
        if any(w in n for w in ("닭다리", "후라이드", "프라이드")):
            return "치킨"
        best = None
        for x in menu:
            for a in [x["name"], *x.get("aka", [])]:
                kk = _plain_key(a)
                if kk and kk in n and (best is None or len(kk) > best[0]):
                    best = (len(kk), x.get("family"))
        if best:
            return best[1]
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
            import dinner_pick
            return dinner_pick.family_of(text)
        except Exception:
            return None

    def same_family(name, note):
        """짜장면 ↔ '중식 세트(짜장·짬뽕·탕수육)', 까르보나라 ↔ 크림 파스타처럼 같은 좁은 계열이면 같은 음식으로 봐요.
        찌개·탕·국수·전골처럼 넓은 계열은 부대찌개 ↔ 김치찌개가 다른 음식이라 같다고 보지 않아요."""
        fa = family(name)
        if not fa or fa in BROAD:
            return False
        # 메모에 여러 음식이 적혀 있으면('짜장·짬뽕·탕수육') 하나씩 봐요
        parts = [p for p in re.split(r"[·,()\s/]+", note or "") if p] + [note]
        return any(family(p) == fa for p in parts)

    for k, cell in enumerate(grid):
        ph = (cell or {}).get("photo") or {}
        url = str(ph.get("url") or "")
        if url.startswith("vault:"):
            # 2026-11-12 사용자: 보관함 사진도 실제 음식과 다르면 안 돼요. shows 는 우리가 적는 말이라 틀릴 수 있어서,
            # 사용자가 직접 붙인 메모와 메뉴 이름을 맞춰 봐요('라면 끓이는 모습' 사진을 짬뽕 칸에 넣으면 막아요)
            note, ks = vault.get(url), keys(names.get(k, ""))
            if note and ks and not any(kk in _plain_key(note) for kk in ks) and not same_family(names.get(k, ""), note):
                out.append(f"4칸 중 {k + 1}번 칸('{names.get(k, '')}') 보관함 사진의 메모는 '{note[:30]}' 이에요. 메뉴와 다른 음식일 수 있어요. "
                           "그 메뉴 사진으로 바꾸거나, 사진이 맞으면 메뉴를 사진에 맞춰요.")
            continue
        if not url or "visitkorea.or.kr" in url:
            continue
        shows = _plain_key(ph.get("shows"))
        ks = keys(names.get(k, ""))
        eng = ph.get("query") and not re.search(r"[가-힣]", str(ph["query"]))
        where = f"4칸 중 {k + 1}번 칸('{names.get(k, '')}') 사진"
        if not shows:
            out.append(f"{where}에 shows(사진에 실제로 찍힌 것)가 없어요. 사진을 열어 보고 그 메뉴가 맞는지 적어 주세요"
                       + ("(영어 검색으로 찾은 사진이에요)" if eng else "") + ". 맞는 사진이 없으면 다른 사진이나 다른 후보 메뉴로 바꿔요.")
        elif ks and not any(kk in shows for kk in ks):
            out.append(f"{where}의 shows('{ph.get('shows')}')에 메뉴 이름이 없어요. 비슷한 다른 음식 사진일 수 있어요"
                       + ("(영어 검색으로 찾은 사진)" if eng else "") + ". 그 메뉴가 맞으면 shows 에 이름을 적고, 아니면 사진이나 메뉴를 바꿔요.")
    return out


def _spec_day(spec):
    from datetime import date, datetime, timedelta, timezone
    d = spec.get("_day") or (spec.get("dates") or {}).get("checked")
    try:
        return date.fromisoformat(str(d)[:10])
    except Exception:
        return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _recent_dinners(day, days=7):
    """day 앞 days 일의 저녁 추천 설계도 [(날짜, spec)]."""
    from datetime import timedelta
    out = []
    root = Path(__file__).resolve().parent.parent / "videos"
    for k in range(1, days + 1):
        f = root / (day - timedelta(days=k)).isoformat() / "3-dinner.json"
        try:
            out.append(((day - timedelta(days=k)).isoformat(), json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            pass
    return out


def _plain(t):
    return re.sub(r"\[\[|\]\]", "", str(t or "")).strip()


DINNER_END = re.compile(r"[.!?~…\s]+$")


def dinner_script_problems(spec):
    """메뉴 소개 문장이 같은 틀로 되풀이되지 않는지 (2026-11-13 사용자: '○○ 당기면 이거!'만 반복하면 AI가 기계적으로 추천하는 느낌).
    메뉴 문장(hl 이 있는 문장)끼리 ① '당기면' 두 번 넘게 ② 끝 어미(마지막 두 글자) 겹침 ③ 쉼표 앞 말 겹침 → 꼭 고칠 것.
    ④ 첫 낱말 겹침 ⑤ 네 문장이 모두 같은 꼴(물음만·마침표만) → 보면 좋은 것. ⑥ 메뉴 이름이 그 문장에 없으면 꼭 고칠 것."""
    must, should = [], []
    lines = spec.get("lines") or []
    menu = [(l["show"]["hl"], l) for l in lines if isinstance(l.get("show"), dict) and isinstance(l["show"].get("hl"), int)]
    if len(menu) < 2:
        return must, should
    says = [(k, _plain(l.get("say"))) for k, l in menu]
    if sum(t.count("당기면") for _, t in says) >= 2:
        must.append("메뉴 문장에 '당기면'이 두 번 넘게 나와요. 메뉴마다 맛·식감·조리 장면·함께 먹는 사람·계절·분위기 가운데 다른 것으로 소개해요.")
    ends, fronts, firsts, kinds = {}, {}, {}, set()
    for k, t in says:
        last = re.split(r"(?<=[.!?])\s+", t.strip())[-1]
        tail = re.sub(r"[^가-힣]", "", DINNER_END.sub("", last))[-2:]
        ends.setdefault(tail, []).append(k)
        if "," in t:
            fw = t.split(",")[0].split()[-1:]
            if fw:
                fronts.setdefault(fw[0], []).append(k)
        first = t.split()[0] if t.split() else ""
        firsts.setdefault(re.sub(r"[^가-힣A-Za-z0-9]", "", first), []).append(k)
        kinds.add(t.strip()[-1:] if t.strip()[-1:] in "?!" else ".")
    for tail, ks in ends.items():
        if tail and len(ks) >= 2:
            must.append(f"메뉴 문장 {len(ks)}개가 같은 어미 '~{tail}'로 끝나요(칸 {', '.join(str(x + 1) for x in ks)}). 물음·감탄·권유·짧은 한마디로 끝을 바꿔요.")
    for w, ks in fronts.items():
        if len(ks) >= 2:
            must.append(f"메뉴 문장 {len(ks)}개가 '… {w},' 같은 틀이에요(칸 {', '.join(str(x + 1) for x in ks)}). 문장 짜임을 다르게 써요.")
    for w, ks in firsts.items():
        if w and len(ks) >= 2:
            should.append(f"메뉴 문장 {len(ks)}개가 '{w}'(으)로 시작해요. 시작을 바꾸면 덜 기계적으로 들려요.")
    if len(kinds) == 1 and len(says) >= 3:
        should.append("메뉴 문장이 모두 같은 꼴(물음·감탄·평서 중 하나)이에요. 섞어 주세요.")
    if len(lines) >= 3:  # 여는 말(2번)·끝 물음(마지막)이 지난 사흘과 같으면 날마다 같은 영상처럼 들려요
        for d, past in _recent_dinners(_spec_day(spec), 3):
            pl = past.get("lines") or []
            if len(pl) >= 3:
                for name, a_, b_ in (("2번 문장", lines[1], pl[1]), ("마지막 문장", lines[-1], pl[-1])):
                    if _plain(a_.get("say")) == _plain(b_.get("say")):
                        should.append(f"{name} '{_plain(a_.get('say'))}'이 {d} 저녁과 같아요. 날마다 말을 바꿔요.")
    for k, l in menu:  # 줄임 조사('불금엔', '주말엔')는 TTS 가 뭉개요. 대사는 두고 read 칸에 풀어 써요(2026-11-13)
        hard = [w for w in re.findall(r"[가-힣]+(?:엔|겐|껜)(?=\s|[,.!?]|$)", _plain(l.get("say"))) if len(w) >= 2]
        if hard and not l.get("read"):
            must.append(f"{k + 1}번 칸 문장의 '{', '.join(hard)}' 는 TTS 가 뭉개기 쉬워요('불금엔→불구멘'). \"read\" 칸에 '…에는'처럼 풀어 써 주세요.")
    picked = (spec.get("menu_pick") or {}).get("menus") or []
    for k, t in says:
        if k < len(picked):
            name = re.sub(r"\s", "", picked[k])
            if name and name not in re.sub(r"\s", "", t) and name[-3:] not in re.sub(r"\s", "", t):
                must.append(f"{k + 1}번 칸 문장에 메뉴 이름 '{picked[k]}'이 없어요. 띠 자막으로 메뉴를 알 수 있게 이름을 넣어요.")
    return must, should


DINNER_HEAD2 = ("아직못골랐어?", "아직못골랐어", "내가골라줄게")  # 저녁 썸네일 둘째 줄은 이 둘만 (2026-11-14 사용자)


def dinner_thumb_problems(spec):
    """저녁 썸네일 문구 검사 (2026-11-14 사용자: "저번처럼 '토요일 저녁 아직 못 골랐어?' 아니면 '내가 골라 줄게'로").
    ① 두 줄 제목은 '{요일} 저녁' + '아직 못 골랐어?' 또는 '내가 골라 줄게' 만, 요일은 그날 요일
    ② 지난 7일 저녁 썸네일과 흰 띠 글이 같으면 꼭 고칠 것. (11-13의 '골라' 되풀이 금지는 11-14에 그만둠)"""
    import thumb
    must = list(thumb.grid_problems(spec))  # 4칸·2×2·빈칸 없음 (2026-11-13 사용자)
    t = spec.get("thumb") or {}
    head = _plain(t.get("head") or spec.get("headline"))
    sub = _plain(t.get("sub"))
    if not head:
        return must
    day = "월화수목금토일"[_spec_day(spec).weekday()] + "요일 저녁"
    rows = [re.sub(r"[\s,.!~]+$", "", r).strip() for r in head.split(chr(10))]
    if len(rows) != 2 or rows[0] != day or rows[1].replace(" ", "") not in DINNER_HEAD2:
        must.append(f"썸네일 제목 '{head.replace(chr(10), ' / ')}' → '{day} / 아직 못 골랐어?' 또는 '{day} / 내가 골라 줄게' 둘 중 하나로 써요"
                    f" (headline·thumb.head 같게, 1번 문장도 같은 말). 꾸밈말(불금·비 오는)은 흰 띠 글에 써요.")
    for d, past in _recent_dinners(_spec_day(spec)):
        pt = past.get("thumb") or {}
        if sub and sub == _plain(pt.get("sub")):
            must.append(f"썸네일 흰 띠 글 '{sub}'이 {d} 와 같아요. 이 영상에 맞는 말로 바꿔요.")
    seen, out = set(), []
    for m in must:  # 같은 말을 날마다 되풀이해 적지 않게
        k = m.split("(")[0][:30]
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out[:6]


def dinner_menu_problems(spec):
    """고른 메뉴가 최근 저녁 영상과 겹치는지·사진 때문에 골랐는지 (scripts/dinner_pick.py menu_problems, 2026-11-13)."""
    mp = spec.get("menu_pick") or {}
    if not mp.get("menus"):
        return [], []
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import dinner_pick
        return dinner_pick.menu_problems(mp["menus"], _spec_day(spec), mp.get("why"), mp.get("again"))
    except Exception as e:  # 검사 도구가 실패해도 제작은 멈추지 않아요
        return [], [f"메뉴 겹침 검사를 못 했어요: {e}"]


def problems(spec, cuts=None, subs=None):
    """추천 쇼츠 검사. 자막 조각(한 글자·숫자와 단위 끊김·서술어만 남음·너무 김), 장면이 없는 문장,
    한 장면이 오래 머무는지, 가격표·묶음 화면이 오래 머무는지. (꼭 고칠 것, 보면 좋은 것)"""
    from build import units
    must, should = [], []
    lines = spec.get("lines") or []
    for n, l in enumerate(lines, 1):
        parts = _sub_parts(l)
        shows = l.get("shows") or ([l["show"]] if l.get("show") else [])
        if n == 1 and not shows:
            must.append("1번 문장에 장면(show)이 없어요.")
        if l.get("shows") and len(l["shows"]) > len(parts):
            must.append(f"{n}번 문장: shows 가 자막 조각보다 많아요.")
        joined = "".join(p.replace(" ", "") for p in parts).replace("[[", "").replace("]]", "")
        said = l["say"].replace(" ", "").replace("[[", "").replace("]]", "")
        if l.get("subs") and joined != said:
            must.append(f"{n}번 문장: 자막 조각을 이어도 대사와 달라요. ({' / '.join(parts)})")
        for k, p in enumerate(parts):
            bare = p.replace("[[", "").replace("]]", "").strip()
            words = bare.split()
            if units(bare) <= 2.5:
                must.append(f"{n}번 문장: 자막 '{bare}' 이 한두 글자뿐이에요.")
            elif len(words) == 1 and len(parts) > 1 and re.fullmatch(r"\S{1,4}[요다죠야네까]\W*", bare):
                must.append(f"{n}번 문장: 자막 '{bare}' 이 서술어만 따로 나와요.")
            if n - 1 < int(spec.get("intro", 1)) and units(bare) > BAND_ROOM:  # 흰 띠 자막은 58px 고정이라 넘치면 두 줄이 돼요(2026-11-12)
                must.append(f"{n}번 문장: 흰 띠 자막 '{bare}' 이 58px 한 줄({BAND_ROOM}칸)보다 길어요({units(bare):.1f}칸). 글씨는 줄이지 않으니 subs 로 나누거나 줄여 주세요.")
            elif units(bare) > 15:
                should.append(f"{n}번 문장: 자막 '{bare}' 이 길어요({units(bare):.0f}칸). 한 화면에 13칸쯤이 읽기 좋아요.")
            if k + 1 < len(parts):  # 2026-11-08: 이어진 말('빠질 / 수 없는', '비벼 / 먹으면') 사이에서 나누지 않아요(직접 적은 subs 도)
                import voice as V
                why = V.bad_joint(parts[k], parts[k + 1])
                if why:
                    must.append(f"{n}번 문장: 자막이 '{bare[-8:]} / {V.plain(parts[k + 1])[:8]}' 로 나뉘어 {why}. 쉼표를 넣거나 subs 로 나눠 주세요.")
            if k + 1 < len(parts):
                nxt = parts[k + 1].replace("[[", "").strip()
                if re.search(r"[\d만천백]$", bare) or (nxt and any(nxt.startswith(u) for u in UNITS) and re.search(r"\d", bare.split()[-1])):
                    must.append(f"{n}번 문장: 숫자와 단위가 나뉘어요 ('{bare}' / '{nxt}').")
    if spec.get("kind") == "저녁":
        must += dinner_photo_problems(spec)
        for fn_ in (dinner_script_problems, dinner_menu_problems):
            m_, s_ = fn_(spec)
            must += m_
            should += s_
        must += dinner_thumb_problems(spec)
    for c in cuts or []:
        if c["kind"] in ("product", "set") and c["dur"] > 3.2:
            should.append(f"{c['at']:.1f}초 {c['kind']} 화면이 {c['dur']:.1f}초 머물러요. 3초 안쪽으로.")
        elif c["dur"] > 4.0 and c["kind"] != "video":  # 영상은 움직이니 길어도 멈춘 화면이 아니에요
            should.append(f"{c['at']:.1f}초 장면이 {c['dur']:.1f}초 바뀌지 않아요. 4초 안쪽으로 나눠 주세요.")
    return must, should
