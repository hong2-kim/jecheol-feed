# -*- coding: utf-8 -*-
"""오늘 저녁 추천 메뉴 후보 고르기 (2026-11-12 사용자: 짬뽕·탕수육·돈가스처럼 익숙한 메뉴만 되풀이되지 않게).

  python scripts/dinner_pick.py                        오늘(한국 시간) 후보 18개와 추천 4칸 조합
  python scripts/dinner_pick.py 2026-11-13 --weather rain   그날·날씨(cold·rain·hot·mild)에 맞춰
  python scripts/dinner_pick.py --history              지난 저녁 추천 기록(메뉴·계열·마지막 날·횟수·조회수)
  python scripts/dinner_pick.py --save                 기록을 state/dinner_history.json 에 써요(아침 실행이 저녁을 만든 뒤)
  python scripts/dinner_pick.py --simulate 30          발행 없이 30일 치를 이어서 골라 보고 반복·비율을 세요(시험 A)
  python scripts/dinner_pick.py --stats                메뉴 사전의 갈래·메뉴 수
  python scripts/dinner_pick.py add "이름" --cat 7 --en "english name" [--tier new] [--snack]
                                                       사전에 없는 실제 음식을 더해요(계열·재료·조리는 이름으로 어림)

메뉴 사전은 ideas/dinner_menu.json(갈래 24개). 이름·갈래·계열·주재료·조리 방식·익숙함(popular 익숙한 인기 /
nostalgic 오랜만에 먹고 싶은 / new 새로운)·한 끼 여부(meal)·영어 검색어(en, Unsplash·Pexels·위키미디어용)·제철 달을 적어요.

반복은 막지 않고 점수에만 넣어요(권장 기준, 강제 차단 아님):
  같은 메뉴 30일 안 ↓, 같은 계열 7일 안 ↓, 같은 갈래 사흘 연속 ↓, 같은 주재료·조리 방식 몰림 ↓, 오래 안 나온 메뉴 ↑,
  제철·날씨 ↑, 예전 반응(조회수) 좋았던 메뉴 ↑, 지난 30번의 익숙함 비율이 목표(40·25·20·15%)보다 모자란 쪽 ↑.
그래서 어제 짬뽕이 나와도 오늘 짬뽕이 후보에서 빠지지 않아요. 다만 점수가 내려가 다른 메뉴와 견줘 보게 돼요.
한 끼가 안 되는 간식·디저트(meal=false)는 저녁 추천 후보에 넣지 않아요(rules/daily/dinner.md, 2026-11-09 사용자).
읽기만 해요(--save·add 만 파일을 써요).
"""
import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "ideas" / "dinner_menu.json"
HISTORY = ROOT / "state" / "dinner_history.json"
KST_OFFSET = timedelta(hours=9)

# 익숙함 목표(30번 기준, 참고용). season 은 그날 제철·날씨에 맞는 메뉴(어느 익숙함이든)를 뜻해요.
TARGET = {"popular": 0.40, "nostalgic": 0.25, "new": 0.20, "season": 0.15}
TIER_BASE = {"popular": 1.0, "nostalgic": 0.9, "new": 0.86}
TIER_KO = {"popular": "익숙한 인기", "nostalgic": "오랜만에", "new": "새로운", "season": "제철·날씨"}

# ── 계열·주재료·조리 방식 어림 (먼저 맞는 것) ─────────────────────────────
FAMILY = [
    (r"짜장", "짜장면"), (r"짬뽕", "짬뽕"), (r"탕수육|꿔바로우", "탕수육"), (r"떡볶이|라볶이", "떡볶이"),
    (r"함박", "함박스테이크"), (r"돈카츠|돈가스|돈까스|가츠|카츠|커틀릿|슈니첼", "돈가스·커틀릿"),
    (r"마라", "마라"), (r"훠궈|샤브|나베|스키야키|전골|어복쟁반|신선로|낙곱새", "전골·샤브"),
    (r"국밥|순댓국|해장국", "국밥"), (r"칼국수|수제비|옹심이", "칼국수·수제비"), (r"냉면|밀면|막국수", "냉면·막국수"),
    (r"쌀국수|분짜|분보|분리우|분팃", "쌀국수"), (r"라멘|츠케멘|마제소바|아부라소바|탄탄", "라멘"), (r"우동", "우동"),
    (r"소바|모밀", "소바"), (r"국수|소면|쫄면|우육면|도삭면|란저우|비앙비앙|완탕면|락사|호키엔미|라그만|미고렝|량피|쏸라펀", "국수"),
    (r"파스타|봉골레|까르보나라|볼로네제|아라비아타|알리오|라자냐|라비올리|뇨키|카초에페페", "파스타"), (r"리소토", "리소토"),
    (r"피자|칼초네|피데|하차푸리", "피자"), (r"버거", "버거"),
    (r"치킨|닭강정|파닭|윙|텐더|너겟|가라아게|치킨난반|지파이", "치킨"),
    (r"스테이크|토마호크|웰링턴|부르기뇽", "스테이크"),
    (r"카레|커리|마살라|빈달루|로간조시|달마크니|팔락|달밧", "카레"),
    (r"초밥|스시|마키|롤$|이나리", "초밥"), (r"비빔밥", "비빔밥"),
    (r"덮밥|동$|돈부리|루러우판|로코모코", "덮밥"), (r"볶음밥|카오팟|나시고렝|비리야니|플로프|빠에야|마클루바", "볶음밥·쌀요리"),
    (r"솥밥|곤드레밥|굴밥|콩나물밥|시래기밥|가지밥|무밥|영양솥밥", "솥밥·나물밥"),
    (r"물회|회무침|회$|사시미|회덮밥|숙회|탕탕이|산낙지", "회"), (r"찌개|짜글이|청국장", "찌개"),
    (r"족발|보쌈|수육", "족발·보쌈"), (r"곱창|대창|막창", "곱창"), (r"닭갈비", "닭갈비"), (r"오리", "오리"),
    (r"삼겹|목살|항정|가브리|갈매기|흑돼지", "돼지구이"), (r"갈비찜|등갈비|김치찜", "갈비찜"),
    (r"갈비$|LA갈비|불고기|너비아니|떡갈비|소고기구이|한우", "소불고기·갈비"), (r"제육|오삼|두루치기", "제육볶음"),
    (r"주꾸미|쭈꾸미|낙지|오징어", "낙지·오징어"), (r"게장", "게장"), (r"대게|킹크랩|랍스터|꽃게", "게·갑각류"),
    (r"조개|가리비|바지락|홍합", "조개"), (r"굴", "굴"), (r"아귀|해물찜|생선찜|알곤이", "해물찜"),
    (r"고등어|삼치|갈치|조기|꽁치|코다리|생선구이|열빙어", "생선구이·조림"),
    (r"장어", "장어"), (r"탕$|곰탕|백숙|삼계|개장|미역국|뭇국|북엇국|매생이국|어묵탕", "탕·국"),
    (r"타코|부리토|퀘사디아|엔칠라다|파히타|나초|치미창가|토스타다|타말레", "타코·부리토"),
    (r"케밥|샤와르마|기로스|코프타|사테|꼬치|야키토리|쿠시카츠|양꼬치", "꼬치·케밥"),
    (r"만두|딤섬|샤오롱바오|하가우|슈마이|모모|힌칼리|피에로기|펠메니|춘권|차슈바오|삼사|짜조|엠파나다", "만두·딤섬"),
    (r"샌드위치|파니니|반미|잠봉뵈르|크로크|토스트|베이글|필리치즈|루벤", "샌드위치·토스트"),
    (r"샐러드|포케|볼$|카프레제|랩$", "샐러드·볼"), (r"죽$", "죽"), (r"수프|스프|차우더|보르시|미네스트로네", "수프"),
    (r"전$|파전|전병|빈대떡|육전|굴전|오코노미야키|반쎄오|총좌빙|딴삥", "전·부침"),
    (r"도시락|벤토|에키벤|컵밥", "도시락"), (r"순대", "순대"), (r"라면|볶음면|비빔면", "라면"),
    (r"바비큐|폭립|립$|풀드포크|브리스킷|아사도|추라스코|슈하스코|허르헉", "바비큐"),
]
ING = [
    ("해산물", r"오징어|낙지|주꾸미|쭈꾸미|문어|새우|대하|게$|게장|꽃게|대게|킹크랩|랍스터|조개|바지락|굴|꼬막|멍게|해삼|개불|전복|홍합|가리비|해물|해산물|봉골레|룽샹|크랩|쉬림프|에비|카이센|모케카|세비체|차우더|깐쇼|칠리새우|크림새우|감바스|팔보채|유산슬|양장피"),
    ("생선", r"고등어|삼치|갈치|조기|광어|우럭|참돔|연어|참치|방어|전어|동태|대구|아귀|복국|황태|북엇|코다리|꽁치|장어|명란|알탕|알곤이|생선|피시|회$|회덮밥|사케|사시미|초밥|어묵|매생이|열빙어"),
    ("닭", r"닭|치킨|삼계|오야코|가라아게|야키토리|탄두리|카오만가이|버터치킨|티카|폴로|라조기|깐풍기|유린기|지파이|아도보|난반"),
    ("오리", r"오리|북경"),
    ("양", r"양꼬치|양갈비|만사프|라그만|플로프|로간조시"),
    ("돼지", r"삼겹|목살|항정|가브리|갈매기|돼지|제육|족발|보쌈|수육|돈|포크|폭립|차슈|동파육|홍소육|회과육|부타|카르니타스|베이컨|햄|순대|등갈비|감자탕|뼈해장|오삼|흑돼지|탕수육|꿔바로우|경장육슬|어향육슬|김치찜|부대|잠봉|모츠|바쿠테|카오카무|알파스토르|짜글이|고추장찌개|몸국|무사카|학센|커리부어스트|미트로프"),
    ("소", r"소고기|소갈비|소불고기|LA갈비|갈비탕|설렁탕|곰탕|도가니|꼬리|육회|불고기|스테이크|차돌|규|육개장|우육|비프|브리스킷|소머리|육전|떡갈비|너비아니|곱창|대창|막창|뭉티기|어복쟁반|쟁반|함박|비리아|미트볼|볼로네제|로모|아사도|추라스코|슈하스코|굴라시|부르기뇽|웰링턴|셰퍼드|필리|루벤|퐁|로코모코|보보티|허르헉|버거|라자냐|칠리|파히타|엔칠라다|타코|키마|코프타|피에로기|펠메니|힌칼리|만두|딤섬"),
    ("두부·콩", r"두부|순두부|비지|청국장|콩국수|콩나물|녹두|후무스|팔라펠|차나|달|두부"),
    ("치즈·유제품", r"치즈|크림|까르보나라|고르곤졸라|리코타|부라타|카프레제|퐁뒤|라클렛|마르게리타|하차푸리"),
]
HOW = [
    ("밥", r"^(?!.*우동)(?!.*난$).*(커리|카레|마살라|빈달루|로간조시|달마크니|팔락|달밧|백반|정식$|껌승|쿠스쿠스)"),
    ("볶음", r"떡볶이|라볶이|순대볶음|감바스|아히요"),
    ("죽", r"죽$"),
    ("샐러드", r"샐러드|볼$|랩$|카프레제|쏨땀|얌운센|후무스|바바가누쉬|과카몰리"),
    ("찜·조림", r"대게$|킹크랩|랍스터|크랩|룽샤|꼬막|칠리콘카르네|아도보|샥슈카|에그인헬|차슈바오|꽃빵|퐁뒤|라클렛"),
    ("날것", r"회무침|해산물모둠|삼합"),
    ("국물", r"개장|수주육편|쏸라펀"),
    ("면", r"쌀국수|분보|분리우|라멘|우육면|란저우|완탕면|락사|칼국수|수제비|옹심이|짬뽕|우동|국수|소바|모밀"),
    ("면", r"짜장|마라반"),
    ("튀김", r"파닭|푸틴"),
    ("구이", r"장어|풀드포크|학센"),
    ("빵·반죽", r"도사|인제라"),
    ("날것", r"회$|사시미|육회|포케|세비체|물회|회덮밥|산낙지|탕탕이|게장|간장새우|카이센|사케동|멍게|해삼|개불|뭉티기|초밥|스시|마키|롤$|이나리|유부초밥|카프레제"),
    ("국물", r"찌개|짜글이|청국장|국$|국밥|탕$|해장국|곰탕|전골|나베|샤브|훠궈|스키야키|어복쟁반|신선로|낙곱새|수프|스프|차우더|보르시|미네스트로네|굴라시|똠|쌀국수|분보|분리우|라멘|우육면|란저우|완탕면|락사|바쿠테|시니강|칼국수|수제비|옹심이|짬뽕|우동|백숙|삼계|매생이국|미역국|국수|어묵탕|마라탕|모츠|미즈타키|몸국|달밧|페이조아다|모케카|라그만"),
    ("면", r"면$|냉면|막국수|밀면|쫄면|소면|소바|모밀|파스타|봉골레|까르보나라|볼로네제|아라비아타|알리오|라자냐|라비올리|뇨키|카초에페페|팟타이|팟씨유|팟키마오|야키소바|미고렝|호키엔미|분짜|분팃|비앙비앙|량피|도삭면|탄탄|츠케멘|마제소바|아부라소바|라볶이|비빔면|볶음면|라면"),
    ("튀김", r"튀김|치킨|가스|까스|카츠|탕수육|꿔바로우|깐풍|가라아게|텐|커틀릿|슈니첼|피시앤칩스|깐쇼|유린기|라조기|닭강정|너겟|윙|텐더|난반|지파이|사모사|파코라|춘권|짜조|칠리새우|크림새우|팔라펠|엠파나다|치미창가|아란치니|어니언링|프라이"),
    ("구이", r"구이|삼겹|목살|항정|가브리|갈매기|갈비$|LA갈비|스테이크|토마호크|바비큐|야키토리|양꼬치|양갈비|케밥|샤와르마|기로스|사테|꼬치|탄두리|폭립|립$|아사도|추라스코|슈하스코|로스트|그릴|떡갈비|너비아니|불고기|곱창|대창|막창|오리로스|훈제|북경오리|로스트덕|허르헉|코프타|폴로|흑돼지|함박"),
    ("볶음", r"볶음|주물럭|제육|오삼|닭갈비|마라샹궈|고추잡채|지삼선|회과육|어향|경장육슬|팔보채|유산슬|파히타|로모살타도|마파|카파오|볶음밥|카오팟|나시고렝|계란토마토|잡채"),
    ("찜·조림", r"찜$|찜닭|조림|수육|보쌈|족발|동파육|홍소육|김치찜|갈비찜|타진|부르기뇽|굴라시|셰퍼드|무사카|라따뚜이|웰링턴|미트로프|보보티|이맘바이을드|마클루바|만사프|딤섬|만두|샤오롱바오|하가우|슈마이|모모|힌칼리|펠메니|피에로기|타말레"),
    ("밥", r"밥$|덮밥|동$|비빔밥|솥밥|리소토|빠에야|비리야니|플로프|오므라이스|라이스|컵밥|도시락|벤토|오니기리|카레|커리|루러우판|로코모코|나시르막|카오만가이|카오카무"),
    ("빵·반죽", r"피자|칼초네|버거|샌드위치|토스트|파니니|반미|잠봉뵈르|크로크|베이글|타코|부리토|퀘사디아|엔칠라다|나초|토스타다|아레파|난$|피타|포카치아|키슈|갈레트|피데|하차푸리|전$|파전|전병|오코노미야키|반쎄오|총좌빙|딴삥|에그베네딕트|핫도그|와플|팬케이크"),
]
GROUP = {1: "한식", 2: "한식", 3: "한식", 4: "한식", 5: "한식", 6: "중식", 7: "중식", 8: "일식", 9: "일식", 10: "양식", 11: "양식",
         12: "분식", 13: "양식", 14: "양식", 15: "간편식", 16: "해외", 17: "해외", 18: "해외", 19: "해외", 20: "한식", 21: "양식",
         22: "한식", 23: "간식", 24: "해외"}
# 저녁 화면에서 "갈래가 다르게"(국물·면·튀김·고기…) 보는 칸 갈래. 조리 방식을 저녁 추천 말투로 묶어요.
SLOT = {"국물": "국물", "면": "면", "튀김": "바삭", "구이": "고기·구이", "볶음": "매콤·볶음", "찜·조림": "푸짐·찜",
        "밥": "밥·덮밥", "날것": "회·날것", "빵·반죽": "한 판·빵", "죽": "죽", "샐러드": "샐러드·가벼운", "기타": "기타"}


def norm(s):
    return re.sub(r"[\s·\-()]", "", s or "")


def family_of(name):
    n = norm(name)
    for pat, fam in FAMILY:
        if re.search(pat, n):
            return fam
    return n


def ing_of(name):
    n = norm(name)
    out = [k for k, pat in ING if re.search(pat, n)]
    return out[:2] or ["채소·곡물"]


def how_of(name):
    n = norm(name)
    for k, pat in HOW:
        if re.search(pat, n):
            return k
    return "기타"


def today_kst():
    return (datetime.now(timezone.utc) + KST_OFFSET).date()


def load_db():
    data = json.loads(DB.read_text(encoding="utf-8"))
    return data


def items(db=None, meal_only=True):
    db = db or load_db()
    return [x for x in db["items"] if x.get("meal", True) or not meal_only]


# ── 기록 ─────────────────────────────────────────────────────────────
def match_menu(text, by_name):
    """자막 말 '…당기면, 얼큰한 순대국밥.' 에서 메뉴 이름을 찾아요. 사전에 있는 가장 긴 이름, 없으면 쉼표 뒤 말 그대로."""
    t = text.split(",")[-1] if "," in text else text
    t = re.sub(r"[.!?~\[\]]", "", t).strip()
    n = norm(t)
    best = None
    for key, x in by_name.items():
        if key and key in n and (best is None or len(key) > len(best)):
            best = key
    if best:
        return by_name[best]["name"]
    words = t.split()
    return words[-1] if words else t


def name_index(db):
    by = {}
    for x in db["items"]:
        by[norm(x["name"])] = x
        for a in x.get("aka", []):
            by[norm(a)] = x
    return by


def sent_ids():
    try:
        return set(json.loads((ROOT / "state" / "sent_videos.json").read_text(encoding="utf-8")))
    except Exception:
        return set()


def views_by_title():
    """yt_stats 의 마지막 날 기록: 저녁 영상 제목 → 조회수."""
    try:
        y = json.loads((ROOT / "state" / "yt_stats.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    days = y.get("days") or {}
    out = {}
    for d in sorted(days):
        for vid, v in (days[d].get("videos") or {}).items():
            if (y.get("kinds") or {}).get(vid) == "저녁" or "저녁" in (v.get("t") or ""):
                out[v.get("t") or vid] = v.get("v") or 0
    return out


def history(db=None, upto=None, extra=None):
    """실제로 만들어 보낸 저녁 추천만 [{day, menus:[이름…], title, views}]. 보내지 못한 날은 세지 않아요.
    설계도에 menus 칸이 있으면 그것을, 없으면 3~6번 문장에서 이름을 찾아요."""
    db = db or load_db()
    by = name_index(db)
    sent = sent_ids()
    vt = views_by_title()
    out = []
    for f in sorted((ROOT / "videos").glob("*/3-dinner.json")):
        day = f.parent.name
        if upto and day >= upto:
            continue
        try:
            spec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        menus = (spec.get("menu_pick") or {}).get("menus") or spec.get("menus")
        if not menus:
            lines = [l.get("say", "") for l in spec.get("lines", [])]
            menus = [match_menu(s, by) for s in lines[2:6]] if len(lines) >= 6 else []
        title = spec.get("yt_title") or spec.get("title") or ""
        # 유튜브 제목에는 네 메뉴가 다 들어가요. 같은 제목, 아니면 메뉴 셋 넘게 들어간 제목을 그 영상으로 봐요
        views = vt.get(title)
        if views is None:
            hit = [(sum(1 for m in menus if norm(m)[:3] in norm(t)), v) for t, v in vt.items()]
            hit = [h for h in hit if h[0] >= 3]
            views = max(hit)[1] if hit else None
        if sent and f"{day}-3-dinner" not in sent and views is None:
            continue
        out.append({"day": day, "menus": menus, "title": title, "views": views,
                    "why": (spec.get("menu_pick") or {}).get("why")})
    out += extra or []
    return out


def records(db, hist):
    """메뉴마다 기록: 이름·갈래·계열·주재료·조리·마지막 날·횟수·제목·조회수·추천 사유."""
    by = name_index(db)
    rec = {}
    for h in hist:
        for m in h["menus"]:
            x = by.get(norm(m)) or {"name": m, "cat": 0, "family": family_of(m), "ing": ing_of(m), "how": how_of(m)}
            r = rec.setdefault(x["name"], {"name": x["name"], "cat": x.get("cat"), "cat_name": cat_name(db, x.get("cat")),
                                            "family": x.get("family") or family_of(m), "ing": x.get("ing"), "how": x.get("how"),
                                            "tier": x.get("tier"), "count": 0, "last": None, "titles": [], "views": []})
            r["count"] += 1
            r["last"] = h["day"]
            if h.get("title"):
                r["titles"] = (r["titles"] + [h["title"]])[-3:]
            if h.get("views") is not None:
                r["views"].append(h["views"])
            if h.get("why"):
                r["why"] = h["why"] if isinstance(h["why"], str) else (h["why"].get(m) if isinstance(h["why"], dict) else None)
    return rec


def cat_name(db, cat):
    for c in db.get("cats", []):
        if c["id"] == cat:
            return c["name"]
    return ""


# ── 점수 ─────────────────────────────────────────────────────────────
def season_now(x, day, weather):
    tags = []
    if x.get("months") and day.month in x["months"]:
        tags.append("제철")
    w = set(x.get("weather") or [])
    if weather == "cold" and (x.get("how") == "국물" or "cold" in w):
        tags.append("추운 날")
    if weather == "rain" and ("rain" in w or x.get("family") in ("전·부침", "칼국수·수제비", "짬뽕")):
        tags.append("비 오는 날")
    if weather == "hot" and "hot" in w:
        tags.append("더운 날")
    if weather != "hot" and "hot" in w and not (x.get("months") and day.month in x["months"]):
        tags.append("철 아님")
    return tags


def default_weather(day):
    return "cold" if day.month in (11, 12, 1, 2, 3) else "hot" if day.month in (6, 7, 8) else "mild"


def score_all(db, day, hist, weather=None):
    weather = weather or default_weather(day)
    by = name_index(db)
    past = [h for h in hist if h["day"] < day.isoformat()]
    last_day, fam_days, cat_days, ing_cnt, how_cnt = {}, Counter(), {}, Counter(), Counter()
    for h in past:
        d = date.fromisoformat(h["day"])
        ago = (day - d).days
        for m in h["menus"]:
            x = by.get(norm(m))
            name = x["name"] if x else m
            last_day[name] = max(last_day.get(name, d), d)
            fam = (x or {}).get("family") or family_of(m)
            if ago <= 7:
                fam_days[fam] += 1
                for i in (x or {}).get("ing") or ing_of(m):
                    ing_cnt[i] += 1
                how_cnt[(x or {}).get("how") or how_of(m)] += 1
            if ago <= 3:
                cat_days.setdefault((x or {}).get("cat"), set()).add(ago)
    # 지난 30번 익숙함 비율
    tiers = []
    for h in past[-8:]:
        for m in h["menus"]:
            x = by.get(norm(m))
            tiers.append("season" if x and season_now(x, date.fromisoformat(h["day"]), default_weather(date.fromisoformat(h["day"])))[:1] == ["제철"]
                         else (x or {}).get("tier", "popular"))
    tiers = tiers[-30:]
    share = {k: (tiers.count(k) / len(tiers) if tiers else 0) for k in TARGET}
    # 예전 반응: 메뉴가 나온 영상 조회수 / 저녁 영상 조회수 가운데 값
    vs = [h["views"] for h in past if h.get("views")]
    med = statistics.median(vs) if vs else None
    react = {}
    if med:
        for h in past:
            if h.get("views"):
                for m in h["menus"]:
                    x = by.get(norm(m))
                    react.setdefault(x["name"] if x else m, []).append(h["views"] / med)
    seed = int(hashlib.md5(day.isoformat().encode()).hexdigest(), 16)
    out = []
    for x in items(db):
        s, why = TIER_BASE.get(x.get("tier"), 0.8), []
        ld = last_day.get(x["name"])
        if ld:
            ago = (day - ld).days
            if ago <= 30:
                cut = 0.95 if ago <= 2 else 0.9 * (31 - ago) / 30
                s -= cut
                why.append(f"{ago}일 전에 나옴 -{cut:.2f}")
            else:
                s += min(0.25, 0.1 + ago / 400)
                why.append(f"{ago}일 만 +")
        else:
            s += 0.12
            why.append("아직 안 나옴 +0.12")
        f = fam_days.get(x["family"], 0)
        if f:
            s -= 0.3 * f
            why.append(f"같은 계열({x['family']}) 7일 안 {f}번 -{0.3 * f:.2f}")
        if len(cat_days.get(x["cat"], ())) >= 2:
            s -= 0.3
            why.append("같은 갈래가 요 며칠 계속 -0.3")
        crowd = sum(ing_cnt.get(i, 0) for i in x.get("ing") or []) + how_cnt.get(x.get("how"), 0)
        if crowd > 6:
            s -= min(0.35, 0.03 * (crowd - 6))
            why.append(f"주재료·조리 몰림 -{min(0.35, 0.03 * (crowd - 6)):.2f}")
        tags = season_now(x, day, weather)
        if "제철" in tags:
            s += 0.35
        if any(t in tags for t in ("추운 날", "비 오는 날", "더운 날")):
            s += 0.18
        if "철 아님" in tags:
            s -= 0.4
        if tags:
            why.append("·".join(tags))
        tier = "season" if "제철" in tags else x.get("tier", "popular")
        gap = TARGET.get(tier, 0) - share.get(tier, 0)
        if tiers and gap > 0.05:
            s += min(0.3, gap)
            why.append(f"{TIER_KO[tier]} 비율 모자람 +{min(0.3, gap):.2f}")
        r = react.get(x["name"])
        if r:
            bonus = max(-0.15, min(0.2, 0.25 * math.log2(statistics.mean(r))))
            s += bonus
            why.append(f"예전 반응 {statistics.mean(r):.2f}배 {bonus:+.2f}")
        s += ((seed >> (hash_id(x["name"]) % 97)) % 1000) / 1000 * 0.3 - 0.15  # 날마다 조금씩 달라지게
        out.append({**x, "score": round(s, 3), "kind": tier, "why": why, "last": ld.isoformat() if ld else None})
    out.sort(key=lambda r: -r["score"])
    return out, share


def hash_id(s):
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def vault_notes():
    p = ROOT.parent / "jecheol-photos" / "index.json"
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return [norm(x.get("note", "")) for x in idx if x.get("type") == "photo" and not x.get("skip") and not x.get("ask")]


SEA = {"해산물", "생선"}


def candidates(scored, n=18):
    """서로 다른 계열에서 n개(한 갈래는 4개까지). 익숙한 인기·오랜만에·새로운·제철이 고루 들어가게 먼저 몇 개씩 챙겨요."""
    def ok(r, out):
        return r["family"] not in {x["family"] for x in out} and sum(1 for x in out if x["cat"] == r["cat"]) < 4
    out = []
    for kind, k in (("popular", 6), ("nostalgic", 4), ("new", 3), ("season", 3)):
        for r in scored:
            if sum(1 for x in out if x["kind"] == kind) >= k:
                break
            if r["kind"] == kind and ok(r, out):
                out.append(r)
    for r in scored:
        if len(out) >= n:
            break
        if r not in out and ok(r, out):
            out.append(r)
    out.sort(key=lambda r: -r["score"])
    return out


def combo(cands, share=None):
    """4칸: 계열·칸 갈래(국물·면·바삭·고기…)가 모두 다르게. 익숙한 인기 메뉴를 하나 넘게(모자라면 둘), 새로운 것과 제철은 하나까지,
    한식은 셋까지, 분식·간편식은 하나까지, 해산물·생선은 둘까지. 맞는 게 없으면 조건을 풀어요(막지 않아요)."""
    need_pop = 2 if share and share.get("popular", 0) < 0.3 else 1
    for strict in (True, False):
        best = []
        for r in cands:
            if len(best) == 4:
                break
            k = Counter(x["kind"] for x in best)
            g = Counter(GROUP.get(x["cat"], "") for x in best)
            slot = SLOT.get(r.get("how"), "기타")
            sea = sum(1 for x in best if SEA & set(x.get("ing") or []))
            gr = GROUP.get(r["cat"], "")
            bad = (slot in {SLOT.get(x.get("how"), "기타") for x in best}
                   or (gr == "한식" and g["한식"] >= 3) or (gr in ("분식", "간편식") and g[gr] >= 1)
                   or (r["kind"] == "new" and k["new"] >= 1) or (r["kind"] == "season" and k["season"] >= 1)
                   or (SEA & set(r.get("ing") or []) and sea >= 2))
            pops = k["popular"] + (r["kind"] == "popular")
            if strict and (4 - len(best) - 1) < need_pop - pops:  # 남은 칸에 익숙한 메뉴 자리를 남겨요
                bad = True
            if not bad or not strict and r not in best and len(best) < 4 and r is cands[-1]:
                best.append(r)
        if len(best) == 4:
            return sorted(best, key=lambda r: -r["score"])
    for r in cands:  # 그래도 모자라면 점수 차례로 채워요(막지 않아요)
        if len(best) == 4:
            break
        if r not in best:
            best.append(r)
    return best


def show(day, weather, n=18):
    db = load_db()
    hist = history(db)
    scored, share = score_all(db, day, hist, weather)
    cands = candidates(scored, n)
    notes = vault_notes()
    print(f"■ {day} 저녁 추천 후보 (날씨 {weather or default_weather(day)}, 사전 {len(items(db))}개 중, 지난 기록 {len(hist)}일)")
    print("  지난 30번 비율: " + " · ".join(f"{TIER_KO[k]} {share[k] * 100:.0f}%(목표 {TARGET[k] * 100:.0f}%)" for k in TARGET))
    for i, r in enumerate(cands, 1):
        has = ""
        if notes is not None:
            key = norm(r["name"])
            has = " 📷보관함" if any(key in nn for nn in notes) else ""
        print(f"{i:2}. {r['name']} [{cat_name(db, r['cat'])} · {r['family']} · {r['how']} · {TIER_KO[r['kind']]}] "
              f"{r['score']:.2f}{has}  — {'; '.join(r['why'])}  en: {', '.join(r.get('en') or [])}")
    c = combo(cands, share)
    print("■ 추천 4칸(점수 높은 차례로 칸 갈래가 다르게): " + " / ".join(f"{r['name']}({SLOT.get(r['how'], '기타')})" for r in c))
    print("  고르는 법: 위 후보 중 그날 가장 추천하기 좋은 4개를 고른다(사진·날씨·화제를 보고 바꿔도 된다). 반복은 점수일 뿐 금지가 아니다.\n"
          "  설계도에 \"menu_pick\": {\"menus\": [4개], \"from\": \"dinner_pick\", \"why\": {메뉴: 한 줄 까닭}} 을 적는다.\n"
          "  사진이 보관함에 없으면 관광공사 → python scripts/photos.py food \"메뉴\" (한국어로 모자라면 영어로 Unsplash·Pexels·위키미디어를 찾아요).")
    return c


# ── 시험 A: 발행 없이 30일 ─────────────────────────────────────────────
def simulate(days, start=None, weather=None):
    db = load_db()
    hist = history(db)
    start = start or (date.fromisoformat(hist[-1]["day"]) + timedelta(days=1) if hist else today_kst())
    sim, blocked = [], 0
    for k in range(days):
        day = start + timedelta(days=k)
        scored, share = score_all(db, day, hist + sim, weather)
        cands = candidates(scored)
        if len(cands) < 15:
            blocked += 1
        pick = combo(cands, share)
        sim.append({"day": day.isoformat(), "menus": [r["name"] for r in pick], "kinds": [r["kind"] for r in pick], "views": None, "title": ""})
    return db, hist, sim, blocked


def report(db, rows, label):
    by = name_index(db)
    menus = [m for h in rows for m in h["menus"]]
    cnt = Counter(menus)
    fam = Counter((by.get(norm(m)) or {}).get("family") or family_of(m) for m in menus)
    grp = Counter(GROUP.get((by.get(norm(m)) or {}).get("cat"), "?") for m in menus)
    tier = Counter(k for h in rows for k in (h.get("kinds") or [(by.get(norm(m)) or {}).get("tier", "?") for m in h["menus"]]))
    # 같은 메뉴가 30일 안에 다시 나온 횟수, 같은 계열이 7일 안에 다시 나온 횟수
    seen, fseen, rep30, rep7 = {}, {}, 0, 0
    for h in rows:
        d = date.fromisoformat(h["day"])
        for m in h["menus"]:
            x = by.get(norm(m))
            nm, fm = (x or {}).get("name", m), (x or {}).get("family") or family_of(m)
            if nm in seen and (d - seen[nm]).days <= 30:
                rep30 += 1
            if fm in fseen and (d - fseen[fm]).days <= 7:
                rep7 += 1
            seen[nm], fseen[fm] = d, d
    n = len(menus) or 1
    rows = [h for h in rows if h["menus"]]
    print(f"■ {label}: {len(rows)}일 · 메뉴 {len(menus)}번 · 서로 다른 메뉴 {len(cnt)}개 · 서로 다른 계열 {len(fam)}개")
    print(f"  같은 메뉴 30일 안 다시: {rep30}번 · 같은 계열 7일 안 다시: {rep7}번")
    print("  가장 많이: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common(8)))
    print("  계열 많이: " + ", ".join(f"{k} {v}" for k, v in fam.most_common(6)))
    print("  음식 나라: " + ", ".join(f"{k} {v * 100 / n:.0f}%" for k, v in grp.most_common()))
    print("  익숙함: " + ", ".join(f"{TIER_KO.get(k, k)} {v * 100 / n:.0f}%" for k, v in tier.most_common()))
    return {"days": len(rows), "menus": len(menus), "distinct": len(cnt), "families": len(fam), "rep30": rep30, "rep7": rep7,
            "top": cnt.most_common(8), "group": {k: round(v * 100 / n) for k, v in grp.items()},
            "tier": {k: round(v * 100 / n) for k, v in tier.items()}}


def write_db(db):
    """사전은 메뉴 하나에 한 줄로 써요(사람이 고치기 쉽고 git 차이가 작게)."""
    txt = "{\n" + ",\n".join(f' "{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in db.items() if k != "items")
    txt += ',\n "items": [\n' + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in db["items"]) + "\n ]\n}\n"
    DB.write_text(txt, encoding="utf-8")


def add(args):
    db = load_db()
    if any(norm(x["name"]) == norm(args.name) for x in db["items"]):
        sys.exit(f"{args.name} 은(는) 이미 있어요.")
    x = {"name": args.name, "cat": args.cat, "family": family_of(args.name), "ing": ing_of(args.name), "how": how_of(args.name),
         "tier": args.tier, "meal": not args.snack, "en": [e.strip() for e in (args.en or "").split(";") if e.strip()],
         "added": today_kst().isoformat()}
    db["items"].append(x)
    db["updated"] = today_kst().isoformat()
    write_db(db)
    print(json.dumps(x, ensure_ascii=False))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("name")
        ap.add_argument("--cat", type=int, required=True)
        ap.add_argument("--en", default="")
        ap.add_argument("--tier", default="new", choices=list(TIER_BASE))
        ap.add_argument("--snack", action="store_true")
        return add(ap.parse_args())
    ap = argparse.ArgumentParser()
    ap.add_argument("day", nargs="?")
    ap.add_argument("--weather", choices=["cold", "rain", "hot", "mild"])
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--simulate", type=int)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("-n", type=int, default=18)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    day = date.fromisoformat(a.day) if a.day else today_kst()
    db = load_db()
    if a.stats:
        c = Counter(x["cat"] for x in db["items"])
        meal = sum(1 for x in db["items"] if x.get("meal", True))
        print(f"메뉴 {len(db['items'])}개(저녁 한 끼 {meal}개) · 갈래 {len(db['cats'])}개 · 계열 {len({x['family'] for x in db['items']})}개")
        for cc in db["cats"]:
            print(f"  {cc['id']:2}. {cc['name']} {c[cc['id']]}개")
        return
    if a.history or a.save:
        rec = records(db, history(db))
        if a.save:
            HISTORY.write_text(json.dumps({"updated": today_kst().isoformat(), "menus": sorted(rec.values(), key=lambda r: r["last"] or "", reverse=True)},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{HISTORY.relative_to(ROOT)} 에 {len(rec)}개 메뉴 기록을 썼어요.")
        for r in sorted(rec.values(), key=lambda r: (-r["count"], r["name"])):
            v = f" · 조회수 평균 {statistics.mean(r['views']):.0f}" if r["views"] else ""
            print(f"{r['name']} [{r['cat_name'] or '사전에 없음'} · {r['family']} · {r['how']}] {r['count']}번, 마지막 {r['last']}{v}")
        return
    if a.simulate:
        db, hist, sim, blocked = simulate(a.simulate, weather=a.weather)
        before = report(db, hist[-a.simulate:], "지금까지 방식(실제로 보낸 저녁 추천)")
        after = report(db, sim, f"새 방식(시험 {a.simulate}일, {sim[0]['day']}~{sim[-1]['day']})")
        print(f"  후보가 15개보다 적어 막힌 날: {blocked}일")
        for h in sim:
            print(f"  {h['day']}: {' / '.join(h['menus'])}")
        if a.json:
            print(json.dumps({"before": before, "after": after, "blocked": blocked, "sim": sim}, ensure_ascii=False))
        return
    show(day, a.weather, a.n)


if __name__ == "__main__":
    main()
