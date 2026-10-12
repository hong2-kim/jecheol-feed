// 장면마다 data-at(시작 초), data-dur(길이 초)를 읽어, 원하는 시각의 화면을 그대로 만들어요.
// 실시간으로 재생하지 않고 한 장씩 찍기 때문에 움직임이 끊기지 않아요.
(() => {
  // data-split 이 붙은 글은 글자 하나씩 차례로 나타나요.
  document.querySelectorAll("[data-split]").forEach((el) => {
    const step = parseFloat(el.dataset.split) || 0.05;
    const base = parseFloat(el.dataset.from || "0");
    let i = 0;
    const wrap = (node) => {
      [...node.childNodes].forEach((child) => {
        if (child.nodeType === 3) {
          const frag = document.createDocumentFragment();
          [...child.textContent].forEach((ch) => {
            if (ch === " ") { frag.append(" "); return; }
            const s = document.createElement("span");
            s.textContent = ch;
            s.className = "a pop";
            s.style.display = "inline-block";
            s.style.setProperty("--dl", (base + i++ * step).toFixed(3) + "s");
            s.style.setProperty("--d", ".28s");
            frag.append(s);
          });
          child.replaceWith(frag);
        } else if (child.nodeType === 1 && child.tagName !== "BR") wrap(child);
      });
    };
    wrap(el);
  });

  const scenes = [...document.querySelectorAll(".scene")].map((el, i) => {
    el.style.zIndex = i + 1;
    return { el, at: parseFloat(el.dataset.at), dur: parseFloat(el.dataset.dur), out: parseFloat(el.dataset.out || "0.5") };
  });
  window.DURATION = Math.max(...scenes.map((s) => s.at + s.dur));

  // 동영상 장면은 낱장 사진을 시각에 맞춰 바꿔 끼워요.
  const pad = (n) => String(n).padStart(5, "0");
  window.seek = (t) => {
    const waits = [];
    for (const s of scenes) {
      for (const im of s.el.querySelectorAll("img.vf")) {
        const local = Math.max(0, t - s.at);
        const k = Math.min(parseInt(im.dataset.n, 10), Math.floor(local * parseFloat(im.dataset.fps)) + 1);
        const src = `${im.dataset.frames}/${pad(k)}.jpg`;
        if (t >= s.at - 0.1 && t < s.at + s.dur + s.out && im.dataset.cur !== src) {
          im.dataset.cur = src;
          im.src = src;
          waits.push(im.decode().catch(() => {}));
        }
      }
    }
    for (const s of scenes) {
      const local = t - s.at;
      const on = local >= 0 && local < s.dur + s.out;
      s.el.style.visibility = on ? "visible" : "hidden";
      const ms = Math.max(0, local) * 1000;
      for (const anim of s.el.getAnimations({ subtree: true })) {
        anim.pause();
        anim.currentTime = ms;
      }
    }
    return Promise.all(waits);
  };
  window.seek(0);
})();
