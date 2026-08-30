#!/usr/bin/env python3
"""Graft the stvideo recording contract onto an AI-Animation-Skill deck.

The deck HTML is produced by the AI-Animation-Skill workflow (model-authored,
Lucide icons, `.slide` sections, `.anim` staggered enter animations). This
script does NOT restyle anything — it only bolts on what the recorder needs:

  * record-mode CSS — fill the capture frame, hide nav chrome, reserve a
    bottom band so burned-in captions never sit on top of content
  * window.deckAPI — go / playSequence / getSlideCount / getDurationsSec /
    setRecordMode, matching the AI-Animation `.slide`+`.active`+`.anim.show`
    mechanism rather than replacing it

It is idempotent: re-running replaces the previous stvideo block in place.

Usage:
  inject_deck_api.py presentations/<slug>/index.html
  inject_deck_api.py index.html --aspect 9:16 --safe-band 320
  inject_deck_api.py index.html --check          # report only, no write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARKER_START = "<!-- stvideo:inject:start -->"
MARKER_END = "<!-- stvideo:inject:end -->"

# Animation class names seen across AI-Animation-Skill templates.
ANIM_SELECTOR = ".anim, .an, .anim-item, .animate-item"


def build_block(aspect: str, root_font: int, safe_band: int, default_dur: int) -> str:
    vertical = aspect.replace("x", ":") == "9:16"
    return f"""{MARKER_START}
<style>
/* stvideo record mode — layout only, never colours or typeface. */
body.stv-record {{
  width: 100vw !important; height: 100vh !important;
  overflow: hidden !important; margin: 0 !important;
}}
html.stv-font {{ font-size: {root_font}px !important; }}
body.stv-record .slide,
body.stv-record .slide-container {{
  width: 100vw !important; height: 100vh !important;
  max-width: none !important; border-radius: 0 !important;
}}
/* Reserve the caption band so centred content sits above the subtitles. */
body.stv-record .slide {{ padding-bottom: {safe_band}px !important; }}
/* Chrome that no template concept needs in a rendered video. */
body.stv-record .nav-btn, body.stv-record .prev-btn, body.stv-record .next-btn,
body.stv-record .slide-nav, body.stv-record .hint, body.stv-record .keyboard-hint,
body.stv-record .slide-indicator, body.stv-record .indicator,
body.stv-record .progress-container, body.stv-record .nav-hint {{
  display: none !important;
}}
</style>
<script>
(function () {{
  var ANIM = "{ANIM_SELECTOR}";
  var slides = Array.prototype.slice.call(document.querySelectorAll(".slide"));
  if (!slides.length) {{ console.error("stvideo: no .slide element found"); return; }}
  var timers = [], cur = -1;

  function clearTimers() {{ timers.forEach(clearTimeout); timers = []; }}

  function resetAnims(slide) {{
    // Clone each animated node so CSS transitions/keyframes replay on re-entry.
    slide.querySelectorAll(ANIM).forEach(function (el) {{
      el.classList.remove("show", "visible");
    }});
    slide.querySelectorAll(ANIM).forEach(function (el) {{
      var clone = el.cloneNode(true);
      if (el.parentNode) el.parentNode.replaceChild(clone, el);
    }});
  }}

  function showAnims(slide, slideMs) {{
    var items = Array.prototype.slice.call(slide.querySelectorAll(ANIM));
    var n = Math.max(items.length, 1);
    var step = Math.min(300, Math.max(80, (slideMs * 0.3) / n));
    items.forEach(function (el, i) {{
      timers.push(setTimeout(function () {{
        el.classList.add("show"); el.classList.add("visible");
      }}, 200 + i * step));
    }});
  }}

  function go(n, opts) {{
    opts = opts || {{}};
    clearTimers();
    var i = Math.max(0, Math.min(slides.length - 1, n));
    slides.forEach(function (s, k) {{ s.classList.toggle("active", k === i); }});
    slides.forEach(function (s, k) {{
      if (k !== i) s.querySelectorAll(ANIM).forEach(function (e) {{
        e.classList.remove("show", "visible");
      }});
    }});
    resetAnims(slides[i]);
    cur = i;
    var ms = opts.slideMs || (Number(slides[i].dataset.duration || {default_dur}) * 1000);
    showAnims(slides[i], ms);   // re-query: resetAnims replaced the nodes
  }}

  async function playSequence(durationsMs) {{
    for (var s = 0; s < slides.length; s++) {{
      var ms = (durationsMs && durationsMs[s])
        ? durationsMs[s]
        : Number(slides[s].dataset.duration || {default_dur}) * 1000;
      go(s, {{ slideMs: ms }});
      // Keep the clock inside the browser: Python round-trips per slide drift.
      await new Promise(function (r) {{ timers.push(setTimeout(r, ms)); }});
    }}
  }}

  function setRecordMode(on) {{
    document.body.classList.toggle("stv-record", !!on);
    document.documentElement.classList.toggle("stv-font", !!on);
    if (!on) return;
    // Hide fixed-position chrome (nav bars, hints) that lives outside slides.
    document.querySelectorAll("*").forEach(function (el) {{
      if (el === document.body || el === document.documentElement) return;
      if (el.closest && el.closest(".slide")) return;
      if (getComputedStyle(el).position === "fixed") el.style.display = "none";
    }});
  }}

  window.deckAPI = {{
    go: go,
    playSequence: playSequence,
    getSlideCount: function () {{ return slides.length; }},
    getDurationsSec: function () {{
      return slides.map(function (s) {{ return Number(s.dataset.duration || {default_dur}); }});
    }},
    getIndex: function () {{ return cur; }},
    setRecordMode: setRecordMode,
  }};
}})();
</script>
{MARKER_END}"""


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", type=Path, help="deck index.html")
    ap.add_argument("--aspect", default="16:9", help="16:9 (default) | 9:16")
    ap.add_argument("--root-font", type=int, default=0,
                    help="html font-size px (AI-Animation type is rem-based). "
                         "0 = auto (16 landscape / 22 vertical)")
    ap.add_argument("--safe-band", type=int, default=0,
                    help="bottom px reserved for captions (0 = auto)")
    ap.add_argument("--duration", type=int, default=8,
                    help="default per-slide seconds when data-duration is absent")
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    args = ap.parse_args()

    if not args.html.is_file():
        raise SystemExit(f"no deck at {args.html}")

    vertical = args.aspect.replace("x", ":") == "9:16"
    root_font = args.root_font or (22 if vertical else 16)
    safe_band = args.safe_band or (320 if vertical else 150)

    html = args.html.read_text(encoding="utf-8")

    n_slides = len(re.findall(r'class="slide(?:[^"]*)"', html))
    missing_narration = len(re.findall(r'class="slide(?:[^"]*)"(?![^>]*data-narration)', html))

    print(f"{args.html}: {n_slides} slides, aspect={args.aspect}, "
          f"root-font={root_font}px, safe-band={safe_band}px")
    if missing_narration:
        print(f"  WARNING: {missing_narration} slide(s) have no data-narration — "
              "the TTS/subtitle steps read narration.txt, keep them in sync.")
    if "window.deckAPI" in html and MARKER_START not in html:
        print("  note: a hand-written deckAPI is already present; "
              "stvideo will be injected alongside it.")
    if args.check:
        return

    block = build_block(args.aspect, root_font, safe_band, args.duration)
    pattern = re.compile(re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.S)
    if MARKER_START in html:
        html = pattern.sub(lambda m: block, html, count=1)
    else:
        if "</body>" in html:
            html = html.replace("</body>", block + "\n</body>", 1)
        else:
            html = html + "\n" + block

    args.html.write_text(html, encoding="utf-8")
    print(f"  injected deckAPI -> {args.html}")


if __name__ == "__main__":
    main()
