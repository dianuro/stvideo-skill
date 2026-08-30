#!/usr/bin/env python3
"""Resolve the subtitle font — and list what this machine already has.

stvideo does not ship an 18 MB CJK font, and it never downloads one behind the
user's back. The agent is expected to run `--list-system`, show the user the
fonts already installed, and let them pick one or supply their own. Downloading
is opt-in: only `--download` / `--url` fetch anything, and the agent must have
asked first.

Resolution order (no network involved):

  1. --font / $STVIDEO_FONT   a font the user points at explicitly
  2. assets/fonts/*.ttf|ttc|otf   anything previously fetched into the skill
  3. a CJK font already installed on this machine

Every candidate is checked for actual CJK glyph coverage before it is accepted.
This matters: a font that merely exists is not a font that can draw "中文", and
fontconfig will happily hand back a Latin-only face. Without this check captions
silently render as tofu boxes.

stdout carries the resolved path and nothing else — progress and warnings go to
stderr, so `FONT=$(fetch_font.py --resolve)` stays clean.

Usage:
  fetch_font.py --list-system           # every CJK-capable font on this machine
  fetch_font.py --resolve               # print the resolved font path
  fetch_font.py --resolve --font ~/x.ttf
  fetch_font.py --download              # opt-in: fetch LXGW WenKai (asks nobody, so ask first)
  fetch_font.py --download --font lxgw-light
  fetch_font.py --url https://…/My.ttf  # opt-in: fetch any font
  fetch_font.py --list                  # show downloadable presets
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE.parent / "assets" / "fonts"

DEFAULT_PRESET = "lxgw-medium"

# name -> (filename, [urls in preference order])
PRESETS = {
    "lxgw-medium": (
        "LXGWWenKai-Medium.ttf",
        [
            "https://github.com/lxgw/LxgwWenKai/releases/download/v1.501/LXGWWenKai-Medium.ttf",
            "https://raw.githubusercontent.com/lxgw/LxgwWenKai/master/fonts/TTF/LXGWWenKai-Medium.ttf",
        ],
    ),
    "lxgw-regular": (
        "LXGWWenKai-Regular.ttf",
        [
            "https://github.com/lxgw/LxgwWenKai/releases/download/v1.501/LXGWWenKai-Regular.ttf",
            "https://raw.githubusercontent.com/lxgw/LxgwWenKai/master/fonts/TTF/LXGWWenKai-Regular.ttf",
        ],
    ),
    "lxgw-light": (
        "LXGWWenKai-Light.ttf",
        [
            "https://github.com/lxgw/LxgwWenKai/releases/download/v1.501/LXGWWenKai-Light.ttf",
            "https://raw.githubusercontent.com/lxgw/LxgwWenKai/master/fonts/TTF/LXGWWenKai-Light.ttf",
        ],
    ),
}

# Well-known CJK font locations, for machines where fc-list is unavailable.
SYSTEM_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

# Common simplified-Chinese characters; a usable subtitle font covers ~all of them.
CJK_PROBE = "中文视频字幕配音讲解画面的内容我们都"
CJK_MIN_COVERAGE = 0.8

_FONT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO")
FONT_SUFFIXES = (".ttf", ".ttc", ".otf")


def is_font(path: Path) -> bool:
    """A real font: plausible size and a font magic header."""
    try:
        if not path.is_file() or path.stat().st_size < 200_000:
            return False
        with path.open("rb") as fh:
            return fh.read(4).startswith(_FONT_MAGIC)
    except OSError:
        return False


def _covers_cjk_fonttools(path: Path) -> bool | None:
    """True/False from the cmap, or None if fontTools is unavailable."""
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except Exception:  # noqa: BLE001 — optional dependency
        return None
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            faces = TTCollection(str(path), lazy=True).fonts
        else:
            faces = [TTFont(str(path), lazy=True)]
    except Exception:  # noqa: BLE001 — not a font we can parse
        return None
    for face in faces:
        try:
            cmap = face.getBestCmap()
        except Exception:  # noqa: BLE001
            continue
        hit = sum(1 for ch in CJK_PROBE if ord(ch) in cmap)
        if hit / len(CJK_PROBE) >= CJK_MIN_COVERAGE:
            return True
    return False


def _covers_cjk_pil(path: Path) -> bool | None:
    """Heuristic without fontTools: does '中' draw differently from a glyph
    that is guaranteed missing?"""
    try:
        from PIL import ImageFont
    except Exception:  # noqa: BLE001
        return None
    try:
        font = ImageFont.truetype(str(path), 48)
        probe = font.getbbox("中")
        missing = font.getbbox("\ue05f")  # private use area: no font has it
    except Exception:  # noqa: BLE001
        return None
    if probe is None:
        return False
    if missing is None:
        return True
    return probe != missing


def covers_cjk(path: Path, quiet: bool = False) -> bool:
    """Can this font actually draw Chinese? Assume yes only if unverifiable."""
    verdict = _covers_cjk_fonttools(path)
    if verdict is None:
        verdict = _covers_cjk_pil(path)
    if verdict is None:
        return True
    if not verdict and not quiet:
        print(f"  (skipping {path.name}: no CJK glyphs)", file=sys.stderr)
    return verdict


def font_family(path: Path, fallback: str) -> str:
    """Human-readable family name from the font's name table."""
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except Exception:  # noqa: BLE001 — optional dependency
        return fallback
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            faces = TTCollection(str(path), lazy=True).fonts
        else:
            faces = [TTFont(str(path), lazy=True)]
    except Exception:  # noqa: BLE001
        return fallback
    names: list[str] = []
    for face in faces:
        try:
            table = face["name"]
            name = table.getDebugName(16) or table.getDebugName(1)
        except Exception:  # noqa: BLE001
            name = None
        if name and name not in names:
            names.append(name)
    if not names:
        return fallback
    return names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1} faces)"


def _fc_list(lang: str) -> list[tuple[Path, str]]:
    """fontconfig entries for a language, as (path, family) pairs."""
    if not shutil.which("fc-list"):
        return []
    try:
        out = subprocess.run(
            ["fc-list", f":lang={lang}", "-f", "%{file}\t%{family[0]}\n"],
            capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pairs = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if parts and parts[0].strip():
            pairs.append((Path(parts[0].strip()),
                          parts[1].strip() if len(parts) > 1 else ""))
    return pairs


def system_fonts() -> list[tuple[Path, str]]:
    """Every CJK-capable font on this machine, as (path, family) pairs.

    Ordered: known system paths first, then fontconfig's zh-cn and zh lists.
    """
    seen: set[Path] = set()
    out: list[tuple[Path, str]] = []

    def add(path: Path, family: str = "") -> None:
        try:
            rp = path.resolve()
        except OSError:
            rp = path
        if rp in seen or not rp.is_file():
            return
        seen.add(rp)
        # Quiet: enumerating is expected to turn up non-CJK faces.
        if covers_cjk(rp, quiet=True):
            out.append((rp, family or font_family(rp, rp.stem)))

    for c in SYSTEM_CANDIDATES:
        add(Path(c))
    for lang in ("zh-cn", "zh"):
        for path, family in _fc_list(lang):
            add(path, family)
    return out


def resolve_font(explicit: str | None = None) -> Path | None:
    """Find a subtitle font. Never touches the network."""
    # 1. explicit path from --font or the environment
    cand = explicit or os.environ.get("STVIDEO_FONT", "")
    if cand:
        p = Path(cand).expanduser()
        if p.is_file():
            if not covers_cjk(p):
                print(f"warning: {p} has no CJK glyphs — captions will be blank",
                      file=sys.stderr)
            return p
        print(f"warning: STVIDEO_FONT/--font not found: {cand}", file=sys.stderr)

    # 2. anything already fetched into the skill (consented to at the time)
    if FONT_DIR.is_dir():
        for p in sorted(FONT_DIR.iterdir()):
            if p.suffix.lower() in FONT_SUFFIXES and is_font(p) and covers_cjk(p):
                return p

    # 3. a CJK font installed on this machine
    for path, _ in system_fonts():
        return path
    return None


def download(urls: list[str], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for url in urls:
        try:
            # Progress goes to stderr: callers capture stdout to get the path.
            print(f"downloading {url}", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=120) as r, dest.open("wb") as fh:
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
            if not is_font(dest):
                dest.unlink(missing_ok=True)
                last = f"downloaded file is not a valid font: {url}"
                continue
            if not covers_cjk(dest):
                dest.unlink(missing_ok=True)
                last = f"downloaded font has no CJK glyphs: {url}"
                continue
            print(f"saved {dest} ({dest.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)
            return dest
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last = f"{url}: {exc}"
            dest.unlink(missing_ok=True)
    raise SystemExit(f"font download failed. {last}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-system", action="store_true",
                    help="list every CJK-capable font installed on this machine")
    ap.add_argument("--resolve", action="store_true",
                    help="print the resolved font path, never download")
    ap.add_argument("--download", action="store_true",
                    help="opt-in: fetch a preset font (agent must ask the user first)")
    ap.add_argument("--font", help="path to a font file, or a preset name (see --list)")
    ap.add_argument("--url", help="opt-in: download an arbitrary font URL")
    ap.add_argument("--dest", type=Path, default=FONT_DIR, help="where to cache it")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for name, (fname, urls) in PRESETS.items():
            tag = " (default)" if name == DEFAULT_PRESET else ""
            print(f"{name}{tag}\n  -> {fname}\n     {urls[0]}")
        return

    if args.list_system:
        found = system_fonts()
        if not found:
            print("no CJK font found on this machine", file=sys.stderr)
            sys.exit(1)
        for path, family in found:
            size = path.stat().st_size / 1e6
            print(f"{family}\t{path}\t{size:.1f} MB")
        return

    if args.resolve:
        explicit = args.font
        if explicit and explicit in PRESETS:
            explicit = None
        found = resolve_font(explicit)
        if found:
            print(found)
        else:
            sys.exit(1)
        return

    if args.url:
        fname = os.path.basename(args.url.split("?")[0]) or "custom.ttf"
        print(download([args.url], args.dest / fname))
        return

    preset = args.font or DEFAULT_PRESET
    if preset not in PRESETS:
        raise SystemExit(f"unknown font preset {preset!r}; --list shows preset names")

    if args.download:
        fname, urls = PRESETS[preset]
        print(download(urls, args.dest / fname))
        return

    # Reached only when neither --resolve nor --download was given: the agent
    # forgot to make a decision. Say so instead of silently fetching 18 MB.
    raise SystemExit(
        "fetch_font.py does nothing without --resolve / --list-system / --download.\n"
        "  --list-system   show fonts already on this machine, then ask the user\n"
        "  --resolve       print the resolved path (no network)\n"
        "  --download      only after the user has agreed to an 18 MB download")


if __name__ == "__main__":
    main()
