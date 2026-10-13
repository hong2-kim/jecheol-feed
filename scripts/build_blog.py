# -*- coding: utf-8 -*-
"""blog 폴더의 초안으로 네이버 블로그에 붙여 넣을 페이지를 만들어요.

  python scripts/build_blog.py
만드는 것: public/blog/<id>.html (제목·본문·태그 복사 버튼이 있는 페이지)
build_feed.py 가 함께 불러서, 따로 돌리지 않아도 돼요.
"""
import html
import json
import re
import sys

from common import ROOT, log_error, read_json

REQUIRED = ["id", "date", "subject", "keyword", "title", "tags", "blocks", "checked"]
TYPES = ["p", "h2", "h3", "ul", "summary", "quote", "table", "photo", "exp", "source", "faq"]


def esc(text):
    return html.escape(str(text))


def rich(text):
    """**굵게** 만 꾸밈으로 바꿔요. 나머지는 글자 그대로 보여요."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))


def plain(block):
    """글자 수를 셀 때 쓰는, 블록 하나의 글."""
    t = block.get("type")
    if t in ("p", "h2", "h3", "quote", "exp"):
        return block.get("text", "")
    if t in ("ul", "summary"):
        return " ".join(block.get("items", []))
    if t == "table":
        return " ".join(block.get("head", []) + [c for row in block.get("rows", []) for c in row])
    if t == "faq":
        return " ".join(x.get("q", "") + " " + x.get("a", "") for x in block.get("items", []))
    return ""


def check(post, name):
    """초안 하나에서 고칠 곳을 찾아요. 없으면 빈 목록."""
    missing = [k for k in REQUIRED if not post.get(k)]
    if missing:
        return [f"빠진 항목 {missing}"]
    out, blocks = [], post["blocks"]
    if post["id"] != name or not name.startswith(post["date"]):
        out.append("id 는 파일 이름과 같고 날짜로 시작해야 해요")
    bad = [b.get("type") for b in blocks if b.get("type") not in TYPES]
    if bad:
        return out + [f"모르는 블록 종류 {bad}"]
    squash = lambda s: s.replace(" ", "")
    at = squash(post["title"]).find(squash(post["keyword"]))
    if not 0 <= at <= 10:
        out.append("제목 앞쪽에 핵심 키워드(keyword)가 그대로 들어가야 해요")
    if len(post["title"]) > 50:
        out.append(f"제목이 길어요 ({len(post['title'])}자, 50자까지)")
    intro = ""
    for b in blocks:
        if b["type"] == "h2":
            break
        intro += plain(b)
    if not all(word in intro for word in post["keyword"].split()):
        out.append("첫 소제목 앞 글에 핵심 키워드의 낱말이 모두 들어가야 해요")
    count = lambda t: sum(1 for b in blocks if b["type"] == t)
    if count("photo") < 3:
        out.append("사진 자리(photo)가 3곳 이상 있어야 해요")
    # 자동으로 올리기 시작한 날부터는 사람이 사진을 채우지 않으니, 추천 사진이 들어 있어야 해요.
    auto = (read_json(ROOT / "config.json", {}) or {}).get("blog_publish") or {}
    need = int(auto.get("photos_required", 3))
    if auto.get("on") and post["date"] >= auto.get("since", "") and sum(1 for b in blocks if b["type"] == "photo" and b.get("url")) < need:
        out.append(f"추천 사진(url)이 들어간 사진 자리가 {need}곳 이상 있어야 해요 (네이버에 자동으로 올라가요)")
    if count("summary") != 1:
        out.append("핵심 요약(summary)은 하나만 있어야 해요")
    if count("table") < 1:
        out.append("비교표(table)가 하나 이상 있어야 해요")
    if not any(b["type"] == "faq" and len(b.get("items", [])) >= 3 for b in blocks):
        out.append("자주 묻는 질문(faq)이 3개 이상 있어야 해요")
    heads = [b["text"] for b in blocks if b["type"] == "h2"]
    if len(heads) < 4 or sum(h.rstrip().endswith("?") for h in heads) * 2 < len(heads):
        out.append("소제목(h2)은 4개 이상, 절반 넘게 질문형(?)이어야 해요")
    tags = post["tags"]
    if not 10 <= len(tags) <= 15 or any(" " in t or "#" in t for t in tags):
        out.append("태그는 10~15개, 띄어쓰기와 # 없이 적어요")
    size = len("".join(plain(b) for b in blocks).replace(" ", ""))
    if size < 1800:
        out.append(f"본문이 짧아요 ({size}자, 1800자 이상)")
    links = [l.get("url", "") for b in blocks if b["type"] == "source" for l in b.get("links", [])]
    if len(set(links)) < 2 or not all(u.startswith("http") for u in links):
        out.append("출처(source)는 원문 링크로 2곳 이상 있어야 해요")
    for b in blocks:
        if b["type"] == "photo" and b.get("url") and not str(b["url"]).startswith("http"):
            out.append("추천 사진 주소(url)는 http 로 시작해야 해요")
        if b["type"] == "table" and any(len(r) != len(b.get("head", [])) for r in b.get("rows", [])):
            out.append("표의 줄마다 칸 수가 제목 줄과 같아야 해요")
    return out


def load_posts():
    """blog 폴더의 초안을 모두 읽고 문제를 찾아요. (초안 목록, 문제 목록)"""
    posts, problems, seen = [], [], {}
    for path in sorted((ROOT / "blog").glob("*.json")):
        try:
            post = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"blog/{path.name}: 읽을 수 없어요 ({e})")
            continue
        found = check(post, path.stem)
        if found:
            problems += [f"blog/{path.name}: {x}" for x in found]
            continue
        key = f"{post['subject']}|{post['date'][:4]}".replace(" ", "")
        if key in seen:
            problems.append(f"blog/{path.name}: {seen[key]} 와 같은 주제라 뺐어요")
            continue
        seen[key] = path.name
        posts.append(post)
    posts.sort(key=lambda p: p["id"], reverse=True)
    return posts, problems


def todo(post):
    """올리기 전에 사람이 채울 자리 수."""
    blocks = post["blocks"]
    return {"photo": sum(1 for b in blocks if b["type"] == "photo"),
            "exp": sum(1 for b in blocks if b["type"] == "exp")}


def block_html(b):
    t = b["type"]
    if t == "p":
        return f"<p>{rich(b['text'])}</p>"
    if t in ("h2", "h3"):
        return f"<{t}>{rich(b['text'])}</{t}>"
    if t == "ul":
        return "<ul>" + "".join(f"<li>{rich(x)}</li>" for x in b["items"]) + "</ul>"
    if t == "summary":
        return "<blockquote><p><b>핵심 요약</b></p><ul>" + "".join(f"<li>{rich(x)}</li>" for x in b["items"]) + "</ul></blockquote>"
    if t == "quote":
        return f"<blockquote><p>{rich(b['text'])}</p></blockquote>"
    if t == "table":
        head = "".join(f"<th>{rich(c)}</th>" for c in b["head"])
        rows = "".join("<tr>" + "".join(f"<td>{rich(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    if t == "photo":
        # 추천 사진은 고를 때 보라고 보여 주는 것이라, 본문을 복사할 때는 빠져요.
        tip = ""
        if b.get("url"):
            credit = f"<br>이 사진을 쓰면 사진 아래에 적어 주세요: <b>{esc(b['credit'])}</b>" if b.get("credit") else "<br>출처를 적지 않아도 되는 사진이에요."
            tip = (f'<div class="pick" data-nocopy><img src="{esc(b["url"])}" alt="{esc(b["desc"])}" loading="lazy">'
                   f'<small>추천 사진 · <a href="{esc(b["url"])}" target="_blank" rel="noopener">크게 보기·저장</a>{credit}</small></div>')
        return f'<div class="photo">📷 사진 자리: {esc(b["desc"])}{tip}</div>'
    if t == "exp":
        return f'<div class="exp">✍️ 경험 자리: {esc(b["text"])}</div>'
    if t == "source":
        return "<p>출처: " + ", ".join(f'<a href="{esc(l["url"])}">{esc(l["name"])}</a>' for l in b["links"]) + "</p>"
    if t == "faq":
        return "<h2>자주 묻는 질문</h2>" + "".join(f"<h3>Q. {rich(x['q'])}</h3><p>{rich(x['a'])}</p>" for x in b["items"])
    return ""


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>블로그 초안 · __SUBJECT__</title>
<style>
  :root {
    --bg: #f4f5f7; --panel: #ffffff; --text: #1f2328; --muted: #5b636e;
    --line: #dde1e6; --accent: #03c75a; --accent-ink: #ffffff;
    --photo-bg: #eef6ff; --photo-line: #7aa7e0; --exp-bg: #fff7e6; --exp-line: #e0a93a;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #15181c; --panel: #1e2227; --text: #e6e8eb; --muted: #9aa3ad;
      --line: #343a41; --photo-bg: #1b2a3d; --photo-line: #4d7fbf; --exp-bg: #3a2f17; --exp-line: #b8872a;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; line-height: 1.75; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 24px 16px 64px; }
  .guide { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .guide h2 { margin: 0 0 8px; font-size: 18px; }
  .guide ol { margin: 0 0 12px; padding-left: 20px; color: var(--muted); }
  .guide .meta { color: var(--muted); font-size: 14px; margin: 0 0 8px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 12px; }
  .label { font-weight: 700; font-size: 14px; }
  .field { flex: 1 1 280px; min-width: 0; background: var(--bg); color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; font-size: 15px; }
  button { background: var(--accent); color: var(--accent-ink); border: 0; border-radius: 8px; padding: 10px 16px;
    font-size: 15px; font-weight: 700; cursor: pointer; }
  button:focus-visible { outline: 3px solid var(--text); outline-offset: 2px; }
  .status { font-size: 14px; color: var(--accent); min-height: 1.2em; }
  #post { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 28px 22px; }
  #post h2 { font-size: 21px; margin: 36px 0 12px; }
  #post h3 { font-size: 18px; margin: 24px 0 8px; }
  #post p, #post li { font-size: 16px; }
  #post blockquote { margin: 16px 0; padding: 12px 16px; border-left: 4px solid var(--accent); background: var(--bg); }
  #post table { width: 100%; border-collapse: collapse; margin: 12px 0 20px; font-size: 15px; }
  #post th, #post td { border: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }
  #post th { background: var(--bg); }
  .table-scroll { overflow-x: auto; }
  .photo { background: var(--photo-bg); border: 2px dashed var(--photo-line); border-radius: 8px; padding: 12px 14px; margin: 16px 0; }
  .exp { background: var(--exp-bg); border: 2px dashed var(--exp-line); border-radius: 8px; padding: 12px 14px; margin: 16px 0; }
  .pick { margin-top: 10px; }
  .pick img { display: block; width: 100%; max-width: 420px; border-radius: 8px; }
  .pick small { display: block; margin-top: 6px; color: var(--muted); line-height: 1.5; }
  a { color: inherit; word-break: break-all; }
</style>
</head>
<body>
<div class="wrap">

  <section class="guide" aria-label="붙여 넣기 안내">
    <h2>네이버 블로그에 올리는 순서</h2>
    <p class="meta">__DATE__ 초안 · 사진 자리 __PHOTOS__곳 · 경험 자리 __EXPS__곳 · 내용 확인 날짜 __CHECKED__</p>
    <ol>
      <li><b>제목 복사</b> → 네이버 글쓰기 제목 칸에 붙여 넣기</li>
      <li><b>본문 복사</b> → 본문 칸에 붙여 넣기 (표가 깨지면 네이버 에디터의 표 기능으로 다시 넣기)</li>
      <li>파란 점선 상자 <b>📷 사진 자리</b>를 지우고 사진 넣기 (직접 찍은 사진이 가장 좋아요. 추천 사진은 복사되지 않으니 저장해서 넣어요)</li>
      <li>노란 점선 상자 <b>✍️ 경험 자리</b>에 직접 겪은 내용을 한두 줄 쓰기 (쓸 내용이 없으면 상자 지우기)</li>
      <li><b>태그 복사</b> → 태그 칸에 붙여 넣기</li>
    </ol>
    <div class="row">
      <span class="label">제목</span>
      <input class="field" id="title" readonly value="__TITLE__">
      <button type="button" data-copy="title">제목 복사</button>
    </div>
    <div class="row">
      <span class="label">본문</span>
      <button type="button" data-copy="post">본문 복사</button>
      <span class="status" id="status" role="status" aria-live="polite"></span>
    </div>
    <div class="row">
      <span class="label">태그</span>
      <input class="field" id="tagline" readonly value="__TAGS__">
      <button type="button" data-copy="tagline">태그 복사</button>
    </div>
  </section>

  <article id="post">
__BODY__
  </article>

</div>
<script>
  const statusEl = document.getElementById('status');
  function say(msg) { statusEl.textContent = msg; setTimeout(() => { statusEl.textContent = ''; }, 2500); }
  async function copyPost() {
    // 추천 사진처럼 보기만 하는 것은 빼고 복사해요.
    const post = document.getElementById('post').cloneNode(true);
    post.querySelectorAll('[data-nocopy]').forEach(el => el.remove());
    const holder = document.createElement('div');
    holder.style.cssText = 'position:fixed;left:-9999px;top:0;width:700px';
    holder.appendChild(post);
    document.body.appendChild(holder);
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([post.innerHTML], { type: 'text/html' }),
        'text/plain': new Blob([post.innerText], { type: 'text/plain' })
      })]);
      say('본문을 복사했습니다');
    } catch (e) {
      const range = document.createRange();
      range.selectNodeContents(post);
      const sel = window.getSelection();
      sel.removeAllRanges(); sel.addRange(range);
      try { document.execCommand('copy'); say('본문을 복사했습니다'); }
      catch (e2) { say('자동 복사가 안 됩니다. 본문을 드래그해서 복사하세요'); }
      sel.removeAllRanges();
    }
    holder.remove();
  }
  async function copyField(id) {
    const el = document.getElementById(id);
    try { await navigator.clipboard.writeText(el.value); }
    catch (e) { el.select(); try { document.execCommand('copy'); } catch (e2) {} }
    say(id === 'title' ? '제목을 복사했습니다' : '태그를 복사했습니다');
  }
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.copy;
      if (t === 'post') copyPost(); else copyField(t);
    });
  });
</script>
</body>
</html>
"""


def page_html(post):
    left = todo(post)
    fill = {
        "__SUBJECT__": esc(post["subject"]), "__DATE__": esc(post["date"]), "__CHECKED__": esc(post["checked"]),
        "__PHOTOS__": str(left["photo"]), "__EXPS__": str(left["exp"]),
        "__TITLE__": esc(post["title"]), "__TAGS__": esc(" ".join("#" + t for t in post["tags"])),
        "__BODY__": "\n".join("    " + block_html(b) for b in post["blocks"]),
    }
    return re.sub("|".join(fill), lambda m: fill[m.group(0)], PAGE)


def build(out):
    """초안 페이지를 out/blog 에 만들고 (초안 목록, 문제 목록)을 돌려줘요."""
    posts, problems = load_posts()
    folder = out / "blog"
    folder.mkdir(parents=True, exist_ok=True)
    for post in posts:
        (folder / f"{post['id']}.html").write_text(page_html(post), encoding="utf-8")
    return posts, problems


def main():
    out = ROOT / "public"
    posts, problems = build(out)
    for p in problems:
        print("확인 필요:", p)
        log_error("build_blog", p)
    print(f"블로그 초안 페이지를 만들었어요: {len(posts)}개, 문제 {len(problems)}건")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
