# 시험 영상 만들기 (운영 produce.py 를 고치지 않고 그 함수만 불러 써요). 쓰는 법: python3 trial.py <설계도.json> <이름> [check]
import json
import sys
from pathlib import Path

ROOT = Path("/home/user/jecheol-feed")
sys.path.insert(0, str(ROOT / "video"))
sys.path.insert(0, str(ROOT / "scripts"))
import voice  # noqa: E402

spec_path, name = sys.argv[1], sys.argv[2]
spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
spec.update({"_day": "2026-11-18", "_name": name})
must, should, total = voice.problems(spec)
print(f"어림 길이 {total:.1f}초")
print("꼭 고칠 것:", *must, sep="\n  - ") if must else print("꼭 고칠 것: 없음")
print("보면 좋은 것:", *should, sep="\n  - ") if should else print("보면 좋은 것: 없음")
if len(sys.argv) > 3 and sys.argv[3] == "check":
    sys.exit(0)
from playwright.sync_api import sync_playwright  # noqa: E402
import produce  # noqa: E402
with sync_playwright() as p:
    browser = p.chromium.launch()
    tw = []
    try:
        print("썸네일:", produce.render_thumb(spec, name, browser, tw), tw)
    except Exception as e:
        print("썸네일 실패:", e)
    warns = []
    out, dur = produce.render(spec, name, browser, warns)
    print("영상:", out, f"{dur:.1f}초")
    print("검수:", *warns, sep="\n  - ")
