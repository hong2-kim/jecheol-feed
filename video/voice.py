# -*- coding: utf-8 -*-
"""내레이션 쇼츠 (설계도 "format": "voice"). 2026-10-17 사용자가 '꿀꺽' 채널처럼 하루 한 편 만들자고 함.

  화면: 위쪽에 큰 제목 두 줄이 영상 내내 고정 → 그 아래 흰 띠에 지금 읽는 말(자막) → 그 아래 사진이 문장마다 바뀜
  소리: 채널 목소리(config.json 의 youtube.voice, 빠르기)로 문장마다 읽고, 오디오 보관함 곡을 작게 깔아요.
  길이: 문장을 읽는 시간만큼. 35~50초가 되게 대본을 써요(59초를 넘으면 안 돼요).

설계도:
  {"format": "voice", "kind": "해설", "headline": "결국 밝혀진\\n[[치킨 원가]]",
   "lines": [{"say": "읽을 문장", "photo": {...}, "chip": "사진 위 작은 글(없어도 됨)"}, ...], 그 밖은 다른 영상과 같아요}

대화형·그래픽 (2026-10-19 저녁 추천 쇼츠, rules/daily/dinner.md):
  "cast": {"A": {"voice": "ko-KR-Chirp3-HD-Puck", "rate": 1.1, "label": "준", "color": "#2F7DD1"}, "B": {...}}
      등장인물마다 다른 목소리. 문장에 "who": "A" 를 적어요. 한 목소리로 두 사람을 하지 않아요(problems 가 막아요).
  문장마다 "gap"(다음 문장까지 쉼, 초. 끼어드는 맞장구는 -0.1까지), "rate"(그 문장만 빠르기)를 적을 수 있어요.
  사진 대신 "card": 가격표(price)·순서(steps)·예산 막대(budget)·고르기(pick)·막대(bars)·가게 이름표(shops)·끝 화면 이름표 콜라주(collage) 그래픽, "video": 영상 조각(소리는 빼요).
      다음 문장에 그림이 없으면 앞 그림이 끊기지 않고 이어져요. 카드 줄은 "beat": n 이면 그 묶음의 n번째 문장이 시작될 때 나와요.
  "photo_note": "사진은 예시예요" 를 적으면 사진·영상 장면 귀퉁이에 작게 보여요(실제 상품 사진이 아닐 때). 그 음식을 찍은 것이면 "own": true.
  "narrator": {"voice": ..., "rate": ...} 혼자 읽는 영상을 채널 목소리와 다른 목소리로 읽어요.
  "cast": "duo" 채널 짝(config.json youtube.duo)으로 나눠 읽어요. 문장에 "who": "host"(진행, 여)·"guide"(설명, 남). 이름표는 없어요.
      혼자 읽으면 "narrator": "host" 또는 "guide". (2026-10-28 사용자가 정함, rules/daily/voice.md)
  확정 목소리 (2026-10-28 2차, config.json youtube.voices·pairs):
      "narrator": "achird"·"puck"·"charon"·"aoede" 혼자 / "cast": "A"(Puck+Erinome)·"B"(Achird+Laomedeia), 문장 "who": "puck" 처럼 이름.
      "voice_pick": {"mode": "solo|A|B", "voices": [...], "why": "고른 까닭"} 을 적으면 호흡 모드: 문장 나눠 읽기, 쉼표 뒤 [pause short],
      문장마다 "pace"(hook·fun·react·reveal·number·soft·end, 안 적으면 자동)로 빠르기와 쉼이 달라져요. "take": 2 로 그 문장만 다시 만들어요.
      대본과 TTS 에 보낸 말은 목소리 wav 옆 .txt 에 남아요(voice_log).
  "length": [20, 35] 로 목표 길이를, "facts": [...] 로 가격·시간 근거를 적어요(verify 가 대본 속 금액·시간과 맞춰 봐요).

말투·소재 (2026-10-19 2차):
  "talk": "v0" — video/talk.json 의 말투(문장 사이 간격). 문장에 "act": "react"·"answer"·"number"·"cut" 을 적으면 그만큼 붙여요.
      적지 않으면 예전 그대로예요. 참고 영상을 본 뒤 talk.json 에 v1 을 더하고 "talk" 만 바꾸면 목소리만 다시 만들어져요.
  "assets": [...] — 사진·영상의 출처·이용 조건(scripts/media.py check). 회사 상품 이미지는 허락(permission)이 없으면 막아요.
"""
import re
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
TURN = 0.18  # 대화에서 말하는 사람이 바뀔 때 쉼(초)
LOUD = 0.085  # 대화형은 목소리마다 크기가 달라서 이 크기(RMS)로 맞춰요
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


def tts(text, name=None, rate=None, markup=False, take=None, tail=0.08):
    """문장 하나를 읽은 소리(모노, -1~1). 같은 문장은 build/tts 에 받아 둔 걸 다시 써요. 키가 없으면 None.
    name·rate 를 주면 그 목소리로 읽어요(대화형의 등장인물). 없으면 채널 목소리예요.
    markup 이면 text 를 Chirp 3 의 markup 칸으로 보내요("[pause short]" 쉼 표시가 먹어요). 안 되면 표시를 빼고 text 로 다시 읽어요.
    take 를 바꾸면 그 문장만 새로 만들어요(받아 둔 소리가 이상할 때)."""
    base_name, base_rate = _voice_conf()
    name, rate = name or base_name, float(rate or base_rate)
    tag = f"{name}|{rate}|{text}" + ("|M" if markup else "") + (f"|take{take}" if take else "")
    path = ROOT / "build" / "tts" / (hashlib.sha1(tag.encode()).hexdigest()[:16] + ".wav")
    if not path.exists():
        key = _key()
        if not key:
            return None
        def ask(inp):
            body = {"input": inp, "voice": {"languageCode": "ko-KR", "name": name},
                    "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": rate, "sampleRateHertz": SR}}
            req = urllib.request.Request(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            return base64.b64decode(json.loads(urllib.request.urlopen(req, timeout=60).read())["audioContent"])
        if markup:
            try:
                data = ask({"markup": text})
            except urllib.error.HTTPError:  # markup(미리보기 기능)이 막히면 쉼 표시를 빼고 그냥 읽어요
                data = ask({"text": " ".join(re.sub(r"\[pause[^\]]*\]", " ", text).split())})
        else:
            data = ask({"text": text})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with wave.open(str(path), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(axis=1)
    loud = np.nonzero(np.abs(x) > 0.02)[0]  # 앞뒤의 빈소리를 잘라 말이 바로 이어지게 해요
    if len(loud):
        x = x[max(0, loud[0] - int(SR * 0.03)): loud[-1] + int(SR * tail)]
    return x


def spoken(line):
    """목소리로 읽을 글. 자막(say)과 읽는 말이 달라야 하면 "read" 를 적어요.
    "4~5시"를 "네 시에서 오 시"로 잘못 읽어서(2026-10-17), 범위(~)는 "4시에서 5시"처럼 풀어 읽혀요."""
    text = line.get("read") or line["say"]
    text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"[ㅋㅎㅠㅜ]+", "", text)  # 'ㅋㅋ'를 글자 그대로 읽지 않게 (2026-10-19)
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


STRETCH = 1.25  # 자막 한 덩어리는 room 의 이만큼까지 늘려도 돼요 (글자를 그만큼 줄여요, sub_size)


def chunks(text, room=CHUNK):
    """자막을 한 번에 읽기 좋은 덩어리로 나눠요. 한 줄에 들어가면 통째로, 길면 말이 끊기는 곳(쉼표·물음표 뒤)에서 고르게 나눠요.
    2026-10-21 사용자가 "여러분은 어느 쪽 드셔 / 보셨어요?"처럼 띄엄띄엄 끊지 말고 이어 보여 달라고 함 (모든 먹고갈지도 영상)."""
    from build import units
    words = text.split()
    if not words:
        return []
    top = room * STRETCH
    w = [units(x) for x in words]

    def size(i, j):  # words[i:j] 한 덩어리의 칸 수
        return sum(w[i:j]) + 0.3 * (j - i - 1)

    n = len(words)
    inside, depth = [False], 0  # inside[j]: words[j-1] 뒤가 [[강조]] 안쪽인지
    for x in words:
        depth += x.count("[[") - x.count("]]")
        inside.append(depth > 0)
    k = max(1, -(-size(0, n) // top))  # 덩어리 수는 될 수 있는 대로 적게
    while True:
        goal = size(0, n) / k
        # best[j] = words[:j] 를 몇 덩어리로 나눴을 때의 (덩어리 수, 벌점, 나눈 자리)
        best = {0: (0, 0.0, [])}
        for j in range(1, n + 1):
            for i in range(j):
                if i not in best or size(i, j) > top and j - i > 1:
                    continue
                cnt, cost, cuts = best[i]
                piece = size(i, j)
                end = words[j - 1].replace("]]", "")
                cost2 = cost + (piece - goal) ** 2
                if j < n and not re.search(r"[,.!?…~]$", end):
                    cost2 += 6  # 쉼표·마침표 뒤가 아니면 덜 자연스러워요
                if piece < 5:
                    cost2 += 60  # "보셨어요?"처럼 짧게 떨어지는 조각은 피해요
                if j < n and inside[j]:
                    cost2 += 80  # [[강조]] 한가운데서는 끊지 않아요
                cand = (cnt + 1, cost2, cuts + [j])
                if cnt + 1 <= k and (j not in best or cand[:2] < best[j][:2]):
                    best[j] = cand
        if n in best:
            break
        k += 1
    out, start = [], 0
    for cut in best[n][2]:
        out.append(" ".join(words[start:cut]))
        start = cut
    # [[강조]] 가 덩어리 사이에서 끊기면 양쪽을 닫고 열어 줘요
    fixed, open_ = [], False
    for c in out:
        c = ("[[" if open_ else "") + c
        open_ = c.count("[[") > c.count("]]")
        fixed.append(c + ("]]" if open_ else ""))
    return fixed


def sub_size(text, base=70, room=CHUNK):
    """자막 글자 크기. room 칸이 넘는 덩어리는 한 줄에 들어가게 그만큼 줄여요."""
    from build import units
    return min(base, int(base * room / max(units(text), 1)))


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
.vback.dark { background: #0E0B09; }
.vsub { overflow: visible; }
.vsub span.vwho { flex: none; margin: 0 -18px 0 34px; padding: 4px 20px 8px; border-radius: 999px; color: #fff; font-weight: 900; font-size: 40px;
        letter-spacing: -1px; }
.vsub span.vwho + div { font-size: 62px; padding: 0 28px; }
.vnote { position: absolute; right: 26px; top: 1630px; padding: 6px 18px 9px; border-radius: 12px; background: rgba(0,0,0,.55); color: #fff;
         font-weight: 700; font-size: 30px; letter-spacing: -.5px; }
.vcard { position: absolute; left: 0; right: 0; top: 810px; height: 890px; background: #FFF6E6; color: #1d1a16; padding: 48px 64px 0;
         font-weight: 800; letter-spacing: -1.5px; }
.vct { font-weight: 900; font-size: 76px; letter-spacing: -2.5px; }
.vct .am, .vcs .am { color: #D8432B; }
.vcs { margin-top: 6px; font-size: 42px; color: #6d5f4c; font-weight: 800; }
.vcb { margin-top: 26px; }
.vrow { display: flex; justify-content: space-between; align-items: baseline; font-size: 62px; padding: 18px 4px; border-bottom: 4px dashed #E6D5B5; }
.vrow span { display: flex; align-items: baseline; gap: 14px; }
.vrow small { font-size: 32px; color: #8a7a64; font-weight: 700; }
.vrow em { display: inline-block; width: 30px; height: 30px; border-radius: 8px; align-self: center; }
.vrow b { font-weight: 900; font-variant-numeric: tabular-nums; }
.vtot { display: flex; justify-content: space-between; margin-top: 22px; padding: 16px 26px 22px; border-radius: 22px; background: #1F2A1A; color: #fff;
        font-size: 72px; font-weight: 900; }
.vtot b { color: #FFB23E; }
.vleft { margin-top: 16px; font-size: 44px; font-weight: 900; color: #2E6B3A; text-align: right; }
.vsrc { margin-top: 22px; font-size: 31px; line-height: 1.3; color: #85776a; font-weight: 700; letter-spacing: -.5px; }
.vbar { position: relative; height: 64px; border-radius: 18px; background: #EADCC2; overflow: hidden; margin-bottom: 18px; }
.vseg { position: absolute; top: 0; bottom: 0; transform-origin: left center; }
.grow.a { animation-name: grow; }
@keyframes grow { from { transform: scaleX(0); } to { transform: none; } }
.vcard.budget { padding-top: 40px; }
.vcard.budget .vrow { font-size: 56px; padding: 12px 4px; }
.vcard.budget .vtot { font-size: 64px; margin-top: 16px; padding: 10px 26px 14px; }
.vcard.budget .vleft { margin-top: 10px; }
.vstep { display: flex; align-items: center; gap: 26px; font-size: 64px; padding: 22px 0; }
.vstep i { flex: none; width: 84px; height: 84px; border-radius: 50%; background: #D8432B; color: #fff; font-style: normal; font-size: 50px;
           display: flex; align-items: center; justify-content: center; }
.vpick { display: flex; flex-direction: column; gap: 6px; margin-bottom: 30px; padding: 26px 34px; border-radius: 26px; background: #fff;
         box-shadow: 0 6px 0 #E6D5B5; }
.vpick span { font-size: 44px; color: #6d5f4c; }
.vpick b { font-size: 66px; font-weight: 900; }
.vbr { display: flex; align-items: center; gap: 20px; margin: 14px 0; }
.vbr > span { flex: none; width: 250px; font-size: 48px; font-weight: 900; color: #6d5f4c; }
.vbr.hl > span { color: #1d1a16; }
.vbr .tr { flex: 1; display: flex; align-items: center; gap: 16px; height: 86px; }
.vbr .fill { flex: none; height: 100%; border-radius: 0 16px 16px 0; transform-origin: left center; }
.vbr b { flex: none; font-size: 46px; font-weight: 900; color: #6d5f4c; font-variant-numeric: tabular-nums; white-space: nowrap; }
.vbr.hl b { color: #D8432B; font-size: 52px; }
.vcard.shops { padding-top: 34px; }
.vshop { display: flex; align-items: center; gap: 30px; margin-bottom: 18px; padding: 20px 32px; border-radius: 26px; background: #fff;
         box-shadow: 0 6px 0 #E6D5B5; }
.vshop i { flex: none; width: 172px; padding: 12px 0 16px; border-radius: 18px; color: #fff; font-style: normal; font-size: 40px; font-weight: 900;
           text-align: center; line-height: 1.15; }
.vshop div { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.vshop b { font-size: 64px; font-weight: 900; letter-spacing: -2px; white-space: nowrap; line-height: 1.15; }
.vshop span { font-size: 42px; color: #6d5f4c; font-weight: 800; line-height: 1.2; }
.vshop span .am { color: #D8432B; }
.vcard.collage { padding: 34px 34px 0; background: #1F2A1A; }
.vcol { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px 10px; align-items: center; }
.vtag { justify-self: center; padding: 10px 20px 14px; line-height: 1.15; border-radius: 14px; border: 5px solid #FFF6E6; color: #fff; font-weight: 900;
        white-space: nowrap; letter-spacing: -1.5px; box-shadow: 0 6px 0 rgba(0,0,0,.35); }
.vmid { grid-column: 1 / -1; margin: 16px 0; padding: 34px 20px 42px; border-radius: 30px; background: #FFF6E6; text-align: center;
        font-size: 78px; font-weight: 900; line-height: 1.22; letter-spacing: -3px; color: #1d1a16; }
.vmid .am { color: #D8432B; }
.vcard.collage .vsrc { color: #b9c7ae; text-align: center; margin-top: 18px; }
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
    if B.zoomed(photo) or B.fills(photo):  # 음식 사진은 칸을 꽉 채워요 (2026-10-28 사용자 승인, 가장자리만 잘려요. 핵심 위치는 pos)
        return f'<div class="vpic"><img src="{src}" style="object-position:{pos}"></div>'
    # 포스터·안내문처럼 전체가 중요한 사진("fit": "contain", "kind": "poster")은 잘리지 않게 통째로 (2026-10-17 사용자가 정함)
    return f'<div class="vpic whole"><img class="bg" src="{B.backdrop(photo)}"><img src="{src}"></div>'


def line_photos(lines):
    """문장마다 보여 줄 사진 목록. "photos": [...] 를 적으면 그 문장 안에서 차례로 바뀌어요. 없으면 앞 사진을 이어 써요."""
    out, last = [], None
    for l in lines:
        ps = l.get("photos") or ([l["photo"]] if l.get("photo") else [last])
        out.append(ps)
        last = ps[-1]
    return out


def roster():
    """확정한 목소리({"achird": {...}, ...})와 2인 조합({"A": ["puck", "erinome"], ...}). config.json youtube.voices·pairs."""
    yt = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("youtube") or {}
    return yt.get("voices") or {}, yt.get("pairs") or {}


def with_duo(spec):
    """줄여 쓴 목소리를 config.json 값으로 풀어요. 이름표 없이 목소리만 달라요.
    - "narrator": "achird"·"aoede"… / "cast": "A"(Puck+Erinome)·"B"(Achird+Laomedeia), 문장마다 "who": "puck" (2026-10-28 확정, youtube.voices·pairs)
    - 예전 것: "cast": "duo"(진행 host·설명 guide), "narrator": "host"·"guide" (youtube.duo)"""
    if not isinstance(spec.get("cast"), str) and not isinstance(spec.get("narrator"), str):
        return spec
    yt = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("youtube") or {}
    duo, voices, pairs = yt.get("duo") or {}, yt.get("voices") or {}, yt.get("pairs") or {}
    spec = dict(spec)
    if spec.get("cast") == "duo":
        spec["cast"] = duo
    elif isinstance(spec.get("cast"), str):
        spec["cast"] = {n: voices.get(n, {}) for n in pairs.get(spec["cast"], [])}
    if isinstance(spec.get("narrator"), str):
        spec["narrator"] = voices.get(spec["narrator"]) or duo.get(spec["narrator"], {})
    return spec


# ── 호흡·빠르기 (2026-10-28 사용자: "단어를 붙여 읽거나 문장 사이를 쉬지 않아 알아듣기 어렵다") ──
# 잰 것: 여섯 목소리 모두 짧은 문장의 쉼표에서 거의 쉬지 않아요(0.05~0.08초). markup 의 [pause short] 를 넣으면 0.4~0.6초 쉬고,
# 그걸 상황에 맞는 길이로 줄여요. 문장(. ? !)은 따로 만들어 사이를 직접 띄워요. 설계도에 "voice_pick" 이 있을 때만 이렇게 하고,
# 없으면 예전 그대로예요(이미 만든 영상이 바뀌지 않게).
PACE = {"hook": 1.04, "fun": 1.0, "react": 1.1, "reveal": 0.96, "number": 0.95, "soft": 0.94, "end": 0.96}  # 목소리 기본 빠르기에 곱해요
COMMA = {"hook": 0.16, "fun": 0.2, "react": 0.14, "reveal": 0.26, "number": 0.26, "soft": 0.26, "end": 0.22}  # 쉼표 쉼(초)


def breathing(spec):
    return bool(spec.get("voice_pick"))


def pace_of(spec, lines, i):
    """문장의 말투: 적은 "pace" 가 먼저. 없으면 첫 문장 hook, 마지막 end, 숫자가 든 문장 number, 그 밖은 영상 "mood"(soft) 또는 fun."""
    l = lines[i]
    if l.get("pace") in PACE:
        return l["pace"]
    if i == 0:
        return "hook"
    if i == len(lines) - 1:
        return "end"
    if re.search(r"\d", l.get("say", "")):
        return "number"
    return "soft" if spec.get("mood") == "soft" else "fun"


def sentences(text):
    """한 문장 칸 안의 말을 마침표·물음표·느낌표·말줄임표 뒤에서 나눠요(나눈 조각마다 따로 읽어 끝 억양이 살아요)."""
    return [s for s in re.split(r"(?<=[.?!…])\s+", text.strip()) if s]


def _rms10(x):
    win = SR // 100
    n = len(x) // win
    return np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1)) if n else np.zeros(0)


def squeeze(x, target):
    """말 가운데 쉼이 target 초보다 길면 target 으로 줄여요(markup 쉼이 목소리마다 0.4~0.6초라서). (줄인 소리, 가장 긴 쉼)"""
    e, win = _rms10(x), SR // 100
    quiet, out, i, last, longest = e < 0.008, [], 0, 0, 0.0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if 0 < i and j < len(quiet):  # 앞뒤 끝은 tts 가 이미 잘랐어요
                run = (j - i) / 100
                keep = min(run, target)
                longest = max(longest, keep)
                if run > keep + 0.02:
                    a, b = i * win, j * win
                    half = int(SR * keep / 2)
                    out.append(x[last: a + half])
                    last = b - half
            i = j
        else:
            i += 1
    out.append(x[last:])
    return np.concatenate(out), longest


def _pauses(x):
    """말 사이 0.1초 넘는 쉼의 합(초)."""
    quiet, total, run = _rms10(x) < 0.008, 0, 0
    for q in list(quiet) + [False]:
        if q:
            run += 1
        else:
            total += run if run >= 10 else 0
            run = 0
    return total / 100


def syllables(text):
    return len(re.findall(r"[가-힣0-9]", text))


def speak(spec, lines, i, c):
    """문장 하나를 호흡 넣어 읽어요. (소리, 기록 dict)"""
    l, pace = lines[i], pace_of(spec, lines, i)
    rate = round(float(l.get("rate") or float(c.get("rate") or _voice_conf()[1]) * PACE[pace]), 3)
    said = spoken(l)
    parts, sent, why = sentences(said), [], []
    if l.get("read"):
        why.append("read 칸(자막과 다르게 읽음)")
    if said != " ".join(l["say"].replace("[[", "").replace("]]", "").split()) and not l.get("read"):
        why.append("숫자·시각을 풀어 읽음")
    if len(parts) > 1:
        why.append(f"문장 {len(parts)}개로 나눠 읽음")
    pieces, longest, warn = [], 0.0, []
    for k, s in enumerate(parts):
        # 쉼표 뒤에 쉼 표시. 짧은 맞장구(react)는 넣지 않아요("아, 그렇구나"가 늘어져요)
        mk = re.sub(r",\s*", ", [pause short] ", s) if "," in s.rstrip(",") and pace != "react" else ""
        v = tts(mk or s, c.get("voice"), rate, markup=bool(mk), take=l.get("take"), tail=0.12)
        if v is None:
            return None, {}
        if mk:
            v, lp = squeeze(v, COMMA[pace])
            longest = max(longest, lp)
            if lp < 0.1:
                warn.append(f"쉼표에서 안 쉼('{s[:14]}…')")
        sent.append(mk or s)
        pieces.append(v)
        if k < len(parts) - 1:
            pieces.append(np.zeros(int(SR * (0.36 if s.endswith("?") else 0.3))))
    if any("[pause" in s for s in sent):
        why.append("쉼표 뒤에 [pause short] 넣고 쉼을 줄임")
    v = np.concatenate(pieces)
    v = v * min(LOUD / max(1e-9, np.sqrt(np.mean(v ** 2))), 0.98 / max(1e-9, np.abs(v).max()))  # 목소리·문장마다 크기를 맞춰요
    sps = syllables(said) / max(0.01, len(v) / SR - _pauses(v))  # 0.1초 넘는 쉼을 뺀 말 빠르기
    if syllables(said) >= 8 and sps > 8.4:
        warn.append(f"빨라요({sps:.1f}음절/초)")
    elif syllables(said) >= 8 and sps < 5.2:
        warn.append(f"느려요({sps:.1f}음절/초)")
    who = next((k for k, cc in (spec.get("cast") or {}).items() if cc is c), "") or (c.get("voice") or "").rsplit("-", 1)[-1].lower()
    return v, {"n": i + 1, "who": who, "voice": c.get("voice"), "pace": pace, "rate": rate, "say": l["say"], "tts": sent,
               "why": why, "sec": round(len(v) / SR, 2), "sps": round(sps, 1), "comma": round(longest, 2), "warn": warn}


def breath_gaps(spec, lines, paces):
    """문장 사이 쉼(초). 모두 같게 두지 않아요: 물음 뒤·화자 바뀜·숫자·반전 앞은 길게, 짧은 맞장구는 짧게. "gap" 을 적으면 그게 먼저."""
    out = []
    for i, l in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if "gap" in l:
            out.append(max(-0.15, float(l["gap"])))
            continue
        if nxt is None:
            out.append(0.3)
            continue
        g = 0.42 if l["say"].rstrip().endswith("?") else 0.3
        if syllables(l["say"]) <= 8:
            g -= 0.05
        if spec.get("cast") and nxt.get("who") != l.get("who"):
            g += 0.06
        if paces[i + 1] == "react" or nxt.get("act") == "react":
            g = 0.18
        if paces[i + 1] == "reveal":
            g += 0.15
        if paces[i + 1] == "number":
            g += 0.1
        if paces[i] == "number":
            g += 0.06
        if i + 1 == len(lines) - 1:
            g += 0.08
        out.append(round(min(0.7, max(0.15, g)), 2))
    return out


def voice_log(spec, logs, gaps_):
    """대본과 실제로 TTS 에 보낸 말, 빠르기·쉼·경고를 한눈에. 문제가 대본인지 목소리인지 편집인지 가르려고 남겨요."""
    pick = spec.get("voice_pick") or {}
    out = [f"목소리: {pick.get('mode', '')} · {', '.join(pick.get('voices', []))}", f"고른 까닭: {pick.get('why', '')}", ""]
    for g, r in zip(gaps_, logs):
        out.append(f"[{r['n']}] {r['who']} · {r['pace']} · 빠르기 {r['rate']} · {r['sec']}초 · {r['sps']}음절/초 · 쉼표 쉼 {r['comma']}초 · 다음까지 {g}초")
        out.append(f"   대본: {r['say']}")
        if [s.replace(", [pause short] ", ", ") for s in r["tts"]] != [r["say"].replace("[[", "").replace("]]", "")] or r["why"]:
            out.append(f"   TTS : {' / '.join(r['tts'])}")
            out.append(f"   바꾼 까닭: {', '.join(r['why']) or '-'}")
        if r["warn"]:
            out.append(f"   ⚠ {', '.join(r['warn'])}")
    return "\n".join(out)


def who_of(spec, line):
    """그 문장을 말하는 사람의 설정(목소리·빠르기·이름·색). 혼자 읽는 영상이면 빈 dict."""
    return (spec.get("cast") or {}).get(line.get("who") or "", {}) if line.get("who") else {}


def talk_conf():
    """video/talk.json — 목소리 목록(성별·느낌)과 말투(styles: 문장 사이 간격). 참고 영상을 본 뒤 v1 을 더해요."""
    return json.loads((HERE / "talk.json").read_text(encoding="utf-8"))


def talk_style(spec):
    """설계도 "talk": "v0" 처럼 고른 말투. 적지 않으면 None → 예전 그대로(GAP·TURN)."""
    if not spec.get("talk"):
        return None
    return talk_conf()["styles"].get(spec["talk"])


def gaps(spec, lines):
    """문장마다 다음 문장까지 쉼. 적은 값이 없으면 같은 사람은 GAP, 사람이 바뀌면 TURN.
    설계도에 "talk"(말투)를 적으면 그 값을 쓰고, 다음 문장에 "act"(react·answer·number·cut)가 있으면 그만큼 붙여요."""
    style = talk_style(spec) or {}
    same, turn, acts = style.get("same", GAP), style.get("turn", TURN), style.get("act") or {}
    out = []
    for i, l in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else {}
        if "gap" in l:
            out.append(max(-0.15, float(l["gap"])))
        elif style and nxt.get("act") in acts:
            out.append(max(-0.15, float(acts[nxt["act"]])))
        elif spec.get("cast") and nxt and nxt.get("who") != l.get("who"):
            out.append(turn)
        else:
            out.append(same)
    return out


def pair_of(spec):
    """대화형 목소리 조합 "남+여"·"여+여"·"남+남". 목록에 없는 목소리는 "?"."""
    voices = talk_conf()["voices"]
    return "+".join(sorted((voices.get(c.get("voice"), {}).get("sex", "?") for c in (spec.get("cast") or {}).values()),
                           key=lambda s: "남여?".index(s)))


def segments(lines):
    """보여 줄 그림 묶음 [[첫 문장, 끝 문장(빼고), 그림]]. 그림이 없는 문장은 앞 그림을 끊지 않고 이어요."""
    segs = []
    for i, l in enumerate(lines):
        v = ({"card": l["card"]} if l.get("card") else {"video": l["video"]} if l.get("video")
             else {"photos": l.get("photos") or [l["photo"]]} if (l.get("photos") or l.get("photo")) else None)
        if v or not segs:
            segs.append([i, i + 1, v or {}])
        else:
            segs[-1][1] = i + 1
    return segs


def won(n):
    return f"{int(round(n)):,}원"


def _at(item, k, beats, step=0.32, first=0.25):
    """카드 줄이 나오는 때(묶음 시작부터 초). "at" > "beat"(묶음의 n번째 문장이 시작될 때, "after" 초 뒤) > 차례대로."""
    if "at" in item:
        return float(item["at"])
    if "beat" in item and int(item["beat"]) < len(beats):
        return beats[int(item["beat"])] + 0.1 + float(item.get("after", 0))  # "after": 같은 문장 안에서 조금 뒤에
    return first + k * step


def _total_at(card, beats, last):
    if "total_beat" in card and int(card["total_beat"]) < len(beats):
        return beats[int(card["total_beat"])] + 0.1 + float(card.get("total_after", 0))
    return last + 0.45


def card_html(B, card, beats):
    """사진 칸(810~1700)에 그리는 그래픽. 직접 찍지 않는 채널이라 가격·순서·예산은 그림으로 보여 줘요."""
    kind = card.get("type", "price")
    esc, rich = B.esc, B.rich
    title = f'<div class="vct">{rich(card["title"])}</div>' if card.get("title") else ""
    sub = f'<div class="vcs">{rich(card["sub"])}</div>' if card.get("sub") else ""
    src = f'<div class="vsrc">{esc(card["src"])}</div>' if card.get("src") else ""
    colors = ["#D8432B", "#E89A1C", "#2E8B57", "#2F7DD1", "#8A5CC2"]
    body, last = [], 0.0
    if kind in ("price", "budget"):
        items = card.get("items") or card.get("parts")
        approx = "약 " if card.get("est") or any(it.get("est") for it in items) else ""
        total = sum(it["price"] for it in items)
        budget = card.get("budget")
        bars, x = [], 0.0
        for k, it in enumerate(items):
            t = _at(it, k, beats, step=0.32 if kind == "price" else 0.6)
            last = max(last, t)
            color = it.get("color", colors[k % 5])
            dot = f'<em style="background:{color}"></em>' if kind == "budget" else ""
            note = f'<small>{esc(it["note"])}</small>' if it.get("note") else ""
            body.append(f'<div class="vrow a pop" style="--dl:{t:.2f}s;--d:.28s"><span>{dot}{rich(it["name"])}{note}</span>'
                        f'<b>{"약 " if it.get("est") else ""}{won(it["price"])}</b></div>')
            if kind == "budget":
                w = it["price"] / budget * 100
                bars.append(f'<div class="vseg a grow" style="left:{x:.2f}%;width:{w:.2f}%;background:{color};--dl:{t:.2f}s;--d:.45s"></div>')
                x += w
        if bars:
            body.insert(0, f'<div class="vbar">{"".join(bars)}</div>')
        t = _total_at(card, beats, last)
        left = ""
        if budget:
            rest = budget - total
            what = f"남는 돈 {approx}{won(rest)}" if rest > 0 else "예산에 딱 맞아요" if rest == 0 else f"예산보다 {won(-rest)} 넘어요"
            left = f'<div class="vleft">예산 {won(budget)} · {what}{" · " + esc(card["rest_note"]) if card.get("rest_note") else ""}</div>'
        body.append(f'<div class="vtot a pop" style="--dl:{t:.2f}s;--d:.3s"><span>{esc(card.get("total_label", "합계"))}</span><b>{approx}{won(total)}</b></div>'
                    f'<div class="a rise" style="--dl:{t + .25:.2f}s;--d:.3s">{left}</div>')
    elif kind == "steps":
        for k, st in enumerate(card["steps"]):
            st = st if isinstance(st, dict) else {"text": st}
            t = _at(st, k, beats, step=0.45)
            body.append(f'<div class="vstep a rise" style="--dl:{t:.2f}s;--d:.3s"><i>{k + 1}</i><span>{rich(st["text"])}</span></div>')
    elif kind == "pick":
        for k, r in enumerate(card["rows"]):
            t = _at(r, k, beats, step=0.5)
            body.append(f'<div class="vpick a rise" style="--dl:{t:.2f}s;--d:.3s"><span>{rich(r["if"])}</span><b>{rich(r["then"])}</b></div>')
    elif kind == "bars":  # 막대 비교: 줄마다 {"name", "value", "label", "hl": true(강조)}. 막대 길이는 value 끼리 견줘요
        top = card.get("max") or max(r["value"] for r in card["rows"])
        for k, r in enumerate(card["rows"]):
            t = _at(r, k, beats, step=0.4)
            color = r.get("color") or ("#D8432B" if r.get("hl") else "#B9A88E")
            body.append(f'<div class="vbr{" hl" if r.get("hl") else ""}"><span class="a rise" style="--dl:{t:.2f}s;--d:.25s">{rich(r["name"])}</span>'
                        f'<div class="tr"><div class="fill a grow" style="width:{r["value"] / top * 100 * card.get("scale", .45):.1f}%;background:{color};--dl:{t:.2f}s;--d:.5s"></div>'
                        f'<b class="a rise" style="--dl:{t + .35:.2f}s;--d:.25s">{rich(r.get("label", ""))}</b></div></div>')
    elif kind == "shops":  # 가게 소개: 줄마다 {"name": 상호, "region": 지역, "menu": 대표 메뉴}. 사진 없이 이름표로 (이용 허락된 가게 사진이 없을 때)
        for k, r in enumerate(card["rows"]):
            t = _at(r, k, beats, step=0.45)
            body.append(f'<div class="vshop a rise" style="--dl:{t:.2f}s;--d:.3s"><i style="background:{r.get("color", colors[k % 5])}">{esc(r["region"]).replace(chr(10), "<br>")}</i>'
                        f'<div><b>{esc(r["name"])}</b><span>{rich(r["menu"])}</span></div></div>')
    elif kind == "collage":  # 끝 화면: 가운데 큰 물음, 둘레에 가게 이름표. "names" 12개 안팎(위 6 · 아래 6)
        names = card["names"]
        half = (len(names) + 1) // 2
        tag = lambda k, n: (f'<div class="vtag a pop" style="background:{colors[k % 5]};font-size:{50 if len(n) <= 4 else 44 if len(n) <= 6 else 37}px;'
                            f'transform:rotate({(-2, 1.5, -1, 2)[k % 4]}deg);--dl:{.15 + k * .07:.2f}s;--d:.25s">{esc(n)}</div>')
        body.append('<div class="vcol">' + "".join(tag(k, n) for k, n in enumerate(names[:half]))
                    + f'<div class="vmid a pop" style="--dl:.05s;--d:.3s">{rich(card["center"]).replace(chr(10), "<br>")}</div>'
                    + "".join(tag(half + k, n) for k, n in enumerate(names[half:])) + '</div>')
    return f'<div class="vcard {esc(kind)}">{title}{sub}<div class="vcb">{"".join(body)}</div>{src}</div>'


def video_html(B, video, dur):
    """영상 조각. 소리는 쓰지 않아요(B.clip 이 소리를 빼고 낱장으로 풀어요). 설계도 확인만 할 때는 빈 칸이에요."""
    if not B.EXTRACT:
        return '<div class="vpic"></div>'
    first, folder, count, tall = B.clip(video, dur)
    pos = video.get("pos", "50% 50%") if isinstance(video, dict) else "50% 50%"
    return (f'<div class="vpic"><img class="vf" src="{first}" data-frames="{folder}" data-n="{count}" data-fps="{B.FPS}" '
            f'style="object-position:{pos}"></div>')


def build_voice(spec, work=None):
    """내레이션 쇼츠 HTML. (HTML, 길이, meta) — meta["voice"] 는 목소리 wav 경로(키가 없으면 None)."""
    import build as B

    spec = with_duo(spec)
    lines = spec["lines"]
    voices, logs = [], []
    narr = spec.get("narrator") or {}  # 혼자 읽는 영상의 목소리를 채널 목소리와 다르게 할 때 {"voice": ..., "rate": ...}
    for i, l in enumerate(lines):
        c = who_of(spec, l) or narr
        if breathing(spec):  # 2026-10-28: 문장 나눠 읽기·쉼표 쉼·말투별 빠르기
            v, r = speak(spec, lines, i, c)
            logs.append(r)
        else:
            v = tts(spoken(l), c.get("voice"), l.get("rate") or c.get("rate"))
            if v is not None and spec.get("cast") and len(v):  # 목소리마다 크기가 달라서 맞춰요
                v = v * min(LOUD / max(1e-9, np.sqrt(np.mean(v ** 2))), 0.98 / max(1e-9, np.abs(v).max()))
        voices.append(v)
    real = all(v is not None for v in voices)
    speech = [len(v) / SR if real else estimate(l["say"]) for v, l in zip(voices, lines)]
    gaps_ = breath_gaps(spec, lines, [pace_of(spec, lines, i) for i in range(len(lines))]) if breathing(spec) else gaps(spec, lines)
    durs = [s + g for s, g in zip(speech, gaps_)]
    starts = [sum(durs[:i]) for i in range(len(lines))]
    body = sum(durs)
    credits = []  # 끝 장면에는 사진 출처를 넣지 않고 게시글·설명에만 적어요 (2026-10-22·10-28 사용자: "글로만 넣을꺼라고 했어")
    tail = 1.6
    css = (HERE / "base.css").read_text(encoding="utf-8").replace("FONT_DIR", (HERE / "fonts").as_uri())
    import thumb
    if spec.get("layout") == "rec":  # 추천 쇼츠 화면 (2026-10-20, video/rec.py)
        import rec
        css += rec.CSS
        parts, cuts, sfx, subs = rec.build_rec(spec, voices, speech, durs, starts, real)
        credits = []  # 추천 쇼츠 끝 장면에는 사진 출처를 넣지 않고 게시글·설명에만 적어요 (2026-10-26 사용자)
        out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
               f"<style>{css}{CSS}{thumb.css().replace('FONT_DIR', (HERE / 'fonts').as_uri())}{rec.CSS}</style></head>",
               '<body style="--ac:#D8432B">'] + parts
    else:
        cuts = sfx = subs = None
    if cuts is None:  # 예전 화면: 위쪽 큰 제목을 영상 내내 고정
        head = spec.get("headline", spec.get("title", ""))
        name = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("account") or "먹고갈지도"
        out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">', f"<style>{css}{CSS}{thumb.css().replace('FONT_DIR', (HERE / 'fonts').as_uri())}</style></head>",
               '<body style="--ac:#D8432B">',
               # 위쪽 큰 제목은 영상 내내 그대로 있어요 (끝 장면에서만 사라져요). 첫 화면이 곧 썸네일이에요. (thumb.py)
               f'<section class="scene first" data-at="0" data-dur="{body:.2f}" data-out="0" style="z-index:900;pointer-events:none">'
               f'{thumb.head_html(head, name, (spec.get("thumb") or {}).get("color", thumb.AC))}</section>']
        note = f'<div class="vnote">{B.esc(spec["photo_note"])}</div>' if spec.get("photo_note") else ""
        last_photo = None
        for n, (a, b, vis) in enumerate(segments(lines)):
            at, d = starts[a], sum(durs[a:b])
            chip = f'<div class="vchip">{B.rich(lines[a]["chip"])}</div>' if lines[a].get("chip") else ""
            anim = ' style="animation:in-fade .12s ease both"' if n else ""
            first = "" if n else " first"
            if vis.get("card"):
                beats = [starts[i] - at for i in range(a, b)]
                out.append(f'<section class="scene{first}" data-at="{at:.2f}" data-dur="{d:.2f}" data-out="0"{anim}>{card_html(B, vis["card"], beats)}{chip}</section>')
                continue
            if vis.get("video"):
                out.append(f'<section class="scene{first}" data-at="{at:.2f}" data-dur="{d:.2f}" data-out="0"{anim}>'
                           f'<div class="vback dark"></div>{video_html(B, vis["video"], d)}{chip}{"" if vis["video"].get("own") else note}</section>')
                continue
            photos = vis.get("photos") or [last_photo]
            d0 = durs[a]  # 사진이 여러 장이면 첫 문장 동안 고르게 나눠 바꾸고, 마지막 장은 묶음 끝까지 이어요
            for k, photo in enumerate(photos):
                pa = at + d0 * k / len(photos)
                pd = d0 / len(photos) if k < len(photos) - 1 else at + d - pa
                mark = "" if isinstance(photo, dict) and photo.get("own") else note  # "own": 그 음식을 찍은 사진이면 예시 표시를 안 해요
                out.append(f'<section class="scene{first if not k else ""}" data-at="{pa:.2f}" data-dur="{pd:.2f}" data-out="0"{anim if (n or k) else ""}>'
                           f'<div class="vback"><img src="{B.backdrop(photo)}"></div>{pic_html(B, photo)}{chip}{mark}</section>')
            last_photo = photos[-1]
        for i, l in enumerate(lines):
            # 자막: 문장을 덩어리로 나눠 읽는 속도에 맞춰 차례로 바꿔요. 대화형은 말하는 사람 이름표와 색 띠를 붙여요
            # (해설의 진행·설명 짝처럼 cast 에 label 이 없으면 이름표 없이 목소리만 바꿔요, 2026-10-28)
            c = who_of(spec, l)
            tag = f'<span class="vwho" style="background:{c.get("color", "#333")}">{B.esc(c["label"])}</span>' if c.get("label") else ""
            bar = f' style="box-shadow:inset 18px 0 0 {c["color"]}"' if c.get("color") else ""
            room = CHUNK - 2 if tag else CHUNK  # 이름표 자리만큼 한 번에 보여 줄 글을 줄여요
            parts = chunks(l["say"], room)
            weights = [B.units(p) + 1 for p in parts]
            t, said, d = starts[i], speech[i], durs[i]
            for k, (p, w) in enumerate(zip(parts, weights)):
                pd = said * w / sum(weights) + (max(0.0, d - said) if k == len(parts) - 1 else 0)
                out.append(f'<section class="scene" data-at="{t:.2f}" data-dur="{max(pd, 0.05):.2f}" data-out="0" style="z-index:950">'
                           f'<div class="vsub"{bar}>{tag}<div style="font-size:{sub_size(p, 62 if c else 70, room)}px">{B.rich(p)}</div></div></section>')
                t += pd
    outro = B.scene_outro(credits)
    lics = sorted({m[1].lower() for c in spec.get("credits") or [] for m in [re.search(r"CC (BY(?:-SA)?) (\d\.\d)", str(c))] if m} |
                  {f"{m[1].lower()}/{m[2]}" for c in spec.get("credits") or [] for m in [re.search(r"CC (BY(?:-SA)?) (\d\.\d)", str(c))] if m})
    lics = [x for x in lics if "/" in x]
    if cuts is not None and lics:  # 추천 쇼츠: CC BY 라이선스 주소를 정확히 (2026-10-20)
        outro = outro.replace("creativecommons.org/licenses", " · ".join(f"creativecommons.org/licenses/{x}" for x in lics))
    out.append(f'<section class="scene outro" data-at="{body:.2f}" data-dur="{tail}" data-out="0" style="z-index:990;animation:in-fade .25s ease both">'
               f'{outro}</section>')
    out.append(f"<script>{(HERE / 'base.js').read_text(encoding='utf-8')}</script></body></html>")
    total = body + tail
    voice_path = None
    if real:
        track = np.zeros(int(SR * total) + SR)
        for v, s in zip(voices, starts):
            i = int(s * SR)
            track[i: i + len(v)] += v
        key = json.dumps([spec.get("cast"), lines], ensure_ascii=False)
        voice_path = Path(work or ROOT / "build") / f"voice-{hashlib.sha1(key.encode()).hexdigest()[:10]}.wav"
        voice_path.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(track[: int(SR * total)], -1, 1) * 32767).astype(np.int16)
        with wave.open(str(voice_path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm.tobytes())
    meta = {"music": B.song(spec), "sfx": sfx or [], "ambience": [], "voice": str(voice_path) if voice_path else None}
    if real and logs:  # 대본 ↔ TTS 에 보낸 말 기록 (목소리 wav 옆에 같은 이름 .txt)
        meta["voice_log"] = voice_log(spec, logs, gaps_)
        voice_path.with_suffix(".txt").write_text(meta["voice_log"], encoding="utf-8")
        bad = [f"{r['n']}번 {', '.join(r['warn'])}" for r in logs if r["warn"]]
        print("  목소리:", (spec.get("voice_pick") or {}).get("mode"), "· 다시 볼 문장:", "; ".join(bad) if bad else "없음")
    if cuts is not None:
        meta["rec"] = {"cuts": cuts, "subs": subs, "starts": starts, "durs": durs}
    return "\n".join(out), total, meta


def pick_problems(spec):
    """확정 목소리(이름·A/B)를 쓰는 설계도: 고른 기록(voice_pick)과 띄어쓰기·끊어 읽기. (꼭 고칠 것, 보면 좋은 것)"""
    voices, pairs = roster()
    named = isinstance(spec.get("narrator"), str) and spec["narrator"] in voices or isinstance(spec.get("cast"), str) and spec["cast"] in pairs
    must, should = [], []
    if isinstance(spec.get("narrator"), str) and spec["narrator"] not in voices and spec["narrator"] not in ("host", "guide"):
        must.append(f"narrator '{spec['narrator']}' 는 확정 목소리가 아니에요({', '.join(voices)}).")
    if isinstance(spec.get("cast"), str) and spec["cast"] not in pairs and spec["cast"] != "duo":
        must.append(f"cast '{spec['cast']}' 는 없는 조합이에요({', '.join(pairs)}).")
    pick = spec.get("voice_pick")
    if named and not pick:
        must.append('voice_pick 이 없어요. {"mode": "solo|A|B", "voices": [...], "why": "고른 까닭"} 을 적어 주세요.')
    if pick and not (pick.get("mode") and pick.get("voices") and pick.get("why")):
        must.append("voice_pick 에 mode·voices·why 가 다 있어야 해요.")
    if not pick:
        if not spec.get("narrator") and not spec.get("cast"):
            should.append("목소리를 고르지 않아서 예전 채널 목소리로 읽어요. rules/daily/voice.md 대로 narrator·cast 와 voice_pick 을 적어 주세요.")
        return must, should
    lines = spec.get("lines") or []
    for n, l in enumerate(lines, 1):
        t = (l.get("read") or l.get("say") or "").replace("[[", "").replace("]]", "")
        if "  " in t:
            should.append(f"{n}번 문장: 띄어쓰기가 두 칸이에요.")
        if re.search(r"[,.?!](?=[가-힣A-Za-z0-9])", t):
            should.append(f"{n}번 문장: 문장부호 뒤에 띄어쓰기가 없어요('{t[:16]}…'). 붙여 읽혀요.")
        for run in re.split(r"[,.?!…]", t):
            if syllables(run) > 20:
                should.append(f"{n}번 문장: '{run.strip()[:14]}…' 이 쉼 없이 {syllables(run)}음절이에요. 뜻이 끊기는 곳에 쉼표를 넣거나 나눠 주세요.")
    if isinstance(spec.get("cast"), str):
        turns = sum(1 for a, b in zip(lines, lines[1:]) if a.get("who") != b.get("who"))
        if len(lines) > 4 and turns >= len(lines) - 1:
            should.append(f"2인 대화가 거의 한 문장씩 번갈아요({turns}번 바뀜). 실제 대화처럼 한 사람이 이어 말하는 곳을 두세요.")
    return must, should


def problems(spec):
    """대본 길이와 빠진 것을 알려 줘요. (꼭 고칠 것, 보면 좋은 것, 어림 길이)"""
    import build as B
    pm, ps = pick_problems(spec)
    spec = with_duo(spec)
    must, should = pm, ps
    lines = spec.get("lines") or []
    lo, hi = spec.get("length") or (35, 50)  # 저녁 추천처럼 짧게 만드는 영상은 "length": [20, 35]
    short = hi <= 40
    if not spec.get("headline"):
        must.append("headline(위쪽 고정 제목 두 줄)이 없어요.")
    else:
        import thumb
        should += thumb.problems(spec["headline"], "제목")
    few, many = (6, 16) if short else (8, 18)
    if not few <= len(lines) <= many:
        should.append(f"문장이 {len(lines)}개예요. {few}~{many}개가 좋아요.")
    for n, l in enumerate(lines, 1):
        if not l.get("say"):
            must.append(f"{n}번 문장에 say 가 없어요.")
        if n == 1 and spec.get("layout") != "rec" and not (l.get("photo") or l.get("photos") or l.get("video") or l.get("card")):
            must.append("1번 문장에 photo(또는 video·card)가 없어요.")
        if l.get("say") and B.units(l["say"]) > 42:
            should.append(f"{n}번 문장이 길어요({B.units(l['say']):.0f}칸). 두 문장으로 나누면 자막이 읽기 쉬워요.")
    if short and lines and lines[0].get("say") and estimate(lines[0]["say"]) > 2.6:
        should.append(f"첫 문장이 {estimate(lines[0]['say']):.1f}초쯤이에요. 1~2초 안에 상황이나 핵심이 들리게 줄여 주세요.")
    must += cast_problems(spec)
    m, s = talk_problems(spec)
    must, should = must + m, should + s
    if not spec.get("cast"):
        shown = line_photos(lines) if lines and (lines[0].get("photo") or lines[0].get("photos")) else []
        keys = {json.dumps(p, sort_keys=True) for ps in shown for p in ps}
        if shown and len(keys) < 8 and not short:
            should.append(f"서로 다른 사진이 {len(keys)}장이에요. 8~12장이 좋아요(사진이 자주 바뀌어야 끝까지 봐요).")
    run = 0
    if spec.get("layout") == "rec":  # 추천 쇼츠는 장면을 자막 조각마다 따로 정해요 (rec.problems)
        import rec
        m, s = rec.problems(spec)
        must, should = must + m, should + s
    for n, (a, b, vis) in enumerate([] if spec.get("layout") == "rec" else segments(lines)):
        if b - a >= 3 and not vis.get("card"):
            should.append(f"{a + 1}~{b}번 문장 동안 같은 그림이 이어져요. 2문장까지만 쓰고 바꿔 주세요.")
        run = run + 1 if vis.get("photos") and not vis.get("video") else 0
        if run == 4 and short:
            should.append(f"{a + 1}번 문장까지 사진만 네 번 이어져요. 영상 조각이나 가격·순서 그래픽을 섞어 주세요.")
    total = sum(estimate(l.get("say", "")) for l in lines) + sum(gaps(spec, lines)) + 1.6
    if total > LONGEST:
        must.append(f"읽는 데 {total:.0f}초쯤 걸려요. 59초 안으로 줄여 주세요.")
    elif total > hi + 3:
        should.append(f"읽는 데 {total:.0f}초쯤이에요. {lo}~{hi}초로 줄여 주세요.")
    elif total < lo - 3:
        should.append(f"읽는 데 {total:.0f}초쯤이에요. {lo}~{hi}초가 되게 늘리면 좋아요.")
    # 가격·시간 확인은 저녁 추천처럼 근거(facts)를 적는 영상만 해요. 매일 내레이션 쇼츠(10-voice)는 지금 규칙 그대로예요.
    m, s = verify(spec) if (spec.get("facts") is not None or spec.get("kind") == "저녁추천") else ([], [])
    must, should = must + m, should + s
    # 소재 출처·이용 조건 (2026-10-19 사용자가 정한 우선순위·회사 이미지 기준). 저녁 추천이나 "assets" 를 적은 영상만 봐요.
    if spec.get("assets") is not None or spec.get("kind") == "저녁추천":
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import media
        m, s = media.check(spec)
        must, should = must + m, should + s
    return must, should, total


def cast_problems(spec):
    """대화형: 등장인물마다 다른 목소리인지, 문장의 who 가 cast 에 있는지. (꼭 고칠 것)"""
    cast, out = spec.get("cast") or {}, []
    if not cast:
        if any(l.get("who") for l in spec.get("lines") or []):
            out.append('문장에 who 가 있는데 cast(등장인물 목소리)가 없어요.')
        return out
    voices = [c.get("voice") for c in cast.values()]
    if len(set(voices)) < len(voices) or None in voices:
        out.append("등장인물끼리 같은 목소리를 써요. 한 목소리로 두 사람을 하지 않아요(사람마다 voice 를 다르게).")
    for n, l in enumerate(spec.get("lines") or [], 1):
        if l.get("who") not in cast:
            out.append(f"{n}번 문장의 who({l.get('who')})가 cast 에 없어요.")
    if len({l.get("who") for l in spec.get("lines") or []}) < 2:
        out.append("cast 를 적었는데 한 사람만 말해요. 혼자 읽는 영상이면 cast 를 빼요.")
    if spec.get("narrator"):
        out.append("cast(대화형)와 narrator(혼자 읽기)를 같이 적었어요. 하나만 골라요.")
    return out


def talk_problems(spec):
    """말투·목소리 목록 확인. (꼭 고칠 것, 보면 좋은 것)"""
    must, should = [], []
    conf = talk_conf()
    if spec.get("talk") and spec["talk"] not in conf["styles"]:
        must.append(f"talk '{spec['talk']}' 가 video/talk.json 의 styles 에 없어요.")
    acts = set((talk_style(spec) or {}).get("act") or {})
    for n, l in enumerate(spec.get("lines") or [], 1):
        if l.get("act") and spec.get("talk") and l["act"] not in acts:
            should.append(f"{n}번 문장의 act '{l['act']}' 는 말투 '{spec['talk']}' 에 없어요({', '.join(sorted(acts))}).")
    for k, c in (spec.get("cast") or {}).items():
        if c.get("voice") and c["voice"] not in conf["voices"]:
            should.append(f"{k}({c.get('label', '')})의 목소리 {c['voice']} 가 video/talk.json voices 에 없어요. 성별·느낌을 적어 두면 조합을 돌려 쓰기 쉬워요.")
    return must, should


MONEY = re.compile(r"(?:(\d+)\s*만)?\s*(?:(\d+)\s*천)?\s*(\d[\d,]*)?\s*원")
MINUTES = re.compile(r"(\d+)\s*분(?![의기류])")


def _amounts(text):
    """글 속 금액들 [(원문, 원)]. 7,500원 · 5만 원 · 4만 7천 원 · 3천 원 모두 읽어요."""
    out = []
    for m in MONEY.finditer(text.replace("[[", "").replace("]]", "")):
        if not (m[1] or m[2] or m[3]):
            continue
        v = int(m[1] or 0) * 10000 + int(m[2] or 0) * 1000 + int((m[3] or "0").replace(",", ""))
        out.append((m[0].strip(), v))
    return out


def verify(spec):
    """가격·시간 확인 (2026-10-19 사용자가 정함: 검증되지 않은 정보를 사실처럼 말하지 않는다).

    "facts": [{"id": "udon", "what": "CU 고메김치우동한그릇", "value": 4500, "unit": "원", "src": "CU 홈페이지 상품 목록",
               "url": "...", "checked": "2026-10-19", "status": "확인" | "추정" | "미확인"}, ...]
    카드의 줄에 "fact": "udon" 을 적으면 값이 같은지 봐요. 제목·대사의 금액은 근거(사실, 합계, 예산, 남는 돈)와 같아야 하고,
    추정이 섞인 합계를 말할 때는 "약·쯤·안팎"을 붙여야 해요. "N분" 같은 조리 시간은 확인된 시간 근거가 있을 때만 써요."""
    must, should = [], []
    facts = {f["id"]: f for f in spec.get("facts") or [] if f.get("id")}
    for f in facts.values():
        if f.get("status") == "확인" and not (f.get("src") and f.get("checked")):
            must.append(f"근거 '{f['id']}' 에 출처(src)나 확인 날짜(checked)가 없어요.")
    known, rough = set(), set()  # 말해도 되는 금액, 그중 추정이 섞인 것
    for f in facts.values():
        if f.get("unit") == "원" and f.get("status") in ("확인", "추정"):
            known.add(round(f["value"]))
            if f["status"] == "추정":
                rough.add(round(f["value"]))
    for n, l in enumerate(spec.get("lines") or [], 1):
        card = l.get("card") or {}
        items = card.get("items") or card.get("parts") or []
        if not items:
            continue
        est = bool(card.get("est"))
        for it in items:
            f = facts.get(it.get("fact")) if it.get("fact") else None
            if it.get("fact") and not f:
                must.append(f"{n}번 문장 카드의 '{it['name']}' 근거 '{it['fact']}' 가 facts 에 없어요.")
            if f and f.get("unit") == "원" and round(f["value"]) != round(it["price"]):
                must.append(f"{n}번 문장 카드의 '{it['name']}' 값 {won(it['price'])} 이 근거 {won(f['value'])} 와 달라요.")
            if f and f.get("status") != "확인" and not it.get("est"):
                must.append(f"{n}번 문장 카드의 '{it['name']}' 은 근거가 '{f.get('status')}' 이에요. \"est\": true 로 '약'을 붙여요.")
            if not it.get("fact"):
                should.append(f"{n}번 문장 카드의 '{it['name']}' 에 근거(fact)가 없어요.")
            est = est or bool(it.get("est"))
            known.add(round(it["price"]))
        total = sum(it["price"] for it in items)
        known.add(round(total))
        if est:
            rough.add(round(total))
        if card.get("budget"):
            known.add(round(card["budget"]))
            rest = card["budget"] - total
            if rest < 0:
                must.append(f"{n}번 문장 카드 합계 {won(total)} 가 예산 {won(card['budget'])} 을 넘어요. 제목이나 구성을 바꿔요.")
            known.add(round(rest))
            if est:
                rough.add(round(rest))
    for b in spec.get("budgets") or []:  # 제목에 쓰는 예산(만 원, 5만 원)
        known.add(round(b))

    def near(v, pool):
        return any(abs(v - k) <= max(100, k * 0.02) for k in pool)  # "약 4만 7천 원"처럼 반올림해 말한 것

    texts = [("제목", spec.get("headline", ""))] + [(f"{n}번 문장", l.get("say", "") + " " + l.get("read", ""))
                                                   for n, l in enumerate(spec.get("lines") or [], 1)]
    for where, text in texts:
        for raw, v in _amounts(text):
            if v in known:
                hit = v
            elif near(v, known):
                hit = min(known, key=lambda k: abs(k - v))
                if not re.search(r"약|쯤|안팎|정도|남짓", text):
                    must.append(f"{where}의 '{raw}' 는 근거 {won(hit)} 를 반올림했어요. '약'을 붙여요.")
                    continue
            else:
                must.append(f"{where}의 '{raw}' 는 근거(facts·카드 합계·예산)에 없는 금액이에요.")
                continue
            if hit in rough and not re.search(r"약|쯤|안팎|정도|남짓", text):
                must.append(f"{where}의 '{raw}' 는 추정이 섞인 값이에요. '약'이나 '쯤'을 붙여요.")
        for m in MINUTES.finditer(text):
            ok = any(f.get("unit") == "분" and f.get("status") == "확인" and round(f["value"]) == int(m[1]) for f in facts.values())
            if not ok:
                must.append(f"{where}의 '{m[0]}' 은 확인된 조리 시간 근거가 없어요. 숫자를 빼거나 facts 에 근거를 적어요.")
    if (spec.get("budgets") or any(l.get("card") for l in spec.get("lines") or [])) and not spec.get("basis"):
        should.append('"basis"(몇 명 기준인지, 밥·양념·음료·배송비를 넣었는지)를 적어요.')
    return must, should
