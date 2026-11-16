# finish_image.py options

```
finish_image.py INPUT --out PATH [--preset NAME | --size WxH[px|in|mm]] [--dpi N]
                [--fit contain|cover|stretch] [--padding "T R B L"] [--trim] [--bg COLOR]
                [--upscale FACTOR] [--format png|jpg|jpeg|webp|tif|tiff|pdf] [--quality N]
                [--overwrite]
```

| Flag | Meaning |
|---|---|
| `--out` | Output path. The extension sets the format unless `--format` is given. An existing file gets `-v2`, `-v3` unless `--overwrite`. |
| `--preset` | Named canvas (table below). Carries its own default DPI. |
| `--size` | Canvas: `1080x1350` (px), `8.5x11in`, `210x297mm`. in/mm sizes default to 300 dpi. |
| `--dpi` | Resolution written into the file and used to convert in/mm to pixels. |
| `--fit` | `contain` (default): whole image, padding fills the gaps. `cover`: fill the box, center-crop the overflow. `stretch`: distort to fill. |
| `--padding` | 1 to 4 values, CSS order (top right bottom left). Units: px (default), `in`, `mm`, `%` of the short edge. Padding is inside the canvas. |
| `--trim` | Crop the image to its content (anything differing from the background) before placing, so the padding becomes the true margin to the artwork. |
| `--bg` | Padding colour: `auto` (sample the corners, the default), `#f5f0e6`, `white`, `transparent`. |
| `--upscale` | With no size: multiply pixel dimensions (Lanczos). Interpolated, not new detail. |
| `--quality` | JPG/WebP quality, default 92. |

Transparency is kept for PNG, WebP and TIFF. JPG and PDF are flattened to RGB.

## Presets

| Preset | Canvas | DPI |
|---|---|---|
| `ig-feed` / `fb-feed` | 1080x1350 px (4:5) | 72 |
| `ig-square` | 1080x1080 px | 72 |
| `ig-story` / `reel-cover` | 1080x1920 px (9:16) | 72 |
| `fb-cover` | 1640x624 px | 72 |
| `fb-event` | 1920x1005 px | 72 |
| `gbp-post` | 1200x900 px (4:3) | 72 |
| `og-image` | 1200x630 px | 72 |
| `yt-thumb` | 1280x720 px (16:9) | 72 |
| `web-hero` | 2400x1350 px (16:9) | 72 |
| `letter` / `letter-landscape` | 8.5x11 in / 11x8.5 in | 300 |
| `tabloid` | 11x17 in | 300 |
| `flyer-half` | 5.5x8.5 in | 300 |
| `postcard-4x6` / `postcard-5x7` | 4x6 in / 5x7 in | 300 |
| `biz-card` | 3.5x2 in | 300 |
| `poster-18x24` / `poster-24x36` | 18x24 in / 24x36 in | 150 |

Match the prompt's aspect ratio to the preset (`--aspect` on `codex_generate.sh`) so `contain`
doesn't leave big bars and `cover` doesn't crop the subject.

## Recipes

```bash
# Print poster, exact margins, PDF
finish_image.py raw.png --preset letter --padding "1.25in 1.25in 2in" --trim --out <output folder>/poster.pdf

# Instagram feed, fill the frame
finish_image.py raw.png --preset ig-feed --fit cover --out <output folder>/promo-ig.jpg

# Same art, story size, keep it all with branded bars
finish_image.py raw.png --preset ig-story --bg "#111111" --out <output folder>/promo-story.jpg

# Transparent sticker with 40 px clear space
finish_image.py raw.png --trim --size 1200x1200 --padding 40 --bg transparent --out <output folder>/sticker.png

# Plain 2x enlargement, WebP
finish_image.py raw.png --upscale 2 --format webp --out <output folder>/raw-2x
```
