# 소식 글 (`items/`)

> 언제 읽나: 매일. 공통 규칙은 `PROMPT.md`. (2026-10-19 PROMPT.md 에서 옮겨 왔다. 고친 곳은 `docs/stage3-rule-split.md`)

## 소식 글

`items/2026-10-11/` 의 글이 본보기다. 하루 5개(한국 제철 1, 해외 제철 1, 축제 1, 식품 안전 1, 예고 1), 최소 3개. 여기서도 버섯류, 기름·양념류, 어른 취향 소재는 피한다.

| 항목 | 뜻 |
|---|---|
| `id`, `date` | `날짜-이름`, 내보내는 날 |
| `category` | 한국 제철 / 해외 제철 / 축제 / 식품 안전 / 예고 |
| `country`, `region`, `subject`, `angle`, `season` | 나라, 지역, 주제, 다루는 각도, 시기 |
| `title`, `summary`(3~5문장), `facts` | 릴스 제목, 핵심 내용, 흥미로운 사실 |
| `script` | `hook`(첫 3초), `flow`, `closing` |
| `length_sec`(15~45), `visuals`, `pairing`(`drink`, `note`), `cautions` | 길이, 화면 아이디어, 어울리는 술, 주의사항 |
| `unverified`, `sources`(`name`, `url`, `official`), `checked` | 추가 확인 필요, 출처, 확인 날짜 |

`angle`(다루는 각도)과 `facts`(흥미로운 사실)는 "우리가 만드는 것"의 갈래에서 찾는다. "지금 제철이다"에서 그치지 않고, 왜 지금인지, 어디서 시작됐는지, 지역이나 나라마다 어떻게 다르게 먹는지 가운데 확인되는 것을 고른다.

직접 열지 못한 출처에는 `official` 을 `true` 로 적지 않는다. `pairing.drink` 는 `소주`, `맥주`, `소주 or 사케` 처럼 쉽게 쓴다.
