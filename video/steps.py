# -*- coding: utf-8 -*-
"""넘겨 보는 해설 (설계도 "format": "steps"). 2026-10-18 사용자가 정함.

계란 껍데기 숫자처럼 "어디를 보면 되는지"가 있는 정보는 글로만 설명하지 않는다.
실제 사진 한 장을 깔고, 한 장(슬라이드)마다 한 군데만 표시하고 확대해서 보여 준다.
  1장: 전체 사진 + 표시 위치 전부(번호)      → "이게 다 무슨 뜻이지?"
  2장~: 한 군데씩 크게 확대 + 그 뜻 한 줄      → 다음 장이 궁금해서 넘겨요
  끝장: 살 때 볼 곳만 다시 표시 + 물음 하나

장(1080×1350)은 위쪽 사진 칸(stage)과 아래쪽 글 칸으로 나뉘어요. 확대한 장에는 오른쪽 아래에 전체 사진 속 위치를 작게(미니맵) 보여 줘요.
카드 뉴스와 같은 길로 그림이 만들어지고(dist/날짜-이름-1.jpg …), 유튜브 쇼츠용 영상도 그 그림을 넘기는 영상으로 자동으로 나와요.

설계도:
  {"format": "steps", "kind": "해설", "subject", "title",
   "base": {"photo": {...},
            "stamp": {"parts": ["1015", "M3FDS", "2"], "x": 50, "y": 50, "size": 58, "rotate": -4},   ← 사진 위에 찍힌 글(예시 표시)
            "marks": [{"box": [왼, 위, 오른, 아래]}],                                                  ← 또는 사진 속 실제 위치(%)
            "example": "예시"},                                                                          ← 표시가 예시면 사진 위에 작게 알려요
   "slides": [{"focus": [], "view": {"zoom": 0.9, "x": 50, "y": 50}, "tag": "계란 껍데기 숫자", "headline": "…", "lines": ["…"]},
              {"focus": [0], "zoom": 2.6, "tag": "① 앞 4자리", "headline": "…", "lines": ["…"], "legend": [{"no": "1", "name": "방사", "sub": "…"}]}, …],
   "src": "식약처", "caption", "tags", "sources", "credits", "yt_*" …}
focus 는 stamp.parts(또는 marks)의 차례 번호(0부터)예요. 여러 개를 적으면 모두 들어오게 확대해요.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
SIZE = {"width": 1080, "height": 1350}
COLORS = ["#FF6A3D", "#3D8BFF", "#22B573", "#B36BFF", "#FFB23E"]  # 표시 위치마다 색 (1번 주황, 2번 파랑, 3번 초록 …)
STAGE = 740  # 위쪽 사진 칸 높이 (legend 가 있는 장은 조금 줄여요)
NUMS = "①②③④⑤⑥⑦⑧⑨"

CSS = """
@font-face { font-family: "Noto Sans KR"; src: url("FONT_DIR/NotoSansKR-VF.ttf"); font-weight: 100 900; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1080px; background: #17130F; }
body { color: #fff; font-family: "Noto Sans KR", sans-serif; word-break: keep-all; -webkit-font-smoothing: antialiased; }
.am { color: var(--ac); }
.st { position: relative; width: 1080px; height: 1350px; overflow: hidden; background: #17130F; }
.stage { position: absolute; left: 0; top: 0; width: 1080px; overflow: hidden; background: #fff; }
.world { position: absolute; left: 0; top: 0; width: 1080px; transform-origin: 0 0; }
.world > img { display: block; width: 100%; }
.stamp { position: absolute; transform: translate(-50%, -50%); white-space: nowrap; font-weight: 800; letter-spacing: 3px;
  color: rgba(150, 28, 34, .82); mix-blend-mode: multiply; filter: blur(.5px); }
.stamp .seg { display: inline-block; padding: 0 4px; border-radius: 8px; }
.mark { position: absolute; border-radius: 10px; }
.dim .seg:not(.on), .dim .mark:not(.on) { opacity: .28; }
.seg.on, .mark.on { outline: 5px solid var(--c); outline-offset: 3px; background: color-mix(in srgb, var(--c) 14%, transparent); }
/* 1장: 숫자 묶음마다 색 밑줄과 번호 */
.lab { position: absolute; transform: translateX(-50%); display: flex; flex-direction: column; align-items: center; gap: 6px; }
.lab i { width: var(--w); height: 8px; border-radius: 4px; background: var(--c); }
.lab b { width: 66px; height: 66px; border-radius: 50%; background: var(--c); color: #fff; font-size: 42px; font-weight: 900;
  display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 16px rgba(0,0,0,.25); }
.ex { position: absolute; right: 26px; top: 112px; padding: 4px 16px 7px; border-radius: 8px; background: rgba(23,19,15,.72); color: #fff; font-size: 26px; font-weight: 700; }
.zoomchip { position: absolute; left: 26px; bottom: 22px; display: flex; align-items: center; gap: 8px; padding: 6px 18px 9px; border-radius: 999px;
  background: rgba(23,19,15,.78); color: #fff; font-size: 30px; font-weight: 800; }
.zoomchip svg { width: 30px; height: 30px; }
.mini { position: absolute; right: 22px; bottom: 22px; width: 230px; overflow: hidden; border-radius: 14px; border: 4px solid #fff;
  box-shadow: 0 8px 22px rgba(0,0,0,.35); background: #F4F1EC; }
.mini .mw { width: 1080px; }
.mini .vp { position: absolute; border: 4px solid var(--c); border-radius: 6px; box-shadow: 0 0 0 999px rgba(23,19,15,.32); }
.shade { position: absolute; left: 0; right: 0; height: 140px; background: linear-gradient(180deg, rgba(23,19,15,0), #17130F); }
.mast { position: absolute; left: 44px; right: 44px; top: 34px; display: flex; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 12px; padding: 8px 20px 11px 14px; border-radius: 999px; background: rgba(23,19,15,.8);
  font-weight: 900; font-size: 36px; letter-spacing: -1.2px; }
.brand svg { width: 32px; height: 40px; flex: none; }
.brand b { color: var(--ac); }
.brand i { margin-left: 4px; padding: 2px 12px 5px; border-radius: 8px; background: var(--ac); color: #17130F; font-style: normal; font-size: 26px; letter-spacing: 0; }
.no { padding: 6px 18px 9px; border-radius: 999px; background: rgba(23,19,15,.8); font-weight: 800; font-size: 30px; }
.txt { position: absolute; left: 60px; right: 60px; }
.tag { display: inline-block; padding: 5px 18px 9px; border-radius: 10px; background: var(--c); color: #fff; font-weight: 900; font-size: 36px; letter-spacing: -.5px; }
.hl { margin-top: 16px; font-weight: 900; line-height: 1.16; letter-spacing: -3.5px; white-space: pre-line; }
.hl .am { color: var(--c); }
.ln { margin-top: 10px; font-weight: 600; font-size: 36px; line-height: 1.38; letter-spacing: -1px; color: rgba(255,255,255,.9); }
.ln .am { color: var(--c); font-weight: 800; }
.legend { margin-top: 20px; display: grid; grid-template-columns: repeat(var(--n), 1fr); gap: 12px; }
.legend div { padding: 14px 8px 16px; border-radius: 16px; background: #2A231C; text-align: center; border: 3px solid transparent; }
.legend div.on { border-color: var(--c); background: color-mix(in srgb, var(--c) 22%, #2A231C); }
.legend b { display: block; font-size: 60px; font-weight: 900; line-height: 1.05; color: var(--c); }
.legend span { display: block; margin-top: 4px; font-size: 32px; font-weight: 800; letter-spacing: -1px; }
.legend small { display: block; margin-top: 2px; font-size: 24px; font-weight: 600; color: rgba(255,255,255,.7); letter-spacing: -.5px; }
.foot { position: absolute; left: 60px; right: 60px; bottom: 40px; display: flex; align-items: center; justify-content: space-between;
  font-size: 28px; font-weight: 600; color: rgba(255,255,255,.62); }
.foot b { color: var(--ac); font-weight: 900; font-size: 34px; }
"""

LOUPE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">'
         '<circle cx="10" cy="10" r="6.5"/><path d="M15 15l6 6"/><path d="M10 7v6M7 10h6" stroke-width="2.4"/></svg>')

# 사진 칸 안에서 확대할 곳을 재고 옮겨요. 글자 위치는 글꼴이 그려진 뒤에야 알 수 있어서 화면에서 재요.
# produce.py 가 글꼴을 기다린 뒤 window.ready() 를 불러요. (그 전에 불려도 한 번 더 부르면 그대로 맞춰져요)
JS = """
window.ready = () => {
  document.querySelectorAll('.st').forEach((st) => {
    const stage = st.querySelector('.stage'), world = st.querySelector('.stage > .world');
    const W = stage.clientWidth, H = stage.clientHeight, WH = world.offsetHeight;
    world.style.transform = 'none';
    const focus = JSON.parse(st.dataset.focus || '[]');
    const zoom = parseFloat(st.dataset.zoom || '0');
    const segs = [...world.querySelectorAll('[data-k]')];
    const wr = world.getBoundingClientRect();
    const box = (els) => {
      const rs = els.map((e) => e.getBoundingClientRect());
      return {x0: Math.min(...rs.map((r) => r.left)) - wr.left, y0: Math.min(...rs.map((r) => r.top)) - wr.top,
              x1: Math.max(...rs.map((r) => r.right)) - wr.left, y1: Math.max(...rs.map((r) => r.bottom)) - wr.top};
    };
    // 1장: 숫자 묶음마다 밑줄과 번호를 달아요
    st.querySelectorAll('.lab').forEach((lab) => {
      const b = box([world.querySelector(`[data-k="${lab.dataset.k}"]`)]);
      lab.style.left = ((b.x0 + b.x1) / 2) + 'px';
      lab.style.top = (b.y1 + 10) + 'px';
      lab.style.setProperty('--w', (b.x1 - b.x0) + 'px');
    });
    let z = 1, tx = 0, ty = (H - WH) / 2;
    const picked = focus.map((k) => segs.find((e) => +e.dataset.k === k)).filter(Boolean);
    const view = JSON.parse(st.dataset.view || '{}');
    if (!picked.length && view.zoom) {  // 1장: 전체가 들어오게 줄이거나 키워서 (x, y)% 를 가운데에
      z = view.zoom;
      tx = W / 2 - (view.x ?? 50) / 100 * W * z; ty = H / 2 - (view.y ?? 50) / 100 * WH * z;
    }
    if (picked.length) {
      const b = box(picked);
      const cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2;
      z = zoom || Math.min(4, (W * 0.62) / (b.x1 - b.x0), (H * 0.5) / (b.y1 - b.y0));
      z = Math.max(z, 1);
      tx = W / 2 - cx * z; ty = H * 0.47 - cy * z;
      tx = Math.min(0, Math.max(W - W * z, tx));
      ty = Math.min(0, Math.max(H - WH * z, ty));
      if (WH * z < H) ty = (H - WH * z) / 2;
    }
    world.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`;
    const mini = st.querySelector('.mini');
    if (mini) {  // 전체 사진에서 지금 보이는 곳
      const k = mini.clientWidth / W;
      mini.style.height = (WH * k) + 'px';
      mini.querySelector('.mw').style.transform = `scale(${k})`;
      const vp = mini.querySelector('.vp');
      vp.style.left = (-tx / z * k) + 'px'; vp.style.top = (Math.max(0, -ty) / z * k) + 'px';
      vp.style.width = (W / z * k) + 'px'; vp.style.height = (Math.min(H, WH * z) / z * k) + 'px';
    }
  });
  return true;
};
document.fonts.ready.then(() => window.ready());
"""


def _world(B, base, focus, labels):
    """사진 한 장 + 그 위의 표시(stamp 글자 또는 marks 상자). 확대는 JS 가 해요."""
    src, _ = B.fetch_photo(base["photo"])
    parts = []
    st = base.get("stamp")
    if st:
        segs = "".join(f'<span class="seg{" on" if k in focus else ""}" data-k="{k}" style="--c:{COLORS[k % len(COLORS)]}">{B.esc(p)}</span>'
                       for k, p in enumerate(st["parts"]))
        parts.append(f'<div class="stamp" style="left:{st.get("x", 50)}%;top:{st.get("y", 50)}%;font-size:{st.get("size", 56)}px;'
                     f'transform:translate(-50%,-50%) rotate({st.get("rotate", 0)}deg)">{segs}</div>')
        count = len(st["parts"])
    else:
        marks = base.get("marks") or []
        for k, m in enumerate(marks):
            x0, y0, x1, y1 = m["box"]
            parts.append(f'<div class="mark{" on" if k in focus else ""}" data-k="{k}" style="--c:{COLORS[k % len(COLORS)]};'
                         f'left:{x0}%;top:{y0}%;width:{x1 - x0}%;height:{y1 - y0}%"></div>')
        count = len(marks)
    if labels:
        parts += [f'<div class="lab" data-k="{k}" style="--c:{COLORS[k % len(COLORS)]}"><i></i><b>{k + 1}</b></div>' for k in range(count)]
    return f'<div class="world{" dim" if focus else ""}"><img src="{src}">{"".join(parts)}</div>', src


def slide(B, spec, s, n, total, name, pill):
    base = spec["base"]
    focus = list(s.get("focus") or [])
    color = COLORS[focus[0] % len(COLORS)] if len(focus) == 1 else "var(--ac)"
    legend = s.get("legend") or []
    stage_h = s.get("stage") or (620 if legend else STAGE)
    world, src = _world(B, base, focus, labels=not focus and s.get("labels", True))
    extra = ""
    if focus:
        extra += f'<div class="zoomchip">{LOUPE}<span>{B.esc(s.get("zoom_label", "확대"))}</span></div>'
        mini_world = _world(B, base, focus, labels=False)[0].replace('class="world', 'class="world mw', 1)  # 미니맵: 같은 사진을 작게
        extra += f'<div class="mini" style="--c:{color}">{mini_world}<div class="vp"></div></div>'
    if base.get("example"):
        extra += f'<div class="ex">{B.esc(base["example"])}</div>'
    head = s["headline"]
    size = B.fit_size(head, s.get("size", 88 if legend else 96), 960)
    lines = "".join(f'<div class="ln">{B.rich(x)}</div>' for x in s.get("lines") or [])
    legend_html = ""
    if legend:
        cells = "".join(f'<div class="{"on" if x.get("on") else ""}"><b>{B.esc(x["no"])}</b><span>{B.esc(x["name"])}</span>'
                        + (f'<small>{B.esc(x["sub"])}</small>' if x.get("sub") else "") + "</div>" for x in legend)
        legend_html = f'<div class="legend" style="--n:{len(legend)}">{cells}</div>'
    go = "밀어서 확인하기 →" if n == 1 else (s.get("go") or ("다음 →" if n < total else ""))
    foot = (f'<div class="foot"><span>자료 {B.esc(spec.get("src", ""))}</span>'
            f'<b>{B.esc(go) if go else f"{n} / {total}"}</b></div>')
    tag = f'<span class="tag">{B.esc(s["tag"])}</span>' if s.get("tag") else ""
    return (f'<section class="st" id="c{n}" style="--c:{color}" data-focus="{json.dumps(focus)}" data-zoom="{s.get("zoom", 0)}" data-view="{B.esc(json.dumps(s.get("view") or {}))}">'
            f'<div class="stage" style="height:{stage_h}px">{world}{extra}</div>'
            f'<div class="shade" style="top:{stage_h - 140}px"></div>'
            f'<div class="mast"><div class="brand">{B.OUTRO_PIN}<span>{name}</span><i>{pill}</i></div><div class="no">{n} / {total}</div></div>'
            f'<div class="txt" style="top:{stage_h + 34}px">{tag}<div class="hl" style="font-size:{size}px">{B.rich(head)}</div>{lines}{legend_html}</div>'
            f'{foot}</section>')


def problems(spec):
    """(꼭 고칠 것, 고치면 좋은 것)"""
    import build as B
    must, should = [], []
    base = spec.get("base") or {}
    if not base.get("photo"):
        must.append("base.photo(깔아 둘 실제 사진)가 없어요.")
    count = len((base.get("stamp") or {}).get("parts") or base.get("marks") or [])
    if not count:
        must.append("표시할 곳이 없어요. base.stamp.parts 나 base.marks 를 적어 주세요.")
    slides = spec.get("slides") or []
    if not 3 <= len(slides) <= 8:
        must.append(f"장이 {len(slides)}장이에요. 3~8장으로 맞춰 주세요.")
    if slides and slides[0].get("focus"):
        should.append("1장은 확대하지 않고 전체 사진에 표시 위치를 모두 보여 주는 게 좋아요(focus 를 비워 주세요).")
    for n, s in enumerate(slides, 1):
        if not s.get("headline"):
            must.append(f"{n}장에 headline 이 없어요.")
            continue
        if len(s["headline"].split("\n")) > 2:
            must.append(f"{n}장: headline 은 두 줄까지예요.")
        if max(B.units(x) for x in s["headline"].split("\n")) > 11:
            should.append(f"{n}장: headline 한 줄이 길어 글자가 작아져요. 10자 안쪽으로 줄여 주세요.")
        if len(s.get("lines") or []) > 2:
            must.append(f"{n}장: lines 는 두 줄까지예요. 나머지는 게시글에 써 주세요.")
        if any(k >= count for k in s.get("focus") or []):
            must.append(f"{n}장: focus 번호가 표시할 곳 수({count})를 넘어요.")
    if "출처" not in (spec.get("caption") or ""):
        must.append("게시글(caption) 끝에 '출처: 기관·매체 이름(날짜)' 줄을 적어 주세요.")
    return must, should


def build_steps(spec):
    """한 쪽짜리 HTML. 장은 #c1, #c2 … (HTML, 장수)"""
    import build as B
    must, _ = problems(spec)
    if must:
        raise ValueError(" / ".join(must))
    name = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8")).get("account") or ""
    name = f"{B.esc(name[:2])}<b>{B.esc(name[2:])}</b>" if name.startswith("먹고") else B.esc(name)
    pill = spec.get("pill", "알고 먹기")
    accent = spec.get("accent", "#FFB23E")
    slides = spec["slides"]
    body = "".join(slide(B, spec, s, n, len(slides), name, pill) for n, s in enumerate(slides, 1))
    css = CSS.replace("FONT_DIR", (HERE / "fonts").as_uri())
    page = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body style="--ac:{accent}">{body}<script>{JS}</script></body></html>')
    return page, len(slides)
