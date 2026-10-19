# -*- coding: utf-8 -*-
"""우리 채널 쇼츠 가운데 비슷한 주제가 예전에 얼마나 보였는지 찾아요. 점수표 관심도의 근거로 써요. (2026-10-18)

  python scripts/channel_ref.py 편의점 김밥
  python scripts/channel_ref.py --kind 소식

- state/yt_stats.json 의 가장 최근 기록에서 제목에 낱말이 하나라도 들어간 쇼츠를 찾아요(--kind 면 그 종류 전부).
- 영상마다 조회수와 그때 몇 시간 지났는지(나이)를 보여 줘요. 갓 올린 영상은 조회수가 아직 덜 쌓였어요.
- 맨 끝에 표본 수(n)와 조회수 중앙값, 채널 전체 중앙값을 적어요. 주제가 얼마나 비슷한지는 사람이(모델이) 판단해 적어요.
조회수는 올린 시각, 제목, 영상 꼴, 노출량에도 영향을 받아요. 주제가 좋다는 증거로 단정하지 않아요.
"""
import argparse
import json
import statistics
from datetime import datetime

from common import ROOT, read_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*")
    ap.add_argument("--kind", help="영상 종류(소식, 발견, 저녁, 유행, 해설 …)")
    a = ap.parse_args()
    led = read_json(ROOT / "state" / "yt_stats.json", {}) or {}
    days = sorted((led.get("days") or {}).items())
    if not days:
        print(json.dumps({"채널자료": "없음"}, ensure_ascii=False))
        return
    day, snap = days[-1]
    ats = [datetime.fromisoformat(v["at"].replace("Z", "+00:00")) for v in snap["videos"].values()]
    # 매일 오전 9시(한국)에 모으지만 실제로는 늦게 돌기도 해요. 그 기록에 든 가장 새 영상보다 앞일 수는 없어요
    taken = max([datetime.fromisoformat(day + "T00:00:00+00:00")] + ats)
    kinds = led.get("kinds") or {}
    allv = [v["v"] for v in snap["videos"].values()]
    hits = []
    for vid, v in snap["videos"].items():
        if (a.kind and kinds.get(vid) == a.kind) or (a.words and any(w in v["t"] for w in a.words)):
            age = (taken - datetime.fromisoformat(v["at"].replace("Z", "+00:00"))).total_seconds() / 3600
            hits.append({"제목": v["t"], "종류": kinds.get(vid, "?"), "조회수": v["v"], "나이_시간": round(age)})
    for h in sorted(hits, key=lambda h: -h["조회수"]):
        print(json.dumps(h, ensure_ascii=False))
    young = sum(h["나이_시간"] < 24 for h in hits)
    print(json.dumps({"기준일": day, "n": len(hits), "조회수_중앙값": statistics.median([h["조회수"] for h in hits]) if hits else None,
                      "채널전체_중앙값": statistics.median(allv) if allv else None, "채널전체_n": len(allv),
                      "참고": (f"{young}개는 올린 지 하루가 안 돼 덜 쌓였어요. " if young else "") + "n 이 3보다 적으면 근거가 약해요"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
