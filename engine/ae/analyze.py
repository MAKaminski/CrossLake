"""Analysis layers: topology, transfer processes, capacity math, entities.

Everything here is derived from the EvidenceStore and nothing else. Every
number carries a basis so a reader can tell a measurement from an assumption --
which is the difference between a diligence finding and a guess.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .core import Component, Edge, EvidenceStore, SystemGraph

BASIS_RANK = {"assumed": 0, "inferred": 1, "declared": 2, "measured": 3}


# --------------------------------------------------------------------------
# 1. Topology
# --------------------------------------------------------------------------

def build_graph(store: EvidenceStore, cfg: Dict[str, Any]) -> SystemGraph:
    g = SystemGraph()

    for o in store.of_kind("component"):
        a = o.attrs
        g.add_component(Component(
            key=o.key, layer=o.layer, kind=a.get("kind", "service"),
            tech=a.get("tech", ""), replicas=_int(a.get("replicas")),
            cpu_request=a.get("cpu_request"), mem_request=a.get("mem_request"),
            capacity_rps=_float(a.get("capacity_rps")),
            monthly_cost=_float(a.get("monthly_cost")),
            notes=["%s=%s" % (k, a[k]) for k in
                   ("instance_class", "instance_type", "engine", "launch_type",
                    "workload_kind") if a.get(k)],
            evidence=[o.evidence.locator]))

    # A store referenced by env vars but never declared still belongs on the map.
    for o in store.of_kind("entity"):
        if "primary-database" not in g.components:
            g.add_component(Component(key="primary-database", layer="data", kind="store",
                                      tech="relational", evidence=[o.evidence.locator]))
        break

    for o in store.of_kind("edge"):
        a = o.attrs
        if a.get("src") not in g.components or a.get("dst") not in g.components:
            continue
        g.add_edge(Edge(src=a["src"], dst=a["dst"], protocol=a.get("protocol", "https"),
                        sync=bool(a.get("sync", True)),
                        calls_per_request=float(a.get("calls_per_request", 1.0)),
                        rps=_float(a.get("rps")), payload_bytes=_int(a.get("payload_bytes")),
                        p95_ms=_float(a.get("p95_ms")), basis=a.get("basis", "inferred"),
                        evidence=[o.evidence.locator]))

    # Measured latency lands on the component that serves the route.
    for o in store.of_kind("metric"):
        if o.key.startswith("latency:"):
            svc = _service_for_route(store, o.attrs.get("endpoint", ""))
            if svc and svc in g.components:
                g.components[svc].p95_ms = o.attrs.get("value")

    _canonicalise(g)
    _infer_structural_edges(store, g)
    _apply_costs(store, g)
    return g


PROVIDER_PREFIXES = ("aws-db-instance-", "aws-rds-cluster-", "aws-ecs-service-",
                     "aws-lambda-function-", "aws-app-runner-service-",
                     "aws-elasticache-cluster-", "google-sql-database-instance-")


def _canonicalise(g: SystemGraph) -> None:
    """One real thing, one node.

    A service seen in code and again in Terraform is the same service. Merging
    them keeps the diagram honest and stops the capacity model from splitting
    one component's load across two half-empty nodes.
    """
    aliases: Dict[str, str] = {}

    # provider-named resources fold into the code-level component they run
    for key in list(g.components):
        stripped = key
        for pre in PROVIDER_PREFIXES:
            if key.startswith(pre):
                stripped = key[len(pre):]
                break
        if stripped == key:
            continue
        for other in g.components:
            if other == key:
                continue
            if other == stripped or stripped.endswith(other) or other.endswith(stripped):
                aliases[key] = other
                break

    # a generic inferred store folds into the one concrete store, if there is one
    generic = "primary-database"
    if generic in g.components:
        concrete = [k for k, c in g.components.items()
                    if c.layer == "data" and c.kind == "store" and k != generic
                    and k not in aliases]
        if len(concrete) == 1:
            aliases[generic] = concrete[0]

    for src, dst in aliases.items():
        if src not in g.components or dst not in g.components:
            continue
        keep, drop = g.components[dst], g.components[src]
        for f in ("tech", "replicas", "cpu_request", "mem_request", "capacity_rps",
                  "p95_ms", "monthly_cost"):
            if getattr(keep, f) in (None, "") and getattr(drop, f) not in (None, ""):
                setattr(keep, f, getattr(drop, f))
        keep.notes.extend(n for n in drop.notes if n not in keep.notes)
        keep.evidence.extend(e for e in drop.evidence if e not in keep.evidence)
        keep.notes.append("merged from %s" % src)
        g.aliases[src] = dst
        del g.components[src]

    for ekey in list(g.edges):
        e = g.edges.pop(ekey)
        e.src = aliases.get(e.src, e.src)
        e.dst = aliases.get(e.dst, e.dst)
        if e.src == e.dst or e.src not in g.components or e.dst not in g.components:
            continue
        g.edges[e.key] = e


def _infer_structural_edges(store: EvidenceStore, g: SystemGraph) -> None:
    """Fill in the spine: users -> frontend -> middleware -> data."""
    layers = g.layers()
    front = [c.key for c in layers.get("frontend", [])]
    mids = [c.key for c in layers.get("middleware", []) if c.kind != "job"]
    # Only services that actually expose HTTP routes sit behind the front end.
    route_services = {o.attrs.get("service") for o in store.of_kind("config")
                      if o.attrs.get("type") == "http_route"}
    route_services.discard(None)
    WORKERISH = ("worker", "job", "cron", "consumer", "scheduler", "daemon", "queue")
    callable_mids = [m for m in mids
                     if (m in route_services if route_services else True)
                     and not any(w in m.lower() for w in WORKERISH)]
    background = [m for m in mids if m not in callable_mids]
    mids = callable_mids or mids
    stores = [c.key for c in layers.get("data", [])]

    if front or mids:
        g.add_component(Component(key="users", layer="external", kind="actor",
                                  tech="end users", evidence=["(topology)"]))
    for f in front:
        g.add_edge(Edge("users", f, "https", True, 1.0, basis="inferred",
                        evidence=["(topology)"]))
    for f in front:
        for m in mids:
            g.add_edge(Edge(f, m, "https/json", True, 1.0, basis="inferred",
                            evidence=["(topology)"]))
    if not front:
        for m in mids:
            g.add_edge(Edge("users", m, "https/json", True, 1.0, basis="inferred",
                            evidence=["(topology)"]))
    for m in mids:
        for s in stores:
            g.add_edge(Edge(m, s, "sql", True, 3.0, basis="assumed",
                            evidence=["(topology)"]))
    for key in background:
        for s in stores:
            g.add_edge(Edge(key, s, "sql", False, 1.0, basis="assumed",
                            evidence=["(topology)"]))
    for c in g.components.values():
        if c.kind == "job":
            for s in stores:
                g.add_edge(Edge(c.key, s, "sql", False, 1.0, basis="assumed",
                                evidence=["(topology)"]))


def _apply_costs(store: EvidenceStore, g: SystemGraph) -> None:
    for o in store.of_kind("cost"):
        key = o.key.split(":", 1)[-1]
        for ckey, comp in g.components.items():
            if key in ckey or ckey in key:
                comp.monthly_cost = o.attrs.get("monthly_cost")
                break


def _service_for_route(store: EvidenceStore, endpoint: str) -> Optional[str]:
    for o in store.of_kind("config"):
        if o.attrs.get("type") == "http_route" and o.attrs.get("path") == endpoint:
            return o.attrs.get("service")
    return None


def _int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# 2. Use cases
# --------------------------------------------------------------------------

def resolve_usecases(store: EvidenceStore, g: SystemGraph,
                     cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Configured use cases win. Otherwise synthesise one per busiest route so
    the scaling math still has something to attach to -- flagged as assumed."""
    configured = cfg.get("usecases") or []
    out: List[Dict[str, Any]] = []
    for uc in configured:
        path = uc.get("path") or _default_path(g)
        resolved = [r for r in (_resolve_key(p, g) for p in path) if r]
        fanout = {}
        for comp, n in (uc.get("fanout") or {}).items():
            fanout[_resolve_key(comp, g) or comp] = n
        out.append({
            "name": uc["name"],
            "path": resolved or _default_path(g),
            "volume_per_day": float(uc.get("volume_per_day", 0) or 0),
            "peak_factor": float(uc.get("peak_factor")
                                 or cfg["assumptions"]["peak_factor"]),
            "fanout": fanout,
            "revenue_per_event": _float(uc.get("revenue_per_event")),
            "basis": "declared",
        })
    if out:
        return out

    default_path = _default_path(g)
    routes = [o for o in store.of_kind("config") if o.attrs.get("type") == "http_route"]
    seeds = routes[:3] or [None]
    for r in seeds:
        name = r.attrs["path"] if r else "primary user flow"
        out.append({
            "name": "request %s" % name if r else name,
            "path": default_path,
            "volume_per_day": float(cfg["assumptions"].get("default_volume_per_day", 100_000)),
            "peak_factor": float(cfg["assumptions"]["peak_factor"]),
            "fanout": {},
            "revenue_per_event": None,
            "basis": "assumed",
        })
    return out


def _resolve_key(name: str, g: SystemGraph) -> Optional[str]:
    """Match a configured component name against what was actually found.

    Use-case configs are written by humans against logical names; the graph
    holds whatever the collectors saw. Exact match wins, then containment.
    """
    if name in g.components:
        return name
    if name in g.aliases and g.aliases[name] in g.components:
        return g.aliases[name]
    n = name.lower()
    candidates = [k for k in g.components if n in k.lower() or k.lower() in n]
    if candidates:
        return sorted(candidates, key=len)[0]
    # token overlap, with the obvious abbreviations folded together
    synonyms = {"db": "database", "pg": "postgres", "svc": "service",
                "www": "web", "ui": "web", "frontend": "web"}

    def toks(v: str) -> set:
        raw = {t for t in re.split(r"[^a-z0-9]+", v.lower()) if t and t not in
               ("aws", "gcp", "azure", "instance", "resource", "prod", "production")}
        return {synonyms.get(t, t) for t in raw}

    want = toks(name)
    best, best_score = None, 0.0
    for k in g.components:
        have = toks(k)
        if not have or not want:
            continue
        score = len(want & have) / float(len(want | have))
        if score > best_score:
            best, best_score = k, score
    return best if best_score >= 0.25 else None


def _default_path(g: SystemGraph) -> List[str]:
    layers = g.layers()
    path: List[str] = []
    for ly in ("frontend", "middleware", "data"):
        picks = [c.key for c in layers.get(ly, []) if c.kind != "job"]
        if picks:
            path.append(picks[0])
    return path or list(g.components)[:1]


# --------------------------------------------------------------------------
# 3. Capacity / scaling math
# --------------------------------------------------------------------------

def _capacity_rps(c: Component, a: Dict[str, Any]) -> Tuple[float, str]:
    if c.capacity_rps:
        return c.capacity_rps, "declared"
    service_ms = c.p95_ms or float(a["default_service_ms"])
    basis = "measured" if c.p95_ms else "assumed"
    if c.kind == "store":
        # A relational store is bounded by its connection pool, not by replicas.
        conns = 100
        return conns / (service_ms / 1000.0) / 4.0, basis
    replicas = c.replicas or 1
    conc = float(a["default_concurrency_per_replica"])
    return replicas * conc / (service_ms / 1000.0), basis


def capacity_report(g: SystemGraph, usecases: List[Dict[str, Any]],
                    cfg: Dict[str, Any]) -> Dict[str, Any]:
    a = cfg["assumptions"]
    target_u = float(a["target_utilisation"])
    load: Dict[str, float] = {k: 0.0 for k in g.components}
    contributions: Dict[str, List[str]] = {k: [] for k in g.components}

    for uc in usecases:
        lam_peak = uc["volume_per_day"] / 86400.0 * uc["peak_factor"]
        for idx, comp in enumerate(uc["path"]):
            fan = float(uc["fanout"].get(comp, 1.0))
            if idx > 0:
                prev = uc["path"][idx - 1]
                e = g.edges.get("%s->%s" % (prev, comp))
                if e and not uc["fanout"].get(comp):
                    fan = e.calls_per_request
            load[comp] = load.get(comp, 0.0) + lam_peak * fan
            contributions[comp].append("%s x%.1f" % (uc["name"], fan))

    rows: List[Dict[str, Any]] = []
    for key, c in sorted(g.components.items()):
        if c.layer == "external" or c.kind == "actor":
            continue
        cap, cap_basis = _capacity_rps(c, a)
        lam = load.get(key, 0.0)
        rho = (lam / cap) if cap else 0.0
        headroom = (cap / lam) if lam > 0 else float("inf")
        # M/M/1 waiting time -- the queue term that makes utilisation nonlinear.
        wq_ms = ((rho / (cap * (1 - rho))) * 1000.0) if 0 < rho < 1 else None
        # Volume at which this component saturates, expressed in daily events.
        daily_break = None
        if lam > 0:
            scale = cap / lam
            daily_break = sum(u["volume_per_day"] for u in usecases) * scale
        # Values are stored unrounded: rounding belongs to the renderer, not to
        # the model. Rounding here made derived identities stop holding.
        rows.append({
            "component": key, "layer": c.layer, "kind": c.kind, "tech": c.tech,
            "replicas": c.replicas, "p95_ms": c.p95_ms,
            "capacity_rps": cap, "capacity_basis": cap_basis,
            "peak_rps": lam, "utilisation": rho,
            "headroom_x": None if headroom == float("inf") else headroom,
            "queue_wait_ms": wq_ms,
            "break_point_per_day": int(round(daily_break)) if daily_break else None,
            "over_target": rho > target_u,
            "monthly_cost": c.monthly_cost,
            "drivers": contributions.get(key, []),
        })

    ranked = sorted([r for r in rows if r["peak_rps"] > 0],
                    key=lambda r: -r["utilisation"])
    bottleneck = ranked[0] if ranked else None
    total_daily = sum(u["volume_per_day"] for u in usecases)
    observed_cost = sum(r["monthly_cost"] or 0 for r in rows)
    declared_cost = float(a.get("declared_monthly_infra_cost") or 0)
    monthly_cost = observed_cost or declared_cost
    cost_basis = ("observed" if observed_cost else
                  "declared" if declared_cost else "unknown")
    cost_per_1k = (monthly_cost / (total_daily * 30 / 1000.0)) if total_daily else None

    return {
        "rows": rows,
        "bottleneck": bottleneck,
        "over_target": [r for r in rows if r["over_target"]],
        "target_utilisation": target_u,
        "total_daily_events": total_daily,
        "monthly_infra_cost": round(monthly_cost, 2) if monthly_cost else None,
        "cost_basis": cost_basis,
        "cost_per_1k_events": round(cost_per_1k, 4) if cost_per_1k else None,
        "system_break_point_per_day": min(
            [r["break_point_per_day"] for r in rows if r["break_point_per_day"]] or [0]) or None,
    }


def flow_report(g: SystemGraph, capacity: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transfer processes: every edge with its frequency, size and basis."""
    util = {r["component"]: r for r in capacity["rows"]}
    out: List[Dict[str, Any]] = []
    for e in sorted(g.edges.values(), key=lambda x: x.key):
        dst = util.get(e.dst)
        src = util.get(e.src)
        rps = e.rps
        if rps is None and src:
            rps = src["peak_rps"] * e.calls_per_request
        bytes_per_s = (rps * e.payload_bytes) if (rps and e.payload_bytes) else None
        out.append({
            "edge": e.key, "src": e.src, "dst": e.dst, "protocol": e.protocol,
            "mode": "sync" if e.sync else "async",
            "calls_per_request": e.calls_per_request,
            "peak_rps": round(rps, 3) if rps else None,
            "payload_bytes": e.payload_bytes,
            "throughput_bps": int(bytes_per_s) if bytes_per_s else None,
            "p95_ms": e.p95_ms or (dst["p95_ms"] if dst else None),
            "downstream_utilisation": dst["utilisation"] if dst else None,
            "basis": e.basis,
        })
    return out


# --------------------------------------------------------------------------
# 4. Entities
# --------------------------------------------------------------------------

MONEY_HINTS = ("payment", "invoice", "charge", "subscription", "price", "fee",
               "loan", "balance", "transaction", "order", "refund", "payout",
               "amount", "revenue", "billing", "credit", "interest")
IDENTITY_HINTS = ("user", "customer", "account", "borrower", "member", "client",
                  "merchant", "org", "tenant")


def entity_model(store: EvidenceStore) -> Dict[str, Any]:
    entities: Dict[str, Dict[str, Any]] = {}
    for o in store.of_kind("entity"):
        cur = entities.get(o.key)
        if cur and cur.get("source") == "introspection":
            continue
        cols = o.attrs.get("columns") or []
        blob = (o.key + " " + " ".join(c.get("name", "") for c in cols)).lower()
        entities[o.key] = {
            "name": o.key,
            "columns": cols,
            "row_count": o.attrs.get("row_count"),
            "bytes": o.attrs.get("bytes"),
            "source": o.attrs.get("source"),
            "money_bearing": any(h in blob for h in MONEY_HINTS),
            "identity_bearing": any(h in blob for h in IDENTITY_HINTS),
            "evidence": o.evidence.locator,
        }
    relations = []
    for o in store.of_kind("relation"):
        relations.append({"from": o.attrs["from"], "to": o.attrs["to"],
                          "column": o.attrs.get("column"),
                          "cardinality": o.attrs.get("cardinality", "many-to-one"),
                          "evidence": o.evidence.locator})
    indexes: Dict[str, List[str]] = {}
    for o in store.of_kind("config"):
        if o.attrs.get("type") == "index":
            indexes.setdefault(o.attrs.get("table", ""), []).append(o.key.split(":", 1)[-1])
    for name, e in entities.items():
        e["indexes"] = indexes.get(name, [])
    return {"entities": entities, "relations": relations}


def growth_projection(entities: Dict[str, Any], usecases: List[Dict[str, Any]],
                      horizon_months: int = 24) -> List[Dict[str, Any]]:
    """Rows added per day per table, taken from use-case volume, projected out."""
    daily = sum(u["volume_per_day"] for u in usecases)
    out = []
    for name, e in sorted(entities["entities"].items()):
        rows = e.get("row_count")
        if rows is None:
            continue
        # Assume transactional tables grow with volume; reference tables do not.
        growth_per_day = daily if (e["money_bearing"] or e["identity_bearing"]) else 0.0
        projected = rows + growth_per_day * 30 * horizon_months
        out.append({
            "entity": name, "rows_now": rows,
            "growth_per_day": int(growth_per_day),
            "rows_at_horizon": int(projected),
            "multiple": round(projected / rows, 1) if rows else None,
            "horizon_months": horizon_months,
        })
    return sorted(out, key=lambda r: -(r["multiple"] or 0))
