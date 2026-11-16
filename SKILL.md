---
name: chatgpt-images-for-claude
description: >
  Generate or edit images with ChatGPT's image model straight from Claude Code, through the Codex
  CLI's built-in image_gen tool (ChatGPT sign-in, no OpenAI API key), then finish them to spec:
  exact pixel or print size, resolution/DPI, padding or margins, fit (contain/cover), background,
  upscale, and output format (PNG, JPG, WebP, TIFF, PDF). Every run is approved on a read-only
  HTML preview first. Use when: "generate an image", "make this in ChatGPT", "run this prompt
  through Codex", "create a poster/flyer/social graphic/ad image", "make a 1080x1350 version",
  "give me a print-ready PDF of this", "edit this photo with ChatGPT", "make 3 variations",
  "batch 12 images", "make a whole set of images from these prompts", or when prompts already
  exist and the user wants the images made instead of pasting them into the ChatGPT app.
  NOT for: video, or vector/logo work that belongs in SVG.
license: MIT
user-invocable: true
argument-hint: "<what to make> [output folder] [size/preset] [format] [padding] [variants]"
metadata:
  version: "1.0.0"
  category: images
---

# ChatGPT Images for Claude

Claude writes the prompt, Codex makes the pixels, a script makes it to spec, Claude checks it,
and the file lands in the folder the user chose. The user approves every prompt on an HTML
preview before anything is generated and asks for changes in chat. Four scripts do the
mechanical work. They live in `scripts/` next to this file; below, `$SKILL_DIR` means the folder
that contains this SKILL.md.

| Script | Job |
|---|---|
| `scripts/codex_generate.sh` | One `codex exec` call, built-in `image_gen` tool, raw PNG into a folder. Roughly 1 to 2.5 min per image. |
| `scripts/finish_image.py` | Size, DPI, padding, fit, background, upscale, format. Deterministic, never overwrites. |
| `scripts/make_preview.py` | Read-only HTML approval page from the manifest; during a run it becomes the live results page. Opens from file://, no server. |
| `scripts/batch_generate.py` | Runs the approved manifest (1 or many jobs): generate + finish, 2 at a time, resumable. |

**Why the split:** the built-in `image_gen` tool picks its own pixel size (about 1.5 MP, e.g.
1122x1402 for 4:5) and does not hold exact margins (a request for a 2 in bottom margin came back
at about 1.25 in). So the prompt only sets **aspect ratio and composition**. Every exact number
(size, DPI, padding, format) is enforced by `finish_image.py`.

## Requirements

- Codex CLI signed in with a ChatGPT account on a plan that includes image generation (not
  the Free plan). The scripts look for it in this order:
  `$CODEX_BIN`, then `codex` on `PATH`, then the copy bundled inside the ChatGPT desktop app
  (`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` on macOS, or
  `Resources/codex` on older app versions). If none is found the script
  exits 3 with a message; tell the user to install the ChatGPT app or Codex CLI, or set
  `CODEX_BIN`.
- Python 3 with Pillow (`python3 -m pip install Pillow`).
- The Codex `imagegen` system skill, which ships with Codex at
  `${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/`.

## Inputs to collect

Take them from the request. Ask only for what blocks the job; default the rest and say so.

| Input | Default |
|---|---|
| What to make / prompt | **Required.** |
| Base folder | **Required. Ask if not given** (see "Where files go"). |
| Exact on-image text | None. Any text gets checked letter by letter (step 8). |
| Size | A preset from `references/output-options.md`, or `WxH` px, or `WxHin` / `WxHmm` for print. None = keep native size. |
| Resolution | 300 dpi for print sizes, 72 for screen sizes. |
| Padding | 0. Accepts px, in, mm, % of the short edge; 1 to 4 values in CSS order (top right bottom left). |
| Fit | `contain` (whole image, padding fills the rest). `cover` fills and crops. |
| Background (padding colour) | `auto` (sampled from the image corners). Or hex, `white`, `transparent`. |
| Format | PNG. JPG for photos going to social, PDF for print handoff, WebP for web. |
| Variants | 1. Each variant is its own generation (1 to 2.5 min, counts against the ChatGPT plan). |
| Reference / edit images | None. Any image file works (see "Source images"). |

**Batch size:** any number of images works. Past 4, call out the count and estimated time in the
preview handoff; ChatGPT plan image limits are not published and vary.

## Source images

Any image file can be sent with a prompt, in one of two roles: **reference** (likeness, logo,
style; several allowed, `refs` in the manifest) or **edit target** (change only what's asked,
keep the rest; `edit`).

**Use only images the user names, or that the prompt doc they point to names.** Never search
folders and pick images yourself. If a prompt says "attached", "reference photo", "exact
likeness", "reproduce the logo" or similar but no file is named, ask which file before building
the preview. If a named file doesn't exist at that path, say so and ask; don't substitute a
look-alike. The preview shows a thumbnail of every image being sent, so the user confirms them
along with the prompt. Use absolute paths for `refs` and `edit`.

## Where files go

**There is no default output folder. The user picks the base folder.** If they haven't named
one, and the prompt doc they point to doesn't say, **ask before writing the preview** (use
AskUserQuestion when available). Suggest 2-3 likely folders from the current project (an
existing exports, assets, images or print folder) and let them choose or type another. Never
pick one silently.

Inside the base folder the layout is fixed:

```
<base folder>/
  <name>-<preset>.jpg ...          finished files
  codex-raw/
    <set>.json                     manifest (what gets generated)
    <set>.preview.html             the approval page
    <set>.status.json              batch progress
    <name>.png                     raw original from ChatGPT, kept
    <name>.prompt.txt              exact prompt sent
    <name>.codex/                  Codex instructions, JSON log, last message
```

Name files `<project-slug>-<subject>` in kebab case, e.g. `acme-bakery-spring-poster`. Nothing
is ever overwritten; repeats get `-v2`, `-v3`.

Codex also keeps its own copy of each image under `${CODEX_HOME:-$HOME/.codex}/generated_images/`.
If the ChatGPT app has its own workspace folder (on the tested setup, `~/Documents/Codex/`),
leave it alone.

## Workflow

Every run, even a single image, goes manifest → preview → approval → generate. Nothing is sent
to Codex until the user says go.

1. **Load context.** Settle the base folder (ask, see above). If the project has brand docs
   (brand guidelines, style guide, design tokens), read colours, fonts and voice before writing
   the prompt. Follow any writing rules the project or user has set for on-image copy.

2. **Write the prompt(s).** Follow the labeled schema in
   `${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/SKILL.md` (Use case, Asset type, Subject,
   Style, Composition, Lighting, Palette, `Text (verbatim)`, Constraints, Avoid) and its
   `references/prompting.md`. Rules:
   - State the **aspect ratio** and orientation in words ("portrait 4:5").
   - For padding or print margins, ask for **generous even breathing room**, never for exact
     inches or pixels. The exact margin is applied later with `trim` + `padding`.
   - Quote every on-image word and say "no other words, letters, logos or watermarks".
   - Photo plus text overlay: describe two layers, a full-bleed photo and an inset graphics
     layer that holds the text. Never write "fit inside the central 70%"; image models respond
     by shrinking the whole picture.
   - When reference images are attached, open the prompt by saying what each one is for
     (likeness to match, logo to reproduce exactly, style only).
   - Detailed prompt from the user: normalize it, do not embellish.

3. **Write the manifest** to `<base>/codex-raw/<project-slug>-<set>-<YYYY-MM-DD>.json`. The
   format is in the docstring of `scripts/batch_generate.py`: `defaults` (aspect, finish list)
   plus `jobs` (name, prompt, optional aspect, refs, edit, transparent, finish). Finish entries
   take any `finish_image.py` flag (preset, size, dpi, fit, padding, trim, bg, upscale, format,
   quality); full list in `references/output-options.md`. Several finish entries per job give
   several files from one generation; the preset name becomes the file suffix (or set
   `suffix`). Variants of one idea are separate jobs (`-a`, `-b` names).

4. **Build the preview and hand it over.**
   ```bash
   python3 "$SKILL_DIR/scripts/make_preview.py" "<manifest>" --raw-dir "<base>/codex-raw" --final-dir "<base>" --title "<Project name>"
   ```
   Then open the printed `.preview.html` in the user's browser (`open` on macOS, `xdg-open` on
   Linux). The page is read-only: every prompt, the outputs, reference thumbnails and both
   folders. Give the user its full path, the image count and a time estimate (about 1.5 min per
   image, halved at concurrency 2), and stop. More than 4 images: say the count and time
   explicitly; approving the preview is the opt-in. Do not make the preview editable.

5. **Wait for "go" or change requests.** Changes come in chat ("make the text white"): update
   the manifest, rebuild the preview (same command, it overwrites the page), reopen it, and wait
   again. Only "go" (or a clear equivalent) starts generation.

6. **Generate and finish.**
   ```bash
   python3 "$SKILL_DIR/scripts/batch_generate.py" "<manifest>" --raw-dir "<base>/codex-raw" --final-dir "<base>" --concurrency 2
   ```
   One or two images: run in the foreground with a long timeout (10 min). More: run it in the
   background. Go above concurrency 2 only if the user asks; max 4. Progress is saved to
   `<manifest-stem>.status.json`; re-running the same command resumes and skips finished jobs.
   `--dry-run` validates the manifest and lists the jobs without generating anything.

   **Live results:** the batch rebuilds the preview page every time a job starts or finishes.
   Each card then shows a status badge, the generated original, the finished files (images as
   thumbnails, PDF/TIFF as links) and any warning, and the page reloads itself every 15 s while
   jobs are queued or running. The copy the user approved has no auto-reload, so right after
   starting the batch, open the preview page again so they get the live version.
   Each card reads top to bottom: prompt, output (images, then type, size, resolution and file
   size of every file), then files and links. Every file and folder (references, planned and
   finished files, raw original, Codex log, plus the batch folders, manifest and page at the
   bottom) has a Copy path button; full paths are hidden on load behind a "Full paths" switch.
   There are no open-in-Finder links: browsers can only open file:// links in the browser.
   - Exit 4 (`IMAGEGEN_UNAVAILABLE`: plan limit, outage, or the built-in tool is missing) halts
     the batch. The paid API fallback (`scripts/image_gen.py` in the Codex imagegen skill) needs
     `OPENAI_API_KEY` and costs money. **Ask the user; never switch on your own.**
   - Exit 3: no Codex CLI found. Tell the user (see Requirements).

7. **Look at every raw image** with Read.

8. **Check the text letter by letter** against the requested copy: spelling, extra or missing
   words, stray letters, fake labels or signatures. Also check likeness, logo fidelity against
   the reference, composition, and the Avoid list. On a miss, fix that job's prompt in the
   manifest (one targeted change, e.g. spell the word out letter by letter) and re-run with
   `--redo <name>`. Still wrong after 2 retries: stop and show the user. A small flaw that is
   quicker to fix in a design tool (e.g. fake text on a product label): report it, don't
   regenerate.

9. **Check the finished files** (Read the image; for a PDF, `pdfinfo` for page size if
   available). Confirm padding looks right and `cover` didn't crop anything important. Read the
   batch report:
   - `WARNING: source enlarged` means detail is interpolated. For print over 1.5x, or when the
     user wants it sharp, offer an AI upscale with whatever tool they use and run
     `finish_image.py` on the upscaled file.
   - Print output under about 150 effective ppi: mention it.

10. **Report**: full paths of finished files, size/format, text check result, any warning
    (upscale, ppi, retries, small flaws). For several images, a table: name, text check, files,
    notes. Offer the next variant or format in one line.

`scripts/codex_generate.sh` and `scripts/finish_image.py` can still be called directly for a
quick re-finish of an existing raw image (a new size or format needs no new generation, so no
preview). Anything that calls Codex goes through the preview.

## Known limits

- One image per `image_gen` call; variants are separate calls.
- Native output is about 1.5 MP. Anything larger is an upscale.
- The image model ignores exact inch/pixel margin requests; margins are the finisher's job.
- Editing (`edit`) works on the attached image; masks and API-only controls need the paid
  fallback, which requires the user's OK.

## Tested on

Observed on macOS with codex-cli 0.155.0-alpha (2026-09-25 to 2026-09-28). These are notes from
testing, not guarantees; Codex and ChatGPT change often.

- `image_gen` works under `codex exec` with the ChatGPT app closed.
- `-s workspace-write -C <dir>` is enough to write outside the home folder.
- Native size about 1.5 MP (e.g. 1122x1402 for 4:5); 55 to 150 s per image.
- Two parallel runs worked.
- The aspect ratio stated in the prompt is honored; exact margins are not.
- The model is GPT Image (Codex docs name gpt-image-2; the tool does not report the exact
  version).
