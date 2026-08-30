#!/usr/bin/env bash
# stvideo assembly half: narration.txt + index.html -> final MP4 with voiceover.
#
# Every step skips if its output exists, so re-running is cheap and you can
# iterate on one stage at a time:
#   build_video.sh presentations/foo --only mix,compose --bgm-volume 0.12
#   build_video.sh presentations/foo --from record                 # re-record onward
#   build_video.sh presentations/foo --only srt,compose            # captions off
#   build_video.sh presentations/foo --font /path/to/X.ttf         # subtitle font
#   build_video.sh presentations/foo --force                       # rebuild all
#
# The subtitle font is never downloaded silently. Run
#   fetch_font.py --list-system
# show the user what is installed, and pass their choice via --font.
#
# Steps: inject · tts · srt · timeline · record · mix · compose
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT="${1:-}"; shift || true
[[ -n "$PROJECT" ]] || { echo "usage: build_video.sh <project-dir> [options]" >&2; exit 2; }
PROJECT="$(cd "$PROJECT" && pwd)"

PY="${PY:-$(dirname "$(dirname "$PROJECT")")/.venv/bin/python}"
[[ -x "$PY" ]] || PY="python3"

TTS_ENGINE="edge"; VOICE=""; BGM="none"; BGM_VOLUME="0.20"
VOICE_INPUT=""; SRT_INPUT=""; LEAD="auto"
FROM=""; ONLY=""; FORCE=0
# Aspect / frame size. Default landscape 16:9; `--aspect 9:16` gives vertical.
# 0 / -1 mean "derive from aspect".
ASPECT="16:9"; WIDTH=0; HEIGHT=0
CAP_WIDTH=0; CAP_HEIGHT=0; CAP_MARGIN=-1; CAP_FONT_SIZE=0
CAP_OPACITY=235; CAP_BOX_ALPHA=0; CAP_STROKE=2
FONT=""; ALLOW_FETCH=0
ALL_STEPS="inject tts srt timeline record mix compose"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tts)        TTS_ENGINE="$2";    shift 2 ;;
    --voice)      VOICE="$2";         shift 2 ;;
    --bgm)        BGM="$2";           shift 2 ;;
    --bgm-volume) BGM_VOLUME="$2";    shift 2 ;;
    --audio)      VOICE_INPUT="$2";   shift 2 ;;
    --srt-file)   SRT_INPUT="$2";     shift 2 ;;
    --lead)       LEAD="$2";          shift 2 ;;
    --from)       FROM="$2";          shift 2 ;;
    --only)       ONLY="$2";          shift 2 ;;
    --force)      FORCE=1;            shift ;;
    --python)     PY="$2";            shift 2 ;;
    --aspect)     ASPECT="$2";        shift 2 ;;   # 16:9 (default) | 9:16
    --width)      WIDTH="$2";         shift 2 ;;   # explicit frame width
    --height)     HEIGHT="$2";        shift 2 ;;   # explicit frame height
    --font)        FONT="$2";           shift 2 ;;  # subtitle font file (user-supplied)
    --allow-fetch) ALLOW_FETCH=1;      shift ;;     # only after the user agreed to download
    --cap-width)    CAP_WIDTH="$2";      shift 2 ;;
    --cap-height)   CAP_HEIGHT="$2";     shift 2 ;;
    --cap-font-size) CAP_FONT_SIZE="$2"; shift 2 ;;
    --cap-margin)   CAP_MARGIN="$2";    shift 2 ;;
    --cap-opacity)  CAP_OPACITY="$2";   shift 2 ;;
    --cap-box-alpha) CAP_BOX_ALPHA="$2"; shift 2 ;;
    --cap-stroke)   CAP_STROKE="$2";    shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Resolve frame size from --aspect (or explicit --width/--height), then derive
# caption defaults from the resulting orientation.
if [[ "$ASPECT" == "9:16" || "$ASPECT" == "9x16" ]]; then
  DW=1080; DH=1920
else
  DW=1920; DH=1080
fi
(( WIDTH ))  || WIDTH=$DW
(( HEIGHT )) || HEIGHT=$DH

if (( HEIGHT > WIDTH )); then   # vertical: keep captions clear of the safe band
  DCW=1080; DCH=1920; DCM=240; DCF=44
else                            # landscape
  DCW=1920; DCH=1080; DCM=70;  DCF=44
fi
(( CAP_WIDTH ))     || CAP_WIDTH=$DCW
(( CAP_HEIGHT ))    || CAP_HEIGHT=$DCH
(( CAP_MARGIN >= 0 )) || CAP_MARGIN=$DCM
(( CAP_FONT_SIZE )) || CAP_FONT_SIZE=$DCF
echo "frame=${WIDTH}x${HEIGHT} ($ASPECT)  captions=${CAP_WIDTH}x${CAP_HEIGHT} size=${CAP_FONT_SIZE} margin=${CAP_MARGIN}"

known_step() { case " $ALL_STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
if [[ -n "$ONLY" ]]; then
  ENABLED=" ${ONLY//,/ } "
elif [[ -n "$FROM" ]]; then
  known_step "$FROM" || { echo "unknown step: $FROM" >&2; exit 2; }
  ENABLED=""; seen=0
  for s in $ALL_STEPS; do
    [[ "$s" == "$FROM" ]] && seen=1
    [[ $seen == 1 ]] && ENABLED="$ENABLED $s"
  done
  ENABLED="$ENABLED "
else
  ENABLED=" $ALL_STEPS "
fi
for s in $ENABLED; do
  known_step "$s" || { echo "unknown step: $s" >&2; exit 2; }
done
enabled() { case "$ENABLED" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
should_run() {
  enabled "$1" || return 1
  if [[ $FORCE == 0 && -e "$2" ]]; then
    echo "skip $1 ($(basename "$2") exists — pass --force to redo)"
    return 1
  fi
  echo; echo "=== $1 ==="
  return 0
}

# Graft the recording contract onto the AI-Animation deck. Cheap + idempotent,
# so it runs every time (it replaces its own previous block in place).
if enabled inject; then
  echo; echo "=== inject ==="
  [[ -f "$PROJECT/index.html" ]] || { echo "no index.html in $PROJECT" >&2; exit 1; }
  "$PY" "$HERE/inject_deck_api.py" "$PROJECT/index.html" --aspect "$ASPECT"
fi

SLUG="$(basename "$PROJECT")"
VOICE_WAV="$PROJECT/audio/voice.wav"
SRT="$PROJECT/audio/voice.srt"
MIXED="$PROJECT/audio/voice_with_bgm.wav"
CAPTURE="$PROJECT/record/animated_capture.webm"
FINAL="$PROJECT/final/$SLUG.mp4"
mkdir -p "$PROJECT/audio" "$PROJECT/record" "$PROJECT/final"

if [[ -n "$VOICE_INPUT" ]]; then
  [[ -f "$VOICE_INPUT" ]] || { echo "audio file not found: $VOICE_INPUT" >&2; exit 1; }
  cp "$VOICE_INPUT" "$VOICE_WAV"
  echo "using existing audio -> $VOICE_WAV"
elif should_run tts "$VOICE_WAV"; then
  echo "tts engine=edge${VOICE:+ voice=$VOICE}"
  "$PY" "$HERE/tts.py" \
    --text-file "$PROJECT/narration.txt" --out "$VOICE_WAV" \
    --voice "$VOICE"
fi
[[ -f "$VOICE_WAV" ]] || { echo "no voice audio at $VOICE_WAV" >&2; exit 1; }

if [[ -n "$SRT_INPUT" ]]; then
  [[ -f "$SRT_INPUT" ]] || { echo "SRT file not found: $SRT_INPUT" >&2; exit 1; }
  cp "$SRT_INPUT" "$SRT"
  echo "using existing captions -> $SRT"
elif should_run srt "$SRT"; then
  "$PY" "$HERE/build_srt.py" --text-file "$PROJECT/narration.txt" \
    --audio "$VOICE_WAV" --out "$SRT"
fi

if should_run timeline "$PROJECT/record/timeline.json"; then
  "$PY" "$HERE/deck_capture.py" timeline --project "$PROJECT" --audio "$VOICE_WAV" \
    --width "$WIDTH" --height "$HEIGHT"
fi

if should_run record "$CAPTURE"; then
  "$PY" "$HERE/deck_capture.py" video --project "$PROJECT" \
    --width "$WIDTH" --height "$HEIGHT"
fi

if enabled mix; then
  if [[ "$BGM" == "none" ]]; then
    echo "mix: skipped (--bgm none)"
    MIXED="$VOICE_WAV"
  elif should_run mix "$MIXED"; then
    echo "bgm=$BGM volume=$BGM_VOLUME"
    bash "$HERE/mix_bgm.sh" --voice "$VOICE_WAV" --bgm "$BGM" --out "$MIXED" --volume "$BGM_VOLUME"
  fi
fi
[[ -f "$MIXED" ]] || MIXED="$VOICE_WAV"

# Subtitle font: --font, else $STVIDEO_FONT, else a CJK font already installed.
# Never downloads unless the user explicitly agreed (--allow-fetch): the agent is
# expected to run `--list-system`, show the user what is available and ask.
if enabled compose; then
  if [[ -z "$FONT" ]]; then
    FONT="$("$PY" "$HERE/fetch_font.py" --resolve 2>/dev/null || true)"
  fi
  if [[ -z "$FONT" && $ALLOW_FETCH -eq 1 ]]; then
    echo "user agreed — fetching LXGWWenKai-Medium (18.5 MB)"
    FONT="$("$PY" "$HERE/fetch_font.py" --download)"
  fi
  if [[ -z "$FONT" ]]; then
    echo "error: no CJK subtitle font available. Stop and ask the user:" >&2
    echo "  1) python3 $HERE/fetch_font.py --list-system    # fonts already installed" >&2
    echo "  2) let the user pick one, or supply their own, then re-run with:" >&2
    echo "       build_video.sh <project> --font /path/to/font.ttf" >&2
    echo "  3) only if the user agrees to an 18.5 MB download: --allow-fetch" >&2
    exit 1
  fi
  echo "caption font: $FONT"
fi

if enabled compose; then
  echo; echo "=== compose ==="
  bash "$HERE/compose.sh" --project "$PROJECT" \
    --video "$CAPTURE" --audio "$MIXED" --srt "$SRT" --lead "$LEAD" --out "$FINAL" \
    --python "$PY" \
    --cap-width "$CAP_WIDTH" --cap-height "$CAP_HEIGHT" \
    --cap-font "$FONT" --cap-font-size "$CAP_FONT_SIZE" --cap-margin "$CAP_MARGIN" \
    --cap-opacity "$CAP_OPACITY" --cap-box-alpha "$CAP_BOX_ALPHA" --cap-stroke "$CAP_STROKE"
  echo; echo "done -> $FINAL"
fi
