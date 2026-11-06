# -*- coding: utf-8 -*-
"""특정 제품의 실제 사진을 여러 검색어·여러 경로로 한 번에 찾아요. (2026-11-06 사용자: "사진을 못 찾으면 포기하는 시스템이 아니라,
스스로 검색 방법을 바꿔 정확한 사진을 확보하는 시스템")

  python3 scripts/findphoto.py "파리바게뜨" "초코 쫀득 츄러스" [--en "churros"] [--days 90]
  python3 scripts/findphoto.py rights          회사별 사진 이용 조건과 '회사 확인 필요'(권한 미확인) 목록 (sources.json photo_rights)

하는 일 (읽기만 해요. 사진을 내려받거나 설계도를 고치지 않아요):
  1. 검색어를 여러 꼴로 만들어요: 브랜드+제품명, 제품명만, 줄임말·회사 이름(파바·SPC, GS리테일…), '출시'·'신제품'을 붙인 말, 띄어쓰기 뺀 말
  2. 경로를 차례로 봐요: ① 뉴스와이어 보도자료(원본 사진. 배포됐다는 것만으로 상업적 재사용이 허용되지는 않아요: 사진 출처·약관 조건·허용 범위를 photo_rights 대로 따로 봐요) ② 언론 기사의 사진 설명('○○ 제공' = 회사 보도자료 사진 → 원본은 회사 게시판)
     ③ 회사 보도자료 게시판 주소(권리 기록부의 press_board) ④ 위키미디어·오픈버스의 CC 사진(그 제품·그 회사 매장)
  3. 회사 사진 이용 상태(사용 가능/확인 필요/사용 불가)를 권리 기록부에서 찾아 같이 알려 줘요. 상태를 바꾸지 않아요.
  4. 설계도 photo_search 에 붙일 한 줄 기록을 만들어 줘요.
찾은 사진은 꼭 열어 보고(photos.py get 뒤 Read) 제품 이름·로고·포장 글자·생김새가 맞는지 확인한 뒤 match: 정확 으로 써요.
기자·통신사가 찍은 사진, 판매 사이트 사진은 여기서 찾아도 쓰지 않아요(기존 기준 그대로).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web import WebError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# 같은 회사를 부르는 다른 이름. 검색어를 바꿀 때 써요
ALIASES = {
    "파리바게뜨": ["파바", "SPC", "SPC 파리바게뜨"], "배스킨라빈스": ["배라", "SPC"], "던킨": ["SPC"], "삼립": ["SPC삼립"],
    "GS25": ["GS리테일", "지에스25"], "CU": ["BGF리테일", "씨유"], "세븐일레븐": ["코리아세븐"], "이마트24": ["emart24"],
    "이마트": ["신세계"], "롯데마트": ["롯데쇼핑"], "농심": [], "오뚜기": [], "CJ": ["CJ제일제당"], "비비고": ["CJ제일제당"],
    "풀무원": [], "동원": ["동원F&B"], "대상": ["청정원"], "청정원": ["대상"], "하림": [], "오리온": [], "빙그레": [], "해태": ["해태제과"],
    "롯데웰푸드": ["롯데"], "맘스터치": [], "롯데리아": ["롯데GRS"], "맥도날드": [], "버거킹": [], "스타벅스": [], "투썸": ["투썸플레이스"],
}
EXTRA = ("출시", "신제품")
# 위키미디어·오픈버스는 영어 제목이 많아요
EN_BRAND = {"파리바게뜨": ["Paris Baguette"], "배스킨라빈스": ["Baskin Robbins"], "던킨": ["Dunkin"], "GS25": ["GS25"], "CU": ["CU convenience"],
            "세븐일레븐": ["7-Eleven Korea"], "이마트24": ["emart24"], "이마트": ["E-mart", "Emart"], "롯데마트": ["Lotte Mart"], "농심": ["Nongshim"],
            "오뚜기": ["Ottogi"], "CJ": ["CJ CheilJedang"], "비비고": ["bibigo"], "풀무원": ["Pulmuone"], "오리온": ["Orion"], "빙그레": ["Binggrae"],
            "맘스터치": ["Mom's Touch"], "롯데리아": ["Lotteria"], "맥도날드": ["McDonald's"], "버거킹": ["Burger King"], "스타벅스": ["Starbucks"],
            "투썸": ["A Twosome Place"], "교촌": ["Kyochon"], "BBQ": ["BBQ chicken"], "bhc": ["bhc chicken"]}


def variants(brand, name):
    """검색어 여러 꼴 (앞에서부터 중요한 차례)."""
    out = [f"{brand} {name}", name, f"{brand} {name.replace(' ', '')}"]
    out += [f"{a} {name}" for a in ALIASES.get(brand, [])]
    out += [f"{brand} {name} {e}" for e in EXTRA]
    words = name.split()
    if len(words) > 2:  # 긴 이름은 앞뒤를 줄여서도 (보도 제목은 이름을 줄여 쓸 때가 많아요)
        out += [f"{brand} {' '.join(words[-2:])}", f"{brand} {words[0]} {words[-1]}"]
    seen, uniq = set(), []
    for q in out:
        q = " ".join(q.split())
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq


def relevant(title, brand, name):
    """제목이 그 제품 이야기인지: 브랜드(또는 다른 이름)와 제품 이름의 특이한 낱말이 함께 있어야 해요."""
    t = title.replace(" ", "")
    names = [brand] + ALIASES.get(brand, [])
    keys = [w for w in name.split() if len(w) >= 2] or [name]
    return any(n.replace(" ", "") in t for n in names) and any(k in t for k in keys)


def rights_rows():
    return json.loads((ROOT / "sources.json").read_text(encoding="utf-8")).get("photo_rights") or []


def rights_of(brand):
    """권리 기록부에서 그 브랜드의 회사 항목. 없으면 None."""
    names = {brand, *ALIASES.get(brand, [])}
    for r in rights_rows():
        if set(r.get("brands") or []) & names or any(n in r.get("name", "") for n in names):
            return r
    return None


def company_photo(caps, brand):
    """사진 설명이 회사가 배포한 사진인지: '○○ 제공', '사진=회사이름'. 기자·그래픽·통신사 촬영은 아니에요."""
    names = [brand, *ALIASES.get(brand, [])]
    for c in caps:
        if re.search(r"기자|그래픽|일러스트|촬영=", c):
            continue
        if "제공" in c or any(re.search(rf"(?:사진|이미지|자료)\s*[=:/]\s*{re.escape(n)}", c) for n in names):
            return True
    return False


def parse_text(out):
    """news.text 결과에서 사진·사진 설명·판단 줄."""
    pick = lambda key: next((json.loads(l[len(key) + 1:]) for l in out.splitlines() if l.startswith(key + " [")), [])
    hint = next((l[len("사진 판단(단서) "):] for l in out.splitlines() if l.startswith("사진 판단(단서) ")), "")
    title = next((l[3:] for l in out.splitlines() if l.startswith("제목 ")), "")
    return title, pick("사진"), pick("사진 설명"), hint


def find(brand, name, en="", days=90, max_open=4):
    import news
    import photos
    report = {"brand": brand, "name": name, "queries": variants(brand, name), "newswire": [], "articles": [], "cc": [], "tried": []}
    r = rights_of(brand)
    report["rights"] = {"name": r.get("name"), "status": r.get("status"), "scope": r.get("scope"), "press_board": r.get("press_board", ""),
                        "decision": r.get("decision", "")} if r else {"status": "기록 없음", "scope": "권리 기록부에 이 회사가 없어요. 조건을 확인하면 photo_rights 에 더해요"}
    # ① 뉴스와이어: 회사가 낸 보도자료의 원본 사진. 쓸 수 있는지는 photo_rights '뉴스와이어 배포 보도자료' 의 조건·범위와 사진 설명(촬영자 표시)으로 따로 봐요
    seen = set()
    for q in report["queries"][:4]:
        try:
            rows = news.press(q, days)
        except WebError as e:
            report["tried"].append(f"뉴스와이어 '{q}': 못 읽음({e})")
            continue
        hits = [row for row in rows if relevant(row[1], brand, name) and row[2] not in seen]
        report["tried"].append(f"뉴스와이어 '{q}': {len(rows)}건 중 그 제품 {len(hits)}건")
        for when, title, link in hits[:2]:
            seen.add(link)
            try:
                t, pics, caps, hint = parse_text(news.text(link, chars=0, images=True))
            except WebError as e:
                report["tried"].append(f"  열지 못함 {link} ({e})")
                continue
            report["newswire"].append({"when": when, "title": title, "url": link, "photos": pics, "captions": caps, "use": hint})
        if report["newswire"]:
            break
    # ② 언론 기사의 사진 설명: '○○ 제공' 이면 회사가 배포한 보도자료 사진이에요. 기사에 실린 파일은 쓰지 않고 원본(회사 게시판·뉴스와이어)을 찾아요
    opened = 0
    for q in report["queries"][:3]:
        try:
            rows = news.search(f"{q}", days, 10)
        except WebError as e:
            report["tried"].append(f"기사 검색 '{q}': 못 읽음({e})")
            continue
        hits = [row for row in rows if relevant(row[2], brand, name)]
        report["tried"].append(f"기사 검색 '{q}': {len(rows)}건 중 그 제품 {len(hits)}건")
        for when, src, title, link in hits:
            if opened >= max_open or link in seen:
                continue
            seen.add(link)
            opened += 1
            try:
                t, pics, caps, hint = parse_text(news.text(link, chars=0, images=True))
            except WebError as e:
                report["tried"].append(f"  열지 못함 {src} ({e})")
                continue
            report["articles"].append({"when": when, "source": src, "title": title, "url": link, "captions": caps, "hint": hint,
                                       "company_photo": company_photo(caps, brand)})
        if opened >= max_open:
            break
    # ④ CC 사진: 그 제품·그 회사 매장. 제목에 브랜드(우리말·영어)가 있어야 후보예요. 브랜드 없는 '츄러스' 사진은 비슷한 다른 음식이라 넣지 않아요.
    # 제품 이름까지 있으면 '제품', 브랜드만 있으면 '매장·회사'(그 회사 매장·행사 장면에 분위기 사진으로만)
    brand_keys = [k.lower() for k in [brand, *ALIASES.get(brand, []), *EN_BRAND.get(brand, [])] if len(k) >= 2]
    prod_keys = [w.lower() for w in name.split() if len(w) >= 2] + [w.lower() for w in en.split() if len(w) >= 3]
    seen_url = set()
    for q in dict.fromkeys(x for x in (*(f"{b} {en}".strip() for b in EN_BRAND.get(brand, [])), f"{brand} {en}".strip() if en else "", name,
                                       brand, *EN_BRAND.get(brand, [])) if x):
        for kind, fn in (("commons", photos.commons_rows), ("openverse", photos.openverse_rows)):
            try:
                rows = photos.cached(kind, q, fn)
            except WebError as e:
                report["tried"].append(f"{kind} '{q}': 못 읽음({e})")
                continue
            hits = [row for row in rows if any(k in (row.get("title") or "").lower() for k in brand_keys) and row.get("url") not in seen_url]
            report["tried"].append(f"{kind} '{q}': {len(rows)}장 중 브랜드가 맞는 {len(hits)}장")
            for row in hits[:3]:
                seen_url.add(row.get("url"))
                t = (row.get("title") or "").lower()
                report["cc"].append({"from": kind, "what": "제품" if any(k in t for k in prod_keys) else "회사 관련(이 제품 아님: 매장·행사 장면에만)",
                                     **{k: row.get(k) for k in ("url", "title", "size", "license", "credit")}})
    st = report["rights"].get("status")
    report["next"] = next_step(report, st)
    report["photo_search"] = {
        "exact": f"findphoto '{brand} {name}' 검색어 {len(report['queries'])}꼴",
        "press": f"뉴스와이어 {len(report['newswire'])}건 · 기사 {len(report['articles'])}건(회사 제공 사진 {sum(a['company_photo'] for a in report['articles'])}건) · 회사 상태 {st}",
        "other": f"CC 사진 {len(report['cc'])}장",
    }
    return report


def next_step(rep, status):
    if rep["newswire"] and any(n["photos"] for n in rep["newswire"]):
        return "뉴스와이어 원본 사진이 있어요. 사진 설명에 다른 촬영자·언론사 표시가 없고 photo_rights '뉴스와이어 배포 보도자료' 의 조건·범위 안일 때만, 열어 보고 그 제품이 맞으면 match 정확, credits '사진: ○○ 제공(뉴스와이어)'로 써요"
    company = [a for a in rep["articles"] if a["company_photo"]]
    if company and status == "사용 가능":
        return "회사 배포 사진이 있고 회사 상태가 사용 가능이에요. 원본을 회사 보도자료 게시판에서 받아(press_board) scope 조건대로 써요"
    if company and status == "확인 필요":
        return ("회사 배포 사진은 있지만 회사 상태가 '확인 필요'(이용 권한 미확인)라 게시용으로 쓰지 않아요. "
                "같은 제품의 뉴스와이어 배포분, 조건이 확인된 CC 실제 사진을 다른 검색어·영어 이름(--en)으로 더 찾아요")
    if any(c["what"] == "제품" for c in rep["cc"]):
        return "그 제품이 찍힌 CC 사진 후보가 있어요. 열어 보고 제품 이름·포장·생김새가 맞으면 match 정확으로 써요(라이선스대로 credit)"
    if company and status in ("사용 불가", "확인 필요"):
        tail = ("CC 사진 가운데 그 회사 매장 사진은 매장·행사 장면에만(match 분위기) 쓸 수 있어요. " if rep["cc"] else "")
        return ("실제 제품 사진은 회사 배포 사진뿐이고 이용 권한이 없어요(회사 상태 " + status + "). " + tail +
                "제품을 직접 설명하는 장면은 다른 검색어·영어 이름(--en)·출시 기간(--days)으로 한 번 더 찾고, 그래도 없으면 그 장면만 숫자 카드나 문장 빼기로 풀어요")
    if rep["cc"]:
        return "그 회사 매장 CC 사진만 있어요. 매장·행사 장면에만(match 분위기) 쓰고, 제품 장면 사진은 다른 검색어로 더 찾아요"
    return ("이번 검색어로는 실제 사진이 없어요. 제품 이름을 보도 제목에 나온 꼴로 바꾸거나(--days 늘리기, 영어 이름 --en), "
            "출시 날짜 기사·회사 SNS 공지 기사로 다시 찾아요. 그래도 없을 때만 그 장면을 숫자 카드로 바꾸거나 그 문장을 빼요")


def rights_list():
    rows = rights_rows()
    wait = [r for r in rows if r.get("status") == "확인 필요" and r.get("decision")]
    print("회사 사진 이용 상태 (sources.json photo_rights):")
    for r in rows:
        if r.get("photo_source", "").startswith(("회사", "보도자료")) or r.get("brands"):
            print(f"  {r.get('status'):6} | {r['name']} | {str(r.get('scope') or r.get('note') or '')[:90]}")
    if wait:
        print("\n권한 미확인 (공식 이용 조건이나 회사 허락이 확인되면 기록하고, 그 뒤로는 자동. 사용자 승인만으로는 안 돼요):")
        for r in wait:
            d = r["decision"]
            print(f"  - {r['name']}: {d.get('ask') if isinstance(d, dict) else d}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "rights":
        return rights_list()
    ap = argparse.ArgumentParser()
    ap.add_argument("brand")
    ap.add_argument("name")
    ap.add_argument("--en", default="")
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    print(json.dumps(find(a.brand, a.name, a.en, a.days), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
