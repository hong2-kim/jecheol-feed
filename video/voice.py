# -*- coding: utf-8 -*-
"""내레이션 쇼츠 (설계도 "format": "voice"). 2026-10-17 사용자가 '꿀꺽' 채널처럼 하루 한 편 만들자고 함.

  화면: 위쪽에 큰 제목 두 줄이 영상 내내 고정 → 그 아래 흰 띠에 지금 읽는 말(자막) → 그 아래 사진이 문장마다 바뀜
  소리: 채널 목소리(config.json 의 youtube.voice, 빠르기)로 문장마다 읽고, 오디오 보관함 곡을 작게 깔아요.
  길이: 문장을 읽는 시간만큼. 35~50초가 되게 대본을 써요(59초를 넘으면 안 돼요).

설계도:
  {"format": "voice", "kind": "해설", "headline": "결국 밝혀진\\n[[치킨 원가]]",
   "lines": [{"say": "읽을 문장", "photo": {...}, "chip": "사진 위 작은 글(없어도 됨)"}, ...], 그 밖은 다른 영상과 같아요}
"""
import base64
import hashlib
import json
import os
import urllib.request
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parent
SR = 44100
GAP = 0.12  # 문장 사이 쉼(초)
SHORTEST, LONGEST = 25.0, 59.0
CHUNK = 14  # 자막 한 번에 보여 줄 칸 수(한글 1칸)


def _key():
    k = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
    env = ROOT / ".env"
    if not k and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_TTS_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"')
    return k


def _voice_conf():
    yt = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("youtube") or {}
    return yt.get("voice", "ko-KR-Wavenet-A"), float(yt.get("speaking_rate", 1.3))


def tts(text):
    """문장 하나를 읽은 소리(모노, -1~1). 같은 문장은 build/tts 에 받아 둔 걸 다시 써요. 키가 없으면 None."""
    name, rate = _voice_conf()
    path = ROOT / "build" / "tts" / (hashlib.sha1(f"{name}|{rate}|{text}".encode()).hexdigest()[:16] + ".wav")
    if not path.exists():
        key = _key()
        if not key:
            return None
        body = {"input": {"text": text}, "voice": {"languageCode": "ko-KR", "name": name},
                "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": rate, "sampleRateHertz": SR}}
        req = urllib.request.Request(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        data = base64.b64decode(json.loads(urllib.request.urlopen(req, timeout=60).read())["audioContent"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with wave.open(str(path), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(axis=1)
    loud = np.nonzero(np.abs(x) > 0.02)[0]  # 앞뒤의 빈소리를 잘라 말이 바로 이어지게 해요
    if len(loud):
        x = x[max(0, loud[0] - int(SR * 0.03)): loud[-1] + int(SR * 0.08)]
    return x


def spoken(line):
    """목소리로 읽을 글. 자막(say)과 읽는 말이 달라야 하면 "read" 를 적어요.
    "4~5시"를 "네 시에서 오 시"로 잘못 읽어서(2026-10-17), 범위(~)는 "4시에서 5시"처럼 풀어 읽혀요."""
    import re
    text = line.get("read") or line["say"]
    text = text.replace("[[", "").replace("]]", "")
    # 4~5시, 7,500~9,000원, 3~4개 → 4시에서 5시, 7,500원에서 9,000원, 3개에서 4개
    text = re.sub(r"(\d[\d,.]*)\s*[~∼-]\s*(\d[\d,.]*)\s*(시|원|개|분|명|곳|도|%|kg|g|만 원|천 원)", r"\1\3에서 \2\3", text)
    # 시각은 우리말 수로: 5시 → 다섯 시, 10시 → 열 시 (숫자로 두면 "오 시"처럼 읽을 때가 있어요)
    hours = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "열한", "열두"]
    text = re.sub(r"(?<![\d,.])(\d{1,2})\s*시(?![간작즌])", lambda m: f"{hours[int(m[1])]} 시" if 0 < int(m[1]) <= 12 else m[0], text)
    return " ".join(text.split())


def estimate(text):
    """키가 없을 때(설계도 확인만 할 때) 읽는 시간 어림. 1.3배 빠르기로 한 칸에 0.135초쯤."""
    from build import units
    return 0.25 + units(text) * 0.135


def chunks(text):
    """자막을 한 번에 읽기 좋은 덩어리로 나눠요. 띄어쓰기 단위로 CHUNK 칸까지."""
    from build import units
    out, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and units(trial) > CHUNK:
            out.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        out.append(cur)
    # [[강조]] 가 덩어리 사이에서 끊기면 양쪽을 닫고 열어 줘요
    fixed, open_ = [], False
    for c in out:
        c = ("[[" if open_ else "") + c
        open_ = c.count("[[") > c.count("]]")
        fixed.append(c + ("]]" if open_ else ""))
    return fixed


CSS = """
.vsub { position: absolute; left: 0; right: 0; top: 680px; height: 130px; background: #fff; display: flex; align-items: center; justify-content: center;
        z-index: 1; }
.vsub div { font-weight: 900; font-size: 70px; letter-spacing: -2.5px; color: #111; text-align: center; padding: 0 40px; }
.vsub .am { color: #D8432B; }
.vpic { position: absolute; left: 0; right: 0; top: 810px; height: 890px; overflow: hidden; background: #0E0B09; }
.vpic img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.vback { position: absolute; left: 0; right: 0; top: 1700px; bottom: 0; overflow: hidden; }
.vback img { width: 100%; height: 100%; object-fit: cover; }
.vpic.whole img { object-fit: contain; }
.vpic.whole img.bg { object-fit: cover; }
.vpic.pack { background: #fff; }
.vpic.pack img { object-fit: contain; padding: 34px 56px; }
.vchip { position: absolute; left: 44px; top: 850px; padding: 8px 26px 14px; border-radius: 999px; background: #D8432B; color: #fff; font-weight: 900; font-size: 54px; letter-spacing: -1.5px; box-shadow: 0 6px 20px rgba(0,0,0,.35); }
.vline { position: absolute; left: 0; right: 0; }
"""
PIN = ('<svg viewBox="0 0 200 250"><path d="M100 244C100 244 16 150 16 92a84 84 0 01168 0c0 58-84 152-84 152z" fill="#D8432B"/>'
       '<circle cx="100" cy="92" r="60" fill="#FFFDF5"/><path d="M62 84h76c0 26-16 42-38 42S62 110 62 84z" fill="#D8432B"/>'
       '<rect x="55" y="78" width="90" height="9" rx="4.5" fill="#D8432B"/></svg>')


def is_pack(B, photo):
    """흰 바탕 상품·봉지 사진인지. 가장자리가 거의 흰색이면 자르지 않고 통째로 보여 줘요. (2026-10-17 봉지가 잘려 보인다고 함)
    사진에 "fit": "contain"(통째로) / "cover"(꽉 채워 자름)를 적으면 그대로 따라요."""
    if isinstance(photo, dict) and photo.get("fit") in ("contain", "cover"):
        return photo["fit"] == "contain"
    from PIL import Image
    B.fetch_photo(photo)
    with Image.open(B.CACHE / (B.photo_key(photo) + "-g2.jpg")) as im:
        a = np.asarray(im.convert("L").resize((200, 200)), dtype=float)
    edge = np.concatenate([a[:8].ravel(), a[-8:].ravel(), a[:, :8].ravel(), a[:, -8:].ravel()])
    return (edge > 225).mean() > 0.6


def pic_html(B, photo):
    if is_pack(B, photo):
        return f'<div class="vpic pack"><img src="{B.pack_photo(photo)}"></div>'
    src, pos = B.fetch_photo(photo)
    if B.zoomed(photo):  # "fit": "cover" 를 적었을 때만 칸을 꽉 채워 잘라요
        return f'<div class="vpic"><img src="{src}" style="object-position:{pos}"></div>'
    # 그 밖에는 잘리지 않게 통째로, 빈 곳은 같은 사진을 흐리게 (2026-10-17 사용자가 정함)
    return f'<div class="vpic whole"><img class="bg" src="{B.backdrop(photo)}"><img src="{src}"></div>'


def line_photos(lines):
    """문장마다 보여 줄 사진 목록. "photos": [...] 를 적으면 그 문장 안에서 차례로 바뀌어요. 없으면 앞 사진을 이어 써요."""
    out, last = [], None
    for l in lines:
        ps = l.get("photos") or ([l["photo"]] if l.get("photo") else [last])
        out.append(ps)
        last = ps[-1]
    return out


def build_voice(spec, work=None):
    """내레이션 쇼츠 HTML. (HTML, 길이, meta) — meta["voice"] 는 목소리 wav 경로(키가 없으면 None)."""
    import build as B

    lines = spec["lines"]
    voices = [tts(spoken(l)) for l in lines]
    real = all(v is not None for v in voices)
    durs = [(len(v) / SR if real else estimate(l["say"])) + GAP for v, l in zip(voices, lines)]
    body = sum(durs)
    credits = B.credit_lines(spec)
    credits = credits if len(credits) > 1 else []
    tail = 1.6
    css = (HERE / "base.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    import thumb
    head = spec.get("headline", spec.get("title", ""))
    name = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">', f"<style>{css}{CSS}{thumb.CSS.replace('FONT_DIR', (HERE / 'fonts').as_uri())}</style></head>",
           '<body style="--ac:#D8432B">',
           # 위쪽 큰 제목은 영상 내내 그대로 있어요 (끝 장면에서만 사라져요). 첫 화면이 곧 썸네일이에요. (thumb.py)
           f'<section class="scene first" data-at="0" data-dur="{body:.2f}" data-out="0" style="z-index:900;pointer-events:none">'
           f'{thumb.head_html(head, name, (spec.get("thumb") or {}).get("color", thumb.AC))}</section>']
    at = 0.0
    for i, (l, d, photos) in enumerate(zip(lines, durs, line_photos(lines))):
        chip = f'<div class="vchip">{B.rich(l["chip"])}</div>' if l.get("chip") else ""
        for k, photo in enumerate(photos):  # 한 문장에 사진이 여러 장이면 읽는 동안 고르게 나눠 바꿔요
            pa, pd = at + d * k / len(photos), d / len(photos)
            anim = ' style="animation:in-fade .12s ease both"' if (i or k) else ""
            out.append(f'<section class="scene{" first" if not (i or k) else ""}" data-at="{pa:.2f}" data-dur="{pd:.2f}" data-out="0"{anim}>'
                       f'<div class="vback"><img src="{B.backdrop(photo)}"></div>{pic_html(B, photo)}{chip}</section>')
        # 자막: 문장을 덩어리로 나눠 읽는 속도에 맞춰 차례로 바꿔요
        parts = chunks(l["say"])
        weights = [B.units(p) + 1 for p in parts]
        t = at
        for k, (p, w) in enumerate(zip(parts, weights)):
            pd = (d - GAP) * w / sum(weights) + (GAP if k == len(parts) - 1 else 0)
            out.append(f'<section class="scene" data-at="{t:.2f}" data-dur="{pd:.2f}" data-out="0" style="z-index:950">'
                       f'<div class="vsub"><div>{B.rich(p)}</div></div></section>')
            t += pd
        at += d
    out.append(f'<section class="scene outro" data-at="{at:.2f}" data-dur="{tail}" data-out="0" style="z-index:990;animation:in-fade .25s ease both">'
               f'{B.scene_outro(credits)}</section>')
    out.append(f"<script>{(HERE / 'base.js').read_text(encoding='utf-8')}</script></body></html>")
    total = at + tail
    voice_path = None
    if real:
        track = np.zeros(int(SR * total) + SR)
        at = 0.0
        for v, d in zip(voices, durs):
            i = int(at * SR)
            track[i: i + len(v)] += v
            at += d
        voice_path = Path(work or ROOT / "build") / f"voice-{hashlib.sha1(json.dumps(lines, ensure_ascii=False).encode()).hexdigest()[:10]}.wav"
        voice_path.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(track[: int(SR * total)], -1, 1) * 32767).astype(np.int16)
        with wave.open(str(voice_path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm.tobytes())
    meta = {"music": B.song(spec), "sfx": [], "ambience": [], "voice": str(voice_path) if voice_path else None}
    return "\n".join(out), total, meta


def problems(spec):
    """대본 길이와 빠진 것을 알려 줘요. (꼭 고칠 것, 보면 좋은 것)"""
    import build as B
    must, should = [], []
    lines = spec.get("lines") or []
    if not spec.get("headline"):
        must.append("headline(위쪽 고정 제목 두 줄)이 없어요.")
    else:
        import thumb
        should += thumb.problems(spec["headline"], "제목")
    if not 8 <= len(lines) <= 18:
        should.append(f"문장이 {len(lines)}개예요. 10~16개가 좋아요.")
    for n, l in enumerate(lines, 1):
        if not l.get("say"):
            must.append(f"{n}번 문장에 say 가 없어요.")
        if n == 1 and not (l.get("photo") or l.get("photos")):
            must.append("1번 문장에 photo 가 없어요.")
        if l.get("say") and B.units(l["say"]) > 42:
            should.append(f"{n}번 문장이 길어요({B.units(l['say']):.0f}칸). 두 문장으로 나누면 자막이 읽기 쉬워요.")
    shown = line_photos(lines) if lines and (lines[0].get("photo") or lines[0].get("photos")) else []
    keys = {json.dumps(p, sort_keys=True) for ps in shown for p in ps}
    if shown and len(keys) < 8:
        should.append(f"서로 다른 사진이 {len(keys)}장이에요. 8~12장이 좋아요(사진이 자주 바뀌어야 끝까지 봐요).")
    run, prev = 0, None
    for n, ps in enumerate(shown, 1):
        run = run + 1 if len(ps) == 1 and ps[0] == prev else 1
        prev = ps[-1]
        if run == 3:
            should.append(f"{n}번 문장까지 같은 사진이 3문장 이어져요. 2문장까지만 쓰고 바꿔 주세요.")
    total = sum(estimate(l.get("say", "")) + GAP for l in lines) + 1.6
    if total > LONGEST:
        must.append(f"읽는 데 {total:.0f}초쯤 걸려요. 59초 안으로 줄여 주세요.")
    elif total < SHORTEST:
        should.append(f"읽는 데 {total:.0f}초쯤이에요. 35~50초가 되게 늘리면 좋아요.")
    return must, should, total
