/*
 * deck.js — a tiny runtime for HTML slide decks. No dependencies, no build step.
 *
 *   <script src="deck.js"></script>
 *   <slide-deck width="1920" height="1080">
 *     <section data-label="Title">…</section>
 *     <section data-label="The point">…</section>
 *   </slide-deck>
 *   <script type="application/json" id="speaker-notes">["notes for slide 1", "…"]</script>
 *
 * - Each <section> is one slide, laid out as a width×height box (default 1920×1080).
 *   Slides stay direct light-DOM children, so page CSS like `slide-deck > section { … }` applies.
 * - The deck scales to fit the window, letterboxed. Add `noscale` to render at authored
 *   size with no transform (exporters that read geometry from the DOM set this).
 * - Keys: ←/→, PageUp/PageDown, Space (next), Home/End. Touch: tap left/right half.
 *   N toggles the speaker-notes overlay.
 * - #N in the URL (1-based) picks the slide on load and on hashchange; moving updates it.
 * - Posts {slideIndexChanged: n} (0-based) to window.parent on every change.
 * - Print: every slide is its own page at the design size, so Chrome's
 *   --print-to-pdf gives one page per slide.
 * - window.slideDeck = { count, current, go(n) }   (n is 1-based)
 */
(function () {
  "use strict";

  var STYLE_ID = "slide-deck-runtime-style";

  function injectStyle(w, h) {
    var old = document.getElementById(STYLE_ID);
    if (old) old.remove();
    var css =
      /* :where() keeps specificity at zero, so any page rule wins. */
      ":where(html, body) { margin: 0; height: 100%; }" +
      ":where(body) { overflow: hidden; background: #000; }" +
      ":where(slide-deck) { display: block; position: fixed; left: 50%; top: 50%;" +
      "  width: " + w + "px; height: " + h + "px; transform-origin: 0 0; overflow: hidden; }" +
      ":where(slide-deck[noscale]) { position: relative; left: 0; top: 0; }" +
      ":where(slide-deck > section) { position: absolute; inset: 0; width: 100%; height: 100%; box-sizing: border-box; }" +
      ":where(slide-deck > section:not([data-active])) { visibility: hidden; }" +
      ".slide-deck-notes { position: fixed; left: 0; right: 0; bottom: 0; max-height: 40vh; overflow: auto;" +
      "  margin: 0; padding: 16px 24px; background: rgba(0,0,0,.85); color: #fff; font: 15px/1.5 system-ui, sans-serif;" +
      "  white-space: pre-wrap; z-index: 2147483647; display: none; }" +
      ".slide-deck-notes[data-open] { display: block; }" +
      "@page { size: " + w + "px " + h + "px; margin: 0; }" +
      "@media print {" +
      "  html, body { height: auto !important; overflow: visible !important; }" +
      "  slide-deck { position: static !important; transform: none !important; width: " + w + "px !important;" +
      "    height: auto !important; overflow: visible !important; }" +
      "  slide-deck > section { position: relative !important; inset: auto !important; visibility: visible !important;" +
      "    width: " + w + "px !important; height: " + h + "px !important; overflow: hidden !important;" +
      "    break-after: page; page-break-after: always; }" +
      "  slide-deck > section:last-of-type { break-after: auto; page-break-after: auto; }" +
      "  .slide-deck-notes { display: none !important; }" +
      "}";
    var s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = css;
    document.head.insertBefore(s, document.head.firstChild);
  }

  function readNotes() {
    var el = document.getElementById("speaker-notes");
    if (!el) return [];
    try {
      var v = JSON.parse(el.textContent);
      return Array.isArray(v) ? v : [];
    } catch (e) {
      return [];
    }
  }

  function hashSlide() {
    var m = /^#(\d+)$/.exec(location.hash || "");
    return m ? parseInt(m[1], 10) : null;
  }

  class SlideDeck extends HTMLElement {
    connectedCallback() {
      if (this._connected) return;
      this._connected = true;
      // The element upgrades as soon as the parser meets the tag, before its children exist.
      // Set up once the document has been parsed, so every <section> is there.
      var self = this;
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { self.setup(); }, { once: true });
      } else {
        this.setup();
      }
    }

    setup() {
      this.designW = parseInt(this.getAttribute("width"), 10) || 1920;
      this.designH = parseInt(this.getAttribute("height"), 10) || 1080;
      injectStyle(this.designW, this.designH);

      this.slides = Array.prototype.filter.call(this.children, function (c) {
        return c.tagName === "SECTION";
      });
      this.notes = readNotes();
      this.notesEl = document.createElement("pre");
      this.notesEl.className = "slide-deck-notes";
      document.body.appendChild(this.notesEl);

      this.index = -1;
      var self = this;
      window.slideDeck = {
        get count() { return self.slides.length; },
        get current() { return self.index + 1; },
        go: function (n) { self.go(n); },
      };

      this._onResize = function () { self.fit(); };
      this._onKey = function (e) { self.key(e); };
      this._onHash = function () { var n = hashSlide(); if (n) self.show(n - 1, false); };
      this._onTap = function (e) { self.tap(e); };
      window.addEventListener("resize", this._onResize);
      document.addEventListener("keydown", this._onKey);
      window.addEventListener("hashchange", this._onHash);
      this.addEventListener("click", this._onTap);

      this.fit();
      var start = hashSlide();
      this.show(start ? start - 1 : 0, false);
    }

    disconnectedCallback() {
      window.removeEventListener("resize", this._onResize);
      document.removeEventListener("keydown", this._onKey);
      window.removeEventListener("hashchange", this._onHash);
    }

    fit() {
      if (this.hasAttribute("noscale")) {
        this.style.transform = "none";
        return;
      }
      var k = Math.min(window.innerWidth / this.designW, window.innerHeight / this.designH);
      this.style.transform =
        "scale(" + k + ") translate(" + (-this.designW / 2) + "px, " + (-this.designH / 2) + "px)";
    }

    show(i, updateHash) {
      if (!this.slides.length) return;
      i = Math.max(0, Math.min(this.slides.length - 1, i));
      if (i === this.index) return;
      if (this.index >= 0) this.slides[this.index].removeAttribute("data-active");
      this.index = i;
      this.slides[i].setAttribute("data-active", "");
      this.notesEl.textContent = this.notes[i] || "";
      if (updateHash !== false && location.hash !== "#" + (i + 1)) {
        history.replaceState(null, "", "#" + (i + 1));
      }
      try {
        if (window.parent && window.parent !== window) window.parent.postMessage({ slideIndexChanged: i }, "*");
      } catch (e) { /* cross-origin parent: nothing to tell */ }
      this.dispatchEvent(new CustomEvent("slidechange", { detail: { index: i, slide: i + 1 } }));
    }

    go(n) { this.show(n - 1, true); }
    next() { this.show(this.index + 1, true); }
    prev() { this.show(this.index - 1, true); }

    key(e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      switch (e.key) {
        case "ArrowRight": case "PageDown": case " ": case "Spacebar":
          this.next(); break;
        case "ArrowLeft": case "PageUp":
          this.prev(); break;
        case "Home":
          this.show(0, true); break;
        case "End":
          this.show(this.slides.length - 1, true); break;
        case "n": case "N":
          if (this.notesEl.hasAttribute("data-open")) this.notesEl.removeAttribute("data-open");
          else this.notesEl.setAttribute("data-open", "");
          break;
        default:
          return;
      }
      e.preventDefault();
    }

    tap(e) {
      // Links, buttons and form controls inside a slide keep their click.
      if (e.target.closest && e.target.closest("a, button, input, textarea, select, label, [data-no-nav]")) return;
      // Mouse clicks don't navigate on desktop; taps on touch screens do.
      if (!matchMedia("(pointer: coarse)").matches) return;
      if (e.clientX < window.innerWidth / 2) this.prev();
      else this.next();
    }
  }

  if (!customElements.get("slide-deck")) customElements.define("slide-deck", SlideDeck);
})();
