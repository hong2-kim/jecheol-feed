# -*- coding: utf-8 -*-
"""말투·호흡 B안 (2026-11-12 사용자 승인: "B안_말투호흡개선.mp3 … 이걸로 전부 다해!").

목소리(Chirp3-HD)와 공통 설정은 그대로 두고, 사용자 녹음(방어축제 승인본)의 말투에 가깝게 읽힌 것을 골라요.
config.json youtube.style_b.apply_to 에 적힌 설계도(10-voice·3-dinner)에만 써요. 비우면 예전 읽기(voice.speak)로 돌아가요.

문장마다 하는 일
1. 빠르기 여러 가지 × 두 번 읽기로 후보를 만들어요(구글 TTS 의 speakingRate. 만든 소리를 배속하지 않아요).
2. 물음표 문장에 쉼표가 있으면 쉼표 앞·뒤를 따로 읽힌 짝도 후보로 넣어요(앞 조각 첫 말이 높게 튀지 않고 끝이 내려가게).
3. 문장 가운데 0.25초 넘는 조용한 곳은 0.2초로 줄여요(말소리는 자르거나 늘이지 않아요).
4. 잰 값으로 줄 세워요: 참고 녹음 말 빠르기(물음 6.5·나머지 7.1 음절/초)와의 차이, 늘어짐, 물음 끝 오름, 쉼표 앞 조각 음높이.
5. 앞 문장에 붙여 받아쓰기(faster-whisper)해서 대본 낱말이 다 들리는 첫 후보를 써요(뭉갬·조사 빠짐을 걸러요).
   다 걸리면 긴 지명 낱말을 띄어 읽힌 글('모슬포항에서'→'모슬포 항에서')로 한 번 더 해 보고, 그래도 안 되면 가장 나은 것을 쓰고 경고를 남겨요.
"""
import json
import os
import re
from pathlib import Path

import numpy as np

import voice as V

REF_SPS = {"ask": 6.5, "say": 7.1}
APPROVED = {"rise": 4.8, "front": (1.1, -3.9)}  # 사용자가 고른 B안 1번 문장에서 잰 값(물음 끝, 쉼표 앞 첫 말 높이·끝 내려감)  # 방어축제 승인본(사용자 녹음)에서 잰 쉼 뺀 음절/초
RATE_STEPS = (0.9, 0.96, 1.02, 1.08, 1.14)  # 말투별 기본 빠르기에 곱해요
TAKES = (None, 2)
REC_BREATH = 0.34  # 저녁 추천 한 줄 안 문장 사이 쉼(초)
MORE_TAKES = (3, 4, 5)  # 받아쓰기에 안 들린 말이 남았을 때 더 읽혀 보는 차례
SPLIT_FRONT = (0.92, 1.0)  # 쉼표 앞 조각 빠르기(배): 기본 빠르기에 곱해요
SPLIT_BACK = (0.94, 0.98)
SPLIT_BREATH = 0.15
MID_MAX, MID_TO = 0.25, 0.2
ASR_TRIES = 5
PARTICLES = ("에서", "에게", "으로", "까지", "부터", "에", "로", "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "의")
PLACE_END = set("항시군구동읍면리도산강섬역장포")


def conf():
    yt = json.loads((V.ROOT / "config.json").read_text(encoding="utf-8")).get("youtube") or {}
    return yt.get("style_b") or {}


def applies(spec):
    """B안을 쓰는 설계도인지. apply_to 에 "*" 가 있으면 목소리를 고른(voice_pick) 모든 나레이션(2026-11-13 사용자: 나레이션이 들어가는 모든 콘텐츠)."""
    to = conf().get("apply_to") or []
    if not (V.breathing(spec) and ("*" in to or spec.get("_name") in to)):
        return False
    sp = V.with_duo(spec)  # 직접 녹음한 목소리('user-recording', 방어축제)처럼 TTS 가 아닌 목소리는 건드리지 않아요
    voices = [(sp.get("narrator") or {}).get("voice")] + [(c or {}).get("voice") for c in (sp.get("cast") or {}).values()]
    return all(v is None or str(v).startswith("ko-KR-") for v in voices) and any(voices)


# ── 받아쓰기 ──
_ASR = {"model": None, "failed": False}
_LAST = {"text": ""}  # 앞 문장 대본(받아쓰기 견줄 때 앞에 붙여요)


def _asr_model():
    if _ASR["model"] is None and not _ASR["failed"]:
        try:
            from faster_whisper import WhisperModel
            name = os.environ.get("VOICE_ASR_MODEL") or conf().get("asr_model") or "medium"
            local = V.ROOT.parent / "local-voice-studio" / "models" / ("asr-review" if name == "medium" else "asr")
            if name in ("small", "medium") and (local / "model.bin").is_file():
                name = str(local)  # 이 컴퓨터에 받아 둔 모델
            _ASR["model"] = WhisperModel(name, device="cpu", compute_type="int8")
        except Exception as e:  # 받아쓰기가 없으면 잰 값만으로 골라요
            print(f"  받아쓰기를 못 써요({type(e).__name__}: {str(e)[:80]}) → 잰 값으로만 골라요")
            _ASR["failed"] = True
    return _ASR["model"]


def heard(x):
    """받아쓰기 글. 파일로 쓰지 않고 16kHz 소리를 바로 넘겨요(클라우드의 PyAV 판에서 파일 열기가 깨졌어요, 2026-11-13)."""
    m = _asr_model()
    if m is None:
        return None
    n = int(len(x) * 16000 / V.SR)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    segs, _ = m.transcribe(y, language="ko", beam_size=5, vad_filter=False, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs)


UNITS = (("kcal", "킬로칼로리"), ("mg", "밀리그램"), ("kg", "킬로그램"), ("km", "킬로미터"), ("ml", "밀리리터"), ("g", "그램"), ("%", "퍼센트"))


def _norm(t):
    t = re.sub(r"[\s,.?!~…\"'“”‘’·]", "", t)
    for a, b in UNITS:  # 받아쓰기가 단위를 기호로 적어요
        t = re.sub(a, b, t, flags=re.I)
    return t.replace("구요", "고요")


def _near(w, got, least=0.8):
    """받아쓰기 글에서 w 와 가장 비슷한 같은 길이 조각이 least 이상이면 들린 것으로 쳐요('모술포항' 같은 한 글자 차이는 넘어가요)."""
    from difflib import SequenceMatcher
    n = len(w)
    return any(SequenceMatcher(None, w, got[k: k + n]).ratio() >= least for k in range(max(1, len(got) - n + 1)))


# ── 소리대로 견주기 (2026-11-13: 모든 나레이션에 발음 검사를 넓히며) ──
# 받아쓰기는 들린 소리대로 적어요: '반각굴이'→'반각구리'(연음), '홈부터'→'놈부터'(ㅎ 약화), '피꼬막'→'핏꼬막'(사이시옷).
# 글자로만 견주면 바르게 읽은 말도 '안 들림'이 돼서, 자모로 풀어 소리가 같으면 들린 것으로 쳐요. '불금엔→불구멘'(모음이 바뀜)·
# '광어회→광어에'·'당기면→단기면'처럼 소리가 달라진 것은 그대로 잡혀요.
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_TENSE = set("ㄲㄸㅃㅆㅉ")


def sound(t):
    """한글을 소리 자모로: 초성 ㅇ·ㅎ 은 빼고(연음·ㅎ 약화), 된소리 앞 받침 ㅅ 은 빼요(사이시옷). 한글 아닌 글자는 버려요."""
    out = []
    for ch in t:
        k = ord(ch) - 0xAC00
        if not 0 <= k < 11172:
            continue
        cho, jung, jong = _CHO[k // 588], _JUNG[(k % 588) // 28], _JONG[k % 28]
        if cho not in "ㅇㅎ":
            out.append(cho)
        out.append(jung)
        out.append(jong)
    s = "".join(out)
    return "".join(c for i, c in enumerate(s) if not (c == "ㅅ" and i + 1 < len(s) and s[i + 1] in _TENSE))


NUM_WORD = re.compile(r"^(?:[영일이삼사오육칠팔구십백천만억]|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔|한|두|세|네)+"
                      r"(?:등|개|월|일|년|시|분|명|원|달러|도|위|번|째|살|배|곳|가지|퍼센트)?"
                      r"(?:은|는|이|가|을|를|에|에서|부터|까지|도|만|의|쯤|정도|남짓|이요|예요|이에요)?$")


def heard_as_number(w, transcript):
    """대본은 '열일곱에서'·'십일월부터'처럼 우리말 수로 읽혔는데 받아쓰기는 '17에서'·'11월부터'로 적은 경우."""
    return bool(re.search(r"\d", transcript)) and bool(NUM_WORD.match(w))


def missing(text, transcript):
    """대본(숫자 없는 낱말만)에서 받아쓰기에 안 들린 낱말들. 숫자가 든 낱말은 받아쓰기 표기가 달라 빼요.
    글자가 달라도 소리가 같으면(연음·ㅎ 약화·사이시옷) 들린 것으로, 우리말 수로 읽은 숫자는 받아쓰기가 숫자로 적었으면 들린 것으로 쳐요."""
    got = _norm(transcript)
    got_s = sound(transcript)
    out = []
    for w in re.sub(r"\[\[|\]\]", "", text).split():
        w2 = _norm(w)
        ws = sound(w2)
        if len(ws) >= 3 and ws in got_s:
            continue
        if heard_as_number(w2, transcript):
            continue
        if len(w2) >= 2 and not re.search(r"[0-9A-Za-z]", w2) and w2 not in got and not (len(w2) >= 4 and _near(w2, got)):
            out.append(w)
    return out


def spaced(text, words):
    """안 들린 긴 지명 낱말을 띄어 읽혀요: '모슬포항에서' → '모슬포 항에서'. 자막(say)은 그대로예요."""
    new = text
    for w in words:
        core = re.sub(r"[^가-힣]", "", w)
        stem = core
        for p in PARTICLES:
            if core.endswith(p) and len(core) - len(p) >= 4:
                stem = core[: -len(p)]
                break
        if len(stem) >= 4 and stem[-1] in PLACE_END:
            new = new.replace(stem, stem[:-1] + " " + stem[-1], 1)
    return new


CONTRACT = (("엔", "에는"), ("겐", "게는"), ("껜", "께는"))  # 줄임 조사: TTS 가 뭉개요('불금엔→불구멘', 2026-11-13)


def unpacked(text, words):
    """안 들린 낱말이 줄임 조사로 끝나면 풀어 읽혀요: '불금엔' → '불금에는'. 자막(say)은 그대로예요."""
    new = text
    for w in words:
        core = re.sub(r"[^가-힣]", "", w)
        for a, b in CONTRACT:
            if len(core) >= 2 and core.endswith(a):
                new = new.replace(core, core[: -len(a)] + b, 1)
                break
    return new


# ── 잰 값 ──
def trim_mid(x):
    """문장 가운데 MID_MAX 넘는 조용한 곳을 MID_TO 로. (소리, [(그 자리 초, 줄인 초)])"""
    runs, _ = V._quiet(x, rel=0.05, least=3)
    win = V.SR // 100
    out, last, cut = [], 0, []
    for a, b in runs:
        if (b - a) / 100 > MID_MAX and a > 5 and b * win < len(x) - win * 5:
            out += [x[last: a * win], np.zeros(int(V.SR * MID_TO))]
            last = b * win
            cut.append((a / 100, (b - a) / 100 - MID_TO))
    out.append(x[last:])
    return np.concatenate(out), cut


def _shift(t, cut):
    return t - sum(d for at, d in cut if at < t)


def _st(a, b):
    return 12 * np.log2(a / b)


def _med(f, a, b):
    s = f[int(a * 100): int(b * 100)]
    s = s[s > 0]
    return float(np.median(s)) if len(s) >= 3 else None


def front_shape(x, front_end, front_text):
    """쉼표 앞 조각: 첫 낱말이 문장 평균보다 몇 반음 높은지, 끝 낱말 끝이 처음보다 몇 반음 내려가는지."""
    f = V._f0(x)
    whole = _med(f, 0, len(x) / V.SR * 0.75)
    ws = front_text.rstrip(",").split()
    syl = [max(1, V.syllables(w)) for w in ws]
    tot = sum(syl)
    first_end = front_end * syl[0] / tot
    last_start = front_end * (tot - syl[-1]) / tot
    j = _med(f, 0, first_end)
    span = front_end - last_start
    hd, tl = _med(f, last_start, last_start + span * 0.35), _med(f, front_end - span * 0.3, front_end)
    height = _st(j, whole) if j and whole else 0.0
    fall = _st(tl, hd) if hd and tl else 0.0
    return round(height, 1), round(fall, 1)


def measure(x, s, last_line, front_end=None):
    net = V.syllables(s) / max(0.05, len(x) / V.SR - V._pauses(x))
    bad = V.drawn(x, s)[0]
    ask = s.rstrip().endswith("?")
    m = {"sps": round(net, 2), "drawn": bool(bad)}
    p = abs(net - REF_SPS["ask" if ask else "say"]) + (2 if bad else 0)
    if ask:
        r = V.rise_of(x)
        m["rise"] = r
        low = 2.5 if last_line else V.RISE  # 끝 권유 물음은 참고 녹음도 부드럽게 끝나요(0.7반음)
        p += 3 if r is None or r < low else (1.5 if r > 8 else 0)
        if r is not None and not last_line:
            p += abs(r - APPROVED["rise"]) * 0.3  # 승인본 물음 끝(4.8반음)에 가깝게
    if ask and front_end:
        h, fl = front_shape(x, front_end, s.split(",")[0])
        m["front"] = (h, fl)
        if not last_line:  # 첫 말이 튀지 않고 끝이 내려가게. 승인본(1.1·−3.9반음)에 가깝게
            p += abs(h - APPROVED["front"][0]) * 0.5 + abs(fl - APPROVED["front"][1]) * 0.3 + max(0, h - 1.6)
    m["score"] = round(p, 2)
    return m


# ── 한 문장 ──
def _loud(v):
    return v * min(V.LOUD / max(1e-9, np.sqrt(np.mean(v ** 2))), 0.98 / max(1e-9, np.abs(v).max()))


def candidates(s, c, rate, pace, last_line, takes=None):
    out = []
    for k in RATE_STEPS:
        r = round(rate * k, 3)
        for t in (takes or TAKES):
            x = V.tts(s, c.get("voice"), r, take=t, tail=0.12)
            if x is None:
                return None
            y, starts, breaths, slow = V.comma_breath(x, s, c, r, pace)
            y, cut = trim_mid(y)
            starts = [_shift(t0, cut) for t0 in starts]
            fe = starts[1] if s.endswith("?") and len(starts) > 1 else None
            m = measure(y, s, last_line, fe)
            if slow:
                m["score"] += 1
            out.append({"x": y, "edges": starts, "rate": r, "take": t or 1, "how": f"빠르기 {r}·{t or 1}번째 읽기", "m": m, "comma": max([0.0] + breaths)})
    ps = V.phrases(s)
    if s.endswith("?") and len(ps) == 2 and not takes:  # 쉼표 앞·뒤 따로 읽기(1번 '제주에서 방어축제에,' 고친 방법)
        front = ps[0].strip()
        front = front if front.endswith(",") else front + ","
        back = ps[-1].strip()
        for kf in SPLIT_FRONT:
            for tf in TAKES:
                a = V.tts(front, c.get("voice"), round(rate * kf, 3), take=tf, tail=0.05)
                for kb in SPLIT_BACK:
                    for tb in TAKES:
                        b = V.tts(back, c.get("voice"), round(rate * kb, 3), take=tb, tail=0.12)
                        if a is None or b is None:
                            continue
                        a2 = a * np.sqrt(np.mean(b ** 2) / max(1e-12, np.mean(a ** 2)))
                        y = np.concatenate([a2, np.zeros(int(V.SR * SPLIT_BREATH)), b])
                        y, cut = trim_mid(y)
                        fe = _shift(len(a2) / V.SR, cut)
                        m = measure(y, s, last_line, fe)
                        out.append({"x": y, "edges": [0.0, round(fe + SPLIT_BREATH, 3)],
                                    "rate": round(rate * kf, 3), "take": f"{tf or 1}+{tb or 1}",
                                    "how": f"쉼표 앞뒤 따로 읽음(앞 {round(rate * kf, 3)}·뒤 {round(rate * kb, 3)})", "m": m, "comma": SPLIT_BREATH})
    return out


def choose(cands, s_text, prev, prev_text=""):
    """잰 값 앞 순서 ASR_TRIES 개를 앞 문장에 붙여 받아쓰기하고, 대본과 글자가 가장 많이 맞는 것을 써요.
    (첫 통과 후보를 쓰면 '탄산음료→탄산음류' 같은 한 글자 뭉갬이 지나갔어요, 2026-11-12 시험)
    (후보, 안 들린 낱말 또는 None)"""
    from difflib import SequenceMatcher
    cands = sorted(cands, key=lambda c: c["m"]["score"])
    lead = np.concatenate([prev, np.zeros(int(V.SR * 0.3))]) if prev is not None else np.zeros(0)
    want = _norm((prev_text + " " if prev is not None else "") + s_text)
    tried = []
    for c in cands[:ASR_TRIES]:
        t = heard(np.concatenate([lead, c["x"]]))
        if t is None:
            return cands[0], None  # 받아쓰기 없음
        c["heard"] = t
        c["match"] = SequenceMatcher(None, want, _norm(t)).ratio()
        tried.append(c)
    top = max(c["match"] for c in tried)
    # 한 글자 차이(긴 문장에서 0.01 안팎)도 가려요. 거의 같은 것(0.004 안)끼리만 잰 값으로 골라요 ('당기면→단기면', 2026-11-12)
    best = min((c for c in tried if c["match"] >= top - 0.004), key=lambda c: c["m"]["score"])
    return best, missing(s_text, best["heard"])


def speak(spec, lines, i, c, prev=None):
    """voice.speak 자리에서 불러요. 결과 모양(소리, 기록)은 voice.read_line 과 같아요."""
    l, pace = lines[i], V.pace_of(spec, lines, i)
    if i == 0:
        _LAST["text"] = ""
    if l.get("rate") or l.get("take"):  # 설계도에 빠르기·읽기를 직접 적었으면 그대로
        return V.speak(spec, lines, i, c)
    rate = round(float(c.get("rate") or V._voice_conf()[1]) * V.PACE[pace], 3)
    said = V.spoken(l)
    check = re.sub(r"\[\[|\]\]", "", l.get("read") or l["say"])
    parts = V.sentences(said)
    checks = V.sentences(check) if len(V.sentences(check)) == len(parts) else [check] * len(parts)
    pieces, why, warn, edges, at, sent, commas, speech = [], [], [], [], 0.0, [], [], []
    for k, s in enumerate(parts):
        last_line = i == len(lines) - 1 and k == len(parts) - 1
        cands = candidates(s, c, rate, pace, last_line)
        if cands is None:
            return None, {}
        ctx = speech[-1] if speech else prev  # 앞 말소리(사이 쉼 말고)
        ctx_text = checks[k - 1] if k else _LAST.get("text", "")
        best, miss = choose(cands, checks[k], ctx, ctx_text)
        used = s
        if miss:
            s2 = spaced(s, miss)
            if s2 != s:
                c2 = candidates(s2, c, rate, pace, last_line)
                b2, m2 = choose(c2, checks[k], ctx, ctx_text) if c2 else (None, miss)
                if b2 is not None and (not m2 or len(m2) < len(miss)) and b2.get("match", 0) >= best.get("match", 0):
                    why.append(f"받아쓰기에 안 들린 '{' '.join(miss)}' 를 띄어 읽음")
                    best, miss, used = b2, m2, s2
        if miss:  # 모든 B안 나레이션(2026-11-13 사용자: 발음 검사 공통). 처음엔 저녁 추천에서: '불금엔→불구멘', '광어회→광어에'가 경고만 남고 그대로 나갔어요
            u = unpacked(used, miss)  # ① 줄임 조사를 풀어 다시 합성('불금엔'→'불금에는'), 받아쓰기도 푼 말로 견줘요
            if u != used:
                c4 = candidates(u, c, rate, pace, last_line)
                b4, m4 = choose(c4, unpacked(checks[k], miss), ctx, ctx_text) if c4 else (None, miss)
                if b4 is not None and (not m4 or len(m4) < len(miss)):
                    why.append(f"받아쓰기에 안 들린 '{' '.join(miss)}' 를 풀어 읽음({u})")
                    best, miss, used = b4, m4, u
        if miss:  # ② 같은 글로 다른 읽기를 더 만들어 한 번 더 골라요
            more = candidates(used, c, rate, pace, last_line, takes=MORE_TAKES)
            if more:
                b3, m3 = choose(more, checks[k] if used == s else unpacked(checks[k], miss), ctx, ctx_text)
                if b3 is not None and (not m3 or len(m3) < len(miss)):
                    why.append(f"받아쓰기에 안 들린 '{' '.join(miss)}' 때문에 다시 읽혀 고름")
                    best, miss = b3, m3
        if miss:
            warn.append(f"받아쓰기에 안 들린 낱말: {', '.join(miss)} (들린 말: {(best.get('heard') or '')[-40:]})")
        m = best["m"]
        if best.get("match") is not None:
            why.append(f"받아쓰기 일치 {best['match']:.3f}")
        why.append(f"B안: {best['how']}, 쉼 뺀 {m['sps']}음절/초" + (f", 물음 끝 {m['rise']}반음" if m.get("rise") is not None else "")
                   + (f", 쉼표 앞 첫 말 {m['front'][0]}·끝 {m['front'][1]}반음" if m.get("front") else ""))
        if m["drawn"]:
            warn.append(f"늘어져요('{s[:14]}…')")
        edges += [at + t for t in best["edges"]]
        sent.append(used)
        commas.append(best["comma"])
        pieces.append(best["x"])
        speech.append(best["x"])
        at += len(best["x"]) / V.SR
        if k < len(parts) - 1:
            g = int(V.SR * (0.24 if s.endswith("?") else 0.2))
            if spec.get("kind") == "저녁":  # 저녁 추천: 한 문장 안 두 마디('두툼한 함박스테이크. / 든든한 한 끼가…') 사이에 숨 쉴 틈(2026-11-13 사용자: "숨넘어가")
                g = max(g, int(V.SR * REC_BREATH))
            pieces.append(np.zeros(g))
            at += g / V.SR
    v = _loud(np.concatenate(pieces))
    _LAST["text"] = check
    sps = V.syllables(said) / max(0.01, len(v) / V.SR - V._pauses(v))
    who = next((k for k, cc in (spec.get("cast") or {}).items() if cc is c), "") or (c.get("voice") or "").rsplit("-", 1)[-1].lower()
    return v, {"n": i + 1, "who": who, "voice": c.get("voice"), "pace": pace, "rate": rate, "say": l["say"], "tts": sent,
               "why": why, "sec": round(len(v) / V.SR, 2), "sps": round(sps, 1), "comma": round(max(commas or [0.0]), 2), "warn": warn,
               "edges": [round(t, 3) for t in edges], "style": "B"}
