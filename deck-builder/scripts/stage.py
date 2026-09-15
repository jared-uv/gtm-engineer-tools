#!/usr/bin/env python3
"""The stage: a local server that shows one slide of a deck by itself, at 1920×1080,
with no slide runtime, in one of three modes. Everything that renders or measures a
slide goes through here, so it works the same for any runtime (this plugin's
<slide-deck>, or a <deck-stage> from a design tool's export).

    /__stage/slide?file=<deck.html>&n=<N>&mode=raw       the slide as designed
    /__stage/slide?file=<deck.html>&n=<N>&mode=measure   the same, plus measure.js writing the shape model
    /__stage/slide?file=<deck.html>&n=<N>&mode=effects   only what the shape model can't carry, on transparent
    /__stage/preview/<id>                                an HTML page registered with add_preview()
    anything else                                        a static file from the deck folder

The runtime script is removed and the slide is pinned by CSS: the runtime's job is
navigation and scaling, and both get in the way of measuring one slide at authored size.
"""
import http.server, re, socketserver, threading, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIMES = ("deck-stage.js", "deck.js")
W, H = 1920, 1080

PIN = """
html, body { margin:0 !important; padding:0 !important; width:%(w)dpx !important; height:%(h)dpx !important;
             min-height:0 !important; overflow:hidden !important; }
slide-deck, deck-stage { display:block !important; position:relative !important; width:%(w)dpx !important;
             height:%(h)dpx !important; overflow:hidden !important; transform:none !important; margin:0 !important; }
slide-deck > section:not(:nth-of-type(%(n)d)), deck-stage > section:not(:nth-of-type(%(n)d)) { display:none !important; }
slide-deck > section:nth-of-type(%(n)d), deck-stage > section:nth-of-type(%(n)d) {
             position:absolute !important; left:0 !important; top:0 !important; width:%(w)dpx !important;
             height:%(h)dpx !important; box-sizing:border-box !important; overflow:hidden !important;
             visibility:visible !important; opacity:1 !important; transform:none !important; }
"""

# Only what an editable rebuild loses stays visible: text shadows and glows, shadows on
# shapes, CSS ::before/::after decorations. Text, fills, borders and images go transparent.
EFFECTS = """
html, body { background: transparent !important; }
slide-deck > section, deck-stage > section, section * {
  color: transparent !important; -webkit-text-fill-color: transparent !important;
  background-color: transparent !important; background-image: none !important;
  border-color: transparent !important; outline-color: transparent !important; }
section img, section svg, section video, section canvas, section picture { visibility: hidden !important; }
"""

# A ::before/::after decoration inherits its text colour from its element, which EFFECTS just
# made transparent, so the × on a "not" badge vanished and left an empty pink circle. With the
# effects styles briefly off, read each decoration's own colour, then pin it back on the pseudo-element.
PSEUDO_COLORS = """<script id="__stage_fx_pseudo">(function () {
  var styles = ["__stage_effects", "__stage_effects_late"].map(function (id) { return document.getElementById(id); }).filter(Boolean);
  styles.forEach(function (s) { s.sheet.disabled = true; });
  var rules = [], n = 0;
  document.querySelectorAll("section, section *").forEach(function (el) {
    ["::before", "::after"].forEach(function (p) {
      var ps = getComputedStyle(el, p);
      if (!ps.content || ps.content === "none" || ps.content === "normal" || ps.content === '""') return;
      var id = el.getAttribute("data-stage-fx") || String(n++);
      el.setAttribute("data-stage-fx", id);
      rules.push('[data-stage-fx="' + id + '"]' + p + " { color: " + ps.color + " !important; -webkit-text-fill-color: " + (ps.webkitTextFillColor || ps.color) + " !important; }");
    });
  });
  styles.forEach(function (s) { s.sheet.disabled = false; });
  var st = document.createElement("style"); st.id = "__stage_fx_pseudo_colors"; st.textContent = rules.join("\\n");
  document.body.appendChild(st);
})();</script>"""

def transform(html, file_rel, n, mode, runtimes=RUNTIMES, w=W, h=H):
    names = "|".join(re.escape(r) for r in runtimes)
    html = re.sub(r"<script\b[^>]*\bsrc=[\"'][^\"']*(?:%s)(?:\?[^\"']*)?[\"'][^>]*>\s*</script>" % names, "", html, flags=re.I)
    base = "/" + (str(Path(file_rel).parent).strip("./") + "/" if str(Path(file_rel).parent) not in (".", "") else "")
    head = f'<base href="{base}"><style id="__stage_pin">{PIN % {"w": w, "h": h, "n": n}}</style>'
    if mode == "effects": head += f'<style id="__stage_effects">{EFFECTS}</style>'
    html = re.sub(r"<head([^>]*)>", lambda m: f"<head{m.group(1)}>{head}", html, count=1, flags=re.I) if re.search(r"<head", html, re.I) else head + html
    tail = ""
    if mode == "measure":
        tail = '<pre id="__model" style="display:none"></pre><script src="/__stage/measure.js"></script>'
    # the pin style must also win over author styles declared later in the body
    tail += f'<style id="__stage_pin_late">{PIN % {"w": w, "h": h, "n": n}}</style>'
    if mode == "effects": tail += f'<style id="__stage_effects_late">{EFFECTS}</style>' + PSEUDO_COLORS
    if re.search(r"</body>", html, re.I):
        html = re.sub(r"</body>", lambda m: tail + "</body>", html, count=1, flags=re.I)
    else:
        html += tail
    return html


class Stage:
    """Serve one deck folder. Use as a context manager: `with Stage(folder) as st: st.url(...)`."""

    def __init__(self, deck_dir, runtimes=RUNTIMES):
        self.dir = Path(deck_dir).resolve()
        self.runtimes = runtimes
        self.previews = {}
        stage = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k): super().__init__(*a, directory=str(stage.dir), **k)
            def log_message(self, *a): pass
            def _send(self, body, ctype="text/html; charset=utf-8"):
                b = body.encode() if isinstance(body, str) else body
                self.send_response(200); self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers()
                self.wfile.write(b)
            def do_GET(self):
                u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
                if u.path == "/__stage/slide":
                    rel = q["file"][0]; p = (stage.dir / rel).resolve()
                    if stage.dir not in p.parents and p != stage.dir: self.send_error(403); return
                    return self._send(transform(p.read_text(), rel, int(q["n"][0]), q.get("mode", ["raw"])[0], stage.runtimes))
                if u.path == "/__stage/measure.js":
                    return self._send((HERE / "measure.js").read_text(), "application/javascript")
                if u.path.startswith("/__stage/preview/"):
                    key = u.path.rsplit("/", 1)[-1]
                    if key in stage.previews: return self._send(stage.previews[key])
                    self.send_error(404); return
                return super().do_GET()

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *a): self.httpd.shutdown(); self.httpd.server_close()

    def url(self, file_rel, n, mode="raw"):
        return f"http://127.0.0.1:{self.port}/__stage/slide?" + urllib.parse.urlencode({"file": file_rel, "n": n, "mode": mode})

    def add_preview(self, key, html):
        self.previews[key] = html
        return f"http://127.0.0.1:{self.port}/__stage/preview/{key}"

    def abs_url(self, path):
        return f"http://127.0.0.1:{self.port}/" + str(path).lstrip("/")
