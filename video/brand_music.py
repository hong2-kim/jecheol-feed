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
from audio import SR, bass, bell, env, hat, hz, kick, pluck, put, reed, smooth  # noqa: E402

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


SONGS = {"brand-walk": walk, "brand-market": market, "brand-night": night, "brand-picnic": picnic}


def save(x, path):
    x = x / max(1e-9, np.abs(x).max()) * 0.8
    pcm = (np.stack([x, x], 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    (HERE / "audio").mkdir(exist_ok=True)
    for name, fn in SONGS.items():
        x = fn(LEN)
        last = np.nonzero(np.abs(x) > 1e-4)[0][-1]
        save(x[: last + 1], HERE / "audio" / f"{name}.wav")
        print("만들었어요:", name, f"{(last + 1) / SR:.1f}초")
