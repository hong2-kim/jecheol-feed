# 보류 중인 규칙 (읽지 않는다)

2026-10-19 사용자가 보류하기로 한 것들이다. **매일 실행은 이 폴더를 읽지 않고, 여기 있는 규칙을 따르지 않는다.** `scripts/today_rules.py` 도 이 폴더를 고르지 않는다. 승인되면 그때 `rules/` 나 `PROMPT.md` 로 옮긴다.

| 보류한 것 | 여기 있는 원문 | 원본 |
|---|---|---|
| 100점 점수표 (`score`, `total_checked`, `total_with_guess`, 70/40 판정, `channel_ref` 를 관심도 근거로 쓰는 법) | `card-story-mode-held.md` 의 2-3 | 브랜치 `card-story-mode`(b3ee942)의 `PROMPT.md` |
| 25~34세 타깃 가설 (`target`) | `card-story-mode-held.md` 의 2-2 | 같은 곳 |
| 새 소재 갈래 "먹는 생활이 바뀌는 소식"과 분류 `트렌드`·`연구` | `card-story-mode-held.md` | 같은 곳 |
| `sources.json` 검색어 11개 | `sources.card-story-mode.json` (그 브랜치의 `sources.json` 통째) | 브랜치 `card-story-mode` 의 `sources.json` |
| 이야기 카드 본보기의 보류 칸 | `examples/2-news-story.original.json` (보류 칸을 지우기 전 본보기 그대로) | `main` 의 `video/examples/2-news-story.json` (72fcf02) |

- 실제로 쓰는 `sources.json` 은 바꾸지 않았다. `scripts/fetch_sources.py` 는 이 폴더를 읽지 않는다.
- 설계도에 보류 칸이 들어갔는지는 `python3 scripts/today_rules.py --check 날짜` 가 알려 준다.
- 백업: 브랜치 `card-story-mode`(이름 그대로), 태그 `keep/card-story-mode-2026-10-18`, 번들 `usage/backup/2026-10-18-card-story/card-story-mode-b3ee942.bundle`(저장소 밖).
- `scripts/channel_ref.py` 와 `scripts/reaction_log.py` 는 1차 병합 때 들어온 읽기 전용 도구라 그대로 둔다. `reaction_log.py` 는 이 칸이 없으면 "미기록"으로 보여 준다.
