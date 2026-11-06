# -*- coding: utf-8 -*-
"""비공개 사진 보관함(hong2-kim/jecheol-photos)에 파일을 '더하기만' 해요 (2026-11-06 보관함 525개 삭제 사고 뒤).

  python scripts/vault_put.py press/2026-11-06-news 사진1.jpg 사진2.jpg     보관함 press/2026-11-06-news/ 에 올려요
  python scripts/vault_put.py press/2026-11-06-news 사진1.jpg --replace     같은 이름이 있으면 바꿔요(없으면 그냥 더해요)

저장소를 받아(clone) 커밋하지 않고, GitHub 파일 API 로 한 파일씩 올려요. 그래서 다른 파일을 지울 수 없어요.
- 파일 하나라도 실패하면 거기서 멈추고(끝 코드 2), 이미 올린 파일과 못 올린 파일을 알려 줘요.
- 같은 이름이 이미 있으면 --replace 없이는 바꾸지 않아요(내용이 같으면 건너뛰어요).
- 올린 뒤 보관함의 파일 수가 줄었으면 경고하고 끝 코드 2 로 끝내요.
열쇠: 환경 변수 PHOTOS_TOKEN (없으면 이 컴퓨터의 git 자격 증명).
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "hong2-kim/jecheol-photos"
MAX_BYTES = 20 * 1024 * 1024


def token():
    t = os.environ.get("PHOTOS_TOKEN", "").strip()
    if t:
        return t
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    sys.exit("  멈춤: PHOTOS_TOKEN 이 없어요")


def api(method, path, body=None, tok=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "jecheol-feed-vault-put"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def file_count(tok):
    st, head = api("GET", "/commits/main", tok=tok)
    if st != 200:
        return None
    st, tree = api("GET", f"/git/trees/{head['commit']['tree']['sha']}?recursive=1", tok=tok)
    return sum(1 for x in tree.get("tree", []) if x.get("type") == "blob") if st == 200 else None


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    replace = "--replace" in sys.argv
    if len(args) < 2:
        sys.exit(__doc__)
    dest, files = args[0].strip("/"), [Path(f) for f in args[1:]]
    if dest.startswith(("photos/", "index.json")) or dest in ("", "."):
        sys.exit("  멈춤: 사용자 사진(photos/)·목록(index.json)은 이 도구로 올리지 않아요")
    tok = token()
    before = file_count(tok)
    done, skipped = [], []
    for f in files:
        data = f.read_bytes()
        if len(data) > MAX_BYTES:
            print(f"  멈춤: {f.name} 가 너무 커요({len(data)//1024//1024}MB)")
            break
        path = f"{dest}/{f.name}"
        st, cur = api("GET", f"/contents/{urllib.parse.quote(path)}?ref=main", tok=tok)
        body = {"message": f"{path} 올림 (vault_put)", "content": base64.b64encode(data).decode(), "branch": "main"}
        if st == 200:
            if cur.get("sha") == blob_sha(data):
                skipped.append(path)
                continue
            if not replace:
                print(f"  멈춤: {path} 가 이미 있고 내용이 달라요. 바꾸려면 --replace")
                break
            body["sha"] = cur["sha"]
        st, res = api("PUT", f"/contents/{urllib.parse.quote(path)}", body, tok=tok)
        if st not in (200, 201):
            print(f"  멈춤: {path} 올리기 실패({st}): {str(res.get('message'))[:200]}")
            break
        done.append(path)
    after = file_count(tok)
    print(json.dumps({"올림": done, "같아서 건너뜀": skipped, "못 올림": [f"{dest}/{f.name}" for f in files][len(done) + len(skipped):],
                      "보관함 파일 수": [before, after]}, ensure_ascii=False, indent=1))
    if before is not None and after is not None and after < before:
        print(f"  경고: 보관함 파일 수가 {before} → {after} 로 줄었어요. 바로 확인해요")
        sys.exit(2)
    if len(done) + len(skipped) < len(files):
        sys.exit(2)


if __name__ == "__main__":
    main()
