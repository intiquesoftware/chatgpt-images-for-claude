#!/usr/bin/env bash
# Generate one image through the Codex CLI's built-in image_gen tool (ChatGPT sign-in, no
# OPENAI_API_KEY). Writes <name>.png into --out-dir and prints its path.
#
# Usage:
#   codex_generate.sh --out-dir DIR --name NAME --prompt-file FILE \
#       [--aspect "4:5"] [--ref IMG]... [--edit IMG] [--transparent]
#
# --ref   reference image (repeatable); the prompt says what each one is for
# --edit  image to edit (preserve everything not named in the prompt)
#
# Codex CLI lookup: $CODEX_BIN, then `codex` on PATH, then the copy bundled in the ChatGPT
# desktop app on macOS.
#
# Exit codes: 2 bad args, 3 no Codex CLI, 4 image_gen unavailable, 5 no image written.
set -euo pipefail

# ChatGPT app 26.924 (2026-09-28) moved the bundled CLI from Resources/codex to
# Resources/codex-cli/bin/codex; check both.
MAC_APP_CODEX=""
for c in /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex \
         /Applications/ChatGPT.app/Contents/Resources/codex; do
  [[ -x "$c" ]] && { MAC_APP_CODEX="$c"; break; }
done
if [[ -n "${CODEX_BIN:-}" ]]; then
  CODEX="$CODEX_BIN"
  [[ -x "$CODEX" ]] || { echo "CODEX_BIN is set to '$CODEX' but that is not an executable file." >&2; exit 3; }
elif command -v codex >/dev/null 2>&1; then
  CODEX="$(command -v codex)"
elif [[ -n "$MAC_APP_CODEX" ]]; then
  CODEX="$MAC_APP_CODEX"
else
  cat >&2 <<'EOF'
Codex CLI not found. Looked for:
  1. $CODEX_BIN (not set)
  2. `codex` on PATH
  3. /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex (ChatGPT desktop app, macOS)
  4. /Applications/ChatGPT.app/Contents/Resources/codex (older ChatGPT app versions)
Install the ChatGPT desktop app or the Codex CLI, sign in with ChatGPT, or set CODEX_BIN.
EOF
  exit 3
fi

OUT_DIR="" NAME="" PROMPT_FILE="" ASPECT="" TRANSPARENT=0
REFS=() EDIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --aspect) ASPECT="$2"; shift 2 ;;
    --ref) REFS+=("$2"); shift 2 ;;
    --edit) EDIT="$2"; shift 2 ;;
    --transparent) TRANSPARENT=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$OUT_DIR" && -n "$NAME" && -f "$PROMPT_FILE" ]] || { echo "need --out-dir, --name, --prompt-file" >&2; exit 2; }
for f in "$EDIT" "${REFS[@]+"${REFS[@]}"}"; do
  [[ -z "$f" || -f "$f" ]] || { echo "image not found: $f" >&2; exit 2; }
done
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

# Never overwrite: pick the first free name, name.png, name-v2.png, name-v3.png ...
TARGET="$NAME.png"; n=2
while [[ -e "$OUT_DIR/$TARGET" ]]; do TARGET="$NAME-v$n.png"; n=$((n+1)); done
STEM="${TARGET%.png}"

IMG_ARGS=()
ROLES=""
i=1
if [[ -n "$EDIT" ]]; then IMG_ARGS+=(-i "$EDIT"); ROLES+="Attached image $i is the EDIT TARGET: change only what the prompt asks for and keep everything else unchanged. "; i=$((i+1)); fi
for r in "${REFS[@]+"${REFS[@]}"}"; do IMG_ARGS+=(-i "$r"); ROLES+="Attached image $i is a REFERENCE; the prompt says what it is for. "; i=$((i+1)); done

EXTRA=""
[[ -n "$ASPECT" ]] && EXTRA+="Target aspect ratio: $ASPECT (width:height). If image_gen accepts a size or aspect setting, use the closest one to $ASPECT. "
[[ $TRANSPARENT -eq 1 ]] && EXTRA+="Ask image_gen for a genuinely transparent background and preserve the alpha channel. "

INSTR="Use the imagegen skill with the built-in image_gen tool. Do not use the CLI fallback (scripts/image_gen.py) and do not ask for or use OPENAI_API_KEY. If the built-in tool is unavailable, stop and reply exactly: IMAGEGEN_UNAVAILABLE.
Make exactly one image_gen call. Do not iterate, crop, resize, pad, convert, or make a PDF; post-processing happens elsewhere.
$ROLES$EXTRA
Copy the generated PNG into the current working directory as $TARGET. Do not overwrite any existing file.
Reply with only: the absolute path of $TARGET, the original path under generated_images, and the pixel dimensions.

PROMPT:
$(cat "$PROMPT_FILE")"

LOG="$OUT_DIR/$STEM.codex"
mkdir -p "$LOG"
printf '%s\n' "$INSTR" > "$LOG/instructions.txt"

START=$(date +%s)
set +e
printf '%s' "$INSTR" | "$CODEX" exec --skip-git-repo-check -C "$OUT_DIR" -s workspace-write \
  --json -o "$LOG/last-message.txt" "${IMG_ARGS[@]+"${IMG_ARGS[@]}"}" - > "$LOG/run.jsonl" 2> "$LOG/run.stderr"
RC=$?
set -e
echo "elapsed=$(( $(date +%s) - START ))s exit=$RC codex=$CODEX log=$LOG" >&2

if grep -q IMAGEGEN_UNAVAILABLE "$LOG/last-message.txt" 2>/dev/null; then
  echo "Built-in image_gen unavailable. Do not fall back to the paid API without the user's OK." >&2; exit 4
fi
[[ -f "$OUT_DIR/$TARGET" ]] || { echo "No image written. See $LOG" >&2; exit 5; }
echo "$OUT_DIR/$TARGET"
