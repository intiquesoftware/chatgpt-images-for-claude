#!/usr/bin/env bash
# Smoke tests for chatgpt-images-for-claude. No live image generation: a stub Codex CLI stands in
# for the real one, so this runs offline and costs nothing against your ChatGPT plan.
#
# Usage: tests/smoke.sh            (needs bash, python3 and Pillow)
#        PYTHON=/path/to/python3 tests/smoke.sh
#
# Exits 0 when every check passes, 1 otherwise. Work files go to a temp folder that is removed
# at the end (set KEEP=1 to keep it).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/scripts"
PY="${PYTHON:-python3}"
T="$(mktemp -d "${TMPDIR:-/tmp}/c2c-smoke.XXXXXX")"
[[ "${KEEP:-0}" == 1 ]] && echo "work dir: $T" || trap 'rm -rf "$T"' EXIT

PASS=0 FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; [[ -n "${2:-}" ]] && printf '        %s\n' "$2"; }
check() { local name="$1"; shift; local out; if out="$("$@" 2>&1)"; then ok "$name"; else bad "$name" "$(tail -3 <<<"$out")"; fi; }
size_is() { "$PY" -c "import sys;from PIL import Image;im=Image.open(sys.argv[1]);sys.exit(0 if im.size==(int(sys.argv[2]),int(sys.argv[3])) else 'size '+str(im.size))" "$@"; }

echo "chatgpt-images-for-claude smoke tests"
"$PY" -c "import PIL" 2>/dev/null || { echo "Pillow missing: $PY -m pip install Pillow"; exit 1; }

# --- 1. syntax -------------------------------------------------------------------------------
echo "syntax"
check "codex_generate.sh parses" bash -n "$S/codex_generate.sh"
for f in finish_image make_preview batch_generate; do
  check "$f.py compiles" "$PY" -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$S/$f.py"
done

# --- 2. finisher -----------------------------------------------------------------------------
echo "finish_image.py"
"$PY" -c "from PIL import Image,ImageDraw;im=Image.new('RGB',(1024,1536),'white');ImageDraw.Draw(im).rectangle([200,300,824,1236],fill='#c0392b');im.save('$T/raw.png')"
check "preset ig-feed -> 1080x1350 jpg" "$PY" "$S/finish_image.py" "$T/raw.png" --preset ig-feed --fit cover --out "$T/f/feed.jpg"
check "  size is 1080x1350" size_is "$T/f/feed.jpg" 1080 1350
check "custom size + webp" "$PY" "$S/finish_image.py" "$T/raw.png" --size 2400x1200 --fit contain --format webp --out "$T/f/hero"
check "  size is 2400x1200" size_is "$T/f/hero.webp" 2400 1200
check "letter PDF, trim + 1.25in padding" "$PY" "$S/finish_image.py" "$T/raw.png" --preset letter --trim --padding 1.25in --out "$T/f/poster.pdf"
check "  PDF written" test -s "$T/f/poster.pdf"
check "upscale 2x" "$PY" "$S/finish_image.py" "$T/raw.png" --upscale 2 --out "$T/f/raw2x.png"
check "  size is 2048x3072" size_is "$T/f/raw2x.png" 2048 3072
if "$PY" "$S/finish_image.py" "$T/raw.png" --size nonsense --out "$T/f/x.png" >/dev/null 2>&1; then
  bad "bad --size is rejected"; else ok "bad --size is rejected"; fi

# --- 3. stub Codex CLI -----------------------------------------------------------------------
# Mimics `codex exec -C DIR -o LAST ... -`: reads the instructions on stdin and writes a PNG with
# the requested name into DIR. STUB_MODE=unavailable replies IMAGEGEN_UNAVAILABLE instead; STUB_MODE=wrongcopy
# leaves this run's own image under $CODEX_HOME/generated_images/<thread>/ and copies a different one.
mkdir -p "$T/bin"
cat > "$T/bin/codex" <<EOF
#!/usr/bin/env bash
DIR="" LAST=""
while [[ \$# -gt 0 ]]; do
  case "\$1" in -C) DIR="\$2"; shift 2 ;; -o) LAST="\$2"; shift 2 ;; *) shift ;; esac
done
IN="\$(cat)"
if [[ "\${STUB_MODE:-}" == unavailable ]]; then echo IMAGEGEN_UNAVAILABLE > "\$LAST"; exit 0; fi
if [[ "\${STUB_MODE:-}" == limitonce && ! -e "\$STUB_FLAG" ]]; then
  touch "\$STUB_FLAG"; echo IMAGEGEN_UNAVAILABLE > "\$LAST"; exit 0
fi
if [[ "\${STUB_MODE:-}" == wrongcopy ]]; then
  # The agent copies another job's image; this run's own image sits in generated_images/<thread>/.
  echo '{"type":"thread.started","thread_id":"stub-thread-1"}'
  mkdir -p "\$CODEX_HOME/generated_images/stub-thread-1"
  "$PY" -c "from PIL import Image;Image.new('RGB',(900,900),'#c0392b').save('\$CODEX_HOME/generated_images/stub-thread-1/exec-own.png')"
fi
TARGET="\$(sed -n 's/.*into the current working directory as \([^ ]*\.png\)\..*/\1/p' <<<"\$IN" | head -1)"
"$PY" -c "from PIL import Image;Image.new('RGB',(1024,1536),'#2e86de').save('\$DIR/\$TARGET')"
echo "\$DIR/\$TARGET 1024x1536" > "\$LAST"
EOF
chmod +x "$T/bin/codex"
echo "a bake sale poster" > "$T/prompt.txt"

echo "codex_generate.sh (stub)"
check "generates one image" env CODEX_BIN="$T/bin/codex" bash "$S/codex_generate.sh" --out-dir "$T/raw" --name one --prompt-file "$T/prompt.txt" --aspect 2:3
check "  one.png written" test -f "$T/raw/one.png"
check "never overwrites (writes one-v2.png)" env CODEX_BIN="$T/bin/codex" bash "$S/codex_generate.sh" --out-dir "$T/raw" --name one --prompt-file "$T/prompt.txt"
check "  one-v2.png written" test -f "$T/raw/one-v2.png"
mkdir -p "$T/codexhome"
check "parallel-safe: copies this run's own image" env CODEX_BIN="$T/bin/codex" CODEX_HOME="$T/codexhome" STUB_MODE=wrongcopy bash "$S/codex_generate.sh" --out-dir "$T/raw" --name own --prompt-file "$T/prompt.txt"
check "  own.png is the run's image, not the agent's copy" size_is "$T/raw/own.png" 900 900
env CODEX_BIN="$T/nope" bash "$S/codex_generate.sh" --out-dir "$T/raw" --name x --prompt-file "$T/prompt.txt" >/dev/null 2>&1
[[ $? -eq 3 ]] && ok "missing CODEX_BIN -> exit 3" || bad "missing CODEX_BIN -> exit 3"
env CODEX_BIN="$T/bin/codex" bash "$S/codex_generate.sh" --out-dir "$T/raw" --name x >/dev/null 2>&1
[[ $? -eq 2 ]] && ok "missing args -> exit 2" || bad "missing args -> exit 2"
env CODEX_BIN="$T/bin/codex" STUB_MODE=unavailable bash "$S/codex_generate.sh" --out-dir "$T/raw" --name x --prompt-file "$T/prompt.txt" >/dev/null 2>&1
[[ $? -eq 4 ]] && ok "image_gen unavailable -> exit 4" || bad "image_gen unavailable -> exit 4"

# --- 4. batch + preview ----------------------------------------------------------------------
echo "batch_generate.py + make_preview.py (stub)"
cat > "$T/batch.json" <<EOF
{
  "defaults": {"aspect": "4:5", "finish": [{"preset": "ig-feed", "fit": "cover", "format": "jpg"}]},
  "jobs": [
    {"name": "job-a", "prompt": "a red bicycle"},
    {"name": "job-b", "prompt_file": "$T/prompt.txt",
     "finish": [{"preset": "ig-feed", "fit": "cover", "format": "jpg"},
                {"preset": "ig-story", "fit": "cover", "format": "jpg"}]}
  ]
}
EOF
cp "$T/batch.json" "$T/chat.json"
check "chat-mode batch runs" env CODEX_BIN="$T/bin/codex" "$PY" "$S/batch_generate.py" "$T/chat.json" --raw-dir "$T/craw" --final-dir "$T/cfin"
check "  chat mode writes no HTML page" bash -c '! ls "$1"/*.html "$2"/*.html >/dev/null 2>&1' _ "$T" "$T/craw"
check "preview page builds" "$PY" "$S/make_preview.py" "$T/batch.json" --raw-dir "$T/braw" --final-dir "$T/bfin" --title "Smoke test"
check "  preview.html written" test -s "$T/batch.preview.html"
check "dry run lists jobs" "$PY" "$S/batch_generate.py" "$T/batch.json" --raw-dir "$T/braw" --final-dir "$T/bfin" --dry-run
check "batch runs" env CODEX_BIN="$T/bin/codex" "$PY" "$S/batch_generate.py" "$T/batch.json" --raw-dir "$T/braw" --final-dir "$T/bfin"
check "  job-a finished 1080x1350" size_is "$T/bfin/job-a.jpg" 1080 1350
check "  job-b story finished 1080x1920" size_is "$T/bfin/job-b-ig-story.jpg" 1080 1920
check "  status file says done" "$PY" -c "import json,sys;s=json.load(open(sys.argv[1]));sys.exit(0 if all(r['status']=='done' for r in s.values()) and len(s)==2 else str(s))" "$T/braw/batch.status.json"
out="$(env CODEX_BIN="$T/bin/codex" "$PY" "$S/batch_generate.py" "$T/batch.json" --raw-dir "$T/braw" --final-dir "$T/bfin" 2>&1)"
grep -q "2 already done, 0 to run" <<<"$out" && ok "re-run resumes (skips done jobs)" || bad "re-run resumes (skips done jobs)" "$out"
cp "$T/batch.json" "$T/limit.json"
out="$(env CODEX_BIN="$T/bin/codex" STUB_MODE=limitonce STUB_FLAG="$T/limit.flag" "$PY" "$S/batch_generate.py" "$T/limit.json" --raw-dir "$T/lraw" --final-dir "$T/lfin" --concurrency 1 --pause-minutes 0.01 2>&1)"
grep -q "PAUSED: ChatGPT" <<<"$out" && grep -q "RESUMED" <<<"$out" && grep -q "done 2/2" <<<"$out" && ok "limit hit: pauses, then resumes and finishes" || bad "limit hit: pauses, then resumes and finishes" "$out"
cp "$T/batch.json" "$T/limit0.json"
out="$(env CODEX_BIN="$T/bin/codex" STUB_MODE=unavailable "$PY" "$S/batch_generate.py" "$T/limit0.json" --raw-dir "$T/l0raw" --final-dir "$T/l0fin" --max-pauses 0 2>&1)"
grep -q "STOPPED: ChatGPT" <<<"$out" && grep -q "done 0/2" <<<"$out" && ok "limit with --max-pauses 0: stops, resumable" || bad "limit with --max-pauses 0: stops, resumable" "$out"
printf '{"jobs":[{"name":"dup","prompt":"x"},{"name":"dup","prompt":"y"},{"name":"noprompt"}]}' > "$T/badman.json"
if "$PY" "$S/batch_generate.py" "$T/badman.json" --raw-dir "$T/x" --final-dir "$T/y" --dry-run >/dev/null 2>&1; then
  bad "bad manifest is rejected"; else ok "bad manifest is rejected"; fi

echo
echo "$PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
