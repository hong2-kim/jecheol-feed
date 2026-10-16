# -*- coding: utf-8 -*-
"""먹고갈지도만의 배경음악. 저작권 걱정 없이 쓰려고 직접 만들어요. (2026-10-15)

  python video/brand_music.py          video/audio/brand-*.wav 를 만들어요 (각 16초, 처음과 끝이 이어지게)

모든 곡은 같은 "먹고갈지도" 짧은 가락(솔-미-라-솔, 마지막은 도)으로 끝나서, 어느 곡이든 우리 채널 소리로 들려요.
시끄럽지 않게: 드럼은 가볍게, 소리 크기는 audio.build 가 맞춰요.
"""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from audio import SR, bass, bell, clap, env, hat, hz, kick, load_wav, pluck, put, reed, smooth  # noqa: E402

HERE = Path(__file__).parent
LEN = 16.0

# 먹 고 갈 지 도 — 끝에 늘 붙는 가락 (미디 음, 박)
MOTIF = [(67, .5), (64, .5), (69, .5), (67, .5), (72, 1.5)]


def epiano(note, dur):
    """부드러운 전자 피아노."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = hz(note)
    x = np.sin(2 * np.pi * f * t + 0.8 * np.exp(-3 * t) * np.sin(2 * np.pi * f * t)) + 0.25 * np.sin(4 * np.pi * f * t) * np.exp(-5 * t)
    return x * np.exp(-1.6 * t) * env(n, 0.006, 0.12)


def marimba(note, dur):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = hz(note)
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-30 * t)) * np.exp(-7 * t) * env(n, 0.002, 0.04)


def shaker(loud=1.0):
    n = int(SR * 0.07)
    x = smooth(np.random.default_rng(3).uniform(-1, 1, n), 2)
    x = x - smooth(x, 5)
    return x * np.sin(np.linspace(0, np.pi, n)) * loud


def motif(track, at, beat, voice, gain, shift=0):
    t = at
    for note, b in MOTIF:
        put(track, t, voice(note + shift, beat * b + 0.4), gain)
        t += beat * b


def walk(dur):
    """1. 지도 산책 — 느긋한 전자 피아노와 가벼운 박자. 어떤 영상에도 무난해요."""
    beat = 60 / 86
    tr = np.zeros(int(SR * (dur + 2)))
    prog = [((60, 64, 67, 71), 36), ((57, 60, 64, 67), 33), ((53, 57, 60, 64), 29), ((55, 59, 62, 65), 31)]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        chord, root = prog[bar % 4]
        for i, n in enumerate(chord):
            put(tr, t + i * 0.03, epiano(n, beat * 3.6), 0.16)
        put(tr, t + 2.5 * beat, epiano(chord[-1] + 12, beat), 0.10)
        put(tr, t, bass(root + 12, beat * 2), 0.42)
        put(tr, t + 2 * beat, bass(root + 19, beat * 1.5), 0.30)
        for b in range(4):
            put(tr, t + b * beat, kick(), 0.30 if b in (0, 2) else 0)
            put(tr, t + b * beat + beat / 2, hat(0.6), 0.06)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, epiano, 0.30)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def market(dur):
    """2. 골목 시장 — 통통 튀는 기타 줄과 쉐이커. 저녁 TOP 5, 지역의 먹거리에 어울려요."""
    beat = 60 / 104
    tr = np.zeros(int(SR * (dur + 2)))
    prog = [((60, 64, 67), 36), ((65, 69, 72), 41), ((67, 71, 74), 43), ((60, 64, 67), 36)]
    patt = [0, 2, 1, 2, 0, 2, 1, 2]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        chord, root = prog[bar % 4]
        for s in range(8):
            put(tr, t + s * beat / 2, pluck(chord[patt[s]] + 12, beat * 0.8, 0.75), 0.26)
            put(tr, t + s * beat / 2, shaker(0.9 if s % 2 else 0.5), 0.08)
        put(tr, t, bass(root, beat * 1.4), 0.45)
        put(tr, t + 1.5 * beat, bass(root + 7, beat * .5), 0.30)
        put(tr, t + 2 * beat, bass(root + 12, beat * 1.4), 0.38)
        put(tr, t, kick(), 0.35)
        put(tr, t + 2 * beat, kick(), 0.35)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, lambda n, d: pluck(n + 12, d, 0.8), 0.40)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def night(dur):
    """3. 포장마차 밤 — 느린 재즈 걸음 베이스와 아코디언. 술 조합·저녁 영상에 어울려요."""
    beat = 60 / 92
    tr = np.zeros(int(SR * (dur + 2)))
    prog = [((62, 65, 69, 72), [38, 41, 45, 43]), ((67, 71, 74, 77), [43, 47, 50, 48]),
            ((60, 64, 67, 71), [36, 40, 43, 45]), ((57, 61, 64, 67), [45, 43, 40, 37])]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        chord, walk_notes = prog[bar % 4]
        for n in chord:
            put(tr, t + beat * .66, reed(n, beat * 1.2), 0.10)
            put(tr, t + beat * 2.66, reed(n, beat * 1.0), 0.08)
        for b, n in enumerate(walk_notes):
            put(tr, t + b * beat, bass(n, beat * .95), 0.45)
            put(tr, t + b * beat + beat * .66, hat(0.5), 0.06)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, lambda n, d: reed(n, d), 0.30, shift=-12)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def picnic(dur):
    """4. 주말 나들이 — 맑은 마림바. 제철 체크·한 장 정리처럼 밝은 영상에 어울려요."""
    beat = 60 / 112
    tr = np.zeros(int(SR * (dur + 2)))
    riff = [72, 76, 79, 76, 74, 77, 81, 77, 72, 76, 79, 84, 83, 79, 74, 71]
    roots = [48, 53, 55, 48]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        for s in range(8):
            put(tr, t + s * beat / 2, marimba(riff[(bar * 8 + s) % 16], beat * .8), 0.24)
        put(tr, t, bass(roots[bar % 4], beat * 1.8), 0.40)
        put(tr, t + 2 * beat, bass(roots[bar % 4] + 7, beat * 1.8), 0.32)
        for b in range(4):
            put(tr, t + b * beat, shaker(0.8), 0.07)
        put(tr, t, kick(), 0.25)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, lambda n, d: bell(n + 12, d), 0.22)
    motif(tr, t, beat, marimba, 0.20)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def munch(dur):
    """5. 냠냠 박자 — 통통 튀는 줄 소리에 진짜 먹는 소리(짭짭짭, 바삭, 꿀꺽)를 박자에 맞춰 얹어요. 요즘 뜨는 메뉴에 어울려요. (2026-10-16)

    먹는 소리는 audio/eat/ 에 잘라 둔 퍼블릭 도메인 녹음이에요(위키미디어 공용, 원래 pdsounds.org).
    짭: "Chewing gum mouth open"(ezwa), 바삭: "Eating potato snacks"(russiandoll), 꿀꺽: "Swallowing gulp"(gregoryweir).
    """
    beat = 60 / 100
    tr = np.zeros(int(SR * (dur + 2)))
    chew = [load_wav(f"eat/chew{i}") for i in range(1, 5)]
    crunch = [load_wav(f"eat/crunch{i}") for i in range(1, 5)]
    riffs = [[72, 76, 79, 76, 77, 76, 74, 71], [72, 76, 79, 81, 79, 76, 74, 72]]
    roots = [48, 53, 55, 48]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        for s, n in enumerate(riffs[bar % 2]):
            if s not in (1, 2, 3):  # 짭짭짭 자리는 비워서 먹는 소리가 들리게 해요
                put(tr, t + s * beat / 2, pluck(n, beat * .45, 0.9), 0.22)
        put(tr, t, bass(roots[bar % 4], beat * .9), 0.30)
        put(tr, t + 2 * beat, bass(roots[bar % 4] + 7, beat * .9), 0.24)
        put(tr, t, kick(), 0.22)
        put(tr, t + 2 * beat, kick(), 0.22)
        put(tr, t + beat, clap(), 0.10)
        put(tr, t + 3 * beat, clap(), 0.10)
        for k, s in enumerate((1, 2, 3)):  # 짭 짭 짭
            put(tr, t + s * beat / 2, chew[(bar + k) % 4], 1.0)
        put(tr, t + 6 * beat / 2, crunch[bar % 4], 0.85)  # 바삭
        if bar % 2:
            put(tr, t + 7 * beat / 2, chew[(bar + 1) % 4], 0.6)
        bar += 1
        t += 4 * beat
    put(tr, t - beat * .5, load_wav("eat/gulp"), 0.9)  # 꿀꺽, 그리고 먹고갈지도 가락
    motif(tr, t, beat, lambda n, d: pluck(n + 12, d, 0.8), 0.40)
    motif(tr, t, beat, lambda n, d: bell(n + 12, d), 0.14)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def supersaw(note, dur, width=0.012, k=6):
    """여러 겹 톱니파를 조금씩 어긋나게 겹친 밝은 신스. 부드럽게 깎아 써요."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = hz(note)
    x = sum((2 * ((f * (1 + d) * t + ph) % 1) - 1) for d, ph in zip((-width, -width / 2, 0, width / 2, width), (0, .3, .6, .1, .8)))
    return smooth(x / 5, k) * env(n, 0.01, 0.08)


def pump(n, beat, depth=0.65):
    """박자마다 숨 쉬듯 줄었다 커지는 크기 (사이드체인 느낌)."""
    t = (np.arange(n) / SR) % beat
    return 1 - depth * np.exp(-t / (beat * 0.18))


def horizon(dur):
    """6. 밝은 지평선 — 처음부터 밝은 신스 화음과 반짝이는 아르페지오로 시작하는 신나는 전자음. (2026-10-16, 사용자가 'Vibrant Horizon - Hyperstring' 같은 곡을 원함)"""
    beat = 60 / 120
    n = int(SR * (dur + 2))
    tr = np.zeros(n)
    pad = np.zeros(n)
    prog = [((60, 64, 67, 72), 48), ((55, 59, 62, 67), 43), ((57, 60, 64, 69), 45), ((53, 57, 60, 65), 41)]
    arp = [0, 1, 2, 3, 2, 1, 2, 3]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        chord, root = prog[bar % 4]
        for c in chord:
            put(pad, t, supersaw(c, beat * 4), 0.10)
        for s in range(8):
            put(tr, t + s * beat / 2, pluck(chord[arp[s]] + 12, beat * .5, 0.95), 0.20)
        for b in range(4):
            put(tr, t + b * beat, bass(root, beat * .9), 0.34)
            put(tr, t + b * beat + beat / 2, bass(root + 12, beat * .4), 0.18)
            if bar or b >= 2:  # 첫 마디 앞 두 박은 신스만, 그다음 박자가 들어와요
                put(tr, t + b * beat, kick(), 0.30)
            put(tr, t + b * beat + beat / 2, hat(0.9), 0.07)
        put(tr, t + beat, clap(), 0.12)
        put(tr, t + 3 * beat, clap(), 0.12)
        bar += 1
        t += 4 * beat
    tr += pad * pump(n, beat)
    motif(tr, t, beat, lambda n_, d: pluck(n_ + 12, d, 0.9), 0.40)
    motif(tr, t, beat, lambda n_, d: bell(n_ + 12, d), 0.16)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def horizon_chill(dur):
    """7. 노을 지평선 — 같은 밝은 결인데 조금 느리고 둥근 소리. 퓨처베이스처럼 화음이 숨 쉬듯 출렁여요. (2026-10-16)"""
    beat = 60 / 100
    n = int(SR * (dur + 2))
    tr = np.zeros(n)
    pad = np.zeros(n)
    prog = [((57, 60, 64, 71), 45), ((53, 57, 60, 67), 41), ((60, 64, 67, 74), 48), ((55, 59, 62, 69), 43)]
    lead = [[76, 79, 81, 79], [77, 76, 72, 74], [79, 81, 84, 83], [79, 74, 76, 74]]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        chord, root = prog[bar % 4]
        for c in chord:
            put(pad, t, supersaw(c, beat * 4, 0.008, 10), 0.13)
        for s, note in enumerate(lead[bar % 4]):
            put(tr, t + s * beat, bell(note, beat * 1.2), 0.11)
            put(tr, t + s * beat + beat * .5, pluck(note - 12, beat * .4, 0.8), 0.10)
        put(tr, t, bass(root, beat * 1.8), 0.36)
        put(tr, t + 2.5 * beat, bass(root, beat * 1.2), 0.28)
        put(tr, t, kick(), 0.30)
        put(tr, t + 2.5 * beat, kick(), 0.22)
        put(tr, t + 2 * beat, clap(), 0.13)
        for h in range(8):
            put(tr, t + h * beat / 2 + beat / 4, hat(0.7), 0.05)
        bar += 1
        t += 4 * beat
    tr += pad * pump(n, beat, 0.75)
    motif(tr, t, beat, lambda n_, d: bell(n_ + 12, d), 0.26)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def curious(dur):
    """8. 궁금궁금 — 발끝으로 걷는 듯한 짧은 줄 튕김과 반음씩 기어오르는 베이스, 마디 끝에 "응?" 하고 올라가는 종소리.
    단조로 궁금하게 끌다가 끝의 먹고갈지도 가락(장조)에서 풀려요. 1위를 밝히는 저녁 TOP 5에 어울려요. (2026-10-16 사용자가 궁금한 느낌을 원함)"""
    beat = 60 / 112
    tr = np.zeros(int(SR * (dur + 2)))
    # 라단조: Am - Am - F - E. 베이스는 한 박씩 짧게 끊어 살금살금 걸어요.
    walk_notes = [[45, 48, 52, 51], [45, 48, 52, 53], [41, 45, 48, 47], [40, 44, 47, 44]]
    tops = [[69, 72, 76, 75], [69, 72, 76, 77], [65, 69, 72, 71], [64, 68, 71, 68]]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        for b in range(4):
            put(tr, t + b * beat, bass(walk_notes[bar % 4][b], beat * .35), 0.48)
            put(tr, t + b * beat + beat / 2, pluck(tops[bar % 4][b], beat * .3, 0.7), 0.24)  # 뒷박에 톡
            put(tr, t + b * beat + beat / 2, hat(0.5), 0.05)
        put(tr, t, kick(), 0.22)
        if bar % 2:  # 두 마디마다 "응?" 하고 올라가는 종소리
            put(tr, t + 3 * beat, bell(76, beat * .8), 0.10)
            put(tr, t + 3.5 * beat, bell(81, beat * 1.2), 0.12)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, lambda n, d: pluck(n + 12, d, 0.8), 0.40)
    motif(tr, t, beat, lambda n, d: bell(n + 12, d), 0.16)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


def sneak(dur):
    """9. 살금살금 — 궁금궁금과 같은 결. 마림바가 반음씩 내려가고, 손가락 튕기는 박수와 낮은 아코디언 화음이 깔려요.
    "어? 이게 뭐지?" 하고 들여다보는 발견형에 어울려요. (2026-10-16)"""
    beat = 60 / 100
    tr = np.zeros(int(SR * (dur + 2)))
    # 라단조: Am - Dm - E - Am
    chords = [(57, 60, 64), (57, 62, 65), (56, 59, 64), (57, 60, 64)]
    roots = [45, 38, 40, 45]
    lines = [[76, None, 75, None, 74, None, 73, None], [77, None, 76, None, 74, None, 72, None],
             [76, 71, 68, 71, 76, None, 80, None], [81, None, 76, 72, 69, None, None, None]]
    t, bar = 0.0, 0
    while t < dur - 4 * beat:
        for n in chords[bar % 4]:
            put(tr, t, reed(n - 12, beat * 3.5), 0.07)
        for s, n in enumerate(lines[bar % 4]):
            if n:
                put(tr, t + s * beat / 2, marimba(n, beat * .6), 0.26)
        put(tr, t, bass(roots[bar % 4], beat * .5), 0.45)
        put(tr, t + 1.5 * beat, bass(roots[bar % 4] + 7, beat * .3), 0.30)
        put(tr, t + 2 * beat, bass(roots[bar % 4], beat * .5), 0.40)
        put(tr, t + beat, clap(), 0.09)  # 손가락 튕기기처럼 작게
        put(tr, t + 3 * beat, clap(), 0.09)
        if bar % 4 == 3:  # 네 마디 끝에 "응?"
            put(tr, t + 3 * beat, bell(79, beat * .8), 0.10)
            put(tr, t + 3.5 * beat, bell(84, beat * 1.2), 0.12)
        bar += 1
        t += 4 * beat
    motif(tr, t, beat, marimba, 0.34)
    motif(tr, t, beat, lambda n, d: bell(n + 12, d), 0.16)
    put(tr, t, bass(36, beat * 4), 0.4)
    return tr


SONGS = {"brand-walk": walk, "brand-market": market, "brand-night": night, "brand-picnic": picnic, "brand-munch": munch, "brand-horizon": horizon, "brand-horizon-chill": horizon_chill,
         "brand-curious": curious, "brand-sneak": sneak}
LENGTHS = {"brand-munch": 24.0, "brand-horizon": 24.0, "brand-horizon-chill": 24.0, "brand-curious": 24.0, "brand-sneak": 24.0}  # 카드 쇼츠(20초 남짓)에서도 중간에 끝 가락이 나오지 않게 길게 만들어요


def save(x, path):
    x = x / max(1e-9, np.abs(x).max()) * 0.8
    pcm = (np.stack([x, x], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    (HERE / "audio").mkdir(exist_ok=True)
    for name, fn in SONGS.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        x = fn(LENGTHS.get(name, LEN))
        last = np.nonzero(np.abs(x) > 1e-4)[0][-1]
        save(x[: last + 1], HERE / "audio" / f"{name}.wav")
        print("만들었어요:", name, f"{(last + 1) / SR:.1f}초")
