"""End-to-end smoke test against the synthetic target.

Run: python3 -m tests.test_smoke   (from the AnalysisEngine directory)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ae import analyze as A, ontology as O, recommend as REC  # noqa: E402
from ae.cli import main  # noqa: E402
from ae.core import EvidenceStore, load_target  # noqa: E402
from ae import collect_repo  # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print("  pass  %s" % label)
    else:
        print("  FAIL  %s %s" % (label, detail))
        FAILURES.append(label)


def run():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_target(os.path.join(root, "target.json"))
    store = EvidenceStore()
    store.extend(collect_repo.collect(cfg))

    print("collector")
    check("finds components", len(store.of_kind("component")) >= 8)
    check("finds entities", len(store.of_kind("entity")) == 6,
          "got %d" % len(store.of_kind("entity")))
    check("finds relations", len(store.of_kind("relation")) == 4)
    check("reads .github workflows",
          any(o.attrs.get("type") == "cicd" for o in store.of_kind("config")))
    check("no false CI finding",
          not any(o.key == "no-ci-pipeline" for o in store.of_kind("risk")))
    check("flags single-AZ database",
          any(o.key.startswith("rds-single-az") for o in store.of_kind("risk")))
    check("flags missing k8s limits",
          any(o.key.startswith("k8s-resources") for o in store.of_kind("risk")))
    check("every observation carries evidence",
          all(o.evidence and o.evidence.locator for o in store.all()))

    print("graph")
    g = A.build_graph(store, cfg)
    check("merges duplicate cloud/code nodes", "primary-database" not in g.components)
    check("records the alias", g.aliases.get("primary-database") is not None)
    check("no self edges", all(e.src != e.dst for e in g.edges.values()))
    check("no dangling edges",
          all(e.src in g.components and e.dst in g.components for e in g.edges.values()))
    check("worker is not called by the browser",
          "acme-web->decision-worker" not in g.edges)

    print("capacity math")
    ucs = A.resolve_usecases(store, g, cfg)
    cap = A.capacity_report(g, ucs, cfg)
    db = [r for r in cap["rows"] if "db" in r["component"]][0]
    # 40k/day x4 peak /86400 x6 fanout + 120k/day x3 /86400 x2 fanout = 19.44 rps
    check("arrival rate", abs(db["peak_rps"] - 19.4444444) < 1e-4, "got %s" % db["peak_rps"])
    check("utilisation = lambda/mu",
          abs(db["utilisation"] - db["peak_rps"] / db["capacity_rps"]) < 1e-12)
    check("headroom is the inverse",
          abs(db["headroom_x"] - db["capacity_rps"] / db["peak_rps"]) < 1e-12)
    check("break point scales with headroom",
          abs(db["break_point_per_day"] - cap["total_daily_events"] * db["headroom_x"]) < 1)
    check("bottleneck is the highest utilisation",
          cap["bottleneck"]["utilisation"] == max(r["utilisation"] for r in cap["rows"]))

    print("ontology")
    ents = A.entity_model(store)
    business = O.load_business(os.path.join(root, "business.json"))
    onto = O.build(ents, cap, ucs, business)
    e = onto["unit_economics"]
    check("unit economics complete", e["complete"])
    check("contribution arithmetic",
          abs(e["contribution_per_unit"] - (e["price_per_unit"] - e["variable_cost_per_unit"]))
          < 1e-6)
    check("classifies money objects",
          {"loans", "payments"} <= {o["entity"] for o in onto["objects"] if o["class"] == "money"})
    check("no open questions when fully answered", onto["open_questions"] == [])

    print("recommendations")
    growth = A.growth_projection(ents, ucs)
    recs = REC.build(store, g, cap, ents, onto, growth)
    check("produces a ranked roadmap", len(recs) >= 4)
    check("ranked by score",
          all(recs[i]["score"] >= recs[i + 1]["score"] for i in range(len(recs) - 1)))
    check("every item is executable",
          all(r["action"].get("agent_prompt") and r["action"].get("acceptance") for r in recs))
    check("every item names a deploy trigger",
          all(r["action"]["trigger"]["mode"] in ("git", "manual") for r in recs))
    check("git trigger detected from the repo",
          any(r["action"]["trigger"]["mode"] == "git" for r in recs))

    print("cli")
    with tempfile.TemporaryDirectory() as td:
        rc = main(["analyze", "--target", os.path.join(root, "target.json"),
                   "--business", os.path.join(root, "business.json"), "--out", td])
        files = sorted(os.listdir(td))
        check("exit code 0", rc == 0)
        check("writes nine artefacts", len(files) == 9, str(files))
        check("evidence is valid json",
              isinstance(json.load(open(os.path.join(td, "00_EVIDENCE.json"))), dict))
        for name in ("01_ARCHITECTURE.md", "04_CAPACITY.md", "06_ROADMAP.md"):
            check("%s is non-trivial" % name,
                  os.path.getsize(os.path.join(td, name)) > 1200)

    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILED: %s" % (len(FAILURES), ", ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(run())
