// deck-builder measure: walk the one visible slide and describe it as a shape model an
// editable PowerPoint can reproduce — boxes, text, images — in paint order, plus the
// effects on each element that the model cannot carry (the "why" for the fidelity report).
// Injected by stage.py; writes JSON into <pre id="__model"> so `chrome --dump-dom` returns it.
(function () {
  const SLIDE_W = 1920, SLIDE_H = 1080;
  const INLINE = new Set(["SPAN", "B", "STRONG", "I", "EM", "U", "A", "SMALL", "SUP", "SUB", "MARK", "CODE", "BR", "S", "ABBR", "KBD", "Q", "TIME", "LABEL"]);

  function rgba(c) {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(c || "");
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  }
  function visible(cs) { return cs.display !== "none" && cs.visibility !== "hidden" && parseFloat(cs.opacity) > 0.01; }
  function rectOf(el, origin) {
    const r = el.getBoundingClientRect();
    return { x: r.left - origin.left, y: r.top - origin.top, w: r.width, h: r.height };
  }
  function onSlide(r) { return r.w > 0.5 && r.h > 0.5 && r.x < SLIDE_W && r.y < SLIDE_H && r.x + r.w > 0 && r.y + r.h > 0; }
  function firstFamily(ff) { return (ff || "").split(",")[0].trim().replace(/^["']|["']$/g, ""); }

  // Text colour on a gradient-clipped heading is transparent; the model uses the first gradient stop instead.
  function textColor(cs) {
    const clip = cs.webkitBackgroundClip || cs.backgroundClip;
    const fill = rgba(cs.webkitTextFillColor);
    if (clip === "text" || (fill && fill.a === 0)) {
      const stop = /rgba?\([^)]*\)|#[0-9a-f]{3,8}/i.exec(cs.backgroundImage || "");
      return stop ? rgba(stop[0]) || { r: 255, g: 255, b: 255, a: 1 } : rgba(cs.color);
    }
    return rgba(cs.color);
  }

  function effectsOf(el, cs, isText) {
    const fx = [];
    if (isText && cs.textShadow && cs.textShadow !== "none") fx.push("glowing or shadowed text");
    if (isText && ((cs.webkitBackgroundClip || cs.backgroundClip) === "text")) fx.push("gradient-filled text");
    if (cs.filter && cs.filter !== "none") fx.push("filter (" + cs.filter.split("(")[0] + ")");
    if (cs.backdropFilter && cs.backdropFilter !== "none") fx.push("backdrop blur");
    if (cs.mixBlendMode && cs.mixBlendMode !== "normal") fx.push("blend mode " + cs.mixBlendMode);
    if ((cs.maskImage && cs.maskImage !== "none") || (cs.webkitMaskImage && cs.webkitMaskImage !== "none")) fx.push("mask");
    if (cs.boxShadow && cs.boxShadow !== "none") fx.push("shadow or glow on a shape");
    if (cs.transform && cs.transform !== "none" && !/^matrix\(1, 0, 0, 1,/.test(cs.transform)) fx.push("rotated, skewed or scaled");
    if (cs.clipPath && cs.clipPath !== "none") fx.push("clip path");
    for (const p of ["::before", "::after"]) {
      const ps = getComputedStyle(el, p);
      if (ps.content && ps.content !== "none" && ps.content !== "normal") {
        const bg = rgba(ps.backgroundColor);
        if (ps.content !== '""' || (bg && bg.a > 0) || ps.backgroundImage !== "none" || ps.borderTopWidth !== "0px")
          fx.push("CSS " + p + " decoration" + (ps.content !== '""' ? " " + ps.content.slice(0, 12) : ""));
      }
    }
    return fx;
  }

  // A CSS gradient as the editable copy can draw it: one layer, linear or radial, every stop as a
  // fraction, a radial's centre as fractions of the box. What doesn't carry over is listed in
  // `approx`, each with `visible` saying whether the preview draws the simplification too (so a
  // difference it causes can be explained by it) or only the exported file does.
  function gradientOf(bgImage) {
    if (!bgImage || bgImage === "none") return null;
    const layers = bgImage.split(/,\s*(?=(?:repeating-)?(?:linear|radial|conic)-gradient\(|url\()/);
    const first = layers.find(l => /^(repeating-)?(linear|radial)-gradient\(/.test(l.trim()));
    if (!first) return null;
    const approx = [];
    const note = (what, visible = true) => { if (!approx.some(a => a.what === what)) approx.push({ what, visible }); };
    if (layers.length > 1) note(layers.length + " background layers, only the first gradient kept");
    const m = /^(repeating-)?(linear|radial)-gradient\((.*)\)\s*$/.exec(first.trim());
    if (!m) return null;
    if (m[1]) note("repeating gradient drawn once");
    const kind = m[2];
    const parts = m[3].split(/,(?![^(]*\))/).map(s => s.trim());
    let angle = 180, shape = "ellipse", at = { x: 0.5, y: 0.5 };
    if (kind === "linear" && /deg|^to /.test(parts[0])) {
      const a = parts.shift();
      const map = { "to top": 0, "to right": 90, "to bottom": 180, "to left": 270, "to top right": 45, "to bottom right": 135, "to bottom left": 225, "to top left": 315 };
      angle = /deg/.test(a) ? parseFloat(a) : (map[a] ?? 180);
    } else if (kind === "radial") {
      if (!/rgba?\(/.test(parts[0])) {
        const [shapeSize, pos] = parts.shift().split(/\bat\b/).map(s => (s || "").trim());
        if (/circle/.test(shapeSize) || /^[\d.]+px$/.test(shapeSize)) shape = "circle";
        const size = shapeSize.replace(/circle|ellipse/, "").trim();
        if (size && size !== "farthest-corner") { note("radial size " + size + " drawn as farthest-corner"); }
        if (pos) {
          const kx = { left: 0, center: 0.5, right: 1 }, ky = { top: 0, center: 0.5, bottom: 1 };
          const toks = pos.split(/\s+/);
          if (toks.every(t => /%$/.test(t))) { at = { x: parseFloat(toks[0]) / 100, y: toks[1] ? parseFloat(toks[1]) / 100 : 0.5 }; }
          else if (toks.every(t => t in kx || t in ky)) {
            for (const t of toks) { if (t === "left" || t === "right") at.x = kx[t]; else if (t === "top" || t === "bottom") at.y = ky[t]; }
          } else note("radial centre " + pos + " drawn at the middle");
        }
      }
      note("radial gradient: spread is close, not exact, in PowerPoint and Google Slides", false);
    }
    const colors = parts.map(p => {
      const c = /rgba?\([^)]*\)/.exec(p);
      if (!c) { if (/^[\d.]+%$/.test(p)) note("colour hint " + p + " dropped"); return null; }
      const rest = p.replace(c[0], "").trim();
      const pct = /(-?[\d.]+)%\s*$/.exec(rest);
      if (!pct && rest) note("stop position " + rest + " placed by interpolation");
      return { c: rgba(c[0]), p: pct ? +pct[1] / 100 : null };
    }).filter(Boolean);
    if (colors.length < 2) return null;
    // CSS: a missing first/last position is 0/1, a missing one between is spaced evenly between its
    // neighbours, and a position smaller than the one before it is raised to it
    if (colors[0].p === null) colors[0].p = 0;
    if (colors[colors.length - 1].p === null) colors[colors.length - 1].p = 1;
    for (let i = 1; i < colors.length; i++) {
      if (colors[i].p !== null) continue;
      let j = i; while (colors[j].p === null) j++;
      for (let k = i; k < j; k++) colors[k].p = colors[i - 1].p + (colors[j].p - colors[i - 1].p) * (k - i + 1) / (j - i + 1);
    }
    for (let i = 1; i < colors.length; i++) colors[i].p = Math.max(colors[i].p, colors[i - 1].p);
    return { kind, angle, shape, at, stops: colors, approx };
  }

  // A text block: an element with at least one non-empty own text node whose element
  // children are all inline. Its runs keep per-span colour/weight/style.
  // An inline tag only counts as a text run if it is laid out inline and paints no box of its
  // own. A <span class="bar"> with a gradient, or an inline-block chip, is a shape to measure.
  function plainInline(n) {
    if (!INLINE.has(n.tagName)) return false;
    if (n.tagName === "BR") return true;
    const cs = getComputedStyle(n);
    if (cs.display !== "inline") return false;
    const bg = rgba(cs.backgroundColor);
    if ((bg && bg.a > 0) || (cs.backgroundImage && cs.backgroundImage !== "none")) return false;
    if ((parseFloat(cs.borderTopWidth) || 0) > 0 && cs.borderTopStyle !== "none") return false;
    return true;
  }

  function isTextBlock(el) {
    let hasText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) hasText = true;
      else if (n.nodeType === 1 && !plainInline(n)) return false;
    }
    if (!hasText) for (const n of el.childNodes) if (n.nodeType === 1 && plainInline(n) && n.textContent.trim()) hasText = true;
    return hasText;
  }

  function runsOf(el, inherited, tt) {
    const runs = [];
    const walk = (node, cs) => {
      for (const n of node.childNodes) {
        if (n.nodeType === 3) {
          // pre, pre-wrap and pre-line keep their newlines (a code block, a file tree); pre and pre-wrap keep spaces too
          const ws = cs.whiteSpace || "normal";
          const keepLines = /^pre/.test(ws) || ws === "break-spaces";
          const keepSpaces = ws === "pre" || ws === "pre-wrap" || ws === "break-spaces";
          const pieces = keepLines ? n.textContent.split("\n") : [n.textContent];
          pieces.forEach((piece, pi) => {
            if (pi > 0) runs.push({ t: "\n", br: true, pre: true });
            let t = keepSpaces ? piece.replace(/\t/g, "    ") : piece.replace(/\s+/g, " ");
            if (!t) return;
            if (tt === "uppercase") t = t.toUpperCase(); else if (tt === "lowercase") t = t.toLowerCase();
            runs.push({ t, pre: keepSpaces, color: textColor(cs), bold: parseInt(cs.fontWeight) >= 600, weight: parseInt(cs.fontWeight),
                        italic: cs.fontStyle === "italic", underline: /underline/.test(cs.textDecorationLine), family: firstFamily(cs.fontFamily),
                        size: parseFloat(cs.fontSize), spacing: cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing) || 0 });
          });
        } else if (n.nodeType === 1) {
          if (n.tagName === "BR") { runs.push({ t: "\n", br: true }); continue; }
          const ccs = getComputedStyle(n);
          if (!visible(ccs)) continue;
          walk(n, ccs);
        }
      }
    };
    walk(el, inherited);
    // trim the whitespace HTML indentation leaves at the edges of lines (not inside preformatted text)
    for (let i = 0; i < runs.length; i++) {
      if (runs[i].br || runs[i].pre) continue;
      if (i === 0 || runs[i - 1].br) runs[i].t = runs[i].t.replace(/^ /, "");
      if (i === runs.length - 1 || runs[i + 1].br) runs[i].t = runs[i].t.replace(/ $/, "");
    }
    // a preformatted block that starts or ends with a newline in the source: drop those empty edge lines
    while (runs.length && runs[0].br && runs[0].pre) runs.shift();
    while (runs.length && runs[runs.length - 1].br && runs[runs.length - 1].pre) runs.pop();
    return runs.filter(r => r.br || r.t);
  }

  // The line height the text is actually laid out with. For "normal" that depends on the
  // font, so read the pitch between the first two lines when there are two; 1.2× is only the fallback.
  // Client rects grouped into the lines they sit on. A smaller run on the same line ("FRI 7" at 60px,
  // then "pm" at 30px) has a lower top than the text beside it, so counting distinct tops made it two
  // lines 30px apart, and the export squeezed the label upward. A rect joins a line when its vertical
  // middle falls inside that line's span.
  function visualLines(rects) {
    const lines = [];
    for (const q of [...rects].filter(q => q.width > 0 || q.height > 0).sort((a, b) => a.top - b.top)) {
      const mid = q.top + q.height / 2;
      const line = lines.find(l => mid >= l.top && mid <= l.bottom);
      if (line) { line.top = Math.min(line.top, q.top); line.bottom = Math.max(line.bottom, q.bottom); }
      else lines.push({ top: q.top, bottom: q.bottom });
    }
    return lines.sort((a, b) => a.top - b.top);
  }

  function lineHeightOf(cs, rects) {
    if (cs.lineHeight !== "normal") return parseFloat(cs.lineHeight);
    const lines = visualLines(rects);
    if (lines.length >= 2) return lines[1].top - lines[0].top;
    if (lines.length) return lines[0].bottom - lines[0].top;
    return parseFloat(cs.fontSize) * 1.2;
  }

  // The font's own "single" line height at this size, which is what PowerPoint and Google Slides
  // multiply when line spacing is a percentage. Google Slides ignores spacing in exact points.
  const normalCache = new Map();
  let measureCtx = null;   // a canvas context for measuring list markers
  function normalLineHeight(cs) {
    const key = [cs.fontFamily, cs.fontSize, cs.fontWeight, cs.fontStyle].join("|");
    if (normalCache.has(key)) return normalCache.get(key);
    const probe = document.createElement("div");
    probe.textContent = "Hg";
    Object.assign(probe.style, { position: "absolute", visibility: "hidden", whiteSpace: "nowrap", lineHeight: "normal",
                                 fontFamily: cs.fontFamily, fontSize: cs.fontSize, fontWeight: cs.fontWeight, fontStyle: cs.fontStyle });
    document.body.appendChild(probe);
    const h = probe.getBoundingClientRect().height;
    probe.remove();
    normalCache.set(key, h);
    return h;
  }

  function lineCount(el, cs) {
    const range = document.createRange(); range.selectNodeContents(el);
    return Math.max(1, visualLines(range.getClientRects()).length);
  }

  function run() {
    const host = document.querySelector("slide-deck, deck-stage");
    const slide = host ? [...host.children].find(s => s.tagName === "SECTION" && getComputedStyle(s).display !== "none")
                       : document.querySelector("section");
    // approximations: what the editable copy draws differently on purpose (a gradient simplified),
    // as opposed to `unsupported`, what it can't draw at all
    const out = { items: [], unsupported: [], approximations: [], background: null };
    if (!slide) { document.getElementById("__model").textContent = JSON.stringify({ error: "no visible slide" }); return; }
    const origin = slide.getBoundingClientRect();
    const approximate = (label, r, g, background) => {
      for (const a of (g && g.approx) || [])
        out.approximations.push({ label, x: r.x, y: r.y, w: r.w, h: r.h, effects: ["gradient approximated: " + a.what], visible: a.visible, background });
    };

    // slide background: the section's own fill, else the body's, else the html's
    for (const el of [slide, document.body, document.documentElement]) {
      const cs = getComputedStyle(el); const bg = rgba(cs.backgroundColor); const g = gradientOf(cs.backgroundImage);
      if (g || (bg && bg.a > 0)) { out.background = { fill: bg && bg.a > 0 ? bg : null, gradient: g }; if (el === slide) break; if (bg && bg.a === 1) break; }
    }
    if (out.background) approximate("slide background", { x: 0, y: 0, w: SLIDE_W, h: SLIDE_H }, out.background.gradient, true);

    const visit = (el, depth, alpha = 1) => {
      const cs = getComputedStyle(el);
      if (!visible(cs)) return;
      const op = alpha * parseFloat(cs.opacity);
      const r = rectOf(el, origin);
      const tag = el.tagName;
      const textBlock = isTextBlock(el);
      const fx = el === slide ? [] : effectsOf(el, cs, textBlock);
      const label = (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 48) || (typeof el.className === "string" ? "." + el.className.split(" ")[0] : tag.toLowerCase());
      if (fx.length && onSlide(r)) out.unsupported.push({ label, x: r.x, y: r.y, w: r.w, h: r.h, effects: fx });

      if (el !== slide && onSlide(r)) {
        const bg = rgba(cs.backgroundColor); const g = gradientOf(cs.backgroundImage);
        const bw = parseFloat(cs.borderTopWidth) || 0; const bc = rgba(cs.borderTopColor);
        const hasBorder = bw > 0 && cs.borderTopStyle !== "none" && bc && bc.a > 0;
        if ((bg && bg.a > 0) || g || hasBorder) {
          approximate(label, r, g, false);
          out.items.push({ type: "box", x: r.x, y: r.y, w: r.w, h: r.h, fill: bg && bg.a > 0 ? bg : null, gradient: g,
                           border: hasBorder ? { w: bw, c: bc, dash: cs.borderTopStyle === "dashed" } : null,
                           radius: parseFloat(cs.borderTopLeftRadius) || 0, opacity: op });
        }
        if (tag === "IMG" && el.currentSrc) {
          out.items.push({ type: "image", x: r.x, y: r.y, w: r.w, h: r.h, src: el.currentSrc, fit: cs.objectFit, nw: el.naturalWidth, nh: el.naturalHeight, opacity: op });
          return;
        }
        if (tag === "svg" || tag === "CANVAS" || tag === "VIDEO" || tag === "IFRAME") {
          out.unsupported.push({ label: tag.toLowerCase(), x: r.x, y: r.y, w: r.w, h: r.h, effects: [tag.toLowerCase() + " element"] });
          out.items.push({ type: "raster", x: r.x, y: r.y, w: r.w, h: r.h, why: tag.toLowerCase() });
          return;
        }
        if (textBlock) {
          const pl = parseFloat(cs.paddingLeft) || 0, pr = parseFloat(cs.paddingRight) || 0, pt = parseFloat(cs.paddingTop) || 0, pb = parseFloat(cs.paddingBottom) || 0;
          const range = document.createRange(); range.selectNodeContents(el); const tr = range.getBoundingClientRect();
          const lines = lineCount(el, cs);
          const lh = lineHeightOf(cs, [...range.getClientRects()]);
          const runs = runsOf(el, cs, cs.textTransform);
          // wraps only if the browser broke a line the markup didn't: three <br>-separated lines are three paragraphs, not wrapping
          const paragraphs = 1 + runs.filter(q => q.br).length;
          // A list item's bullet or number is drawn by the browser (::marker) and isn't in the DOM, so it
          // would vanish from the editable copy. Carry it as its own text, ending where the content starts.
          if (cs.display === "list-item" && cs.listStylePosition === "outside" && cs.listStyleType !== "none") {
            const ms = getComputedStyle(el, "::marker");
            const glyph = { disc: "•", circle: "◦", square: "▪" }[cs.listStyleType];
            let t = glyph;
            if (!t && /decimal/.test(cs.listStyleType)) {
              const siblings = [...el.parentElement.children].filter(s => getComputedStyle(s).display === "list-item");
              t = ((el.parentElement.start || 1) + siblings.indexOf(el)) + ".";
            }
            if (t) {
              const size = parseFloat(ms.fontSize) || parseFloat(cs.fontSize);
              const ctx = (measureCtx ||= document.createElement("canvas").getContext("2d"));
              ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${size}px ${cs.fontFamily}`;
              const mw = ctx.measureText(t + " ").width;
              // Chrome doesn't expose the marker's box, so its position is estimated; quiet means it's
              // only named when a difference actually lands on it
              out.approximations.push({ label: "list marker " + t, x: r.x + pl - mw, y: r.y + pt, w: mw, h: lh,
                                        effects: ["list marker position estimated"], visible: true, background: false, quiet: true });
              out.items.push({ type: "text", x: r.x + pl - mw, y: r.y + pt, w: mw, h: lh, tx: r.x + pl - mw, ty: r.y + pt, tw: mw, th: lh,
                               align: "left", valign: "top", lineHeight: lh, normalLH: normalLineHeight(cs), fontSize: size, lines: 1, wrap: false,
                               runs: [{ t: t + " ", pre: true, color: rgba(ms.color) || textColor(cs), bold: parseInt(cs.fontWeight) >= 600, weight: parseInt(cs.fontWeight),
                                        italic: cs.fontStyle === "italic", underline: false, family: firstFamily(cs.fontFamily), size, spacing: 0 }],
                               opacity: op });
            } else {
              out.unsupported.push({ label: "list marker", x: r.x + pl - 40, y: r.y + pt, w: 40, h: lh, effects: ["list marker " + cs.listStyleType] });
            }
          }
          out.items.push({ type: "text", x: r.x + pl, y: r.y + pt, w: r.w - pl - pr, h: r.h - pt - pb,
                           tx: tr.left - origin.left, ty: tr.top - origin.top, tw: tr.width, th: tr.height,
                           align: cs.textAlign === "start" ? "left" : cs.textAlign === "end" ? "right" : cs.textAlign,
                           valign: cs.display.includes("flex") ? ({ center: "middle", "flex-end": "bottom", end: "bottom" }[cs.alignItems] || "top") : "top",
                           lineHeight: lh, normalLH: normalLineHeight(cs), fontSize: parseFloat(cs.fontSize), lines, wrap: lines > paragraphs,
                           runs, opacity: op });
          return;   // inline children are carried as runs
        }
      }
      // A container with both block children and loose text ("<div class=k>Icon</div>a brief"):
      // the loose text nodes are text too, measured one node at a time.
      for (const c of el.childNodes) {
        if (c.nodeType === 3 && c.textContent.trim() && el !== slide || (c.nodeType === 3 && c.textContent.trim() && el === slide)) {
          const range = document.createRange(); range.selectNodeContents(c); const tr = range.getBoundingClientRect();
          const rr = { x: tr.left - origin.left, y: tr.top - origin.top, w: tr.width, h: tr.height };
          if (!onSlide(rr)) continue;
          const rects = [...range.getClientRects()];
          const tops = new Set(rects.map(q => Math.round(q.top)));
          let t = c.textContent.replace(/\s+/g, " ").trim();
          if (cs.textTransform === "uppercase") t = t.toUpperCase();
          const lh = lineHeightOf(cs, rects);
          // Horizontally, the text box is the parent's content box, not the glyphs' tight width:
          // a box exactly as wide as the text rewraps at the first difference in font metrics.
          // Vertically, the range rect is the glyph box; the line box it sits in is taller by the leading.
          const pr = rectOf(el, origin);
          const pl = parseFloat(cs.paddingLeft) || 0, prr = parseFloat(cs.paddingRight) || 0;
          const bx = pr.x + pl, bw = Math.max(rr.w, pr.w - pl - prr);
          const glyphH = rects.length ? rects[0].height : rr.h;
          const lines = Math.max(1, tops.size);
          const by = rr.y - Math.max(0, (lh - glyphH) / 2);
          out.items.push({ type: "text", x: bx, y: by, w: bw, h: lines * lh, tx: rr.x, ty: rr.y, tw: rr.w, th: rr.h,
                           align: cs.textAlign === "start" ? "left" : cs.textAlign === "end" ? "right" : cs.textAlign,
                           valign: "top", lineHeight: lh, normalLH: normalLineHeight(cs), fontSize: parseFloat(cs.fontSize), lines: Math.max(1, tops.size), wrap: tops.size > 1,
                           runs: [{ t, color: textColor(cs), bold: parseInt(cs.fontWeight) >= 600, weight: parseInt(cs.fontWeight), italic: cs.fontStyle === "italic",
                                    underline: false, family: firstFamily(cs.fontFamily), size: parseFloat(cs.fontSize),
                                    spacing: cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing) || 0 }],
                           opacity: op });
        } else if (c.nodeType === 1) visit(c, depth + 1, op);
      }
    };
    visit(slide, 0);
    document.getElementById("__model").textContent = JSON.stringify(out);
  }

  const start = () => setTimeout(run, 600);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start); else window.addEventListener("load", start);
})();
