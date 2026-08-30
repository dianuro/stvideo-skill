#!/usr/bin/env python3
"""Turn narration.txt into audio/voice.wav with edge-tts (Microsoft neural voices).

This is the stvideo voiceover step. The measured duration of the produced wav
is the master clock for the whole pipeline: the slide timeline, the SRT
captions, and the screen recording are all derived from it, never the other
way round. So nothing downstream cares how the audio was made.

Chinese voices (zh-CN) are the default. Override with --voice.

Usage:
  tts.py --text-file narration.txt --out audio/voice.wav
  tts.py --text-file narration.txt --out audio/voice.wav --voice zh-CN-YunxiNeural
  tts.py --list                       # show available zh-CN voices
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Sensible default for Chinese explainer narration.
EDGE_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def run(cmd: list[str]) -> None:
    print("  $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def edge_available() -> bool:
    return subprocess.run(["edge-tts", "--version"], capture_output=True,
                          text=True).returncode == 0


def tts_edge(text_file: Path, out: Path, voice: str) -> None:
    mp3 = out.with_suffix(".edge.mp3")
    print(f"edge-tts voice={voice}")
    run(["edge-tts", "--voice", voice, "--file", str(text_file),
         "--write-media", str(mp3)])
    # Normalize to 24 kHz mono wav so downstream ffprobe/compose are stable.
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
         "-ar", "24000", "-ac", "1", str(out)])
    mp3.unlink(missing_ok=True)


def list_voices() -> None:
    # Print only the Chinese voices to keep the list useful.
    out = subprocess.run(["edge-tts", "--list-voices"], capture_output=True,
                         text=True, check=True).stdout
    for line in out.splitlines():
        if "zh-CN" in line:
            print(line)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text-file", type=Path, help="narration.txt to synthesize")
    ap.add_argument("--out", type=Path, help="output wav path")
    ap.add_argument("--voice", default=EDGE_DEFAULT_VOICE,
                    help="edge-tts voice name (default zh-CN-XiaoxiaoNeural)")
    ap.add_argument("--list", action="store_true",
                    help="list zh-CN voices and exit")
    args = ap.parse_args()

    if args.list:
        list_voices()
        return

    if not edge_available():
        raise SystemExit(
            "edge-tts not found. Install it:\n"
            "  python -m pip install edge-tts\n"
            "then rerun. (Requires network access to the Microsoft TTS endpoint.)"
        )

    if not args.text_file or not args.out:
        ap.error("--text-file and --out are required")
    if not args.text_file.is_file():
        raise SystemExit(f"no narration text at {args.text_file}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tts_edge(args.text_file, args.out, args.voice)

    if not args.out.is_file():
        raise SystemExit(f"edge-tts produced no audio at {args.out}")
    print(f"AUDIO_DURATION={ffprobe_duration(args.out):.2f}  -> {args.out}")


if __name__ == "__main__":
    main()
