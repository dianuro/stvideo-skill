#!/usr/bin/env python3
"""Render SRT cues as transparent PNGs (white text, 2px black stroke) and emit an
ffmpeg burn-in script.

Why PNGs instead of libass `subtitles=`: Homebrew/stock ffmpeg is often built
without libass, and even when present, controlling the exact look — an exact font
file, a 2px black outline around white glyphs, and a configurable
transparency — is far easier here. Overlaying pre-rendered transparent PNGs with
`enable='between(t,start,end)'` gives pixel-exact captions and reliable CJK
rendering on every platform.

Style (per stvideo spec):
  - font:   whatever the user chose; resolved by fetch_font.py, override with `--font`
  - fill:   white with --opacity alpha (semi-transparent -> "一定透明度")
  - stroke: 2px solid black outline around every glyph
  - box:    optional dark rounded box behind the text (--box-alpha, default 0)

Usage:
  render_captions.py --srt audio/voice.srt --project presentations/foo \\
      --input record/aligned.mp4 --output record/captioned.mp4
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fetch_font import resolve_font  # noqa: E402

CUE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = CUE_RE.match(lines[1])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        cues.append((
            h1 * 3600 + m1 * 60 + s1 + ms1 / 1000,
            h2 * 3600 + m2 * 60 + s2 + ms2 / 1000,
            "\n".join(lines[2:]).strip(),
        ))
    return cues


def pick_font(explicit: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Resolve a CJK font, then load it. See fetch_font.py for the chain."""
    path = resolve_font(explicit)
    if path is None:
        raise SystemExit(
            "no CJK subtitle font found. Stop and ask the user which font to use:\n"
            "  python3 scripts/fetch_font.py --list-system   # fonts already installed\n"
            "  … --font /path/to/YourFont.ttf                # or one the user supplies\n"
            "  build_video.sh … --allow-fetch                # only if the user agreed to download"
        )
    print(f"caption font: {path}")
    return ImageFont.truetype(str(path), size)


def render_cue(text: str, font, size: tuple[int, int], margin: int,
               opacity: int, box_alpha: int, stroke: int) -> Image.Image:
    """White glyphs, `stroke` px solid black outline, optional dark backing box."""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = text.split("\n")
    dims = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        dims.append((bb[2] - bb[0], bb[3] - bb[1]))
    tw = max(d[0] for d in dims)
    th = sum(d[1] for d in dims) + (len(lines) - 1) * 12
    pad_x, pad_y = 36, 22
    box_w, box_h = tw + pad_x * 2, th + pad_y * 2
    box_x, box_y = (W - box_w) // 2, H - box_h - margin

    if box_alpha > 0:
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h], radius=18,
            fill=(14, 17, 20, box_alpha),
        )

    y = box_y + (box_h - th) // 2
    for line, (lw, lh) in zip(lines, dims):
        x = (W - lw) // 2
        # black 2px outline drawn behind the (semi-transparent) white fill
        draw.text((x, y), line, font=font, fill=(0, 0, 0, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, opacity))
        y += lh + 12
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--srt", type=Path, required=True)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True, help="video to burn onto")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--width", type=int, default=1080, help="vertical 9:16 default")
    ap.add_argument("--height", type=int, default=1920, help="vertical 9:16 default")
    ap.add_argument("--font", default=None, help="path to the subtitle font")
    ap.add_argument("--font-size", type=int, default=44)
    ap.add_argument("--margin", type=int, default=240,
                    help="px from bottom edge (vertical safe band)")
    ap.add_argument("--opacity", type=int, default=235,
                    help="white text alpha 0-255 -> subtitle transparency")
    ap.add_argument("--box-alpha", type=int, default=0,
                    help="dark backing box alpha; 0 = no box (default)")
    ap.add_argument("--stroke", type=int, default=2, help="black outline width in px")
    ap.add_argument("--crf", type=int, default=17)
    args = ap.parse_args()

    cues = parse_srt(args.srt)
    if not cues:
        raise SystemExit(f"no cues parsed from {args.srt}")

    cap_dir = args.project / "record" / "caps"
    if cap_dir.exists():
        shutil.rmtree(cap_dir)
    cap_dir.mkdir(parents=True)

    font = pick_font(args.font, args.font_size)
    meta = []
    for i, (start, end, text) in enumerate(cues, 1):
        img = render_cue(text, font, (args.width, args.height), args.margin,
                         args.opacity, args.box_alpha, args.stroke)
        path = cap_dir / f"cap_{i:03d}.png"
        img.save(path)
        meta.append({"i": i, "start": start, "end": end, "path": str(path.resolve())})

    (args.project / "record" / "caps_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # One overlay per cue, chained. Fine to ~50 cues; past a few hundred, split
    # the video into parts.
    inputs = ["-i", str(args.input)]
    parts, last = [], "[0:v]"
    for idx, m in enumerate(meta):
        inputs += ["-i", m["path"]]
        out = f"[v{idx + 1}]"
        enable = rf"between(t\,{m['start']:.3f}\,{m['end']:.3f})"
        parts.append(f"{last}[{idx + 1}:v]overlay=0:0:enable='{enable}'{out}")
        last = out

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Pick a working H.264 encoder at run time (libx264 preferred; libopenh264
    # fallback, which needs a bitrate instead of -crf).
    # Snapshot the encoder list instead of piping straight into `grep -q`: with
    # `set -o pipefail` grep exiting on first match SIGPIPEs ffmpeg (141) and the
    # probe reads as a failure, falling back to an encoder that may not exist.
    cmd = (
        'ENC_LIST="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"\n'
        "ENC=libx264; EOPTS='-preset medium -crf " + str(args.crf) + "'\n"
        "if ! printf '%s\\n' \"$ENC_LIST\" | grep -qw -- libx264; then\n"
        "  ENC=libopenh264; EOPTS='-b:v 4M'\n"
        "fi\n"
        "ffmpeg -y -hide_banner -loglevel error "
        + " ".join(inputs)
        + f' -filter_complex "{";".join(parts)}"'
        + ' -map "' + last + '" -c:v "$ENC" $EOPTS'
        + " -pix_fmt yuv420p -an " + str(args.output) + "\n"
    )
    script = args.project / "record" / "burn_caps.sh"
    script.write_text(cmd, encoding="utf-8")
    print(f"{len(meta)} caption PNGs -> {cap_dir}")
    print(f"burn script -> {script}")


if __name__ == "__main__":
    main()
