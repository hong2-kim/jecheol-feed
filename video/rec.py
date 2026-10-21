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

import numpy as np

HEAD_H = 150  # 도입 뒤 위쪽 작은 제목 띠
BOX_TOP, BOX_H = HEAD_H, 1290  # 음식 장면 칸
SUB_Y = 1450  # 자막 띠 가운데

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
    for k in range(1, len(parts)):
        rough = said * sum(w[:k]) / sum(w)
        if voice_arr is not None:  # 따로 읽힌 길이로 어림한 곳에서 가장 가까운 말 사이 쉬는 곳으로
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
            if c.get("photo"):
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
    for n, (t, i, vis) in enumerate(events):
        end = events[n + 1][0] if n + 1 < len(events) else body
        d = end - t
        if vis.get("thumb"):  # 썸네일과 똑같은 첫 화면(큰 제목 + 흰 띠 + 사진). 모양은 thumb.KEEP_CSS(확정 시안)
            html = f'<div class="rkeep">{thumb.body(spec)}</div><style>{thumb.KEEP_CSS}</style>'
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
        tag = f'<span class="vwho" style="background:{c.get("color", "#333")}">{B.esc(c.get("label", s["who"]))}</span>' if c else ""
        y = 745 if s["line"] < intro else SUB_Y  # 745 는 흰 띠 위라서 상자 없이 글자만 (2026-10-21 사용자: 테두리 빼)
        out.append(f'<section class="scene" data-at="{s["at"]:.2f}" data-dur="{max(0.05, s["end"] - s["at"]):.2f}" data-out="0">'
                   f'<div class="rsub{" flat" if y == 745 else ""}" style="top:{y - 60}px;height:120px">{tag}<div style="font-size:{V.sub_size(s['text'], 66)}px">{B.rich(s["text"])}</div></div></section>')
    return out, cuts, sfx, subs


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
            if units(bare) > 15:
                should.append(f"{n}번 문장: 자막 '{bare}' 이 길어요({units(bare):.0f}칸). 한 화면에 13칸쯤이 읽기 좋아요.")
            if k + 1 < len(parts):
                nxt = parts[k + 1].replace("[[", "").strip()
                if re.search(r"[\d만천백]$", bare) or (nxt and any(nxt.startswith(u) for u in UNITS) and re.search(r"\d", bare.split()[-1])):
                    must.append(f"{n}번 문장: 숫자와 단위가 나뉘어요 ('{bare}' / '{nxt}').")
    for c in cuts or []:
        if c["kind"] in ("product", "set") and c["dur"] > 3.2:
            should.append(f"{c['at']:.1f}초 {c['kind']} 화면이 {c['dur']:.1f}초 머물러요. 3초 안쪽으로.")
        elif c["dur"] > 4.0 and c["kind"] != "video":  # 영상은 움직이니 길어도 멈춘 화면이 아니에요
            should.append(f"{c['at']:.1f}초 장면이 {c['dur']:.1f}초 바뀌지 않아요. 4초 안쪽으로 나눠 주세요.")
    return must, should
