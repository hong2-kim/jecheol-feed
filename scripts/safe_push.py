# -*- coding: utf-8 -*-
"""모든 배포 경로가 쓰는 안전한 push (2026-11-06 사용자: 보관함 525개 삭제 사고 재발 방지).

  python scripts/safe_push.py                          지금 폴더(jecheol-feed)를 origin main 에 올려요
  python scripts/safe_push.py ../jecheol-photos --only index.json        보관함: index.json 만 바뀌었을 때만
  python scripts/safe_push.py ../jecheol-photos --only press/            보관함: press/ 아래만
  python scripts/safe_push.py --branch claude/abc      main 이 거부할 때 claude/ 가지로
  python scripts/safe_push.py --allow-delete 30        지우는 파일이 많아도 되는 걸 알고 올릴 때(이유를 커밋 메시지에)
  python scripts/safe_push.py --check                  올리지 않고 검사만

막는 것(하나라도 걸리면 push 하지 않고 끝 코드 2):
  1. 받아 오지 않은(checkout 안 한) 저장소: 추적 파일 수가 커밋의 파일 수보다 크게 적으면 — 빈 인덱스에서 커밋하면 '모두 지움'이 돼요
  2. 대량 삭제: 원격보다 앞선 커밋들이 지우는 파일이 --allow-delete(기본 10개) 넘게, 또는 전체의 5% 넘게
  3. 허락한 경로 밖의 변경(--only 를 준 때)
  4. 다른 세션이 먼저 올린 main: 받아서 다시 얹고(rebase), 충돌이 나면 멈춰요(자동으로 한쪽을 버리지 않아요)
  5. 올린 뒤 원격 머리가 내 커밋과 다르면 실패로 알려요
명령 하나라도 실패하면 거기서 멈춰요(다음 단계로 넘어가지 않아요).
"""
import argparse
import subprocess
import sys
from pathlib import Path

MAX_DELETE = 10
MAX_DELETE_SHARE = 0.05


class Stop(Exception):
    pass


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise Stop(f"git {' '.join(args)} 실패: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout


def tracked_count(repo, ref="HEAD"):
    return len([x for x in git(repo, "ls-tree", "-r", "--name-only", ref).splitlines() if x])


def outgoing(repo, base):
    """원격(base)보다 앞선 커밋들이 바꾼 파일: [(상태, 경로)]"""
    rows = []
    for line in git(repo, "-c", "core.quotepath=false", "diff", "--name-status", "--no-renames", f"{base}..HEAD").splitlines():
        if line.strip():
            st, path = line.split("\t", 1)
            rows.append((st[0], path))
    return rows


def checks(repo, base, only, allow_delete):
    """push 전에 볼 것들. 문제 목록을 돌려줘요."""
    out = []
    head_n = tracked_count(repo)
    index_n = len([x for x in git(repo, "ls-files").splitlines() if x])
    sparse = git(repo, "config", "--get", "core.sparseCheckout", check=False).strip() == "true"
    if not sparse and head_n and index_n < head_n * 0.9:
        out.append(f"받아 오지 않은 저장소 같아요: 커밋에는 파일 {head_n}개, 작업 폴더 목록에는 {index_n}개. --no-checkout 클론에서는 커밋하지 않아요")
    rows = outgoing(repo, base)
    gone = [p for st, p in rows if st == "D"]
    total = max(tracked_count(repo, base), 1)
    if len(gone) > allow_delete or (len(gone) > 3 and len(gone) / total > MAX_DELETE_SHARE and allow_delete <= MAX_DELETE):
        out.append(f"파일 {len(gone)}개를 지우는 커밋이에요(전체 {total}개, 허락 {allow_delete}개): {', '.join(gone[:5])}{' …' if len(gone) > 5 else ''}. "
                   "일부러 지우는 거면 --allow-delete N 으로 다시 올려요")
    if only:
        outside = [p for _, p in rows if not any(p == o or (o.endswith("/") and p.startswith(o)) for o in only)]
        if outside:
            out.append(f"허락한 경로({', '.join(only)}) 밖이 바뀌었어요: {', '.join(outside[:5])}{' …' if len(outside) > 5 else ''}")
    return out, rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="안전한 push")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--only", nargs="*", default=None, help="이 경로(끝이 /면 그 아래)만 바뀌어야 해요")
    ap.add_argument("--allow-delete", type=int, default=MAX_DELETE)
    ap.add_argument("--check", action="store_true", help="올리지 않고 검사만")
    ap.add_argument("--no-rebase", action="store_true", help="merge 작업처럼 이미 합친 뒤")
    a = ap.parse_args()
    repo = Path(a.repo)
    try:
        new_branch = subprocess.run(["git", "-C", str(repo), "fetch", "--quiet", a.remote, a.branch], capture_output=True).returncode != 0
        if new_branch:  # 아직 없는 가지(claude/…): main 을 기준으로 검사하고 다시 얹지 않아요
            git(repo, "fetch", "--quiet", a.remote, "main")
            base = f"{a.remote}/main"
        else:
            base = f"{a.remote}/{a.branch}"
        exists = git(repo, "rev-parse", "--verify", "--quiet", base, check=False).strip()
        if exists and not a.no_rebase and not new_branch:
            if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD"]).returncode != 0:
                r = subprocess.run(["git", "-C", str(repo), "rebase", "--autostash", base], capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r.returncode != 0:
                    subprocess.run(["git", "-C", str(repo), "rebase", "--abort"], capture_output=True)
                    raise Stop(f"다른 세션이 먼저 올린 {base} 와 겹쳐요(충돌). 다시 얹기를 되돌렸어요. 충돌을 직접 풀고 다시 올려요: {(r.stdout + r.stderr).strip()[:300]}")
                print(f"  {base} 의 새 커밋 위로 다시 얹었어요")
        problems, rows = checks(repo, base if exists else "HEAD~0", a.only, a.allow_delete) if exists else ([], [])
        for p in problems:
            print("  막음: " + p)
        if problems:
            sys.exit(2)
        print(f"  올릴 변경 {len(rows)}개 (지움 {sum(1 for s, _ in rows if s == 'D')}개)")
        if a.check:
            print("검사만 했어요(올리지 않음)")
            return
        if not rows and exists:
            print("올릴 것이 없어요")
            return
        target = f"HEAD:{a.branch}"
        git(repo, "push", a.remote, target)
        git(repo, "fetch", "--quiet", a.remote, a.branch)
        if git(repo, "rev-parse", "FETCH_HEAD").strip() != git(repo, "rev-parse", "HEAD").strip():
            raise Stop("올렸는데 원격 머리가 내 커밋과 달라요. 직접 확인해요")
        print(f"올렸어요: {git(repo, 'log', '--oneline', '-1').strip()}")
    except Stop as e:
        print("  멈춤: " + str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
