# -*- coding: utf-8 -*-
"""소재(사진·영상) 목록과 출처·이용 조건 검사. 2026-10-19 사용자가 우선순위를 정함:
① 사용자가 준 음식 사진·영상 ② 한국관광공사 ③ 편의점·마트·식품 회사 공식 상품 이미지(조건이 확인될 때만).

  python scripts/media.py catalog            보관함 목록(jecheol-photos index.json)과 이 컴퓨터의 내-음식-사진 폴더를 맞춰
                                              음식 갈래·쓸 수 있는지를 적은 목록을 만들어요. 사진은 다시 받지 않아요.
  python scripts/media.py find 떡볶이          갈래 이름이나 음식 이름으로 쓸 만한 사진·영상을 찾아요(안 쓴 것, 쓸 수 있는 것 먼저).
  python scripts/media.py groups              갈래마다 몇 개인지.
  python scripts/media.py check 설계도.json    설계도에 쓴 사진·영상의 출처·이용 조건과 '협찬처럼 보이는 말'을 봐요.
  python scripts/media.py public [videos폴더]  이미 만든 영상에 들어간 보관함 사진과 권리 상태를 모아요(_공개사용.md).

목록은 공개 저장소가 아니라 내-음식-사진 폴더 안 _목록.json·_목록.md 에 둬요(사용자 사진 이름·내용이 들어 있어요).
폴더에 있다는 것만으로 쓸 수 있다고 보지 않아요. 항목마다 status(사용 가능 / 검토 필요)와 그 까닭(why)을 적어요.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = json.loads((ROOT / "video" / "sources.json").read_text(encoding="utf-8"))
VAULT_REPO = "https://github.com/hong2-kim/jecheol-photos.git"


def photo_dir():
    """내-음식-사진 폴더. MY_PHOTOS_DIR 이 있으면 그것, 없으면 위쪽 폴더에서 찾아요(작업 폴더 .claude-wt 안에서도)."""
    if os.environ.get("MY_PHOTOS_DIR"):
        return Path(os.environ["MY_PHOTOS_DIR"])
    for p in ROOT.parents:
        if (p / "내-음식-사진").is_dir():
            return p / "내-음식-사진"
    return None


# 음식 갈래. 위에서부터 처음 맞는 것. (사진 이름표 note 로 나눠요)
GROUPS = [
    ("음료·술", r"소주|맥주 건배|소주잔|카페 음료|밀크티|주스|바나나우유$"),
    ("빵·디저트", r"케이크|빵|아이스크림|크레페|타르트|마카롱|와플|츄러스|크루아상|푸딩|디저트|간식|프링글스"),
    ("과일", r"수박|샤인머스캣|과일|한라봉"),
    ("시장·가게", r"수조|수산시장|진열"),
    ("족발·보쌈·수육", r"족발|보쌈|수육"),
    ("분식", r"떡볶이|라볶이|김밥|떡꼬치|분식|주먹밥|어묵 떡"),
    ("라면", r"라면"),
    ("중식", r"짜장|짬뽕|탕수육|중식|마파"),
    ("버거·핫도그", r"버거|맥도날드|KFC|핫도그|햄버거"),
    ("치킨·튀김", r"치킨|통닭|닭다리|닭튀김|닭껍질|튀김"),
    ("돈가스·일식", r"돈가스|돈까스|텐동|초밥|롤 한|라멘|우동|모밀|유부초밥"),
    ("피자·파스타·양식", r"피자|파스타|리조또|스테이크|함박|감바스|샐러드|수프|칼조네|플래터|뷔페"),
    ("면·국수", r"국수|칼국수|냉면|쌀국수|막국수|쫄면"),
    ("만두", r"만두"),
    ("생선구이", r"생선구이|고등어|열빙어|생선"),
    ("찌개·탕·전골", r"찌개|탕|전골|국밥|순댓국|미역국|백숙|샤브샤브|뚝배기|떡국|찜 냄비|죽"),
    ("회·해산물", r"회|대게|꽃게|조개|새우|해물|굴|문어|낙지|주꾸미|쭈꾸미|오징어|홍합|전복|성게|랍스터|알탕|해산물"),
    ("고기구이", r"삼겹살|갈비|목살|막창|곱창|고기|바비큐|숯불|양꼬치|꼬치|소고기|돼지|불고기|육회|육사시미|오리|닭갈비|닭발|소시지"),
    ("전·부침", r"전$|파전|김치전|모둠전|전\("),
    ("밥·한 상", r"볶음밥|비빔밥|밥|백반|한정식|반찬|정식|집밥|도시락|카레|김$|요리하는|조림|찜|모음"),
]
MOVES = r"모습|끓이는|끓는|삶기|비비는|자르기|들어 올리기|발라 먹기|써는|쪼개는"  # 동작이 있는 영상·사진 (대사와 맞출 때)
BRANDS = r"맥도날드|KFC|배스킨|이케아|프링글스"  # 상표가 보일 수 있는 것
ALCOHOL = r"소주|맥주|술자리"


def _norm(s):
    return re.sub(r"[\s()?·,/]|_확인필요", "", s).replace("돈까스", "돈가스")


def group_of(note):
    for name, pat in GROUPS:
        if re.search(pat, note):
            return name
    return "기타"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def vault_index():
    """보관함 index.json. VAULT_DIR 에 받아 둔 게 있으면 그것, 없으면 저장소에서 index.json 하나만 받아요(사진은 안 받아요)."""
    local = os.environ.get("VAULT_DIR", "").strip()
    if local and (Path(local) / "index.json").exists():
        return json.loads((Path(local) / "index.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.gettempdir()) / "jecheol-vault-index"
    if not (tmp / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", VAULT_REPO, str(tmp)], check=True)
    else:
        subprocess.run(["git", "-C", str(tmp), "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", "main"], check=True)
        subprocess.run(["git", "-C", str(tmp), "update-ref", "HEAD", "FETCH_HEAD"], check=True)
    out = subprocess.run(["git", "-C", str(tmp), "show", "HEAD:index.json"], check=True, capture_output=True).stdout
    return json.loads(out.decode("utf-8"))


def judge(note, extra):
    """(status, why[], tags[]) — 사용자 사진 한 장을 쓸 수 있는지. 사진을 직접 보지 않고 목록의 표시로만 정해요."""
    why, tags = [], []
    if extra.get("ask"):
        why.append("무슨 음식인지 확실치 않음(ask) — 사용자에게 물어본 뒤 사용")
    if extra.get("careful"):
        why.append(f"사람이 보임({extra['careful']}) — 쓰기 전에 크게 열어 얼굴이 없는지 다시 확인")
    if re.search(BRANDS, note):
        tags.append("상표")
        why.append("상표·가게 이름이 보일 수 있음 — 협찬처럼 보이지 않게, 그 회사 이야기에만")
    if "콜라주" in note:
        why.append("여러 장을 붙인 그림 — 남이 찍은 사진이 섞였는지 확인 필요")
    if re.search(ALCOHOL, note):
        tags.append("술")
    if re.search(MOVES, note):
        tags.append("동작")
    if extra.get("taken") and extra["taken"][:4].isdigit() and int(extra["taken"][:4]) < 2024:
        tags.append(f"{extra['taken'][:4]}년")  # 오래된 사진: 지금 값·영업 정보로 쓰지 않음
    if not why:
        return "사용 가능", why, tags
    if all(w.startswith("상표") for w in why):
        return "사용 가능(조건)", why, tags
    return "검토 필요", why, tags


RIGHTS_OK = "확인"  # 직접 찍었거나 사용 권한이 확인된 것만 상업용(게시)으로 써요
# 사용자가 대화에서 직접 찍었다고 확인해 준 사진 {보관함 id: 확인한 날}. 대화로 보낸 7장만이고,
# 인스타그램에서 옮긴 421장은 여기 넣지 않는다(사용자가 따로 확인, 2026-10-20 사용자가 정함).
TOLD_MINE = {i: "2026-10-20" for i in (
    "u-2026-10-15-jeon.jpg", "u-2026-10-15-samgyeop.jpg", "u-2026-10-15-kkotge.jpg", "u-2026-10-15-sannakji.jpg",
    "u-2026-10-15-dakgalbi.jpg", "u-2026-10-15-shinemuscat.jpg", "u-2026-10-17-jogaejjim.jpg")}


def rights_of(source_from, answer="", told_on=""):
    """(권리 상태, 까닭). 2026-10-19 사용자가 정함: 인스타그램에서 가져왔다는 것만으로 직접 찍은 사진으로 보지 않는다.
    사용자가 _검토목록.csv 의 '내가 찍음' 칸에 '예'를 적거나 대화에서 확인해 주면(TOLD_MINE) 확인이 돼요.
    검토표에 '아니오'를 적으면 대화 확인보다 앞서요."""
    if answer.strip() in ("아니오", "아니요", "x", "X"):
        return "안 씀", "사용자가 직접 찍은 것이 아니라고 함 — 쓰지 않음"
    if told_on:
        return RIGHTS_OK, f"본인 직접 촬영 확인({told_on} 사용자가 대화에서 확인)"
    if answer.strip() in ("예", "네", "o", "O", "내가 찍음"):
        return RIGHTS_OK, "사용자가 직접 찍었다고 확인(_검토목록.csv)"
    if source_from == "텔레그램":
        return RIGHTS_OK, "사용자가 식당에서 직접 찍어 텔레그램으로 보냄(rules/when/myphotos.md)"
    if source_from == "대화":
        return "미확인", "사용자가 대화로 보낸 사진 — 직접 찍었는지는 확인 전"
    # 2026-10-20 사용자가 확인: 인스타그램에서 옮긴 421장도 모두 본인이 직접 찍었고 먹고갈지도 콘텐츠에 쓰도록 승인함
    return RIGHTS_OK, "본인 직접 촬영·사용 승인(2026-10-20 사용자가 대화에서 확인, 인스타그램에서 옮긴 사진)"


def answers(folder):
    """사용자가 _검토목록.csv 에 적은 답 {보관함 주소: {"name": 음식 이름 확인, "mine": 내가 찍음}}."""
    import csv
    path = folder / "_검토목록.csv" if folder else None
    if not path or not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["보관함 주소"]: {"name": (r.get("음식 이름 확인") or "").strip(), "mine": (r.get("내가 찍음(예/아니오)") or "").strip()}
                for r in csv.DictReader(f) if r.get("보관함 주소")}


def catalog(out_dir=None):
    folder = photo_dir()
    told = answers(folder)
    index = vault_index()
    by_sha = {}
    if folder:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4"):
                by_sha[sha256(p)] = p.name
    rows = []
    for it in index:
        note = re.sub(r"\s*\(사용자가[^)]*\)", "", it.get("note") or "").strip()
        status, why, tags = judge(note, it)
        if not note:
            status, why = "검토 필요", why + ["음식 이름이 없음"]
        local = by_sha.get(it.get("sha256"))
        # 내-음식-사진의 파일 이름(음식 이름)이 보관함 이름과 다르면 어느 쪽이 맞는지 모르니 검토로 둬요 (2026-10-19 52개)
        named = re.sub(r"_확인필요", "", re.sub(r"^\d+_", "", local.rsplit(".", 1)[0])) if local else ""
        ans = told.get(f"vault:{it['file']}", {})
        if ans.get("name"):  # 사용자가 음식 이름을 알려 줬으면 그 이름으로, 이름 검토는 풀어요(사람이 보이는 것은 그대로)
            note = {"보관함": note, "폴더": named}.get(ans["name"], ans["name"]).strip() or note
            why = [w for w in why if not w.startswith("무슨 음식인지")]
            status = "검토 필요" if why else "사용 가능"
        elif named and _norm(named) != _norm(note):
            status, why = "검토 필요", why + [f"폴더 이름은 '{named}' — 보관함 이름과 달라 어느 쪽이 맞는지 사용자 확인"]
        talked = (it.get("from") or "").startswith("사용자가") or it["id"].startswith("u-")
        rights, rights_why = rights_of("대화" if talked else "인스타", ans.get("mine", ""), TOLD_MINE.get(it["id"], ""))
        rows.append({
            "ref": f"vault:{it['file']}",  # 매일 실행(클라우드)에서 쓰는 주소
            "local": f"vault:내-음식-사진/{local}" if local else None,  # 이 컴퓨터에서 VAULT_DIR=상위 폴더로 만들 때
            "type": it.get("type"), "food": note, "food_local": named if named and _norm(named) != _norm(note) else "",
            # 갈래는 사용자가 붙인 폴더 이름을 참고해 나눠요(이름이 확정된 것은 아니에요). 보관함 이름의 갈래는 group_alt
            "group": group_of(named or note), "group_alt": group_of(note) if group_of(note) != group_of(named or note) else "",
            "tags": tags, "source": 1, "from": it.get("from") or ("사용자가 대화로 보냄" if talked else "사용자 인스타그램에서 옮김"),
            "taken": it.get("taken") or "", "w": it.get("w"), "h": it.get("h"),
            "status": status, "why": why, "used": it.get("used") or [],
            "rights": rights, "rights_why": rights_why,
            "pick": "사용자 지정" if "사용자가 지정" in (it.get("note") or "") else "",
        })
    # 텔레그램으로 보낸 사진·영상 (공개 저장소 myphotos/index.json, 매일 저녁 영상용으로 이미 정해진 것)
    tg = ROOT / "myphotos" / "index.json"
    if tg.exists():
        for it in json.loads(tg.read_text(encoding="utf-8")):
            note = it.get("note") or ""
            status, why, tags = judge(note, it)
            rows.append({"ref": it["file"], "local": None, "type": it.get("type"), "food": note, "group": group_of(note),
                         "tags": tags, "source": 1, "from": "사용자가 텔레그램으로 보냄", "taken": it.get("date", ""),
                         "status": "사용 끝" if it.get("used") else status, "why": why, "used": it.get("used") or [],
                         "rights": RIGHTS_OK, "rights_why": rights_of("텔레그램")[1],
                         "pick": "", "plan": it.get("plan") or it.get("side")})
    missing = len(by_sha) - sum(1 for r in rows if r["local"])
    out_dir = Path(out_dir) if out_dir else folder
    if not out_dir:
        sys.exit("내-음식-사진 폴더를 못 찾았어요. MY_PHOTOS_DIR 을 적어 주세요.")
    meta = {"made": __import__("datetime").date.today().isoformat(),
            "basis": "status 는 내용(무슨 음식인지·사람이 보이는지·이름이 맞는지), rights 는 권리(직접 찍었는지·사용 권한). "
                     "2026-10-19 사용자가 정함: 인스타그램에서 가져왔다는 것만으로 직접 찍은 사진으로 보지 않는다. "
                     "직접 찍었거나 권한이 확인된 것(rights '확인')만 상업용 콘텐츠(게시)에 쓰고 나머지는 보류한다. "
                     "폴더 파일 이름은 사용자가 붙인 이름이라 갈래를 나눌 때 참고하지만, 보관함 이름과 다르면 확정하지 않는다. "
                     "status 는 목록의 표시(ask·careful·이름)로만 정한 것이고 사진을 다시 열어 본 것은 아니다. "
                     "얼굴이 보이는 사진은 보관함에 넣을 때 뺐다(보관함 README).",
            "local_only": missing}
    data = {"meta": meta, "items": rows}
    (out_dir / "_목록.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "_목록.md").write_text(summary_md(data), encoding="utf-8")
    review_csv(rows, out_dir, told)
    c = Counter(r["status"] for r in rows)
    print(f"{len(rows)}개 → {out_dir / '_목록.json'}  (내용: {', '.join(f'{k} {v}' for k, v in c.most_common())})")
    c = Counter(r["rights"] for r in rows)
    print(f"  권리: {', '.join(f'{k} {v}' for k, v in c.most_common())} — '확인'만 게시용")
    if missing:
        print(f"보관함 목록에 없는 파일이 내-음식-사진에 {missing}개 있어요(목록에 넣지 않았어요).")


def review_csv(rows, out_dir, told):
    """_검토목록.csv — 파일번호·현재 이름·의심되는 이름·보류 이유. 내용 검토가 필요한 것이 먼저, 그다음 권리만 미확인인 것.
    사용자는 '음식 이름 확인'(보관함 / 폴더 / 새 이름)과 '내가 찍음(예/아니오)' 칸만 채우면 돼요. 다시 만들어도 적은 답은 남아요."""
    import csv

    def num(r):
        return r["local"].split("/", 1)[1].split("_", 1)[0] if r.get("local") else "-"
    order = sorted([r for r in rows if r["status"] != "사용 끝"],
                   key=lambda r: (r["status"] != "검토 필요", r["rights"] == RIGHTS_OK, num(r)))
    with open(out_dir / "_검토목록.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["파일번호", "현재 이름(폴더)", "의심되는 이름(보관함)", "갈래", "종류", "내용 상태", "권리 상태", "보류 이유",
                    "음식 이름 확인", "내가 찍음(예/아니오)", "보관함 주소"])
        for r in order:
            ans = told.get(r["ref"], {})
            current = r.get("food_local") or (r["local"].split("/", 1)[1].split("_", 1)[1].rsplit(".", 1)[0] if r.get("local") else r["food"])
            current = current.replace("_확인필요", "")
            suspect = r["food"] if (_norm(r["food"]) != _norm(current) or "(?)" in r["food"]) else ""
            reasons = r["why"] + ([r["rights_why"]] if r["rights"] != RIGHTS_OK else [])
            w.writerow([num(r), current, suspect, r["group"] + (f" (보관함 이름이면 {r['group_alt']})" if r.get("group_alt") else ""), "영상" if r["type"] == "video" else "사진", r["status"], r["rights"],
                        " / ".join(reasons), ans.get("name", ""), ans.get("mine", ""), r["ref"]])


def summary_md(data):
    rows = data["items"]
    out = ["# 내 음식 사진·영상 목록 (자동으로 만든 것, 고치지 말고 `python scripts/media.py catalog` 로 다시 만들어요)", "",
           f"만든 날: {data['meta']['made']}", "", "> " + data["meta"]["basis"], "",
           "확인할 표: `_검토목록.csv`(엑셀로 열려요). '음식 이름 확인'에 보관함 / 폴더 / 새 이름, '내가 찍음'에 예 / 아니오를 적고 "
           "`python scripts/media.py catalog` 를 다시 돌리면 반영돼요.", "",
           "| 갈래 | 내용 사용 가능 | 내용 검토 필요 | 권리 확인(게시 가능) | 영상 | 이미 씀 |", "|---|---|---|---|---|---|"]
    groups = sorted({r["group"] for r in rows}, key=lambda g: [n for n, _ in GROUPS].index(g) if g in [n for n, _ in GROUPS] else 99)
    for g in groups:
        rs = [r for r in rows if r["group"] == g]
        ok = sum(1 for r in rs if r["status"].startswith("사용 가능"))
        out.append(f"| {g} | {ok} | {sum(1 for r in rs if r['status'] == '검토 필요')} | "
                   f"{sum(1 for r in rs if r['rights'] == RIGHTS_OK and r['status'].startswith('사용 가능'))} | "
                   f"{sum(1 for r in rs if r['type'] == 'video')} | {sum(1 for r in rs if r['used'])} |")
    out += ["", "## 검토 필요한 것", ""]
    for r in rows:
        if r["status"] == "검토 필요":
            out.append(f"- {r['local'] or r['ref']} — {r['food']}: {' / '.join(r['why'])}")
    out += ["", "## 갈래별", ""]
    for g in groups:
        out.append(f"### {g}")
        for r in rows:
            if r["group"] == g:
                mark = ("" if r["status"].startswith("사용 가능") else f" ⚠️{r['status']}") + ("" if r["rights"] == RIGHTS_OK else " 🔒권리 미확인")
                used = f" (씀: {', '.join(r['used'])})" if r["used"] else ""
                tags = f" [{', '.join(r['tags'])}]" if r["tags"] else ""
                other = f" (폴더 이름: {r['food_local']})" if r.get("food_local") else ""
                out.append(f"- {r['food']}{other}{tags}{mark}{used} — `{r['ref']}`" + (f" · `{r['local']}`" if r["local"] else ""))
        out.append("")
    return "\n".join(out)


def load_catalog():
    folder = photo_dir()
    path = folder / "_목록.json" if folder else None
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find(word, show_all=False):
    data = load_catalog()
    if not data:
        sys.exit("목록이 없어요. 먼저 python scripts/media.py catalog")
    hits = [r for r in data["items"] if word == r["group"] or word in r["food"] or word in (r.get("food_local") or "")]
    if not show_all:
        hits = [r for r in hits if r["status"].startswith("사용 가능")]
    hits.sort(key=lambda r: (r.get("rights") != RIGHTS_OK, bool(r["used"]), r["pick"] != "사용자 지정", r["type"] != "video"))
    for r in hits:
        print(json.dumps({k: r[k] for k in ("food", "food_local", "group", "type", "status", "rights", "tags", "used", "ref", "local", "why")
                          if r.get(k)}, ensure_ascii=False))
    if not hits:
        print(f"'{word}' 에 맞는 사용 가능한 사진이 없어요. 다음 순서: 한국관광공사(scripts/photos.py tour) → 자체 그래픽 카드.")


def groups():
    data = load_catalog()
    if not data:
        sys.exit("목록이 없어요. 먼저 python scripts/media.py catalog")
    c = Counter((r["group"], r["status"].startswith("사용 가능")) for r in data["items"])
    for g in sorted({k[0] for k in c}):
        print(f"{g}: 사용 가능 {c[(g, True)]}, 검토 필요 {c[(g, False)]}")


# ── 설계도 검사 ─────────────────────────────────────────────

def media_urls(spec):
    """설계도에 나오는 사진·영상 주소 [(어디, 주소)]."""
    out = []

    def add(where, p):
        if isinstance(p, dict) and p.get("url"):
            out.append((where, p["url"]))
        elif isinstance(p, str):
            out.append((where, p))
    for n, l in enumerate(spec.get("lines") or [], 1):
        for p in l.get("photos") or ([l["photo"]] if l.get("photo") else []):
            add(f"{n}번 문장", p)
        if l.get("video"):
            add(f"{n}번 문장 영상", l["video"])
        # 추천 쇼츠(layout rec)의 장면: show / shows (사진·영상·상품·묶음·여러 칸)
        for v in (l.get("shows") or []) + ([l["show"]] if l.get("show") else []):
            if not v:
                continue
            for k in ("photo", "video"):
                if v.get(k):
                    add(f"{n}번 문장", v[k])
            for it in ([v["product"]] if v.get("product") else []) + ((v.get("set") or {}).get("items") or []) + (v.get("grid") or []):
                add(f"{n}번 문장", it.get("photo") or {"url": it.get("img")})
    for n, s in enumerate(spec.get("scenes") or [], 1):
        for k in ("photo", "video"):
            if s.get(k):
                add(f"{n}번 장면", s[k])
    th = spec.get("thumb") or {}
    if th.get("photo"):
        add("썸네일", th["photo"])
    return out


def tier_of(url, assets):
    """(단계, 이름, 출처 규칙 dict). assets 에 적은 것이 먼저예요."""
    a = assets.get(url)
    if a and a.get("tier"):
        return int(a["tier"]), a.get("src", ""), a
    if url.startswith("vault:") or "/releases/download/myphotos/" in url:
        return 1, "사용자 사진", {}
    for h in SOURCES["hosts"]:
        if any(m in url for m in h["match"]):
            return h["tier"], h["name"], h
    return 0, "모르는 출처", {}


def check(spec):
    """(꼭 고칠 것, 보면 좋은 것). 2026-10-19 사용자가 정한 소재 기준:
    - 사용자 사진: 목록에서 '검토 필요'(무슨 음식인지 모름·사람 보임)면 알려 줘요. 무슨 음식인지 모르는 것은 막아요.
    - 관광공사: credits 에 출처가 있어야 하고, 3유형(변경 금지)은 쓰지 않아요.
    - 회사 공식 상품 이미지: assets 에 상품명·가격·용량·원본 주소·확인 날짜·이용 조건을 적고,
      서면 허락(permission)이 없으면 자동 게시에 쓰지 않아요('검토 대상'). 출처 표시만으로 허락이 되지 않아요.
    - 출처를 모르는 사진은 막아요. 협찬·제휴처럼 보이는 말도 막아요.
    """
    must, should = [], []
    assets = {a["url"]: a for a in spec.get("assets") or [] if a.get("url")}
    cat = load_catalog()
    by_ref = {}
    if cat:
        for r in cat["items"]:
            by_ref[r["ref"]] = r
            if r.get("local"):
                by_ref[r["local"]] = r
    credits = " ".join(str(c) for c in spec.get("credits") or [])
    tiers = set()
    for where, url in media_urls(spec):
        tier, name, rule = tier_of(url, assets)
        tiers.add(tier)
        if tier == 1:
            r = by_ref.get(url)
            if cat and url.startswith("vault:") and not r:
                should.append(f"{where}: {url} 가 사진 목록에 없어요. 사용자가 준 사진인지 확인해 주세요.")
            sample = bool(spec.get("sample"))  # 비공개 샘플은 만들 수는 있게 알림만 해요(게시는 안 돼요)
            if r and r["status"] == "검토 필요":
                text = f"{where}: '{r['food']}' 사진은 검토 필요 — {' / '.join(r['why'])}" + (" (샘플이라 알림만, 게시 불가)" if sample else "")
                (must if not sample and any("확실치 않음" in w or "이름이 없음" in w or "폴더 이름" in w for w in r["why"])
                 else should).append(text)
            if r and r.get("rights") and r["rights"] != RIGHTS_OK:
                text = f"{where}: '{r['food']}' — {r['rights_why']}. 게시용으로는 보류해요"
                (should if sample else must).append(text + (" (샘플이라 알림만)" if sample else "."))
            if r and "술" in r["tags"] and spec.get("kind") in ("저녁", "저녁추천"):
                must.append(f"{where}: '{r['food']}' 사진에 술이 나와요. 저녁 영상에는 술을 넣지 않아요(2026-10-18).")
        elif tier == 2:
            if "3유형" in str(assets.get(url, {}).get("license", "")):
                must.append(f"{where}: 공공누리 3유형(변경 금지) 사진이에요. 잘라 쓰거나 글을 얹을 수 없어 쇼츠에 쓰지 않아요.")
            if "한국관광공사" not in credits:
                must.append(f"{where}: 한국관광공사 사진은 credits 에 출처(ⓒ한국관광공사 …)를 꼭 적어요.")
        elif tier == 3:
            a = assets.get(url) or {}
            lack = [k for k in ("company", "product", "price", "size", "page", "checked") if not a.get(k)]
            if lack:
                must.append(f"{where}: 회사 상품 이미지의 기록이 빠졌어요({', '.join(lack)}). assets 에 적어요.")
            company = SOURCES["companies"].get(a.get("company", ""), SOURCES["companies"]["식품 제조사"])
            if not a.get("permission"):
                (should if spec.get("sample") else must).append(  # 비공개 샘플은 알림만(게시 전에는 허락이 있어야 해요)f"{where}: {a.get('company', '회사')} 상품 이미지는 이용 허락이 확인되지 않았어요"
                            f"({company['finding'][:60]}…). 자동 게시용이 아니라 '검토 대상'이에요. "
                            "자체 비교 카드나 사용자 사진으로 바꾸거나, 사용자가 받은 서면 허락을 permission 에 적어요.")
            if a.get("fact") and not any(f.get("id") == a["fact"] for f in spec.get("facts") or []):
                must.append(f"{where}: 상품 이미지의 가격 근거 '{a['fact']}' 가 facts 에 없어요.")
        elif tier == 5:
            lic = str(assets.get(url, {}).get("license", ""))
            if "wikimedia" in url and re.search(r"BY-SA|SA ", lic):
                must.append(f"{where}: CC BY-SA 사진은 쓰지 않아요(영상 전체에 같은 라이선스가 붙을 수 있어요).")
            elif "wikimedia" in url and re.search(r"CC BY", lic):  # 2026-10-20: 조건(저작자·라이선스·원본·고쳤다는 표시)을 채우면 써요
                if not any(str(c).startswith(str(assets.get(url, {}).get("credit", "?"))) for c in spec.get("credits") or []):
                    must.append(f"{where}: CC BY 사진은 credits 에 저작자·라이선스·원본 주소를 그대로 적어요(assets 의 credit).")
            elif "wikimedia" in url and not re.search(r"CC0|퍼블릭|Public", lic, re.I):
                should.append(f"{where}: 위키미디어 사진의 license 를 assets 에 적어요(CC0·퍼블릭 도메인·CC BY).")
        elif url.startswith("http"):
            must.append(f"{where}: 출처를 모르는 사진이에요({url[:60]}). assets 에 출처와 이용 조건을 적거나 다른 사진으로 바꿔요.")
    texts = [spec.get(k, "") for k in ("headline", "title", "caption", "yt_title", "yt_lead", "yt_desc")]
    texts += [l.get("say", "") for l in spec.get("lines") or []] + [s.get("line", "") for s in spec.get("scenes") or []]
    if not spec.get("sponsored"):
        for w in SOURCES["words"]["ban"]:  # "협찬 아님"·"제휴 없음"처럼 아니라고 밝히는 말은 괜찮아요
            if any(re.search(re.escape(w) + r"(?!\s*(아님|아니|없|받지 않|안 받))", str(t)) for t in texts):
                must.append(f"'{w}' 는 협찬·제휴를 받은 것처럼 보여요. 실제 협찬이 아니면 쓰지 않아요.")
    if 3 in tiers and not spec.get("product_note"):
        should.append('회사 상품 이미지를 쓰면 "product_note"(예: "상품 이미지: CU 홈페이지, 10/19 확인 · 값은 점포마다 달라요")를 '
                      '적고 게시글에도 넣어요.')
    return must, should


def public(videos_dir=None):
    """이미 만든 설계도(videos/날짜/*.json)에 들어간 보관함 사진과 그 권리 상태를 모아요. 유튜브에 올라간 것은
    state/yt_stats.json 의 제목으로 찾아요. 결과는 내-음식-사진/_공개사용.md·.json (공개 저장소 밖). 읽기만 해요.
    2026-10-20 사용자가 정함: 기존 공개 쇼츠에 쓴 권리 미확인 사진을 계속 구분해 둔다(영상은 지우거나 고치지 않음)."""
    data = load_catalog()
    if not data:
        sys.exit("_목록.json 이 없어요. 먼저 python scripts/media.py catalog")
    cat = {r["ref"]: r for r in data["items"]}
    vdir = Path(videos_dir) if videos_dir else ROOT / "videos"
    feed = vdir.parent
    yt = json.loads((feed / "state" / "yt_stats.json").read_text(encoding="utf-8")).get("days", {}) if (feed / "state" / "yt_stats.json").exists() else {}
    shorts = yt[max(yt)]["videos"] if yt else {}
    rows = []
    for f in sorted(vdir.glob("*/*.json")):
        spec = json.loads(f.read_text(encoding="utf-8"))
        refs = sorted({u for u in re.findall(r'"url":\s*"(vault:[^"]+)"', f.read_text(encoding="utf-8"))})
        if not refs:
            continue
        day = f.parent.name
        names = {spec.get("title"), spec.get("yt_title")} - {None}
        # 유튜브 제목이 설계도 yt_title 의 앞부분만인 것도 있어요(뒤의 키워드를 빼고 올림)
        hit = [(k, v) for k, v in shorts.items() if any(n == v["t"] or n.startswith(v["t"]) for n in names)]
        how = "제목 같음"
        if not hit and f.stem == "3-dinner":  # 제목을 바꿔 올린 저녁 영상은 그날 '저녁' 제목으로 찾아요
            hit, how = [(k, v) for k, v in shorts.items() if v["at"][:10] == day and "저녁" in v["t"]], "그날 저녁 영상(추정)"
        photos = []
        for u in refs:
            r = cat.get(u)
            if r:
                photos.append({"ref": u, "food": r["food"], "rights": r["rights"], "why": r["rights_why"]})
            elif u.startswith("vault:photos/"):
                photos.append({"ref": u, "food": "", "rights": "미확인", "why": "보관함 index.json 에 항목이 없음 — 어디서 온 사진인지 확인 전"})
            else:
                photos.append({"ref": u, "food": "", "rights": "사진 목록 밖", "why": "음식 사진이 아닌 보관함 자료(공지·그래픽 등) — 이 목록에서 판단하지 않음"})
        bad = [p for p in photos if p["rights"] == "미확인"]
        food = [p for p in photos if p["rights"] != "사진 목록 밖"]
        state = "권리 미확인 사진 포함" if bad else "보관함 음식 사진 모두 확인" if food else "음식 사진 없음(목록 밖 자료만)"
        rows.append({"spec": f"{day}/{f.stem}", "title": spec.get("yt_title") or spec.get("title"),
                     "youtube": [{"id": k, "title": v["t"], "how": how} for k, v in hit],
                     "state": state, "photos": photos})
    out = photo_dir()
    (out / "_공개사용.json").write_text(json.dumps({"made": __import__("datetime").date.today().isoformat(), "items": rows},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# 이미 만든 영상에 쓴 보관함 사진 (자동으로 만든 것, `python scripts/media.py public 설계도폴더` 로 다시 만들어요)", "",
          "영상은 지우거나 고치지 않았어요. '미확인' 사진은 사용자가 확인할 때까지 그대로 미확인으로 둬요.", "",
          "| 설계도 | 유튜브 | 상태 | 권리 미확인 사진 |", "|---|---|---|---|"]
    for r in rows:
        y = ", ".join(f"{v['id']} ({v['how']})" for v in r["youtube"]) or "못 찾음"
        bad = "<br>".join(f"{p['food'] or p['ref']} — {p['why']}" for p in r["photos"] if p["rights"] == "미확인") or "-"
        md.append(f"| {r['spec']} {r['title']} | {y} | {r['state']} | {bad} |")
    (out / "_공개사용.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['spec']}: {r['state']} ({sum(p['rights'] == '미확인' for p in r['photos'])}장 미확인) · 유튜브 {len(r['youtube'])}편")
    print(f"→ {out / '_공개사용.md'}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "public":
        public(sys.argv[2] if len(sys.argv) > 2 else None)
        return
    if cmd == "catalog":
        catalog(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "find" and len(sys.argv) > 2:
        find(sys.argv[2], "--all" in sys.argv)
    elif cmd == "groups":
        groups()
    elif cmd == "check" and len(sys.argv) > 2:
        spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        m, s = check(spec)
        for x in m:
            print("꼭 고쳐 주세요:", x)
        for x in s:
            print("보면 좋아요:", x)
        if not m and not s:
            print("소재 출처·이용 조건 문제 없음")
        sys.exit(1 if m else 0)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
