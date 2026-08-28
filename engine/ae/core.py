"""Core data model for the Analysis Engine.

One repeating pattern runs through the whole system: every fact the engine
learns about a target is an Observation carrying its own Evidence. Collectors
only ever emit Observations; analyzers only ever read them. Nothing else
crosses that boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "1.0"

# The four architectural layers Michael categorises work by, plus two the
# engine needs to keep the graph honest.
LAYERS = ("frontend", "middleware", "backend", "data", "infrastructure", "external")

KINDS = (
    "component",   # a deployable or addressable thing
    "edge",        # a transfer process between two components
    "entity",      # a persisted business object (table / model)
    "relation",    # a foreign-key or logical relation between entities
    "metric",      # a measured or declared number
    "config",      # a setting that matters to risk or cost
    "risk",        # something that is wrong or missing
    "cost",        # a money figure attached to a component
    "usecase",     # a named user-visible flow through the graph
)


def _sha(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


@dataclass
class Evidence:
    """Where a fact came from. No observation is admitted without one."""
    locator: str                 # path:line, arn, table name, url
    excerpt: str = ""
    method: str = "static"       # static | api | query | probe | declared | interview

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Observation:
    kind: str
    key: str
    layer: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    collector: str = "unknown"
    evidence: Optional[Evidence] = None
    observed_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("unknown kind: %s" % self.kind)
        if self.layer not in LAYERS:
            raise ValueError("unknown layer: %s" % self.layer)
        if self.evidence is None:
            self.evidence = Evidence(locator="(none)", method="declared")

    @property
    def id(self) -> str:
        return _sha(self.kind, self.key, self.collector, self.evidence.locator)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        return d


class EvidenceStore:
    """Append-only fact base. Deduplicates, keeps the most confident copy."""

    def __init__(self) -> None:
        self._by_id: Dict[str, Observation] = {}

    def add(self, obs: Observation) -> None:
        existing = self._by_id.get(obs.id)
        if existing is None or obs.confidence > existing.confidence:
            self._by_id[obs.id] = obs

    def extend(self, observations: Iterable[Observation]) -> None:
        for o in observations:
            self.add(o)

    def all(self) -> List[Observation]:
        return list(self._by_id.values())

    def of_kind(self, kind: str) -> List[Observation]:
        return [o for o in self._by_id.values() if o.kind == kind]

    def find(self, kind: str, key: str) -> Optional[Observation]:
        for o in self._by_id.values():
            if o.kind == kind and o.key == key:
                return o
        return None

    def by_layer(self, layer: str) -> List[Observation]:
        return [o for o in self._by_id.values() if o.layer == layer]

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for o in self._by_id.values():
            out[o.kind] = out.get(o.kind, 0) + 1
        return out

    def to_json(self, target: Dict[str, Any]) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "target": target,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": self.counts(),
            "observations": [o.to_dict() for o in sorted(
                self._by_id.values(), key=lambda x: (x.kind, x.layer, x.key))],
        }
        return json.dumps(payload, indent=2, default=str)


# --------------------------------------------------------------------------
# Derived graph
# --------------------------------------------------------------------------

@dataclass
class Component:
    key: str
    layer: str
    kind: str = "service"        # service | page | queue | store | job | saas | gateway
    tech: str = ""
    replicas: Optional[int] = None
    cpu_request: Optional[str] = None
    mem_request: Optional[str] = None
    capacity_rps: Optional[float] = None
    p95_ms: Optional[float] = None
    monthly_cost: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)


@dataclass
class Edge:
    src: str
    dst: str
    protocol: str = "https"
    sync: bool = True
    calls_per_request: float = 1.0
    rps: Optional[float] = None
    payload_bytes: Optional[int] = None
    p95_ms: Optional[float] = None
    basis: str = "assumed"       # measured | declared | inferred | assumed
    evidence: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return "%s->%s" % (self.src, self.dst)


@dataclass
class SystemGraph:
    components: Dict[str, Component] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    # logical name -> canonical component key, recorded when two observations
    # turn out to describe the same real thing
    aliases: Dict[str, str] = field(default_factory=dict)

    def add_component(self, c: Component) -> Component:
        cur = self.components.get(c.key)
        if cur is None:
            self.components[c.key] = c
            return c
        for f in ("tech", "replicas", "cpu_request", "mem_request",
                  "capacity_rps", "p95_ms", "monthly_cost"):
            if getattr(cur, f) in (None, "") and getattr(c, f) not in (None, ""):
                setattr(cur, f, getattr(c, f))
        cur.notes.extend(n for n in c.notes if n not in cur.notes)
        cur.evidence.extend(e for e in c.evidence if e not in cur.evidence)
        return cur

    def add_edge(self, e: Edge) -> Edge:
        cur = self.edges.get(e.key)
        if cur is None:
            self.edges[e.key] = e
            return e
        rank = {"assumed": 0, "inferred": 1, "declared": 2, "measured": 3}
        if rank.get(e.basis, 0) > rank.get(cur.basis, 0):
            self.edges[e.key] = e
            return e
        return cur

    def layers(self) -> Dict[str, List[Component]]:
        out: Dict[str, List[Component]] = {ly: [] for ly in LAYERS}
        for c in self.components.values():
            out[c.layer].append(c)
        return {k: sorted(v, key=lambda c: c.key) for k, v in out.items() if v}

    def out_edges(self, key: str) -> List[Edge]:
        return [e for e in self.edges.values() if e.src == key]


# --------------------------------------------------------------------------
# Target configuration
# --------------------------------------------------------------------------

DEFAULT_TARGET = {
    "name": "unnamed-system",
    "repo": {"path": ".", "ignore": ["node_modules", ".git", "dist", "build",
                                     ".next", "venv", ".venv", "__pycache__"]},
    "cloud": {"enabled": False, "provider": "aws", "profile": None, "region": "us-east-1"},
    "database": {"enabled": False, "dsn": None, "kind": "postgres"},
    "probe": {"enabled": False, "base_url": None, "endpoints": [], "samples": 5,
              "timeout_s": 10},
    "usecases": [],
    "assumptions": {
        "peak_factor": 3.0,
        "default_service_ms": 120.0,
        "default_concurrency_per_replica": 8,
        "target_utilisation": 0.7,
        "declared_monthly_infra_cost": None,
    },
}


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_target(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return json.loads(json.dumps(DEFAULT_TARGET))
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(raw)
        except Exception as exc:  # pragma: no cover
            raise SystemExit("target config must be JSON (or YAML with PyYAML installed): %s" % exc)
    cfg = _deep_merge(DEFAULT_TARGET, data or {})
    base = os.path.dirname(os.path.abspath(path))
    rp = cfg["repo"].get("path") or "."
    if not os.path.isabs(rp):
        cfg["repo"]["path"] = os.path.normpath(os.path.join(base, rp))
    return cfg


def env_expand(value: Optional[str]) -> Optional[str]:
    """Expand ${ENV_VAR} so secrets never live in the config file."""
    if not value:
        return value
    def sub(m: "re.Match[str]") -> str:
        return os.environ.get(m.group(1), "")
    return re.sub(r"\$\{([A-Z0-9_]+)\}", sub, value)
