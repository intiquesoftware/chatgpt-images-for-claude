#!/usr/bin/env python3
"""Turn a raw image_gen PNG into a deliverable: exact size, padding, format, DPI.

The built-in image_gen tool picks its own pixel size (about 1.5 MP), so every
size, resolution, padding and format requirement is enforced here, not in the prompt.

Examples:
  finish_image.py raw.png --preset ig-feed --out finals/promo.jpg
  finish_image.py raw.png --size 8.5x11in --dpi 300 --padding 1.25in --trim --out poster.pdf
  finish_image.py raw.png --size 2400x1200 --fit cover --format webp --out hero
  finish_image.py raw.png --upscale 2 --out raw@2x.png
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops

PRESETS = {
    # name: (width, height, unit, default dpi)
    "ig-feed": (1080, 1350, "px", 72),
    "ig-square": (1080, 1080, "px", 72),
    "ig-story": (1080, 1920, "px", 72),
    "reel-cover": (1080, 1920, "px", 72),
    "fb-feed": (1080, 1350, "px", 72),
    "fb-cover": (1640, 624, "px", 72),
    "fb-event": (1920, 1005, "px", 72),
    "gbp-post": (1200, 900, "px", 72),
    "og-image": (1200, 630, "px", 72),
    "yt-thumb": (1280, 720, "px", 72),
    "web-hero": (2400, 1350, "px", 72),
    "letter": (8.5, 11, "in", 300),
    "letter-landscape": (11, 8.5, "in", 300),
    "tabloid": (11, 17, "in", 300),
    "postcard-4x6": (4, 6, "in", 300),
    "postcard-5x7": (5, 7, "in", 300),
    "flyer-half": (5.5, 8.5, "in", 300),
    "biz-card": (3.5, 2, "in", 300),
    "poster-18x24": (18, 24, "in", 150),
    "poster-24x36": (24, 36, "in", 150),
}

FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "tif": "TIFF", "tiff": "TIFF", "pdf": "PDF"}


def parse_size(s, dpi):
    m = re.fullmatch(r"\s*([\d.]+)\s*x\s*([\d.]+)\s*(px|in|mm)?\s*", s, re.I)
    if not m:
        sys.exit(f"bad --size {s!r}; use 1080x1350, 8.5x11in or 210x297mm")
    w, h, unit = float(m[1]), float(m[2]), (m[3] or "px").lower()
    return to_px(w, unit, dpi), to_px(h, unit, dpi), unit


def to_px(v, unit, dpi):
    return round(v * dpi) if unit == "in" else round(v / 25.4 * dpi) if unit == "mm" else round(v)


def parse_padding(s, w, h, dpi):
    """1-4 CSS-style values (top right bottom left); each px, in, mm or % of the short edge."""
    vals = []
    for tok in s.replace(",", " ").split():
        m = re.fullmatch(r"([\d.]+)(px|in|mm|%)?", tok, re.I)
        if not m:
            sys.exit(f"bad --padding token {tok!r}")
        v, unit = float(m[1]), (m[2] or "px").lower()
        vals.append(round(min(w, h) * v / 100) if unit == "%" else to_px(v, unit, dpi))
    if len(vals) == 1:
        vals *= 4
    elif len(vals) == 2:
        vals *= 2
    elif len(vals) == 3:
        vals.append(vals[1])
    elif len(vals) != 4:
        sys.exit("--padding takes 1 to 4 values")
    return tuple(vals)


def bg_color(img, spec):
    if spec == "transparent":
        return (0, 0, 0, 0)
    if spec and spec != "auto":
        from PIL import ImageColor
        return ImageColor.getcolor(spec, "RGBA")
    # auto: median of the four corners, so paper stays paper
    px = img.convert("RGBA")
    w, h = px.size
    corners = [px.getpixel(p) for p in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]]
    return tuple(sorted(c[i] for c in corners)[1] for i in range(4))


def trim(img, bg, tol=24):
    """Crop to content: anything that differs from the background colour by more than tol."""
    rgb = img.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg[:3])).convert("L")
    box = diff.point(lambda v: 255 if v > tol else 0).getbbox()
    return img.crop(box) if box else img


def next_free(path):
    if not path.exists():
        return path
    n = 2
    while (p := path.with_name(f"{path.stem}-v{n}{path.suffix}")).exists():
        n += 1
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", required=True, help="output path; extension sets format unless --format given")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--size", help="canvas: 1080x1350 (px), 8.5x11in, 210x297mm")
    ap.add_argument("--dpi", type=int, help="print resolution; default 300 for in/mm sizes, 72 otherwise")
    ap.add_argument("--fit", choices=["contain", "cover", "stretch"], default="contain",
                    help="contain = whole image, pad the rest (default); cover = fill and crop; stretch = distort")
    ap.add_argument("--padding", default="0", help="e.g. 60, 5%%, 1.25in, '1.25in 1.25in 2in' (CSS order)")
    ap.add_argument("--trim", action="store_true", help="crop to content before placing, so padding = true margin")
    ap.add_argument("--bg", default="auto", help="padding colour: auto (sample corners), #hex, white, transparent")
    ap.add_argument("--upscale", type=float, help="multiply pixel size (Lanczos) when no --size is given")
    ap.add_argument("--format", choices=sorted(FORMATS))
    ap.add_argument("--quality", type=int, default=92, help="jpg/webp quality")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    src = Image.open(a.input)
    src.load()
    has_alpha = src.mode in ("RGBA", "LA") or "transparency" in src.info
    img = src.convert("RGBA")

    unit = "px"
    if a.preset:
        pw, ph, unit, pdpi = PRESETS[a.preset]
        dpi = a.dpi or pdpi
        W, H = to_px(pw, unit, dpi), to_px(ph, unit, dpi)
    elif a.size:
        dpi = a.dpi or (300 if re.search(r"(in|mm)\s*$", a.size, re.I) else 72)
        W, H, unit = parse_size(a.size, dpi)
    else:
        dpi = a.dpi or 72
        f = a.upscale or 1
        W, H = round(img.width * f), round(img.height * f)

    bg = bg_color(img, a.bg)
    if a.trim:
        img = trim(img, bg)

    t, r, b, l = parse_padding(a.padding, W, H, dpi)
    bw, bh = W - l - r, H - t - b
    if bw <= 0 or bh <= 0:
        sys.exit("padding leaves no room for the image")

    if a.fit == "stretch":
        placed = img.resize((bw, bh), Image.LANCZOS)
    else:
        scale = (min if a.fit == "contain" else max)(bw / img.width, bh / img.height)
        placed = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        if a.fit == "cover":
            x0, y0 = (placed.width - bw) // 2, (placed.height - bh) // 2
            placed = placed.crop((x0, y0, x0 + bw, y0 + bh))
    scale_used = placed.width / img.width

    canvas = Image.new("RGBA", (W, H), bg)
    canvas.alpha_composite(placed, (l + (bw - placed.width) // 2, t + (bh - placed.height) // 2))

    out = Path(a.out).expanduser()
    fmt_key = (a.format or out.suffix.lstrip(".") or "png").lower()
    if fmt_key not in FORMATS:
        sys.exit(f"unknown format {fmt_key!r}")
    if out.suffix.lower().lstrip(".") != fmt_key:
        out = out.with_suffix("." + fmt_key)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not a.overwrite:
        out = next_free(out)

    fmt = FORMATS[fmt_key]
    keep_alpha = fmt in ("PNG", "WEBP", "TIFF") and (has_alpha or bg[3] < 255)
    final = canvas if keep_alpha else canvas.convert("RGB")
    kw = {"dpi": (dpi, dpi)}
    if fmt in ("JPEG", "WEBP"):
        kw["quality"] = a.quality
    if fmt == "PDF":
        kw = {"resolution": float(dpi)}
    final.save(out, fmt, **kw)

    src_ppi = dpi / scale_used  # generated pixels per output inch: the real detail level
    is_print = unit in ("in", "mm") or a.dpi
    print(f"saved: {out}")
    size_note = f" @ {dpi}dpi = {W / dpi:.2f}x{H / dpi:.2f}in, effective {src_ppi:.0f} ppi" if is_print else ""
    print(f"canvas: {W}x{H}px{size_note}  source: {src.width}x{src.height}px")
    print(f"image scale: {scale_used:.2f}x  padding(t r b l): {t} {r} {b} {l}px")
    if scale_used > 1.5:
        print(f"WARNING: source enlarged {scale_used:.1f}x, so detail is interpolated."
              " Fine on screen or at arm's length; soft up close. Use an AI upscale for sharper output.")


if __name__ == "__main__":
    main()
