# Changelog

All notable changes to this skill are listed here. Versions follow [semver](https://semver.org/):
patch = fixes, minor = new presets or flags, major = a change to the manifest format.

## [Unreleased]

### Changed
- Batches pause on the ChatGPT limit instead of stopping. When `image_gen` is unavailable,
  `batch_generate.py` starts no new jobs, lets running ones finish, waits (2, 4, then 8 min)
  and retries the refused and unstarted jobs. It prints plain `PAUSED:`, `RESUMED:` and
  `STOPPED:` lines (images done, images left, retry time), and SKILL.md has Claude watch them
  and tell the user in the chat as they happen. New flags `--pause-minutes` and `--max-pauses`
  (`0` keeps the old stop-at-first-limit behavior). Two new smoke tests.

## [1.1.3] - 2026-11-25

### Fixed
- Parallel batches could save the wrong image. The Codex agent copied the newest image in
  `generated_images/`, so with 2 jobs at once one job could get the other's picture (seen in a
  5-image test: the robot job saved the poster). `codex_generate.sh` now copies the image from
  the run's own folder, `generated_images/<thread_id>/`. New smoke test covers it.

### Added
- SKILL.md: never `edit` a ChatGPT-generated image; regenerate fresh from the prompt and the
  real reference photos instead (quality and faces degrade with each edit pass).
- SKILL.md: documents the 5-image limit per job and that the aspect ratio is not always honored.

## [1.1.2] - 2026-11-25

### Fixed
- `batch_generate.py` no longer writes an HTML page in chat mode. It refreshes the live results
  page only when that page already exists (the user picked HTML for a big batch). Before, every
  batch wrote a `.preview.html` file to disk even when nobody opened it. New smoke test covers it.

## [1.1.1] - 2026-11-25

### Changed
- The HTML page is never used for 1 to 4 images. For a batch of more than 4, Claude now asks
  whether to review it in the chat or on the HTML page, with the chat offered first. Before,
  a big batch went to the HTML page without asking.

## [1.1.0] - 2026-11-25

### Changed
- Review happens in the chat by default. Reference images and finished images are sent into
  the conversation (in the Claude desktop app they render in the side panel), the prompt is
  shown as a short labeled table, and tweaks re-post only the rows that changed. No browser
  page is needed for a normal run.
- The HTML preview (`make_preview.py`) is now optional: used when you ask for it, or for
  batches of more than 4 images (superseded by 1.1.1). Scripts and the manifest format are unchanged.

### Added
- Next-step handoff: when an image is a start frame for another tool (for example an
  image-to-video model), the skill writes that prompt in a copyable code block, links to the
  tool, and reveals the file so it can be dragged in.

## [1.0.1] - 2026-11-23

### Changed
- Skill name is now `chatgpt-imagegen` (was `chatgpt-images-for-claude`). The Agent Skills spec
  reserves the word "claude" in skill names, so the old name failed validation and would be
  rejected on upload to Claude.ai or the Claude API. The repository name is unchanged.
- Install now copies the folder to `~/.claude/skills/chatgpt-imagegen` to match the new name.
  If you installed 1.0.0, rename `~/.claude/skills/chatgpt-images-for-claude` to
  `~/.claude/skills/chatgpt-imagegen`.

## [1.0.0] - 2026-11-15

First public release.

### Added
- `SKILL.md`: generate or edit images with ChatGPT's image model from Claude Code through the
  Codex CLI's built-in `image_gen` tool, using your ChatGPT sign-in (no OpenAI API key).
- `scripts/codex_generate.sh`: one image per call. Finds the Codex CLI via `$CODEX_BIN`, `PATH`,
  or the copy bundled in the ChatGPT desktop app (both the current and older app layouts).
  Supports reference images, edit targets, aspect hints and transparent backgrounds. Never
  overwrites an existing file. Stops with exit code 4 when `image_gen` is unavailable instead of
  falling back to the paid API.
- `scripts/finish_image.py`: exact pixel or print size, DPI, padding, trim, fit
  (contain, cover, stretch), background, upscale, and output as PNG, JPG, WebP, TIFF or PDF.
  20 presets for social, web and print.
- `scripts/batch_generate.py`: run a JSON manifest of jobs 2 at a time (max 4), finish each
  job to one or more specs, save progress after every job and resume where it stopped.
- `scripts/make_preview.py`: a read-only HTML page to approve a batch before anything is
  generated. It becomes the live results page while the batch runs.
- `tests/smoke.sh`: repeatable smoke tests with a stub Codex CLI. No live generation.
- README with install steps and a "Terms, privacy and consent" section. MIT license.
