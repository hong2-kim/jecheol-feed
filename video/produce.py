# -*- coding: utf-8 -*-
"""그날의 영상 설계도를 모두 영상으로 만들어요.

  python video/produce.py 2026-10-12            videos/2026-10-12/*.json 전부
  python video/produce.py 2026-10-12 news       이름이 news 인 것만

만드는 것: dist/날짜-이름.mp4, dist/날짜-이름.txt(게시글용 글), dist/results.json(성공·실패 목록)
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
    if not 9.9 <= duration <= 15.1:
        raise ValueError(f"영상 길이가 {duration:.1f}초예요. 10~15초로 맞춰 주세요.")
    work = ROOT / "build"
    work.mkdir(exist_ok=True)
    html_path = work / f"{name}.html"
    html_path.write_text(page_html, encoding="utf-8")
    wav = work / f"{name}.wav"
    audio.build(meta["music"], meta["sfx"], duration, wav, meta["ambience"])

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
                entry.update({k: spec.get(k) for k in ("kind", "title", "summary", "caption", "tags", "sources", "credits")})
                entry["tags"] = build.hashtags(spec.get("tags"))  # 인스타에 들어가는 5개만
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
