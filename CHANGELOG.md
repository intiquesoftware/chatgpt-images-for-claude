# Changelog

All notable changes to this skill are listed here. Versions follow [semver](https://semver.org/):
patch = fixes, minor = new presets or flags, major = a change to the manifest format.

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
