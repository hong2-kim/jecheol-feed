# -*- coding: utf-8 -*-
"""그날의 영상 설계도를 모두 영상으로 만들어요.

  python video/produce.py 2026-10-12            videos/2026-10-12/*.json 전부
  python video/produce.py 2026-10-12 news       이름이 news 인 것만

만드는 것: dist/날짜-이름.mp4, dist/날짜-이름.txt(게시글용 글), dist/results.json(성공·실패 목록)
카드 뉴스("format": "cards")는 영상 대신 그림으로 만들어요: dist/날짜-이름-1.jpg, -2.jpg …
하나가 실패해도 나머지는 계속 만들고, 실패 이유는 logs/errors.jsonl 에 남겨요.
"""
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import audio  # noqa: E402
import build  # noqa: E402
import thumb  # noqa: E402
from common import log_error  # noqa: E402

ROOT = Path(__file__).parent.parent
FPS = 30
SIZE = {"width": 1080, "height": 1920}


def render(spec, name, browser):
    build.EXTRACT = True
    page_html, duration, meta = build.build_html(spec)
    top = build.longest(spec)
    if not 9.9 <= duration <= top + 0.1:
        raise ValueError(f"영상 길이가 {duration:.1f}초예요. 10~{top:.0f}초로 맞춰 주세요.")
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    html_path = work / f"{name}.html"
    html_path.write_text(page_html, encoding="utf-8")
    wav = work / f"{name}.wav"
    audio.build(meta["music"], meta["sfx"], duration, wav, meta["ambience"], meta.get("voice"))

    out = ROOT / "dist" / f"{name}.mp4"
    out.parent.mkdir(exist_ok=True)
    page = browser.new_page(viewport=SIZE)
    try:
        page.goto(html_path.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth > 0)", timeout=30000)
        ffmpeg = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
             "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-", "-i", str(wav),
             "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p",
             "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-c:v", "libx264", "-profile:v", "high", "-level", "4.0", "-preset", "medium", "-crf", "21",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)],
            stdin=subprocess.PIPE,
        )
        for i in range(round(duration * FPS)):
            page.evaluate("t => window.seek(t)", i / FPS)
            ffmpeg.stdin.write(page.screenshot(type="jpeg", quality=92))
        ffmpeg.stdin.close()
        if ffmpeg.wait() != 0:
            raise RuntimeError("영상을 저장하지 못했어요 (ffmpeg 오류).")
    finally:
        page.close()
    (ROOT / "dist" / f"{name}.txt").write_text(build.description(spec), encoding="utf-8")
    return out, duration


def render_cards(spec, name, browser):
    """카드 뉴스를 그림으로 만들어요. dist/날짜-이름-1.jpg, -2.jpg … (만든 파일 이름들, 마지막 설계도, 그린 뒤 검수로 보류한 장)
    그린 뒤 검수에 걸린 장은 자동으로 고쳐 다시 그리거나(큰 제목 장), 그 장만 빼고 다시 그려요 (2026-10-28 사용자)."""
    held = []
    for _ in range(4):
        files, bad = draw_cards(spec, name, browser)
        if not bad:
            break
        spec, more, whole = build.layout_triage(spec, bad)
        held += more
        if whole:
            raise ValueError("카드 검수: " + whole)
    else:
        raise ValueError("카드 검수: 고쳐 다시 그려도 걸려요 — " + " / ".join(bad[:3]))
    (ROOT / "dist" / f"{name}.txt").write_text(build.description(spec), encoding="utf-8")
    return files, spec, held


def draw_cards(spec, name, browser):
    """카드를 한 번 그려 찍고 그린 뒤 검수를 해요. (파일 이름들, 꼭 고칠 것)"""
    page_html, count = build.build_cards(spec)
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    html_path = work / f"{name}.html"
    html_path.write_text(page_html, encoding="utf-8")
    (ROOT / "dist").mkdir(exist_ok=True)
    files = []
    page = browser.new_page(viewport=build.CARD_SIZE)
    try:
        page.goto(html_path.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth > 0)", timeout=30000)
        page.evaluate("window.ready && window.ready()")  # 넘겨 보는 해설: 글꼴이 그려진 뒤 확대할 곳을 재요 (steps.py)
        for n in range(1, count + 1):
            out = ROOT / "dist" / f"{name}-{n}.jpg"
            page.locator(f"#c{n}").screenshot(path=str(out), type="jpeg", quality=95)
            files.append(out.name)
        probe = page.evaluate(build.LAYOUT_PROBE)
        bad = build.layout_problems(spec, probe, [ROOT / "dist" / f for f in files])
        if bad:  # 제목만 크고 사진이 작은 장, 글자가 겹치거나 잘린 장은 그대로 보내지 않아요 (2026-10-28 사용자)
            return files, bad
        for line in build.layout_checks(spec, probe)[1]:  # 컴퓨터가 판단하기 어려운 것은 사람이 봐요
            print(f"  확인 필요: {line}")
        for stale in (ROOT / "dist").glob(f"{name}-[0-9]*.jpg"):  # 장을 뺀 뒤 남은 예전 그림은 지워요
            if stale.name not in files and re.fullmatch(rf"{re.escape(name)}-\d+\.jpg", stale.name):
                stale.unlink()
        # 큰 제목 장(hero)은 쇼츠에서 가운데 자막이 내레이션 한 줄마다 바뀌어요. 줄마다 한 장씩 더 찍어 둬요 (날짜-이름-장-s줄.jpg)
        for n, c in enumerate(spec.get("cards") or [], 2):
            if c.get("type") != "hero":
                continue
            for k, line in enumerate(c.get("lines") or [], 1):
                page.evaluate("([n, h]) => { document.querySelector(`#c${n} .hsay > div`).innerHTML = h; }", [n, build.rich(line["say"])])
                page.locator(f"#c{n}").screenshot(path=str(ROOT / "dist" / f"{name}-{n}-s{k}.jpg"), type="jpeg", quality=95)
    finally:
        page.close()
    return files, []


COVER_SEC, CARD_SEC, FADE_SEC, THUMB_SEC = 3.0, 4.0, 0.4, 1.2  # 카드 쇼츠: 첫 장, 소식 한 장, 넘어가는 시간, 맨 앞 썸네일
THUMB_HOLD, THUMB_FADE = 3.0, 0.9  # 카드 쇼츠 맨 앞 썸네일: 머무는 시간, 다음 장으로 천천히 넘어가는 시간 (2026-10-21 사용자: 너무 빨라)


def render_thumb(spec, name, browser):
    """썸네일 그림 한 장(dist/날짜-이름-thumb.jpg). 큰 두 줄 제목 + 사진 한 장이에요. (2026-10-17 사용자가 정함, thumb.py)"""
    html_path = ROOT / "build" / f"{name}-thumb.html"
    html_path.parent.mkdir(exist_ok=True)
    html_path.write_text(thumb.page(spec), encoding="utf-8")
    out = ROOT / "dist" / f"{name}-thumb.jpg"
    out.parent.mkdir(exist_ok=True)
    page = browser.new_page(viewport=SIZE)
    try:
        page.goto(html_path.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_function("[...document.images].every(i => i.complete && i.naturalWidth > 0)", timeout=30000)
        page.screenshot(path=str(out), type="jpeg", quality=93)
    finally:
        page.close()
    return out.name


SAY_LEAD, SAY_TAIL, SAY_FADE = 0.25, 0.3, 0.08  # 내레이션 자막 장: 말 앞뒤 여유, 자막이 바뀔 때 겹치는 시간


def card_segments(files, name, spec, front=None):
    """쇼츠에 이어 붙일 장면 (파일, 길이, 앞 장면과 겹치는 시간) 과 내레이션 [(시작 초, 소리)].
    "short_cover": false 면 첫 장(표지)을 쇼츠에서 빼요 (2026-10-21 사용자: 썸네일에 목록이 있어서 표지가 겹쳐요).
    큰 제목 장(hero)에 lines 가 있으면 줄마다 목소리를 넣고, 그 줄 자막이 가운데에 나오는 그림으로 바꿔 가며 보여 줘요."""
    import voice
    segs, said, cards = [], [], spec.get("cards") or []
    if front:
        segs.append((front, THUMB_SEC, 0.0))
    for i, f in enumerate(files):
        if i == 0:
            if spec.get("short_cover") is not False:
                segs.append((f, COVER_SEC, FADE_SEC))
            continue
        c = cards[i - 1] if i - 1 < len(cards) else {}
        if c.get("type") != "hero" or not c.get("lines"):
            segs.append((f, CARD_SEC, FADE_SEC))
            continue
        for k, line in enumerate(c["lines"], 1):
            sound = voice.tts(voice.spoken(line))
            sec = len(sound) / voice.SR if sound is not None else voice.estimate(voice.spoken(line))
            fade = FADE_SEC if k == 1 else SAY_FADE
            lead = SAY_LEAD + (fade if k == 1 else 0)
            start = sum(s[1] for s in segs) - sum(s[2] for s in segs[1:]) - (fade if segs else 0)
            if sound is not None:
                said.append((start + lead, sound))
            segs.append((f"{name}-{i + 1}-s{k}.jpg", lead + sec + SAY_TAIL, fade if segs else 0.0))
    if front and len(segs) > 1:  # 썸네일은 조금 더 머물다 천천히 넘어가요
        segs[0] = (front, THUMB_HOLD, 0.0)
        segs[1] = (segs[1][0], segs[1][1] + THUMB_FADE - segs[1][2], THUMB_FADE)
    return segs, said


def narration(said, total, name):
    """내레이션 소리를 영상 길이 하나로 이어 wav 로 둬요. 내레이션이 없으면 None."""
    if not said:
        return None
    import wave
    import numpy as np
    import voice
    track = np.zeros(int(voice.SR * total) + 1)
    for at, sound in said:
        a = int(at * voice.SR)
        track[a:a + len(sound)] += sound[: max(0, len(track) - a)]
    path = ROOT / "build" / f"{name}-say.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(voice.SR)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def cards_short(files, name, spec, front=None):
    """카드 그림들을 넘겨 보는 세로 영상으로 이어요. 유튜브 쇼츠용이에요. (파일, 길이)

    카드(1080×1350)를 가운데보다 조금 위에 두고(쇼츠는 아래쪽에 제목과 단추가 겹쳐요), 위아래 빈자리는 같은 카드를 흐리고 어둡게 깔아 채워요.
    밑에는 먹고갈지도 노래를 조용히 깔아요. (2026-10-16)
    """
    segs, said = card_segments(files, name, spec, front)
    files, durs, fades = [s[0] for s in segs], [s[1] for s in segs], [s[2] for s in segs]
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    for f, d in zip(files, durs):
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(ROOT / "dist" / f)]
    total = sum(durs) - sum(fades[1:])
    wav = ROOT / "build" / f"{name}-short.wav"
    wav.parent.mkdir(exist_ok=True)
    audio.build(build.song(spec), [], total, wav, voice=narration(said, total, name))
    cmd += ["-i", str(wav)]
    chain = []
    for i in range(len(files)):
        if front and files[i] == front:  # 썸네일은 이미 세로 화면 크기예요
            chain.append(f"[0:v]scale=1080:1920,setsar=1,fps={FPS},format=yuv420p,settb=1/{FPS}[v0]")
            continue
        chain.append(f"[{i}:v]scale=1080:1350,setsar=1,split[f{i}][b{i}];"
                     f"[b{i}]scale=1536:1920,crop=1080:1920,boxblur=28:2,eq=brightness=-0.22[g{i}];"
                     f"[g{i}][f{i}]overlay=0:180:shortest=1,fps={FPS},format=yuv420p,settb=1/{FPS}[v{i}]")
    last, at = "v0", durs[0]
    for i in range(1, len(files)):
        at -= fades[i]
        chain.append(f"[{last}][v{i}]xfade=transition=fade:duration={fades[i]}:offset={at:.2f}[x{i}]")
        last, at = f"x{i}", at + durs[i]
    chain.append(f"[{last}]scale=in_range=pc:out_range=tv,format=yuv420p[out]")  # 이어 붙이면 색 형식이 바뀌어서 쇼츠가 읽는 형식으로 되돌려요
    out = ROOT / "dist" / f"{name}-short.mp4"
    cmd += ["-filter_complex", ";".join(chain), "-map", "[out]", "-map", f"{len(files)}:a",
            "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "21",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return out, total


def main():
    day = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else None
    specs = sorted((ROOT / "videos" / day).glob("*.json"))
    results = []
    ledger = ROOT / "state" / "posted.json"
    posted = {e["id"] for e in json.loads(ledger.read_text(encoding="utf-8"))} if ledger.exists() else set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path in specs:
            if only and path.stem != only:
                continue
            name = f"{day}-{path.stem}"
            if name in posted:
                print(f"이미 인스타에 올린 영상이라 다시 만들지 않아요: {name}")
                continue
            entry = {"id": name, "date": day, "file": f"{name}.mp4"}
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
                spec.update({"_day": day, "_name": path.stem})  # 오디오 보관함 곡을 날짜로 돌려 고를 때 써요
                if spec.get("format") == "cards":  # 문제 있는 장만 빼고 나머지는 그대로 만들어요 (2026-10-28 사용자)
                    spec, held, whole = build.triage(spec, day)
                    if held:
                        entry["held"] = held
                        print(f"  보류한 장: " + "; ".join(f"{h['no']}장 {h['headline']} ({h['grade']})" for h in held))
                    if whole:
                        raise ValueError("전체 보류: " + whole)
                entry["music"] = build.track_info(spec)
                entry.update({k: spec.get(k) for k in ("kind", "title", "summary", "caption", "tags", "sources", "credits", "pin")})
                entry["tags"] = build.hashtags(spec.get("tags"))  # 인스타에 들어가는 5개만
                entry["yt_title"], entry["yt_desc"] = build.youtube_text(spec)
                kw = build.youtube_keywords(spec)
                entry.update({"yt_keyword": kw["keyword"], "yt_related": kw["related"], "yt_tags": kw["tag_text"], "yt_hashtags": kw["hashtags"]})
                if thumb.has(spec):
                    try:  # 썸네일이 안 만들어져도 영상은 그대로 만들어요
                        entry["thumb"] = render_thumb(spec, name, browser)
                    except Exception as e:
                        log_error(f"thumb:{name}", e)
                        print(f"썸네일을 만들지 못했어요: {name} — {e}")
                if build.is_cards(spec):
                    files, spec, more = render_cards(spec, name, browser)
                    if more:  # 그린 뒤 검수로 장을 뺐으면 글·태그·유튜브 글도 남은 장에 맞춰요
                        entry["held"] = entry.get("held", []) + more
                        entry.update({k: spec.get(k) for k in ("title", "summary", "caption", "credits")})
                        entry["tags"] = build.hashtags(spec.get("tags"))
                        entry["yt_title"], entry["yt_desc"] = build.youtube_text(spec)
                    size = sum((ROOT / "dist" / f).stat().st_size for f in files)
                    entry.update({"ok": True, "format": "cards", "file": files[0], "files": files, "size_mb": round(size / 1e6, 1)})
                    print(f"만들었어요: {name} 카드 {len(files)}장")
                    try:  # 쇼츠 영상이 안 만들어져도 인스타용 카드는 그대로 보내요
                        short, sec = cards_short(files, name, spec, entry.get("thumb"))
                        entry.update({"short": short.name, "short_seconds": round(sec, 1)})
                        print(f"만들었어요: {short.name} ({sec:.1f}초, 유튜브 쇼츠용)")
                    except Exception as e:
                        log_error(f"short:{name}", e)
                        print(f"쇼츠 영상을 만들지 못했어요: {name} — {e}")
                else:
                    out, duration = render(spec, name, browser)
                    entry.update({"ok": True, "seconds": round(duration, 1), "size_mb": round(out.stat().st_size / 1e6, 1)})
                    print(f"만들었어요: {out.name} ({duration:.1f}초)")
            except Exception as e:
                entry.update({"ok": False, "error": str(e)[:300]})
                log_error(f"video:{name}", e)
                print(f"실패: {name} — {e}")
                traceback.print_exc()
            results.append(entry)
        browser.close()
    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist" / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"끝. 성공 {sum(r['ok'] for r in results)}개, 실패 {sum(not r['ok'] for r in results)}개")


if __name__ == "__main__":
    main()
