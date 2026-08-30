#!/usr/bin/env bash
# Align the recorded deck to the audio, burn captions, mux the final MP4.
#
# The raw Playwright recording may contain a lead-in before the first slide and
# a short tail after the last one. Trim only the measured lead, then pad/trim
# the video to the audio clock before burning captions. Use --lead for a
# verified value; --lead auto keeps the duration-difference fallback.
#
# Captions default to the PNG render path (render_captions.py) so the bundled
# LXGWWenKai font, white fill + 2px black stroke, and transparency are exact.
# Pass --cap-engine libass to use the subtitles filter instead (needs libass).
#
# Usage:
#   compose.sh --project presentations/foo \
#     --video record/animated_capture.webm \
#     --audio audio/voice_with_bgm.wav \
#     --srt   audio/voice.srt \
#     --lead  0.57 \
#     --out   final/foo.mp4
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT=""; VIDEO=""; AUDIO=""; SRT=""; OUT=""; LEAD_MODE="auto"; PYTHON="${PYTHON:-python3}"

# Caption defaults (vertical 9:16 explainer).
CAP_WIDTH=1080; CAP_HEIGHT=1920; CAP_FONT=""; CAP_FONT_SIZE=44; CAP_MARGIN=240
CAP_OPACITY=235; CAP_BOX_ALPHA=0; CAP_STROKE=2; CAP_ENGINE="png"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --video)   VIDEO="$2";   shift 2 ;;
    --audio)   AUDIO="$2";   shift 2 ;;
    --srt)     SRT="$2";     shift 2 ;;
    --lead)    LEAD_MODE="$2"; shift 2 ;;
    --out)     OUT="$2";     shift 2 ;;
    --python)  PYTHON="$2";  shift 2 ;;
    --cap-width)    CAP_WIDTH="$2";    shift 2 ;;
    --cap-height)   CAP_HEIGHT="$2";   shift 2 ;;
    --cap-font)     CAP_FONT="$2";     shift 2 ;;
    --cap-font-size) CAP_FONT_SIZE="$2"; shift 2 ;;
    --cap-margin)   CAP_MARGIN="$2";  shift 2 ;;
    --cap-opacity)  CAP_OPACITY="$2"; shift 2 ;;
    --cap-box-alpha) CAP_BOX_ALPHA="$2"; shift 2 ;;
    --cap-stroke)   CAP_STROKE="$2";  shift 2 ;;
    --cap-engine)   CAP_ENGINE="$2";  shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$PROJECT" && -n "$VIDEO" && -n "$AUDIO" && -n "$OUT" ]] \
  || { echo "need --project --video --audio --out" >&2; exit 2; }

cd "$PROJECT"
dur() { ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }

# Pick a working H.264 encoder (libx264 preferred; libopenh264 fallback).
# Snapshot the encoder list first: `ffmpeg | grep -q` under `set -o pipefail`
# lets grep exit on first match, SIGPIPEs ffmpeg (141), and the whole pipeline
# reads as a failure — so the probe silently fell back to libopenh264 and died
# with "Unknown encoder" even though libx264 was right there. Never pipe -q here.
ENC_LIST="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
has_enc() { printf '%s\n' "$ENC_LIST" | grep -qw -- "$1"; }
if has_enc libx264; then
  ENC=libx264; EOPTS="-preset veryfast -crf 18"
  EOPTS_CAP="-preset medium -crf 17"
elif has_enc libopenh264; then
  ENC=libopenh264; EOPTS="-b:v 4M"; EOPTS_CAP="-b:v 4M"
else
  echo "error: this ffmpeg build has no H.264 encoder (need libx264 or libopenh264)" >&2
  echo "  check with: ffmpeg -hide_banner -encoders | grep -E 'libx264|libopenh264'" >&2
  exit 1
fi
echo "video encoder: $ENC"

AUDIO_DUR=$(dur "$AUDIO")
VID_DUR=$(dur "$VIDEO")
if [[ "$LEAD_MODE" == "auto" ]]; then
  if [[ -f record/capture_meta.json ]]; then
    LEAD=$("$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(max(0.0, round(float(d.get("recommended_lead_sec", 0)), 3)))' record/capture_meta.json)
    echo "lead=auto (record/capture_meta.json)"
  else
    LEAD=$("$PYTHON" -c 'import sys; print(max(0.0, round(float(sys.argv[1])-float(sys.argv[2]), 3)))' "$VID_DUR" "$AUDIO_DUR")
    echo "WARNING: no capture_meta.json; using video-audio duration difference (${LEAD}s) as lead estimate" >&2
  fi
elif [[ "$LEAD_MODE" == "none" ]]; then
  LEAD="0.0"
else
  LEAD=$("$PYTHON" -c 'import sys; print(max(0.0, round(float(sys.argv[1]), 3)))' "$LEAD_MODE")
fi
echo "audio=${AUDIO_DUR}s video=${VID_DUR}s -> trimming ${LEAD}s of measured lead-in"

mkdir -p record final
TRIMMED="record/aligned.mp4"
ffmpeg -y -hide_banner -loglevel error \
  -ss "$LEAD" -i "$VIDEO" -t "$AUDIO_DUR" \
  -vf "fps=30,format=yuv420p,tpad=stop_mode=clone:stop_duration=1" \
  -c:v "$ENC" $EOPTS -an \
  "$TRIMMED"

VIDEO_TRACK="$TRIMMED"
if [[ -n "$SRT" && -f "$SRT" ]]; then
  if [[ "$CAP_ENGINE" == "libass" ]]; then
    echo "burning captions with libass"
    VIDEO_TRACK="record/captioned.mp4"
    ffmpeg -y -hide_banner -loglevel error -i "$TRIMMED" \
      -vf "subtitles=${SRT}:force_style='FontSize=28,PrimaryColour=&H00FFFFFF&,OutlineColour=&H80000000&,Outline=2,MarginV=60'" \
      -c:v "$ENC" $EOPTS_CAP -pix_fmt yuv420p -an "$VIDEO_TRACK"
  else
    echo "rendering caption PNGs (white + ${CAP_STROKE}px black stroke) and overlaying"
    VIDEO_TRACK="record/captioned.mp4"
    $PYTHON "$HERE/render_captions.py" \
      --srt "$SRT" --project . --input "$TRIMMED" --output "$VIDEO_TRACK" \
      --width "$CAP_WIDTH" --height "$CAP_HEIGHT" \
      ${CAP_FONT:+--font "$CAP_FONT"} \
      --font-size "$CAP_FONT_SIZE" --margin "$CAP_MARGIN" \
      --opacity "$CAP_OPACITY" --box-alpha "$CAP_BOX_ALPHA" --stroke "$CAP_STROKE"
    bash record/burn_caps.sh
  fi
fi

ffmpeg -y -hide_banner -loglevel error \
  -i "$VIDEO_TRACK" -i "$AUDIO" \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 192k \
  -t "$AUDIO_DUR" -shortest \
  "$OUT"

echo "final: $OUT"
ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height \
  -of default=nw=1 "$OUT"
