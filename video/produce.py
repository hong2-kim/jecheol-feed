# -*- coding: utf-8 -*-
"""그날의 영상 설계도를 모두 영상으로 만들어요.

  python video/produce.py 2026-10-12            videos/2026-10-12/*.json 전부
  python video/produce.py 2026-10-12 news       이름이 news 인 것만

만드는 것: dist/날짜-이름.mp4, dist/날짜-이름.txt(게시글용 글), dist/results.json(성공·실패 목록)
카드 뉴스("format": "cards")는 영상 대신 그림으로 만들어요: dist/날짜-이름-1.jpg, -2.jpg …
하나가 실패해도 나머지는 계속 만들고, 실패 이유는 logs/errors.jsonl 에 남겨요.
"""
import json
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
    """카드 뉴스를 그림으로 만들어요. dist/날짜-이름-1.jpg, -2.jpg … (만든 파일 이름들)"""
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
        for n in range(1, count + 1):
            out = ROOT / "dist" / f"{name}-{n}.jpg"
            page.locator(f"#c{n}").screenshot(path=str(out), type="jpeg", quality=95)
            files.append(out.name)
    finally:
        page.close()
    (ROOT / "dist" / f"{name}.txt").write_text(build.description(spec), encoding="utf-8")
    return files


COVER_SEC, CARD_SEC, FADE_SEC = 3.0, 4.0, 0.4  # 카드 쇼츠: 첫 장, 소식 한 장, 넘어가는 시간


def cards_short(files, name, spec):
    """카드 그림들을 넘겨 보는 세로 영상으로 이어요. 유튜브 쇼츠용이에요. (파일, 길이)

    카드(1080×1350)를 가운데보다 조금 위에 두고(쇼츠는 아래쪽에 제목과 단추가 겹쳐요), 위아래 빈자리는 같은 카드를 흐리고 어둡게 깔아 채워요.
    밑에는 먹고갈지도 노래를 조용히 깔아요. (2026-10-16)
    """
    durs = [COVER_SEC] + [CARD_SEC] * (len(files) - 1)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    for f, d in zip(files, durs):
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(ROOT / "dist" / f)]
    total = sum(durs) - FADE_SEC * (len(files) - 1)
    wav = ROOT / "build" / f"{name}-short.wav"
    wav.parent.mkdir(exist_ok=True)
    audio.build(build.song(spec), [], total, wav)
    cmd += ["-i", str(wav)]
    chain = []
    for i in range(len(files)):
        chain.append(f"[{i}:v]scale=1080:1350,setsar=1,split[f{i}][b{i}];"
                     f"[b{i}]scale=1536:1920,crop=1080:1920,boxblur=28:2,eq=brightness=-0.22[g{i}];"
                     f"[g{i}][f{i}]overlay=0:180:shortest=1,fps={FPS},format=yuv420p,settb=1/{FPS}[v{i}]")
    last, at = "v0", 0.0
    for i in range(1, len(files)):
        at += durs[i - 1] - FADE_SEC
        chain.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE_SEC}:offset={at:.2f}[x{i}]")
        last = f"x{i}"
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
                entry["music"] = build.track_info(spec)
                entry.update({k: spec.get(k) for k in ("kind", "title", "summary", "caption", "tags", "sources", "credits", "pin")})
                entry["tags"] = build.hashtags(spec.get("tags"))  # 인스타에 들어가는 5개만
                entry["yt_title"], entry["yt_desc"] = build.youtube_text(spec)
                kw = build.youtube_keywords(spec)
                entry.update({"yt_keyword": kw["keyword"], "yt_related": kw["related"], "yt_tags": kw["tag_text"], "yt_hashtags": kw["hashtags"]})
                if build.is_cards(spec):
                    files = render_cards(spec, name, browser)
                    size = sum((ROOT / "dist" / f).stat().st_size for f in files)
                    entry.update({"ok": True, "format": "cards", "file": files[0], "files": files, "size_mb": round(size / 1e6, 1)})
                    print(f"만들었어요: {name} 카드 {len(files)}장")
                    try:  # 쇼츠 영상이 안 만들어져도 인스타용 카드는 그대로 보내요
                        short, sec = cards_short(files, name, spec)
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
