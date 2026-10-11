# -*- coding: utf-8 -*-
"""여러 스크립트가 함께 쓰는 것들."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

REQUIRED = ["id", "date", "category", "country", "subject", "angle", "title", "summary", "facts",
            "script", "length_sec", "visuals", "pairing", "cautions", "sources", "checked"]
CATEGORIES = ["한국 제철", "해외 제철", "축제", "식품 안전", "예고"]


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def log_error(where, message):
    """오류를 logs/errors.jsonl 에 한 줄씩 남겨요."""
    path = ROOT / "logs" / "errors.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"time": datetime.now(KST).isoformat(timespec="seconds"), "where": where, "message": str(message)[:500]}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def dedupe_key(item):
    """같은 음식·축제의 같은 주제는 한 해에 한 번만 내요."""
    return f"{item['subject']}|{item['angle']}|{item['date'][:4]}".replace(" ", "")


def load_items():
    """items 폴더의 글을 모두 읽고 문제를 찾아요. (글 목록, 문제 목록)"""
    items, problems, seen = [], [], {}
    for path in sorted((ROOT / "items").glob("*/*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"{path.name}: 읽을 수 없어요 ({e})")
            continue
        missing = [k for k in REQUIRED if not item.get(k)]
        if missing:
            problems.append(f"{path.name}: 빠진 항목 {missing}")
            continue
        if item["category"] not in CATEGORIES:
            problems.append(f"{path.name}: 분류가 잘못됐어요 ({item['category']})")
            continue
        if not 3 <= len(item["summary"]) <= 5:
            problems.append(f"{path.name}: 핵심 내용은 3~5문장이어야 해요")
            continue
        if not 15 <= int(item["length_sec"]) <= 45:
            problems.append(f"{path.name}: 추천 길이는 15~45초여야 해요")
            continue
        if not all(s.get("url", "").startswith("http") for s in item["sources"]):
            problems.append(f"{path.name}: 출처에 원문 링크가 없어요")
            continue
        key = dedupe_key(item)
        if key in seen:
            problems.append(f"{path.name}: {seen[key]} 와 같은 내용이라 뺐어요")
            continue
        seen[key] = path.name
        items.append(item)
    items.sort(key=lambda i: (i["date"], i["id"]), reverse=True)
    return items, problems
