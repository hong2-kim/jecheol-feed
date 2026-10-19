# -*- coding: utf-8 -*-
"""매일 실행에 필요한 파이썬 패키지를 준비해요. 여러 번 돌려도 돼요(이미 있으면 몇 초 안에 끝나요). (2026-10-19)

  python3 scripts/setup_env.py

- 지금 이 명령을 돌린 파이썬에 설치해요(`python3 -m pip`). 클라우드에는 `pip` 과 `python3` 가 서로 다른 파이썬이라
  `pip install pillow` 로는 설치돼도 `python3` 에서 못 불러온 적이 있어요(2026-10-19 실행).
- 목록은 저장소 맨 위 `requirements-routine.txt`. 끝에 쓰는 파이썬과 패키지 판을 한 줄로 알려 줘요.
"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEED = {"PIL": "pillow", "numpy": "numpy"}  # 불러올 이름: 설치 이름


def missing():
    out = []
    for mod in NEED:
        try:
            importlib.import_module(mod)
        except ImportError:
            out.append(mod)
    return out


def versions():
    import numpy
    import PIL
    return f"{sys.executable} (Python {sys.version.split()[0]}), pillow {PIL.__version__}, numpy {numpy.__version__}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lack = missing()
    if not lack:
        print("준비돼 있어요:", versions())
        return
    print("설치해요:", ", ".join(NEED[m] for m in lack))
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", str(ROOT / "requirements-routine.txt")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    noise = "Running pip as the 'root' user"
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip() and noise not in line and "venv" not in line:
            print("  " + line)
    importlib.invalidate_caches()
    lack = missing()
    if r.returncode or lack:
        sys.exit("설치하지 못했어요: " + ", ".join(NEED[m] for m in lack or NEED) + ". 영상·카드 검사(build.py)는 건너뛰고 마지막 보고에 적어요.")
    print("준비됐어요:", versions())


if __name__ == "__main__":
    main()
