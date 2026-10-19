# CLAUDE.md 바꿀 곳 (적용하지 않음, 병합할 때 함께)

대상: `C:\Users\User\클로드 연습하기\CLAUDE.md` (저장소 밖. 이 컴퓨터의 Claude Code 대화가 읽는다). "작업 지도" 절의 세 줄만 바꾼다. 다른 절(블로그 정보, 네이버 발행, 유튜브, 사용자 사진 등)은 그대로 둔다.

## 1. "매일 만들기" 줄

지금:
```
- **매일 만들기**: 클라우드 루틴 "먹거리 릴스 매일 제작"(claude.ai, 매일 06:00 한국 시간, RemoteTrigger `trig_01Mwt3bszdL58b5zf1J9RHC1`)이 `jecheol-feed` 저장소의 `PROMPT.md` 를 따라 `videos/날짜/`, `items/날짜/`, `blog/`, `trend/` 를 커밋한다.
```
바꿀 글:
```
- **매일 만들기**: 클라우드 루틴 "먹거리 릴스 매일 제작"(claude.ai, 매일 06:00 한국 시간, RemoteTrigger `trig_01Mwt3bszdL58b5zf1J9RHC1`)이 `jecheol-feed` 의 `PROMPT.md`(공통 규칙)와, `scripts/today_rules.py` 가 그날 고른 `rules/` 파일을 따라 `videos/날짜/`, `items/날짜/`, `blog/`, `trend/` 를 커밋한다.
```

## 2. "고칠 곳" 줄

지금:
```
- **고칠 곳**: 콘텐츠 규칙 `jecheol-feed/PROMPT.md` · 카드·장면 그림 `jecheol-feed/video/build.py` · …
```
바꿀 글 (앞부분만 바뀌고 `· 카드·장면 그림` 부터는 그대로):
```
- **고칠 곳**: 공통 규칙 `jecheol-feed/PROMPT.md` · 콘텐츠·요일별 규칙 `jecheol-feed/rules/`(파일 목록은 PROMPT.md "오늘 읽을 규칙" 표, 어느 날 무엇을 읽는지는 `scripts/today_rules.py`) · 보류 중인 규칙 `rules/_hold/`(매일 실행이 읽지 않음, 승인 전에는 옮기지 않음) · 카드·장면 그림 `jecheol-feed/video/build.py` · …
```
- 규칙을 새로 더할 때: 매일 쓰는 것은 `PROMPT.md`, 한 콘텐츠에만 쓰는 것은 그 `rules/` 파일에 넣는다. 새 파일을 만들면 `today_rules.py` 의 목록과 PROMPT.md 의 표에도 넣는다. (이 줄을 "고칠 곳" 아래에 더한다)

## 3. "읽는 법" 첫 줄

지금:
```
  - `PROMPT.md`(약 147KB)와 `video/build.py`(약 65KB)는 통째로 읽지 않는다. `grep -n '^#' PROMPT.md`, `grep -n 'def ' video/build.py` 로 자리를 찾아 그 부분만 읽는다.
```
바꿀 글:
```
  - `PROMPT.md` 는 공통 규칙만 남아 약 33KB 라 통째로 읽어도 된다. 한 콘텐츠를 고칠 때는 그 `rules/` 파일만 연다. `rules/_hold/`, `docs/rules-history.md` 는 열지 않는다. `video/build.py`(약 65KB)는 통째로 읽지 않고 `grep -n 'def ' video/build.py` 로 자리를 찾아 그 부분만 읽는다.
```
