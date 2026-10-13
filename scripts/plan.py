# -*- coding: utf-8 -*-
"""보낸 사진·동영상을 하루에 하나씩, 받은 순서대로 날짜에 나눠요.

- 한 날에는 하나만 써요. 여러 개를 보내도 하루에 몰아서 쓰지 않아요.
- 그날 쓸 것은 그날 저녁 메뉴 영상의 첫 장면에 들어가요. (PROMPT.md 참고)
- 보내지 않은 날에는 미리 받아 둔 것을 차례로 써요. 기한 없이 보관해요.
- 날짜가 지났는데 못 쓴 것이 있으면 다음 빈 날로 옮겨요.
- 비슷한 음식(돈까스와 치즈돈까스)이 일주일 안에 이어지면 뒤의 것은 한 주 미루고,
  첫 장면이 아니라 메뉴 카드 한 장에 넣어요. 같은 음식이 이틀 내리 주인공이 되지 않게요.
쓸 날짜는 myphotos/index.json 에 적어요. 첫 장면에 쓸 것은 plan, 미뤄서 메뉴 카드에 넣을 것은 side 예요.
"""
from datetime import date, datetime, timedelta

from common import KST

WEEK = "월화수목금토일"
GAP = 7  # 비슷한 음식 사이에 두는 날 수


def first_day(now=None):
    """지금 받으면 가장 빨리 쓸 수 있는 날. 영상은 매일 오전 6시에 만들어요."""
    now = now or datetime.now(KST)
    return (now if (now.hour, now.minute) < (5, 50) else now + timedelta(days=1)).date()


def waiting(index):
    return [e for e in index if not e.get("used") and not e.get("deleted")]


def name(e):
    """함께 적은 글의 첫 낱말을 음식 이름으로 봐요."""
    words = (e.get("note") or "").replace(",", " ").split()
    return words[0] if words else ""


def food(e):
    return name(e).replace("까스", "가스")  # 돈까스와 돈가스는 같은 음식


def similar(a, b):
    """한쪽 이름이 다른 쪽에 들어 있으면 비슷한 음식이에요. (돈까스 ⊂ 치즈돈까스. 한 글자 이름은 보지 않아요)"""
    short, long = sorted((food(a), food(b)), key=len)
    return len(short) >= 2 and short in long


def when(e):
    """그 자료를 썼거나 쓰기로 한 날."""
    text = e["used"][0][:10] if e.get("used") else e.get("plan") or e.get("side")
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def assign(index, now=None):
    """아직 안 쓴 것마다 쓸 날짜를 정해요. 날짜가 새로 정해지거나 바뀐 항목들을 돌려줘요."""
    start = first_day(now)
    today = (now or datetime.now(KST)).date().isoformat()
    taken, sides, changed = set(), set(), []
    seen = [e for e in index if e.get("used") and not e.get("deleted")]  # 이미 쓴 것과, 앞서 날짜를 잡은 것
    for e in sorted(waiting(index), key=lambda e: (e.get("at", 0), e["id"])):
        before = (e.get("plan"), e.get("side"))
        if e.get("plan") == today and today not in taken:  # 오늘 쓰기로 한 것은 오늘이 끝날 때까지 옮기지 않아요
            taken.add(today)
            seen.append(e)
            continue
        if e.get("side") and e["side"] >= start.isoformat() and e["side"] not in sides:  # 이미 미뤄 둔 것은 그대로
            sides.add(e["side"])
            seen.append(e)
            continue
        day = start
        while day.isoformat() in taken:
            day += timedelta(days=1)
        twins = [(when(o), o) for o in seen if similar(e, o) and when(o) and abs((day - when(o)).days) < GAP]
        if twins:
            last, twin = max(twins, key=lambda t: t[0])
            late = max(last + timedelta(days=GAP), start)
            while late.isoformat() in sides:
                late += timedelta(days=1)
            e.pop("plan", None)
            e["side"], e["side_of"] = late.isoformat(), name(twin)
            sides.add(e["side"])
        else:
            e.pop("side", None)
            e.pop("side_of", None)
            e["plan"] = day.isoformat()
            taken.add(e["plan"])
        if (e.get("plan"), e.get("side")) != before:
            changed.append(e)
        seen.append(e)
    return changed


def label(e):
    d = when(e)
    kind = "동영상" if e.get("type") == "video" else "사진"
    text = f"{d.month}월 {d.day}일({WEEK[d.weekday()]}) {kind} '{e.get('note') or '이름 없음'}'"
    if e.get("side"):
        text += f" → '{e.get('side_of')}'와 비슷해 한 주 뒤, 메뉴 카드로"
    return text


def lines(index):
    """앞으로 쓸 순서를 알려 주는 글."""
    items = sorted((e for e in waiting(index) if when(e)), key=when)
    if not items:
        return ["보관 중인 사진·동영상이 없어요. 보내 주시면 다음 날 영상의 첫 장면에 써요."]
    out = ["하루에 하나씩, 그날 저녁 메뉴 영상의 첫 장면에 써요.", *["· " + label(e) for e in items[:14]]]
    if len(items) > 14:
        out.append(f"· 그 뒤로 {len(items) - 14}개 더 있어요.")
    if any(e.get("side") for e in items):
        out.append("비슷한 음식이 이어지면 뒤의 것은 한 주 미뤄서, 첫 장면이 아닌 메뉴 카드에 넣어요.")
    return out


def used_on(index, day):
    """그날 영상에 쓴 것."""
    return [e for e in index if any(u.startswith(day + "/") for u in e.get("used") or [])]
