# -*- coding: utf-8 -*-
"""매일 실행에 필요한 파이썬 패키지를 준비해요. 여러 번 돌려도 돼요(이미 있으면 몇 초 안에 끝나요). (2026-10-19)

  python3 scripts/setup_env.py

- 설치할 것은 저장소 맨 위 `requirements-routine.txt`(Pillow: video/build.py 의 그림, numpy: 썸네일·내레이션).
  2026-10-19 에 Python 3.11·3.12, Pillow 12~13, numpy 2.5 로 시험했어요. 영상 만들기(playwright 등)는 깃허브 자동 작업이 따로 설치해요.
  그 파일은 영어·숫자만 둬요. 한국어 윈도의 pip 이 파일을 cp949 로 읽다가 한글에서 멈춘 적이 있어요.
- 이 명령을 돌린 파이썬에 `그 파이썬 -m pip` 으로 설치해요. 클라우드에는 `pip` 과 `python3` 가 서로 다른 파이썬이라
  `pip install pillow` 로는 설치돼도 `python3` 에서 못 불러온 적이 있어요(2026-10-19 실행).
- 규칙의 명령이 `python` 과 `python3` 를 섞어 쓰니, PATH 의 `python`·`python3` 가 다른 파이썬이면 그것도 준비해요.
  실행되지 않는 것(윈도 스토어의 가짜 python3 등)은 건너뛰어요.
- 끝에 파이썬마다 경로와 패키지 판을 한 줄로 알려 줘요. 이 명령을 돌린 파이썬을 준비하지 못했을 때만 실패로 끝나요.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = "import sys, PIL, numpy; print('Python ' + sys.version.split()[0] + ', pillow ' + PIL.__version__ + ', numpy ' + numpy.__version__)"
NOISE = ("Running pip as the 'root' user", "venv", "WARNING: The script")


def requirements():
    lines = (ROOT / "requirements-routine.txt").read_text(encoding="utf-8").splitlines()
    return [l.split("#")[0].strip() for l in lines if l.split("#")[0].strip()]


def real_python(exe):
    """정말 돌아가는 파이썬이면 그 실행 파일 경로, 아니면 None."""
    try:
        r = subprocess.run([exe, "-c", "import sys; print(sys.executable)"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return os.path.realpath(out) if r.returncode == 0 and out else None


def interpreters():
    """이 명령을 돌린 파이썬 + PATH 의 python3·python (같은 실행 파일은 한 번만)."""
    seen, out = set(), []
    for exe in [sys.executable, shutil.which("python3"), shutil.which("python")]:
        real = real_python(exe) if exe else None
        if real and real not in seen:
            seen.add(real)
            out.append(exe)
    return out


def ready(exe):
    r = subprocess.run([exe, "-c", CHECK], capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else None


def install(exe):
    cmd = [exe, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *requirements()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip() and not any(n in line for n in NOISE):
            print("  " + line)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    me = os.path.realpath(sys.executable)
    failed_me, failed_other = False, []
    for exe in interpreters():
        have = ready(exe)
        if not have:
            print(f"설치해요: {exe}")
            install(exe)
            have = ready(exe)
        if have:
            print(f"준비돼 있어요: {exe} ({have})")
        elif real_python(exe) == me:
            failed_me = True
        else:
            failed_other.append(exe)
    if failed_other:
        print("주의: 이 파이썬에는 준비하지 못했어요:", ", ".join(failed_other), "— 위의 준비된 파이썬으로 명령을 돌려요.")
    if failed_me:
        sys.exit(f"설치하지 못했어요: {sys.executable}. 영상·카드 검사(build.py)를 돌리지 못하면 마지막 보고에 적어요.")


if __name__ == "__main__":
    main()
