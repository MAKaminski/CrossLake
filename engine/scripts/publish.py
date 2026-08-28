#!/usr/bin/env python3
"""Publish a completed run directory to the hosted viewer.

Standard library only, matching the engine's zero-dependency rule, so it runs in a
target's own environment and in CI without an install.

    python3 scripts/publish.py --dir out --url https://<app> --token "$INGEST_TOKEN"

Two secrets are involved and neither substitutes for the other:

  --token   the app's own bearer credential, checked in constant time by the route.
  --bypass  Vercel's Protection Bypass for Automation secret. Deployment Protection
            challenges the request before it ever reaches the route, so without this
            a protected deployment returns a 401 HTML page, not a JSON error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Mirrors RUN_FILES in web/lib/storage.ts. The endpoint rejects anything else.
ALLOWED = (
    "model.json",
    "00_EVIDENCE.json",
    "01_ARCHITECTURE.md",
    "02_FLOWS.md",
    "03_ERD.md",
    "04_CAPACITY.md",
    "05_ONTOLOGY.md",
    "06_ROADMAP.md",
    "index.html",
)
REQUIRED = ("model.json", "00_EVIDENCE.json")


def collect(directory: str) -> dict:
    files = {}
    for name in ALLOWED:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                files[name] = fh.read()

    missing = [n for n in REQUIRED if n not in files]
    if missing:
        raise SystemExit("%s is missing %s — not a completed run"
                         % (directory, ", ".join(missing)))
    return files


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default="out", help="the engine output directory")
    p.add_argument("--url", default=os.environ.get("WEB_URL"),
                   help="base URL of the viewer, e.g. https://app.vercel.app")
    p.add_argument("--token", default=os.environ.get("INGEST_TOKEN"),
                   help="bearer token for POST /api/runs")
    p.add_argument("--bypass", default=os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"),
                   help="Vercel Protection Bypass for Automation secret")
    args = p.parse_args(argv)

    if not args.url:
        raise SystemExit("--url or WEB_URL is required")
    if not args.token:
        raise SystemExit("--token or INGEST_TOKEN is required")

    files = collect(args.dir)
    body = json.dumps({"files": files}).encode("utf-8")

    request = urllib.request.Request(
        args.url.rstrip("/") + "/api/runs",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + args.token,
        },
    )
    if args.bypass:
        request.add_header("x-vercel-protection-bypass", args.bypass)

    print("publishing %d files (%.1f KB) to %s"
          % (len(files), len(body) / 1024.0, args.url))

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:500]
        if err.code == 401 and "<html" in detail.lower():
            print("HTTP 401 with an HTML body: Deployment Protection rejected the "
                  "request before it reached the app. Pass --bypass.", file=sys.stderr)
        else:
            print("HTTP %s: %s" % (err.code, detail), file=sys.stderr)
        return 1
    except urllib.error.URLError as err:
        print("could not reach %s: %s" % (args.url, err.reason), file=sys.stderr)
        return 1

    print("published %s" % payload["id"])
    print("  %s/runs/%s" % (args.url.rstrip("/"), payload["id"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
