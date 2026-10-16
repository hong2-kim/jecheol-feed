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


BRAND_LEVEL = 0.32
LOUDER = {"brand-munch": 0.7}  # 먹는 소리가 들려야 하는 곡은 조금 크게


LIB_RMS = 0.075  # 오디오 보관함 곡은 곡마다 크기가 달라서 평균 크기로 맞춰요 (예전 영상과 비슷한 크기)


def load_lib(key):
    """오디오 보관함 곡(비공개 보관함 music/키.ogg)을 읽어요. 처음 쓸 때 wav로 풀어 둬요."""
    import subprocess

    import imageio_ffmpeg

    wav = Path(__file__).parent.parent / "build" / "audio" / f"lib-{key}.wav"
    if not wav.exists():
        import build as _build  # 비공개 보관함 읽기는 build 에 있어요
        wav.parent.mkdir(parents=True, exist_ok=True)
        ogg = wav.with_suffix(".ogg")
        ogg.write_bytes(_build.read_source(f"vault:music/{key}.ogg"))
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(ogg), "-ac", "2", "-ar", str(SR), str(wav)], check=True)
        ogg.unlink()
    with wave.open(str(wav), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64).reshape(-1, 2).mean(axis=1) / 32768


def best_start(song, n):
    """곡에서 영상 길이(n)만큼 쓸 가장 좋은 구간의 시작 위치(샘플). (2026-10-17 사용자가 "구간은 알아서 잘 골라라"고 함)

    잔잔한 도입부나 중간에 비는 곳(브레이크)보다, 곡의 본 가락이 꽉 차게 이어지는 구간을 골라요.
    시작은 박자가 세게 들어오는 순간(어택)에 맞춰서 영상 첫 장면부터 바로 귀에 들어오게 해요.
    곡 끝 2초는 피하고, 점수가 비슷하면 앞쪽을 골라요.
    """
    hop = int(SR * 0.05)
    tail = int(SR * 2)
    if len(song) < n + tail + hop:
        return 0
    frames = len(song) // hop
    fr = song[: frames * hop].reshape(frames, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    edge = np.sqrt((np.diff(song[: frames * hop], prepend=0).reshape(frames, hop) ** 2).mean(axis=1))  # 높은 소리 쪽 세기
    onset = np.maximum(np.diff(smooth(edge, 2), prepend=edge[0]), 0)
    width = n // hop
    last = (len(song) - n - tail) // hop
    csum = np.concatenate([[0], np.cumsum(rms)])
    means = (csum[width:] - csum[:-width])[: last + 1] / width
    block = max(1, int(1.0 / 0.05))
    peak_mean = means.max() + 1e-9
    thresh = np.percentile(onset[: last + 1], 75)
    typical = np.median(rms[: last + width]) + 1e-9
    best, best_score = 0, -1e9
    for strict in (True, False):  # 조건에 맞는 곳이 없으면 조건을 풀고 다시 찾아요
        for s in range(0, last + 1):
            if onset[s] < thresh or (s and onset[s] < onset[s - 1]) or (s + 1 < len(onset) and onset[s] < onset[s + 1]):
                continue  # 박자가 세게 들어오는 순간에서만 시작해요
            if strict and rms[s: s + block].mean() < 0.9 * typical:
                continue  # 첫 1초가 곡의 보통 크기보다 작으면(조용한 틈) 시작하지 않아요
            score = _score(rms, s, width, block, means, peak_mean, onset, last)
            if score > best_score:
                best, best_score = s, score
        if best_score > -1e9:
            break
    return best * hop


def _score(rms, s, width, block, means, peak_mean, onset, last):
    """구간 점수: 꽉 찬 정도 + 중간에 비지 않음 + 첫 1초부터 소리가 참 + 세게 들어옴, 뒤쪽일수록 조금 깎아요."""
    w = rms[s: s + width]
    blocks = w[: len(w) // block * block].reshape(-1, block).mean(axis=1)
    steady = blocks.min() / (w.mean() + 1e-9)  # 중간에 비는 곳이 있으면 낮아져요
    lead = rms[s: s + block].mean() / (w.mean() + 1e-9)  # 첫 1초부터 소리가 차 있는지
    return means[s] / peak_mean + 0.5 * steady + 0.25 * min(lead, 1.2) + 0.2 * onset[s] / (onset.max() + 1e-9) - 0.15 * s / max(1, last)


def build(mood, sfx, dur, path, ambience=()):
    """mood 가 "file:이름" 이면 audio/이름.wav 를, "lib:키" 면 오디오 보관함 곡을 배경음악으로 써요.
    ambience 는 [[시작, 끝, 이름, 크기], ...] 로, 장면 밑에 까는 현장 소리예요."""
    n = int(SR * dur)
    if mood.startswith("lib:"):
        try:
            song = load_lib(mood[4:])
        except Exception as e:  # 보관함을 못 읽으면 먹고갈지도 노래로 대신해요
            print(f"오디오 보관함 곡을 못 읽어 먹고갈지도 노래로 대신해요: {mood} ({e})")
            mood = "file:brand-walk"
    if mood.startswith("lib:"):
        start = best_start(song, n)
        music = np.tile(song[start:], n // max(1, len(song) - start) + 1)[:n].copy()  # 가장 좋은 구간부터 써요
        music *= LIB_RMS / max(1e-9, np.sqrt(np.mean(music ** 2)))
        music *= min(1.0, 0.95 / max(1e-9, np.abs(music).max()))
        music[: int(SR * 0.05)] *= np.linspace(0, 1, int(SR * 0.05))
        music[-int(SR * 1.6):] *= np.linspace(1, 0, int(SR * 1.6))
    elif mood == "none":
        music = np.zeros(n)
    elif mood.startswith("file:brand-"):
        # 먹고갈지도 노래는 끝에 "먹고갈지도" 가락이 있어요. 영상이 끝날 때 그 가락이 나오게 곡의 뒷부분을 써요.
        song = load_wav(mood[5:])
        music = np.tile(song, n // len(song) + 1)[-n:].copy()  # 영상이 곡보다 길면 앞에 한 번 더 이어 붙여요
    elif mood.startswith("file:"):
        music = loop_to(load_wav(mood[5:]), n).copy()
    else:
        music = MUSIC[mood](dur)[:n]
    if not mood.startswith("lib:"):
        # 먹고갈지도 노래는 조용히 깔아요. 시끄럽지 않게 (2026-10-15 사용자가 정함)
        level = LOUDER.get(mood[5:], BRAND_LEVEL) if mood.startswith("file:brand-") else 0.85
        music *= level / max(1e-9, np.abs(music).max())
        fade_in, fade_out = int(SR * 0.3), int(SR * (0.4 if mood.startswith("file:brand-") else 1.6))
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
