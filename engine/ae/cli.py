"""Command line entry point.

    ae init                 write a target config and interview template
    ae analyze              run collectors, build the model, write the docs
    ae interview            print the structured business interview
    ae doctor               report which optional collectors are available
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

from . import __version__
from .core import EvidenceStore, load_target, DEFAULT_TARGET
from . import collect_repo, collect_cloud, collect_db, collect_probe
from . import analyze as A
from . import ontology as O
from . import recommend as REC
from . import render as RENDER

COLLECTORS = (("repo", collect_repo), ("cloud", collect_cloud),
              ("database", collect_db), ("probe", collect_probe))

EXAMPLE_TARGET = {
    "name": "acme-lending",
    "repo": {"path": "./fixtures/acme-lending"},
    "cloud": {"enabled": False, "provider": "aws", "profile": "readonly", "region": "us-east-1"},
    "database": {"enabled": False, "kind": "postgres", "dsn": "${ANALYSIS_DB_DSN}"},
    "probe": {"enabled": False, "base_url": "${ANALYSIS_BASE_URL}",
              "endpoints": ["/health", "/api/loans"], "samples": 5},
    "usecases": [
        {"name": "submit loan application", "volume_per_day": 40000,
         "peak_factor": 4.0, "path": ["web", "api", "primary-database"],
         "fanout": {"primary-database": 6}, "revenue_per_event": 0.0},
        {"name": "check application status", "volume_per_day": 120000,
         "peak_factor": 3.0, "path": ["web", "api", "primary-database"],
         "fanout": {"primary-database": 2}}
    ],
    "assumptions": dict(DEFAULT_TARGET["assumptions"], default_volume_per_day=100000),
}


def _write(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def cmd_init(args: argparse.Namespace) -> int:
    t = _write(args.target, json.dumps(EXAMPLE_TARGET, indent=2))
    b = _write(args.business, json.dumps(O.blank_interview(), indent=2))
    print("wrote %s\nwrote %s" % (t, b))
    print("\nNext: edit the target, then run\n  python -m ae analyze --target %s "
          "--business %s" % (t, b))
    return 0


def cmd_interview(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(O.INTERVIEW, indent=2))
    else:
        for i, item in enumerate(O.INTERVIEW, 1):
            print("%2d. [%s] %s" % (i, item["id"], item["q"]))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    rows = []
    for mod, label in (("boto3", "cloud collector (AWS)"),
                       ("psycopg", "database collector (PostgreSQL)"),
                       ("psycopg2", "database collector (PostgreSQL, legacy driver)"),
                       ("yaml", "YAML target configs")):
        try:
            __import__(mod)
            rows.append((mod, "available", label))
        except ImportError:
            rows.append((mod, "missing", label))
    print("analysis-engine %s on python %s\n" % (__version__, sys.version.split()[0]))
    for mod, state, label in rows:
        print("  %-10s %-10s %s" % (mod, state, label))
    print("\nThe repo and probe collectors need nothing beyond the standard library.")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    started = time.time()
    cfg = load_target(args.target)
    if args.repo:
        cfg["repo"]["path"] = os.path.abspath(args.repo)
    if args.name:
        cfg["name"] = args.name
    enabled = set((args.only or "").split(",")) if args.only else None

    store = EvidenceStore()
    ran: List[str] = []
    for name, mod in COLLECTORS:
        if enabled and name not in enabled:
            continue
        if name != "repo" and not (cfg.get(name) or {}).get("enabled"):
            continue
        try:
            obs = mod.collect(cfg)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            print("  ! collector %s failed: %s: %s" % (name, type(exc).__name__, exc),
                  file=sys.stderr)
            continue
        store.extend(obs)
        ran.append("%s(%d)" % (name, len(obs)))

    graph = A.build_graph(store, cfg)
    usecases = A.resolve_usecases(store, graph, cfg)
    capacity = A.capacity_report(graph, usecases, cfg)
    flows = A.flow_report(graph, capacity)
    entities = A.entity_model(store)
    growth = A.growth_projection(entities, usecases, args.horizon)
    business = O.load_business(args.business)
    onto = O.build(entities, capacity, usecases, business)
    recs = REC.build(store, graph, capacity, entities, onto, growth)

    out = args.out
    os.makedirs(out, exist_ok=True)
    written = [
        _write(os.path.join(out, "00_EVIDENCE.json"), store.to_json(cfg)),
        _write(os.path.join(out, "01_ARCHITECTURE.md"),
               RENDER.architecture_md(cfg, graph, flows, store)),
        _write(os.path.join(out, "02_FLOWS.md"), RENDER.flows_md(cfg, flows, capacity)),
        _write(os.path.join(out, "03_ERD.md"), RENDER.erd_md(cfg, entities, growth)),
        _write(os.path.join(out, "04_CAPACITY.md"),
               RENDER.capacity_md(cfg, capacity, usecases, cfg)),
        _write(os.path.join(out, "05_ONTOLOGY.md"), RENDER.ontology_md(cfg, onto)),
        _write(os.path.join(out, "06_ROADMAP.md"), RENDER.roadmap_md(cfg, recs)),
        _write(os.path.join(out, "index.html"),
               RENDER.dashboard_html(cfg, graph, capacity, onto, recs, flows, entities,
                                     len(store.all()))),
        _write(os.path.join(out, "model.json"), json.dumps({
            "target": cfg["name"], "usecases": usecases, "capacity": capacity,
            "flows": flows, "ontology": onto, "recommendations": recs,
            "growth": growth}, indent=2, default=str)),
    ]

    b = capacity.get("bottleneck") or {}
    print("analysis-engine %s -> %s" % (__version__, cfg["name"]))
    print("  collectors     %s" % (", ".join(ran) or "none"))
    print("  observations   %d  (%s)" % (
        len(store.all()), ", ".join("%s %d" % kv for kv in sorted(store.counts().items()))))
    print("  components     %d across %d layers" % (
        len(graph.components), len(graph.layers())))
    print("  transfers      %d" % len(graph.edges))
    print("  entities       %d" % len(entities["entities"]))
    print("  bottleneck     %s at %.0f%% utilisation" % (
        b.get("component", "n/a"), (b.get("utilisation") or 0) * 100))
    print("  break point    %s events/day" % (
        format(capacity["system_break_point_per_day"], ",")
        if capacity.get("system_break_point_per_day") else "n/a"))
    print("  roadmap        %d ranked items (%d now)" % (
        len(recs), len([r for r in recs if r["horizon"] == "now"])))
    print("  open questions %d" % len(onto["open_questions"]))
    print("  wrote          %d files to %s in %.1fs" % (
        len(written), out, time.time() - started))
    return 0


def main(argv: Any = None) -> int:
    p = argparse.ArgumentParser(prog="ae", description="Analysis Engine: point it at a "
                                                       "system, get the documentation set back.")
    p.add_argument("--version", action="version", version="analysis-engine %s" % __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="write an example target config and interview template")
    pi.add_argument("--target", default="target.json")
    pi.add_argument("--business", default="business.json")
    pi.set_defaults(func=cmd_init)

    pa = sub.add_parser("analyze", help="run the full pipeline")
    pa.add_argument("--target", help="path to target.json")
    pa.add_argument("--repo", help="override the repository path")
    pa.add_argument("--business", help="path to interview answers")
    pa.add_argument("--name", help="override the system name")
    pa.add_argument("--out", default="out", help="output directory")
    pa.add_argument("--only", help="comma separated collectors to run")
    pa.add_argument("--horizon", type=int, default=24, help="growth horizon in months")
    pa.set_defaults(func=cmd_analyze)

    pq = sub.add_parser("interview", help="print the structured business interview")
    pq.add_argument("--json", action="store_true")
    pq.set_defaults(func=cmd_interview)

    pd = sub.add_parser("doctor", help="report optional collector availability")
    pd.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    return args.func(args)
