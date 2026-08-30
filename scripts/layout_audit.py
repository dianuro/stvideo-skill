#!/usr/bin/env python3
"""Headless layout audit for an stvideo deck.

Since screenshots can't be eyeballed here, verify layout numerically:
  * every <pre class="code"> keeps its line breaks (white-space: pre)
  * no code block is clipped horizontally (scrollWidth <= clientWidth)
  * no slide content spills into the bottom caption safe band
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
WIDTH, HEIGHT = 1920, 1080
SAFE_TOP_Y = 940  # captions live below this (band = HEIGHT - 150)

JS = """() => {
  const out = {code: [], overflow: null, pre_ok: true};
  const slide = document.querySelector('.slide.active');
  slide.querySelectorAll('pre.code').forEach((el, i) => {
    const cs = getComputedStyle(el);
    const lines = el.textContent.replace(/\\n$/, '').split('\\n').length;
    const lh = parseFloat(cs.lineHeight);
    const padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const expect = lines * lh + padY;
    out.code.push({
      i, lines,
      whiteSpace: cs.whiteSpace,
      fontSize: cs.fontSize,
      lineHeight: cs.lineHeight,
      scrollW: el.scrollWidth, clientW: el.clientWidth,
      clipped: el.scrollWidth > el.clientWidth + 1,
      heightOk: Math.abs(el.scrollHeight - expect) < lh * 0.6,
      renderedH: Math.round(el.scrollHeight), expectH: Math.round(expect),
      fontFamily: cs.fontFamily.split(',')[0],
    });
  });
  let maxBottom = 0, minTop = HEIGHT;
  slide.querySelectorAll('.an').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.height === 0) return;
    maxBottom = Math.max(maxBottom, r.bottom);
    minTop = Math.min(minTop, r.top);
  });
  out.overflow = {
    maxBottom: Math.round(maxBottom),
    minTop: Math.round(minTop),
    intoSafeBand: maxBottom > SAFE_TOP_Y,
    offTop: minTop < 0,
    slideScrollH: slide.scrollHeight,
    slideClientH: slide.clientHeight,
  };
  out.title = (slide.querySelector('h1,h2') || {}).textContent || '';
  return out;
}""".replace("HEIGHT", str(HEIGHT)).replace("SAFE_TOP_Y", str(SAFE_TOP_Y))


def main() -> None:
    html = (PROJECT / "index.html").resolve()
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
        page = ctx.new_page()
        page.goto(html.as_uri() + "?record=1", wait_until="domcontentloaded")
        page.wait_for_function("() => window.deckAPI && typeof window.deckAPI.go === 'function'")
        page.evaluate("() => window.deckAPI.setRecordMode(true)")
        n = page.locator(".slide").count()
        print(f"slides: {n}  viewport: {WIDTH}x{HEIGHT}")
        for i in range(n):
            page.evaluate("i => window.deckAPI.go(i)", i)
            page.wait_for_timeout(1400)  # let staggered enter animations settle
            r = page.evaluate(JS)
            flags = []
            for c in r["code"]:
                if c["clipped"]:
                    flags.append(f'code#{c["i"]} CLIPPED {c["scrollW"]}>{c["clientW"]}')
                if not c["heightOk"]:
                    flags.append(f'code#{c["i"]} LINEBREAK? h={c["renderedH"]} exp={c["expectH"]}')
                if c["whiteSpace"] != "pre":
                    flags.append(f'code#{c["i"]} white-space={c["whiteSpace"]}')
            if r["overflow"]["intoSafeBand"]:
                flags.append(f'bottom={r["overflow"]["maxBottom"]} > {SAFE_TOP_Y} SAFE BAND')
            if r["overflow"]["offTop"]:
                flags.append(f'top={r["overflow"]["minTop"]} < 0 OFF-SCREEN')
            codes = "; ".join(
                f'{c["lines"]}L/{c["fontSize"]}/{"ok" if not c["clipped"] else "CLIP"}' for c in r["code"]
            )
            status = "OK " if not flags else "!! "
            print(f'{status}{i + 1:02d} {r["title"][:26]:<28} {codes or "-":<40} '
                  f'bottom={r["overflow"]["maxBottom"]}')
            for f in flags:
                print(f"      -> {f}")
                problems.append((i + 1, f))
            if r["code"] and i == 0:
                print(f'      font={r["code"][0]["fontFamily"]}')
        ctx.close()
        browser.close()
    print()
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        sys.exit(1)
    print("PASS: no clipping, line breaks intact, content clear of the caption band")


if __name__ == "__main__":
    main()
