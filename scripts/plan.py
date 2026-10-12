# -*- coding: utf-8 -*-
"""보낸 사진·동영상을 하루에 하나씩, 받은 순서대로 날짜에 나눠요.

- 한 날에는 하나만 써요. 여러 개를 보내도 하루에 몰아서 쓰지 않아요.
- 그날 쓸 것은 그날 저녁 메뉴 영상의 첫 장면에 들어가요. (PROMPT.md 참고)
- 보내지 않은 날에는 미리 받아 둔 것을 차례로 써요. 기한 없이 보관해요.
- 날짜가 지났는데 못 쓴 것이 있으면 다음 빈 날로 옮겨요.
쓸 날짜는 myphotos/index.json 의 plan 에 적어요.
"""
from datetime import datetime, timedelta

from common import KST

WEEK = "월화수목금토일"


def first_day(now=None):
    """지금 받으면 가장 빨리 쓸 수 있는 날. 영상은 매일 오전 6시에 만들어요."""
    now = now or datetime.now(KST)
    return (now if (now.hour, now.minute) < (5, 50) else now + timedelta(days=1)).date()


def waiting(index):
    return [e for e in index if not e.get("used") and not e.get("deleted")]


def assign(index, now=None):
    """아직 안 쓴 것마다 쓸 날짜를 정해요. 날짜가 새로 정해지거나 바뀐 항목들을 돌려줘요."""
    start = first_day(now)
    taken, changed = set(), []
    for e in sorted(waiting(index), key=lambda e: (e.get("at", 0), e["id"])):
        plan = e.get("plan")
        if plan and plan >= start.isoformat() and plan not in taken:
            taken.add(plan)
            continue
        day = start
        while day.isoformat() in taken:
            day += timedelta(days=1)
        e["plan"] = day.isoformat()
        taken.add(e["plan"])
        changed.append(e)
    return changed


def label(e):
    d = datetime.strptime(e["plan"], "%Y-%m-%d")
    kind = "동영상" if e.get("type") == "video" else "사진"
    return f"{d.month}월 {d.day}일({WEEK[d.weekday()]}) {kind} '{e.get('note') or '이름 없음'}'"


def lines(index):
    """앞으로 쓸 순서를 알려 주는 글."""
    items = sorted((e for e in waiting(index) if e.get("plan")), key=lambda e: e["plan"])
    if not items:
        return ["보관 중인 사진·동영상이 없어요. 보내 주시면 다음 날 영상의 첫 장면에 써요."]
    out = ["하루에 하나씩, 그날 저녁 메뉴 영상의 첫 장면에 써요.", *["· " + label(e) for e in items[:14]]]
    if len(items) > 14:
        out.append(f"· 그 뒤로 {len(items) - 14}개 더 있어요.")
    return out


def used_on(index, day):
    """그날 영상에 쓴 것."""
    return [e for e in index if any(u.startswith(day + "/") for u in e.get("used") or [])]
