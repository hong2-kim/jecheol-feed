# -*- coding: utf-8 -*-
"""배경음악과 현장 소리를 섞어 한 줄의 소리로 만들어요.

  build("lively" | "waltz" | "cute", [[시각, "whoosh"], ...], 길이, 저장할 wav)
"""
import wave
from pathlib import Path

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def hz(note):
    """미디 음 번호를 주파수로."""
    return 440.0 * 2 ** ((note - 69) / 12)


def env(n, attack=0.005, release=0.08):
    e = np.ones(n)
    a, r = int(SR * attack), int(SR * release)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def smooth(x, k):
    """간단한 저역 필터."""
    return np.convolve(x, np.ones(k) / k, mode="same") if k > 1 else x


_pluck_cache = {}


def pluck(note, dur, bright=0.5):
    """줄을 튕기는 소리 (Karplus-Strong)."""
    key = (note, round(dur, 3), bright)
    if key not in _pluck_cache:
        n = int(SR * dur)
        period = int(SR / hz(note))
        buf = smooth(rng.uniform(-1, 1, period), 1 + int((1 - bright) * 6))
        out = np.empty(n)
        for i in range(n):
            out[i] = buf[i % period]
            buf[i % period] = 0.996 * 0.5 * (buf[i % period] + buf[(i + 1) % period])
        _pluck_cache[key] = out * env(n, 0.002, 0.05)
    return _pluck_cache[key]


def bell(note, dur):
    """맑은 종소리 (FM)."""
    t = np.arange(int(SR * dur)) / SR
    f = hz(note)
    return np.sin(2 * np.pi * f * t + 2.2 * np.exp(-6 * t) * np.sin(2 * np.pi * f * 3.5 * t)) * np.exp(-4.5 * t)


def reed(note, dur):
    """아코디언 비슷한 소리."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = hz(note)
    x = sum(np.sin(2 * np.pi * f * k * t * (1 + 0.002 * d)) / k for k in range(1, 9) for d in (-1, 1))
    x *= 1 + 0.08 * np.sin(2 * np.pi * 5.5 * t)
    return smooth(x, 4) * env(n, 0.03, 0.06) * 0.25


def bass(note, dur):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f = hz(note)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * np.exp(-3 * t) * env(n, 0.004, 0.05)


def kick():
    t = np.arange(int(SR * 0.22)) / SR
    return np.sin(2 * np.pi * (48 * t + 60 * (1 - np.exp(-28 * t)) / 28)) * np.exp(-11 * t)


def hat(loud=1.0):
    n = int(SR * 0.05)
    x = rng.uniform(-1, 1, n)
    return (x - smooth(x, 6)) * np.exp(-np.arange(n) / SR * 90) * loud


def clap():
    n = int(SR * 0.16)
    x = smooth(rng.uniform(-1, 1, n), 2)
    t = np.arange(n) / SR
    burst = sum(np.exp(-np.maximum(t - d, 0) * 60) * (t >= d) for d in (0, 0.012, 0.025))
    return x * burst * 0.5


# 효과음
def sfx_whoosh():
    n = int(SR * 0.42)
    t = np.linspace(0, 1, n)
    x = rng.uniform(-1, 1, n)
    k = np.clip((1 - np.sin(np.pi * t)) * 60, 2, 60).astype(int)
    out = np.array([x[max(0, i - k[i]):i + 1].mean() for i in range(n)])
    return out * np.sin(np.pi * t) ** 1.5 * 2.2


def sfx_pop():
    t = np.arange(int(SR * 0.09)) / SR
    return np.sin(2 * np.pi * (520 * t + 900 * t * t)) * np.exp(-38 * t) * 0.9


def sfx_ding():
    return (bell(88, 0.9) + 0.6 * bell(93, 0.9)) * 0.6


def sfx_thud():
    t = np.arange(int(SR * 0.25)) / SR
    return (np.sin(2 * np.pi * 70 * t) * np.exp(-16 * t) + smooth(rng.uniform(-1, 1, len(t)), 8) * np.exp(-40 * t) * 0.6) * 1.1


def sfx_bubble():
    t = np.arange(int(SR * 0.13)) / SR
    return np.sin(2 * np.pi * (300 * t + 2600 * t * t)) * np.exp(-22 * t) * 0.6


def sfx_tick():
    t = np.arange(int(SR * 0.03)) / SR
    return np.sin(2 * np.pi * 1900 * t) * np.exp(-140 * t) * 0.5


def sfx_sizzle():
    n = int(SR * 1.2)
    x = rng.uniform(-1, 1, n)
    x = x - smooth(x, 10)
    crackle = (rng.uniform(0, 1, n) > 0.9993) * rng.uniform(0.5, 1, n)
    crackle = np.convolve(crackle, np.exp(-np.arange(200) / 25), mode="same")
    return (x * 0.25 + crackle * x * 2.5) * env(n, 0.1, 0.5)


SFX = {"whoosh": sfx_whoosh, "pop": sfx_pop, "ding": sfx_ding, "thud": sfx_thud, "bubble": sfx_bubble, "tick": sfx_tick, "sizzle": sfx_sizzle}


def put(track, at, sound, gain=1.0):
    i = int(at * SR)
    if i >= len(track):
        return
    sound = sound[: len(track) - i]
    track[i:i + len(sound)] += sound * gain


def music_lively(dur):
    """밝고 통통 튀는 4박자. 먹음직스러운 음식 영상용."""
    beat = 60 / 112
    track = np.zeros(int(SR * (dur + 1)))
    chords = [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)]
    roots = [36, 33, 29, 31]
    pattern = [0, 1, 2, 1, 0, 2, 1, 2]
    bar, t = 0, 0.0
    while t < dur:
        chord, root = chords[bar % 4], roots[bar % 4]
        for step in range(8):
            at = t + step * beat / 2
            put(track, at, pluck(chord[pattern[step]] + 12, beat * 0.9, 0.7), 0.30)
            put(track, at, hat(0.5 if step % 2 else 0.9), 0.10)
        for b in range(4):
            if b in (0, 2):
                put(track, t + b * beat, kick(), 0.55)
                put(track, t + b * beat, bass(root + 12, beat * 1.6), 0.38)
            else:
                put(track, t + b * beat, clap(), 0.30)
        put(track, t + 3.5 * beat, bass(root + 12, beat * 0.5), 0.25)
        bar += 1
        t += 4 * beat
    return track


def music_waltz(dur):
    """쿵짝짝 3박자. 유럽 마을 축제 느낌."""
    beat = 60 / 138
    track = np.zeros(int(SR * (dur + 1)))
    bars = [((55, 59, 62), 43), ((57, 60, 66), 38), ((55, 59, 62), 43), ((60, 64, 67), 36),
            ((55, 59, 62), 43), ((57, 60, 66), 38), ((57, 60, 66), 42), ((55, 59, 62), 43)]
    melody = [74, 71, 67, 72, 69, 66, 74, 71, 67, 76, 72, 67, 74, 71, 67, 72, 69, 66, 69, 72, 66, 67, 71, 74]
    bar, t = 0, 0.0
    while t < dur:
        chord, root = bars[bar % 8]
        put(track, t, bass(root, beat * 1.1), 0.50)
        put(track, t, kick(), 0.25)
        for b in (1, 2):
            for note in chord:
                put(track, t + b * beat, reed(note, beat * 0.55), 0.15)
            put(track, t + b * beat, hat(0.7), 0.07)
        for b in range(3):
            note = melody[(bar * 3 + b) % len(melody)]
            put(track, t + b * beat, reed(note + 12, beat * 0.9), 0.20)
        bar += 1
        t += 3 * beat
    return track


def music_cute(dur):
    """맑고 귀여운 종소리. 쉬운 설명 영상용."""
    beat = 60 / 100
    track = np.zeros(int(SR * (dur + 1)))
    scale = [72, 74, 76, 79, 81, 84]
    riff = [0, 2, 3, 2, 4, 3, 2, 1, 0, 2, 3, 5, 4, 3, 2, 3]
    roots = [48, 45, 41, 43]
    bar, t = 0, 0.0
    while t < dur:
        root = roots[bar % 4]
        for step in range(8):
            at = t + step * beat / 2
            put(track, at, bell(scale[riff[(bar * 8 + step) % 16]], beat * 1.4), 0.17)
            if step % 2 == 1:
                put(track, at, hat(0.6), 0.06)
        for b in (0, 2):
            put(track, t + b * beat, bass(root, beat * 1.8), 0.40)
            put(track, t + b * beat, kick(), 0.32)
        put(track, t + beat, pluck(root + 24, beat, 0.4), 0.18)
        put(track, t + 3 * beat, pluck(root + 31, beat, 0.4), 0.18)
        bar += 1
        t += 4 * beat
    return track


MUSIC = {"lively": music_lively, "waltz": music_waltz, "cute": music_cute}


def load_wav(name):
    """video/audio 폴더의 음원(ogg)을 읽어요. 처음 쓸 때 wav로 풀어 둬요."""
    import subprocess

    import imageio_ffmpeg

    here = Path(__file__).parent
    wav = here.parent / "build" / "audio" / f"{name}.wav"
    if not wav.exists():
        wav.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(here / "audio" / f"{name}.ogg"),
                        "-ac", "2", "-ar", str(SR), str(wav)], check=True)
    with wave.open(str(wav), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        if w.getnchannels() == 2:
            data = data.reshape(-1, 2).mean(axis=1)
    return data


def loop_to(sound, n):
    return np.tile(sound, n // len(sound) + 1)[:n]


def build(mood, sfx, dur, path, ambience=()):
    """mood 가 "file:이름" 이면 audio/이름.wav 를 배경음악으로 써요.
    ambience 는 [[시작, 끝, 이름, 크기], ...] 로, 장면 밑에 까는 현장 소리예요."""
    n = int(SR * dur)
    if mood.startswith("file:"):
        music = loop_to(load_wav(mood[5:]), n).copy()
    else:
        music = MUSIC[mood](dur)[:n]
    music *= 0.85 / max(1e-9, np.abs(music).max())
    fade_in, fade_out = int(SR * 0.3), int(SR * 1.6)
    music[:fade_in] *= np.linspace(0, 1, fade_in)
    music[-fade_out:] *= np.linspace(1, 0, fade_out)
    fx = np.zeros(n)
    for at, name in sfx:
        put(fx, at, SFX[name](), 0.55)
    for start, end, name, gain in ambience:
        length = int((end - start) * SR)
        sound = loop_to(SFX[name]() if name in SFX else load_wav(name), length).copy()
        sound *= gain / max(1e-9, np.abs(sound).max())
        edge = min(int(SR * 0.4), length // 2)
        sound[:edge] *= np.linspace(0, 1, edge)
        sound[-edge:] *= np.linspace(1, 0, edge)
        put(fx, start, sound)
    mix = np.tanh((music + fx) * 1.1) * 0.89
    pcm = (np.stack([mix, mix], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
