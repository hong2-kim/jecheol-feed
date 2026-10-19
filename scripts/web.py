# -*- coding: utf-8 -*-
"""웹에서 내려받을 때 함께 쓰는 도구예요. 같은 곳에 너무 자주 묻지 않고, 요청 제한(429)에는 몇 번만 다시 해요. (2026-10-19)

  from web import get, WebError
  data = get(url)                              바이트를 돌려줘요
  data = get(url, retries=3, gap=1.0)          gap: 같은 곳에 묻는 최소 간격(초), retries: 다시 할 횟수

- 429·503 이면 Retry-After(초 또는 날짜)를 지켜 기다렸다가 다시 해요. 없으면 2초, 4초, 8초로 늘려요.
- Retry-After 가 WAIT_LIMIT 보다 길거나 retries 번 다 실패하면 기다리지 않고 WebError 를 내요. 쓰는 쪽은 다른 사진·자료로 넘어가요.
- 연결이 끊기거나(ConnectionReset) 시간이 넘으면 1초, 2초 쉬었다가 다시 해요.
- 간격은 호스트마다 임시 폴더의 작은 파일에 마지막 요청 시각을 적어 지켜요. 따로 돌린 명령끼리도 간격이 지켜져요.
"""
import email.utils
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "jecheol-feed/1.0 (https://github.com/hong2-kim/jecheol-feed)"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6"}
# 위키미디어는 봇 요청을 1초에 한 번쯤으로 권해요. 구글 뉴스도 몰아서 물으면 429 를 줘요.
GAP = {"commons.wikimedia.org": 1.0, "upload.wikimedia.org": 0.3, "news.google.com": 1.0}
WAIT_LIMIT = 60
RETRY_CODES = (429, 503)


class WebError(Exception):
    pass


def _stamp(host):
    return os.path.join(tempfile.gettempdir(), f"jecheol-web-{host or 'local'}.ts")


def _take_turn(host, gap):
    """같은 호스트에 gap 초보다 자주 묻지 않게 기다려요."""
    if gap <= 0:
        return
    path = _stamp(host)
    try:
        with open(path, encoding="utf-8") as f:
            last = float(f.read().strip() or 0)
    except (OSError, ValueError):
        last = 0.0
    wait = last + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def retry_after(headers):
    """Retry-After 를 초로 바꿔요. 없거나 못 읽으면 None."""
    value = (headers or {}).get("Retry-After") if headers is not None else None
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
        return max(0.0, when.timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def get(url, timeout=40, headers=None, retries=3, gap=None, data=None, quiet=False):
    host = urllib.parse.urlsplit(url).hostname or ""
    gap = GAP.get(host, 0.0) if gap is None else gap
    for n in range(retries + 1):
        _take_turn(host, gap)
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES:
                raise WebError(f"{host}: HTTP {e.code} {e.reason}") from None
            wait = retry_after(e.headers)
            if wait is None:
                wait = float(2 ** (n + 1))
            if wait > WAIT_LIMIT:
                raise WebError(f"{host}: 요청 제한(HTTP {e.code}). {wait:.0f}초 뒤에 다시 하라고 해서 기다리지 않아요") from None
            if n == retries:
                raise WebError(f"{host}: 요청 제한(HTTP {e.code})이 {retries + 1}번 이어져 그만해요") from None
            if not quiet:
                print(f"  {host}: 요청 제한(HTTP {e.code}). {wait:.0f}초 기다렸다가 다시 해요 ({n + 1}/{retries})", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if n == retries:
                raise WebError(f"{host}: 연결 실패 ({str(e)[:80]})") from None
            time.sleep(float(2 ** n))
    raise WebError(f"{host}: 실패")
