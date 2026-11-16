#!/usr/bin/env python3
"""Build a read-only HTML preview of a generation manifest, for the user to approve before any
image is generated. Opens from file://, no server. The user replies "go" or asks Claude for
changes in chat; Claude edits the manifest and rebuilds the page.

Once a batch runs, the same page becomes the results page: batch_generate.py rebuilds it as
jobs start and finish, showing each generated image, the finished files and any warnings. While
jobs are queued or running the page reloads itself every 15 s.

Each card reads top to bottom: prompt, output, then files and links. Every file and folder is
listed with a Copy path button; full paths are hidden on every load until the viewer flips the
"Full paths" switch. Browsers cannot open Finder or File Explorer, so there are
no open-in-folder links; paste a copied path into the file manager instead.

Usage: make_preview.py MANIFEST.json --raw-dir DIR --final-dir DIR [--title "Project name"]
Writes <manifest-stem>.preview.html next to the manifest and prints its path.
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finish_image import PRESETS  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
REFRESH_SECONDS = 15
BADGES = {
    "queued": ("Queued", "wait"),
    "running": ("Generating", "run"),
    "generated": ("Finishing", "run"),
    "done": ("Done", "ok"),
    "failed": ("Failed", "bad"),
    "finish_failed": ("Finish failed", "bad"),
}
TOGGLE = ('<button class="ptoggle" type="button" role="switch" aria-checked="false">'
          '<span class="sw" aria-hidden="true"></span><span class="swl">Full paths</span></button>')


def finish_label(spec):
    s = dict(spec)
    fmt = s.pop("format", "png").upper()
    parts = []
    if "preset" in s:
        w, h, unit, dpi = PRESETS[s.pop("preset")]
        parts.append(f"{w}x{h}{'' if unit == 'px' else unit} @ {s.pop('dpi', dpi)}dpi")
    if "size" in s:
        parts.append(s.pop("size"))
    s.pop("suffix", None)
    parts += [f"{k} {v}" if v is not True else k for k, v in s.items()]
    return f"<b>{fmt}</b> " + html.escape(", ".join(parts))


def human_size(n):
    """Bytes as B / KB / MB / GB, decimal units like macOS Finder."""
    for unit in ("B", "KB", "MB"):
        if n < 1000:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}" if n < 10 else f"{n:.0f} {unit}"
        n /= 1000
    return f"{n:.1f} GB"


def file_facts(p):
    """' · 1122x1402 px · 2.2 MB' for an existing file ('' otherwise); dimensions for images only."""
    fp = Path(p)
    if not fp.exists():
        return ""
    facts = []
    if fp.suffix.lower() in IMAGE_EXTS:
        try:
            from PIL import Image
            with Image.open(fp) as im:
                facts.append(f"{im.width}x{im.height} px")
        except Exception:  # noqa: BLE001
            pass
    facts.append(human_size(fp.stat().st_size))
    return " · " + " · ".join(facts)


def uri(p):
    return html.escape(Path(p).expanduser().resolve().as_uri())


def abspath(p):
    return str(Path(p).expanduser().resolve())


def path_row(label, p, planned=False):
    """One line: label, file name, Copy path button, and the full path (hidden until toggled on)."""
    full = abspath(p)
    exists = Path(full).exists()
    btns = [f'<button class="pbtn copy" type="button" data-path="{html.escape(full)}">Copy path</button>']
    if planned:
        tag = ' <span class="ptag">saves as -v2</span>' if exists else ' <span class="ptag">planned</span>'
    else:
        tag = "" if exists else ' <span class="ptag">not found</span>'
    return (f'<div class="prow"><span class="plab">{html.escape(label)}{tag}</span>'
            f'<span class="pname">{html.escape(Path(full).name)}</span>'
            f'<span class="pbtns">{"".join(btns)}</span>'
            f'<code class="pfull">{html.escape(full)}</code></div>')


def paths_block(title, rows):
    if not rows:
        return ""
    return (f'<div class="files"><div class="fhead"><h3>{title}</h3>{TOGGLE}</div>'
            f'<div class="paths">{"".join(rows)}</div></div>')


def planned_finals(job, final_dir):
    """Paths batch_generate.py will write (before -v2 renaming), same naming rule as finish_args()."""
    specs = job.get("finish", [])
    out = []
    for spec in specs:
        suffix = spec.get("suffix", spec.get("preset") if len(specs) > 1 else None)
        stem = f"{job['name']}-{suffix}" if suffix else job["name"]
        out.append(Path(final_dir).expanduser() / f"{stem}.{spec.get('format', 'png')}")
    return out


def output_html(job, rec):
    """Output section: status, generated image and finished files, warnings, planned outputs."""
    finals = (rec or {}).get("finals", [])
    items = []
    raw = (rec or {}).get("raw")
    if raw and Path(raw).exists():
        items.append(f"<li><b>PNG</b> generated original{html.escape(file_facts(raw))}</li>")
    for k, spec in enumerate(job.get("finish", [])):
        size = f" · {human_size(Path(finals[k]).stat().st_size)}" if k < len(finals) and Path(finals[k]).exists() else ""
        items.append(f"<li>{finish_label(spec)}{html.escape(size)}</li>")
    finishes = "".join(items) or "<li>Raw PNG only</li>"
    parts = []
    if rec:
        label, cls = BADGES.get(rec.get("status"), (rec.get("status", "?"), "wait"))
        meta = [f'<span class="badge {cls}">{label}</span>']
        if rec.get("started"):
            meta.append(f"started {html.escape(rec['started'])}")
        if rec.get("seconds") is not None:
            meta.append(f"{rec['seconds']} s")
        parts.append(f'<div class="rhead">{" · ".join(meta)}</div>')

        tiles = []
        raw = rec.get("raw")
        if raw and Path(raw).exists():
            tiles.append(f'<a class="tile main" href="{uri(raw)}" target="_blank"><img src="{uri(raw)}" alt="">'
                         f'<span>Generated original · {html.escape(Path(raw).name)}</span></a>')
        for f in rec.get("finals", []):
            fp = Path(f)
            if not fp.exists():
                continue
            if fp.suffix.lower() in IMAGE_EXTS:
                tiles.append(f'<a class="tile" href="{uri(f)}" target="_blank"><img src="{uri(f)}" alt="">'
                             f'<span>{html.escape(fp.name)}</span></a>')
            else:
                tiles.append(f'<a class="tile file" href="{uri(f)}" target="_blank"><b>{html.escape(fp.suffix[1:].upper())}</b>'
                             f'<span>{html.escape(fp.name)}</span></a>')
        if tiles:
            parts.append(f'<div class="tiles">{"".join(tiles)}</div>')
        for w in rec.get("warnings", []):
            parts.append(f'<div class="note warn">{html.escape(w)}</div>')
        if rec.get("error"):
            parts.append(f'<div class="note bad">Exit {html.escape(str(rec.get("exit", "")))}: '
                         f'<pre>{html.escape(rec["error"])}</pre></div>')
    parts.append(f'<div class="specs"><h4>File details</h4><ul>{finishes}</ul></div>')
    return f'<div class="section output"><div class="plabel">Output</div>{"".join(parts)}</div>'


def files_html(job, rec, final_dir):
    """Files and links section: images sent, then every path for this job."""
    refs = [("Reference", r) for r in job.get("refs", [])] + ([("Edit target", job["edit"])] if job.get("edit") else [])
    thumbs = "".join(
        f'<figure><img src="{uri(p)}" alt=""><figcaption>{role}: {html.escape(Path(p).name)}</figcaption></figure>'
        for role, p in refs)
    rows = [path_row(role, p) for role, p in refs]
    if job.get("prompt_file"):
        rows.append(path_row("Prompt file", job["prompt_file"]))
    if not rec or rec.get("status") == "queued":
        rows += [path_row("Finished file", f, planned=True) for f in planned_finals(job, final_dir)]
    else:
        raw = rec.get("raw")
        if raw:
            rows.append(path_row("Generated original", raw))
        rows += [path_row("Finished file", f) for f in rec.get("finals", [])]
        if raw:
            rows.append(path_row("Codex log", Path(raw).with_suffix(".codex")))
    body = (f'<div class="refs"><h4>Images sent with the prompt</h4>{thumbs}</div>' if refs else "")
    return f'<div class="section supp">{body}{paths_block("Files and links", rows)}</div>'


def build(manifest, raw_dir, final_dir, title=None):
    """Write the preview page and return its path. title=None keeps the title of an existing page."""
    mpath = Path(manifest).resolve()
    out = mpath.with_name(mpath.stem + ".preview.html")
    if title is None:
        m = out.exists() and re.search(r'<meta name="imagegen-title" content="([^"]*)">', out.read_text())
        title = html.unescape(m[1]) if m else ""

    man = json.loads(mpath.read_text())
    defaults = man.get("defaults", {})
    jobs = [{**defaults, **j} for j in man["jobs"]]
    for j in jobs:
        if "prompt_file" in j and "prompt" not in j:
            j["prompt"] = Path(j["prompt_file"]).expanduser().read_text()

    status_path = Path(raw_dir).expanduser() / f"{mpath.stem}.status.json"
    try:
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
    except json.JSONDecodeError:
        status = {}

    cards = []
    for i, j in enumerate(jobs):
        rec = status.get(j["name"])
        cards.append(f"""
<section class="job" id="{html.escape(j['name'])}">
  <div class="job-head"><span class="num">{i + 1:02d}</span><h2>{html.escape(j['name'])}</h2>
    <span class="aspect">aspect {html.escape(j.get('aspect', 'auto'))}{' · transparent' if j.get('transparent') else ''}</span></div>
  <div class="job-body">
    <div class="section"><div class="plabel">Prompt</div><pre class="prompt">{html.escape(j['prompt'])}</pre></div>
    {output_html(j, rec)}
    {files_html(j, rec, final_dir)}
  </div>
</section>""")

    total = len(jobs)
    outputs = sum(max(1, len(j.get("finish", []))) for j in jobs)
    states = [status.get(j["name"], {}).get("status") for j in jobs]
    live = any(s in ("queued", "running", "generated") for s in states)
    started = any(states)
    done = states.count("done")
    failed = sum(s in ("failed", "finish_failed") for s in states)
    page_title = f"Image prompt preview{' · ' + html.escape(title) if title else ''}"
    if started:
        eyebrow = "ChatGPT Images for Claude · results"
        progress = (f'<div class="progress"><b>{done} of {total}</b> done'
                    f'{f", {failed} failed" if failed else ""}'
                    f'{" · generating, this page refreshes every " + str(REFRESH_SECONDS) + " s" if live else ""}'
                    f' · updated {time.strftime("%H:%M:%S")}</div>')
        howto = ""
    else:
        eyebrow = "ChatGPT Images for Claude · approve before generating"
        progress = ""
        howto = """<div class="howto"><strong>How to approve</strong><ol>
<li>Looks right: tell Claude <strong>"go"</strong>. Results appear on this page as each image finishes.</li>
<li>Want changes: tell Claude what to change. It updates the prompt and refreshes this page.</li>
</ol></div>"""
    batch_rows = [path_row("Finished files folder", final_dir),
                  path_row("Raw originals + logs folder", raw_dir),
                  path_row("Manifest", mpath),
                  path_row("This page", out)]

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="imagegen-title" content="{html.escape(title)}">
{f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">' if live else ''}
<title>{page_title}</title>
<style>
:root {{ --paper:#fafaf8; --card:#fff; --ink:#23241f; --soft:#55564f; --line:#e2e0d8; --accent:#2f6f8f; --accent-soft:#e8f1f5; --warn:#9a5b12; --warn-soft:#fbf1e2; --bad:#a33a24; --bad-soft:#fbe9e5; --ok:#2f7a45; --ok-soft:#e5f3e9; --mono:#f2f1ec; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:19px/1.55 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:40px 24px 80px; }}
header {{ border-bottom:3px solid var(--accent); padding-bottom:16px; margin-bottom:24px; }}
.eyebrow {{ font-size:14px; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); font-weight:700; }}
h1 {{ font-size:2rem; margin:6px 0 8px; }}
.summary {{ color:var(--soft); font-size:1rem; }}
.progress {{ margin-top:10px; font-size:1rem; }}
.howto {{ background:var(--card); border:1px solid var(--line); border-left:5px solid var(--accent); border-radius:0; padding:14px 20px; margin-bottom:28px; font-size:1rem; }}
.howto ol {{ margin:6px 0 0; padding-left:22px; }}
.job {{ background:var(--card); border:1px solid var(--line); border-radius:0; margin-bottom:28px; }}
.job-head {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; background:var(--accent-soft); padding:12px 20px; border-bottom:1px solid var(--line); }}
.num {{ font:800 1.3rem "SF Mono",Menlo,monospace; color:var(--accent); }}
.job-head h2 {{ font-size:1.1rem; margin:0; word-break:break-all; }}
.aspect {{ margin-left:auto; font:0.85rem "SF Mono",Menlo,monospace; color:var(--soft); }}
.job-body {{ padding:16px 20px 20px; }}
.section + .section {{ margin-top:22px; padding-top:18px; border-top:1px solid var(--line); }}
.plabel {{ font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--soft); margin-bottom:8px; }}
.prompt {{ font:0.9rem/1.55 "SF Mono",Menlo,Consolas,monospace; background:var(--mono); border:1px solid var(--line); border-radius:0; padding:14px 16px; margin:0; white-space:pre-wrap; word-wrap:break-word; }}
.rhead {{ font-size:.9rem; color:var(--soft); margin-bottom:12px; }}
.badge {{ display:inline-block; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; padding:3px 10px; border-radius:999px; border:1px solid currentColor; }}
.badge.ok {{ color:var(--ok); background:var(--ok-soft); }}
.badge.run {{ color:var(--accent); background:var(--accent-soft); }}
.badge.wait {{ color:var(--soft); background:var(--mono); }}
.badge.bad {{ color:var(--bad); background:var(--bad-soft); }}
.tiles {{ display:flex; gap:16px; flex-wrap:wrap; align-items:flex-start; }}
.tile {{ display:flex; flex-direction:column; gap:6px; color:var(--ink); text-decoration:none; font-size:.8rem; word-break:break-all; width:200px; }}
.tile img {{ width:100%; height:auto; max-height:260px; object-fit:contain; background:var(--mono); border:1px solid var(--line); display:block; }}
.tile.main {{ width:340px; }}
.tile.main img {{ max-height:440px; }}
.tile.file b {{ display:flex; align-items:center; justify-content:center; height:120px; background:var(--mono); border:1px solid var(--line); font:700 1.4rem "SF Mono",Menlo,monospace; color:var(--accent); }}
.tile:hover span {{ text-decoration:underline; }}
.note {{ margin-top:12px; padding:10px 14px; font-size:.9rem; border-left:4px solid; border-radius:0; }}
.note.warn {{ color:var(--warn); background:var(--warn-soft); }}
.note.bad {{ color:var(--bad); background:var(--bad-soft); }}
.note pre {{ margin:6px 0 0; white-space:pre-wrap; font:.8rem "SF Mono",Menlo,monospace; }}
h4 {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--soft); margin:0 0 4px; }}
.specs {{ margin-top:14px; font-size:.9rem; color:var(--soft); }}
.specs ul {{ margin:0; padding-left:18px; }}
.supp {{ font-size:.9rem; color:var(--soft); }}
.refs {{ display:flex; gap:12px; flex-wrap:wrap; align-items:flex-start; margin-bottom:14px; }}
.refs h4 {{ width:100%; }}
figure {{ margin:0; width:96px; }}
figure img {{ width:96px; height:96px; object-fit:cover; border:1px solid var(--line); display:block; }}
figcaption {{ font-size:.7rem; color:var(--soft); word-break:break-all; }}
.files {{ margin-top:4px; }}
.batch {{ margin-top:36px; background:var(--card); border:1px solid var(--line); padding:14px 20px; font-size:.9rem; color:var(--soft); }}
.fhead {{ display:flex; align-items:center; gap:12px; margin-bottom:4px; }}
.fhead h3 {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--soft); margin:0; }}
.ptoggle {{ margin-left:auto; display:inline-flex; align-items:center; gap:8px; font:600 .75rem -apple-system,"Segoe UI",Helvetica,Arial,sans-serif; color:var(--soft); background:none; border:0; padding:2px 0; cursor:pointer; }}
.ptoggle .sw {{ position:relative; width:34px; height:20px; border-radius:10px; background:var(--line); transition:background .15s; flex:none; }}
.ptoggle .sw::after {{ content:""; position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.25); transition:transform .15s; }}
.ptoggle[aria-checked="true"] .sw {{ background:var(--accent); }}
.ptoggle[aria-checked="true"] .sw::after {{ transform:translateX(14px); }}
.ptoggle:hover {{ color:var(--accent); }}
.ptoggle:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.prow {{ display:grid; grid-template-columns:200px 1fr auto; gap:4px 14px; align-items:center; padding:6px 0; border-top:1px solid var(--line); }}
.plab {{ font-weight:600; }}
.pname {{ font:.8rem "SF Mono",Menlo,Consolas,monospace; color:var(--ink); word-break:break-all; }}
.ptag {{ font-size:.68rem; font-weight:700; text-transform:uppercase; color:var(--warn); margin-left:4px; }}
.pfull {{ display:none; grid-column:1 / -1; font:.78rem/1.4 "SF Mono",Menlo,Consolas,monospace; background:var(--mono); padding:4px 8px; word-break:break-all; user-select:all; color:var(--ink); }}
body.showpaths .pfull {{ display:block; }}
.pbtns {{ display:flex; gap:6px; }}
.pbtn {{ font:600 .74rem -apple-system,"Segoe UI",Helvetica,Arial,sans-serif; color:var(--accent); background:var(--card); border:1px solid var(--line); border-radius:4px; padding:3px 9px; text-decoration:none; cursor:pointer; white-space:nowrap; }}
.pbtn:hover {{ border-color:var(--accent); background:var(--accent-soft); }}
.pbtn.done {{ color:var(--ok); border-color:var(--ok); }}
@media (max-width:700px) {{ .aspect {{ margin-left:0; }} .tile, .tile.main {{ width:100%; }} .prow {{ grid-template-columns:1fr; }} }}
</style></head><body><div class="wrap">
<header><div class="eyebrow">{eyebrow}</div>
<h1>{page_title}</h1>
<div class="summary">{total} image{'s' if total != 1 else ''}{'' if started else ' to generate'}, {outputs} finished file{'s' if outputs != 1 else ''}.</div>
{progress}</header>
{howto}
{''.join(cards)}
<div class="batch">{paths_block("Batch files and folders", batch_rows)}</div>
</div>
<script>
(function () {{
  function setPaths(on) {{
    document.body.classList.toggle("showpaths", on);
    document.querySelectorAll(".ptoggle").forEach(function (b) {{ b.setAttribute("aria-checked", on ? "true" : "false"); }});
  }}
  setPaths(false);
  function fallbackCopy(t) {{
    var ta = document.createElement("textarea"); ta.value = t; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); var ok = false;
    try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
    document.body.removeChild(ta); return ok;
  }}
  document.addEventListener("click", function (e) {{
    var t = e.target.closest(".ptoggle");
    if (t) {{
      setPaths(!document.body.classList.contains("showpaths"));
      return;
    }}
    var b = e.target.closest(".copy"); if (!b) return;
    var p = b.getAttribute("data-path");
    function done(ok) {{ b.textContent = ok ? "Copied" : "Copy failed"; b.classList.toggle("done", ok);
      setTimeout(function () {{ b.textContent = "Copy path"; b.classList.remove("done"); }}, 1800); }}
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(p).then(function () {{ done(true); }}, function () {{ done(fallbackCopy(p)); }});
    else done(fallbackCopy(p));
  }});
}})();
</script>
</body></html>"""
    tmp = out.with_suffix(".tmp")
    tmp.write_text(page)
    tmp.replace(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--final-dir", required=True)
    ap.add_argument("--title", default=None, help="project name shown in the page title (kept on rebuilds)")
    a = ap.parse_args()
    print(build(a.manifest, a.raw_dir, a.final_dir, a.title))


if __name__ == "__main__":
    main()
