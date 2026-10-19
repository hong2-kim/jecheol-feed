# -*- coding: utf-8 -*-
"""저녁 추천 쇼츠에 쓸 가격을 공식 자료에서 찾아요. (2026-10-19, rules/_hold/dinner-v2.md)

  python scripts/prices.py cu 떡볶이 김밥 핫바        CU 홈페이지 상품 목록에서 이름에 그 말이 든 상품과 판매가
  python scripts/prices.py kamis 돼지/앞다리 계란/특란10구 쪽파   KAMIS 전국 평균 소매가(최근 날짜 하나)
  python scripts/prices.py kamis-list                   KAMIS 에서 찾을 수 있는 품목 이름

결과는 한 줄에 하나씩 JSON: {"what", "value", "unit", "src", "url", "checked", "status", "note"}.
그대로 설계도의 "facts" 에 넣고 id 만 붙이면 돼요. 행사(1+1, 2+1)는 note 에만 적고 값에는 넣지 않아요.
CU 목록은 점포 재고가 아니라 본사 상품 목록이라, 영상과 게시글에 "점포마다 없을 수 있어요"를 적어요.
"""
import datetime
import json
import re
import sys
import urllib.parse

from web import get as web_get

CU_URL = "https://cu.bgfretail.com/product/productAjax.do"
CU_CATS = {"10": "간편식사", "20": "즉석조리", "50": "식품", "30": "과자류", "60": "음료"}
KAMIS_URL = "https://www.kamis.or.kr/customer/info/retail/period.do"
# KAMIS 품목 번호 (부류/품목/품종). 2026-10-19 KAMIS 간편가격정보 화면에서 읽었어요.
KAMIS = {
    "돼지/앞다리": ("500", "4304", "25"), "돼지/삼겹살": ("500", "4304", "27"), "돼지/목심": ("500", "4304", "68"),
    "닭/육계": ("500", "9901", "99"), "계란/특란10구": ("500", "9903", "21"), "계란/특란30구": ("500", "9903", "23"),
    "배추": ("200", "211", "03"), "양배추": ("200", "212", "00"), "시금치": ("200", "213", "00"),
    "상추/적": ("200", "214", "01"), "상추/청": ("200", "214", "02"), "무": ("200", "231", "03"), "당근": ("200", "232", "01"),
    "청양고추": ("200", "242", "03"), "풋고추": ("200", "242", "00"), "양파": ("200", "245", "00"), "대파": ("200", "246", "00"),
    "쪽파": ("200", "246", "02"), "깻잎": ("200", "253", "00"), "부추": ("200", "254", "00"), "깐마늘": ("200", "258", "01"),
    "느타리버섯": ("300", "315", "00"), "팽이버섯": ("300", "316", "00"), "새송이버섯": ("300", "317", "00"),
    "쌀": ("100", "111", "EE"),
}


def today():
    return datetime.date.today().isoformat()


def cu_page(cat, page):
    data = urllib.parse.urlencode({"pageIndex": page, "searchMainCategory": cat, "listType": 0, "searchCondition": "setA",
                                   "gdIdx": 0, "codeParent": cat}).encode()
    raw = web_get(CU_URL, data=data, timeout=30)
    return re.findall(rb'view\((\d+)\);"><p>(.*?)</p>.*?<strong>([\d,]+)</strong>(.*?)</li>', raw, re.S)


def cu(words, pages=12):
    """CU 상품 목록(간편식사·즉석조리·식품 등)을 훑어 이름에 words 중 하나가 든 상품."""
    seen = set()
    for cat, cat_name in CU_CATS.items():
        last = None
        for page in range(1, pages + 1):
            rows = cu_page(cat, page)
            if not rows or rows == last:  # 끝 쪽을 넘기면 빈 목록이나 같은 목록이 와요
                break
            last = rows
            for gid, name, price, rest in rows:
                name = name.decode("utf-8", "replace")
                if gid in seen or not any(w in name for w in words):
                    continue
                seen.add(gid)
                badge = {"plus1": "1+1", "plus2": "2+1"}
                event = [badge[b.decode()] for b in re.findall(rb'class="(plus\d)"', rest) if b.decode() in badge]
                yield {"what": f"CU {name}", "value": int(price.decode().replace(",", "")), "unit": "원",
                       "src": f"CU 홈페이지 상품 목록({cat_name})", "url": "https://cu.bgfretail.com/product/product.do",
                       "checked": today(), "status": "확인", "note": f"행사 {', '.join(event)} (값에 넣지 않음)" if event else ""}


def kamis(name):
    """KAMIS 전국 평균 소매가 중 가장 최근 날짜 하나."""
    cat, item, kind = KAMIS[name]
    end = datetime.date.today()
    query = urllib.parse.urlencode({"action": "daily", "startday": (end - datetime.timedelta(days=10)).strftime("%Y.%m.%d"),
                                    "endday": end.strftime("%Y.%m.%d"), "itemcategorycode": cat, "itemcode": item,
                                    "kindcode": kind, "productrankcode": 0, "countycode": ""})
    # KAMIS 는 우리 이름표(User-Agent)로 물으면 답이 없어서 보통 브라우저 이름으로 물어요 (2026-10-19)
    text = web_get(f"{KAMIS_URL}?{query}", timeout=30, headers={"User-Agent": "Mozilla/5.0"}).decode("utf-8", "replace")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    unit = re.search(r"단위 : ([^ ]+)", text)
    rows = re.findall(r"(\d\d)\.(\d\d)\.(\d\d)\s+([\d,]+)", text)
    if not rows:
        return {"what": name, "status": "미확인", "note": "KAMIS 에 최근 10일 값이 없어요"}
    y, m, d, value = rows[0]
    return {"what": f"{name} ({unit[1] if unit else '?'})", "value": int(value.replace(",", "")), "unit": "원",
            "per": unit[1] if unit else "", "src": "KAMIS 소매가격(전국 평균)", "url": KAMIS_URL,
            "checked": f"20{y}-{m}-{d}", "status": "확인", "note": "평균값이라 가게마다 달라요"}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("cu", "kamis", "kamis-list"):
        print(__doc__)
        sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "kamis-list":
        print("\n".join(KAMIS))
        return
    rows = cu(args) if cmd == "cu" else (kamis(a) for a in args)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
