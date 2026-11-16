#!/usr/bin/env python3
"""Run many image generations from one manifest, then finish each to spec.

Each job calls codex_generate.sh (one built-in image_gen call) and then finish_image.py once per
entry in its `finish` list. Jobs run N at a time. Progress is saved after every job to
<raw-dir>/<batch>.status.json, so a re-run skips finished jobs (resume after a crash or a
plan limit). Text/quality review still happens afterward: Claude reads every raw image.

The manifest's .preview.html page is rebuilt whenever a job starts or finishes, so it shows
each generated image and its finished files as they arrive (refreshing itself while jobs run).

Usage:
  batch_generate.py MANIFEST.json --raw-dir DIR --final-dir DIR [--concurrency 2] [--dry-run] [--redo NAME ...]

Manifest:
{
  "defaults": {"aspect": "4:5", "finish": [{"preset": "ig-feed", "fit": "cover", "format": "jpg"}]},
  "jobs": [
    {"name": "acme-promo-01", "prompt": "Use case: ads-marketing ..."},
    {"name": "acme-promo-02", "prompt_file": "/abs/path/prompts/02.txt", "refs": ["/abs/path/ref.jpg"],
     "finish": [{"preset": "ig-feed", "fit": "cover", "format": "jpg"},
                {"preset": "ig-story", "fit": "cover", "format": "jpg", "suffix": "story"}]}
  ]
}
Job keys: name (required), prompt | prompt_file (required), aspect, refs, edit, transparent, finish.
Finish keys: any finish_image.py flag without dashes (preset, size, dpi, fit, padding, trim, bg,
upscale, format, quality) plus optional suffix (default: the preset name when a job has more than
one finish entry). An empty finish list keeps only the raw PNG.
Use absolute paths for prompt_file, refs and edit (relative paths resolve from the current directory).
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_preview  # noqa: E402

GEN = HERE / "codex_generate.sh"
FIN = HERE / "finish_image.py"
lock = threading.Lock()
stop = threading.Event()  # set when image_gen is unavailable; queued jobs then skip
preview_args = None  # (manifest, raw_dir, final_dir) once main() starts a real run


def finish_args(raw, spec, final_dir, name, multi):
    spec = dict(spec)
    fmt = spec.pop("format", "png")
    suffix = spec.pop("suffix", spec.get("preset") if multi else None)
    stem = f"{name}-{suffix}" if suffix else name
    args = [sys.executable, str(FIN), str(raw), "--out", str(Path(final_dir) / f"{stem}.{fmt}")]
    for k, v in spec.items():
        flag = "--" + k.replace("_", "-")
        if v is True:
            args.append(flag)
        elif v not in (False, None):
            args += [flag, str(v)]
    return args


def run_job(job, raw_dir, final_dir, status, status_path):
    name = job["name"]
    if stop.is_set():
        return name, None
    t0 = time.time()
    rec = {"status": "running", "started": time.strftime("%H:%M:%S")}
    with lock:
        status[name] = rec
        save(status, status_path)

    if "prompt_file" in job:
        prompt_file = Path(job["prompt_file"]).expanduser()
    else:
        prompt_file = Path(raw_dir) / f"{name}.prompt.txt"
        prompt_file.write_text(job["prompt"])

    cmd = ["bash", str(GEN), "--out-dir", str(raw_dir), "--name", name, "--prompt-file", str(prompt_file)]
    if job.get("aspect"):
        cmd += ["--aspect", job["aspect"]]
    for r in job.get("refs", []):
        cmd += ["--ref", r]
    if job.get("edit"):
        cmd += ["--edit", job["edit"]]
    if job.get("transparent"):
        cmd.append("--transparent")

    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = p.stdout.strip().splitlines()
    if p.returncode != 0 or not lines:
        rec.update(status="failed", exit=p.returncode, error=p.stderr.strip()[-400:])
        if p.returncode == 4:
            stop.set()
    else:
        raw = lines[-1]
        rec.update(status="generated", raw=raw, finals=[])
        specs = job.get("finish", [])
        for spec in specs:
            f = subprocess.run(finish_args(raw, spec, final_dir, name, len(specs) > 1), capture_output=True, text=True)
            if f.returncode != 0:
                rec.update(status="finish_failed", error=f.stderr.strip()[-400:])
                break
            out = f.stdout.splitlines()
            rec["finals"].append(out[0].removeprefix("saved: "))
            if any(l.startswith("WARNING") for l in out):
                rec.setdefault("warnings", []).append(next(l for l in out if l.startswith("WARNING")))
        else:
            rec["status"] = "done"
    rec["seconds"] = round(time.time() - t0)
    with lock:
        save(status, status_path)
    return name, rec


def save(status, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2))
    tmp.replace(path)
    refresh_preview()


def refresh_preview():
    """Rebuild the results page from the status file; a failure here never stops the batch."""
    if preview_args:
        try:
            make_preview.build(*preview_args)
        except Exception as e:  # noqa: BLE001
            print(f"  (preview not updated: {e})", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--final-dir", required=True)
    ap.add_argument("--concurrency", type=int, default=2, help="parallel generations (default 2, max 4)")
    ap.add_argument("--dry-run", action="store_true", help="validate and list jobs, generate nothing")
    ap.add_argument("--redo", nargs="*", default=[], help="job names to run again even if done")
    a = ap.parse_args()

    man = json.loads(Path(a.manifest).read_text())
    defaults = man.get("defaults", {})
    jobs = [{**defaults, **j} for j in man["jobs"]]
    names = [j.get("name") for j in jobs]
    problems = [f"job {i + 1}: missing name" for i, n in enumerate(names) if not n]
    problems += [f"duplicate name {n}" for n in set(names) if n and names.count(n) > 1]
    problems += [f"{j.get('name')}: needs prompt or prompt_file" for j in jobs if not (j.get("prompt") or j.get("prompt_file"))]
    if problems:
        sys.exit("manifest errors:\n  " + "\n  ".join(problems))

    raw_dir, final_dir = Path(a.raw_dir).expanduser(), Path(a.final_dir).expanduser()
    raw_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    status_path = raw_dir / f"{Path(a.manifest).stem}.status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}

    todo = [j for j in jobs if status.get(j["name"], {}).get("status") != "done" or j["name"] in a.redo]
    conc = max(1, min(a.concurrency, 4))
    est = len(todo) * 90 / conc / 60
    print(f"{len(jobs)} jobs, {len(jobs) - len(todo)} already done, {len(todo)} to run, "
          f"concurrency {conc}, about {est:.0f} min")
    if a.dry_run:
        for j in todo:
            print(f"  {j['name']}  aspect={j.get('aspect', '-')}  finish={len(j.get('finish', []))}")
        return

    global preview_args
    preview_args = (a.manifest, raw_dir, final_dir)
    for j in todo:
        status[j["name"]] = {"status": "queued"}
    save(status, status_path)
    print(f"live results: {make_preview.build(*preview_args)}")

    with ThreadPoolExecutor(conc) as pool:
        futs = [pool.submit(run_job, j, raw_dir, final_dir, status, status_path) for j in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            name, rec = fut.result()
            if rec is None:
                continue
            print(f"[{i}/{len(todo)}] {name}: {rec['status']} ({rec['seconds']}s)"
                  + (f"  {rec.get('error', '')[:160]}" if rec["status"] != "done" else ""), flush=True)
            if rec.get("exit") == 4:
                print("image_gen unavailable (plan limit or outage). Stopping; re-run later to resume.")
                pool.shutdown(cancel_futures=True)
                break

    with lock:  # jobs skipped after a stop go back to not-started
        for n in [n for n, r in status.items() if r["status"] == "queued"]:
            del status[n]
        save(status, status_path)

    done = [n for n, r in status.items() if r["status"] == "done"]
    failed = {n: r for n, r in status.items() if r["status"] != "done"}
    print(f"\ndone {len(done)}/{len(jobs)}. status file: {status_path}")
    for n, r in failed.items():
        print(f"  NOT DONE {n}: {r['status']}")
    for n, r in status.items():
        for w in r.get("warnings", []):
            print(f"  {n}: {w}")


if __name__ == "__main__":
    main()
