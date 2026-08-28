"""Static collector: everything learnable from source without credentials.

This is the spine. It runs on any target, needs no access beyond a checkout,
and produces the components, edges, entities and risks the rest of the engine
reasons over.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .core import Evidence, Observation

NAME = "repo"

TEXT_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".tf",
    ".tfvars", ".sql", ".md", ".toml", ".cfg", ".ini", ".env", ".sh",
    ".dockerfile", ".txt", ".go", ".rb", ".java", ".cs", ".php",
}
MAX_BYTES = 400_000

# Third-party dependencies that imply an external system on the diagram.
SAAS_MAP = {
    "stripe": ("Stripe", "payments"), "plaid": ("Plaid", "banking-data"),
    "twilio": ("Twilio", "messaging"), "sendgrid": ("SendGrid", "email"),
    "resend": ("Resend", "email"), "posthog": ("PostHog", "analytics"),
    "segment": ("Segment", "analytics"), "datadog": ("Datadog", "observability"),
    "sentry": ("Sentry", "observability"), "auth0": ("Auth0", "identity"),
    "clerk": ("Clerk", "identity"), "okta": ("Okta", "identity"),
    "supabase": ("Supabase", "baas"), "firebase": ("Firebase", "baas"),
    "openai": ("OpenAI API", "llm"), "anthropic": ("Anthropic API", "llm"),
    "cohere": ("Cohere", "llm"), "pinecone": ("Pinecone", "vector-db"),
    "weaviate": ("Weaviate", "vector-db"), "qdrant": ("Qdrant", "vector-db"),
    "elasticsearch": ("Elasticsearch", "search"), "algolia": ("Algolia", "search"),
    "snowflake": ("Snowflake", "warehouse"), "databricks": ("Databricks", "warehouse"),
    "salesforce": ("Salesforce", "crm"), "hubspot": ("HubSpot", "crm"),
    "quickbooks": ("QuickBooks", "accounting"), "shopify": ("Shopify", "commerce"),
}

SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key id", "critical"),
    (r"sk_live_[0-9a-zA-Z]{16,}", "Stripe live secret key", "critical"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key", "critical"),
    (r"(?i)(password|passwd|secret|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", "hardcoded credential", "high"),
    (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.", "embedded JWT", "medium"),
]
SECRET_SAFE_HINTS = ("example", "sample", "test", "fixture", "spec", "mock",
                     "dummy", "placeholder", "changeme", "your_", "xxx")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _walk(root: str, ignore: List[str]) -> Iterable[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore and d != ".git"]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def _read(path: str) -> Optional[str]:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return s or "unnamed"


def _ev(root: str, path: str, line: Optional[int] = None, excerpt: str = "",
        method: str = "static") -> Evidence:
    loc = _rel(root, path) + (":%d" % line if line else "")
    return Evidence(locator=loc, excerpt=excerpt.strip()[:200], method=method)


# --------------------------------------------------------------------------
# per-file-type parsers
# --------------------------------------------------------------------------

def _package_json(root: str, path: str, text: str, out: List[Observation]) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    deps: Dict[str, str] = {}
    for k in ("dependencies", "devDependencies"):
        deps.update(data.get(k) or {})
    name = data.get("name") or os.path.basename(os.path.dirname(path)) or "web"
    tech = "node"
    layer = "middleware"
    for fw, lbl in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"),
                    ("svelte", "Svelte"), ("angular", "Angular")):
        if fw in deps:
            tech, layer = lbl, "frontend"
            break
    if layer != "frontend":
        for fw, lbl in (("express", "Express"), ("fastify", "Fastify"),
                        ("nestjs", "NestJS"), ("@nestjs/core", "NestJS")):
            if fw in deps:
                tech, layer = lbl, "middleware"
                break
    out.append(Observation("component", _slug(name), layer, collector=NAME,
                           attrs={"kind": "page" if layer == "frontend" else "service",
                                  "tech": tech, "dependency_count": len(deps)},
                           confidence=0.9, evidence=_ev(root, path, excerpt=name)))
    _saas_from_deps(root, path, deps.keys(), _slug(name), out)


def _saas_from_deps(root: str, path: str, deps: Iterable[str], caller: str,
                    out: List[Observation]) -> None:
    seen = set()
    for dep in deps:
        low = dep.lower()
        for token, (label, role) in SAAS_MAP.items():
            if token in low and label not in seen:
                seen.add(label)
                key = _slug(label)
                out.append(Observation("component", key, "external", collector=NAME,
                                       attrs={"kind": "saas", "tech": label, "role": role},
                                       confidence=0.75,
                                       evidence=_ev(root, path, excerpt=dep)))
                out.append(Observation("edge", "%s->%s" % (caller, key), "external",
                                       collector=NAME,
                                       attrs={"src": caller, "dst": key, "protocol": "https",
                                              "sync": True, "basis": "inferred"},
                                       confidence=0.6,
                                       evidence=_ev(root, path, excerpt=dep)))


def _python_manifest(root: str, path: str, text: str, out: List[Observation]) -> None:
    deps = re.findall(r"^\s*([A-Za-z0-9_.\-]+)", text, re.M)
    svc = _slug(os.path.basename(os.path.dirname(path)) or "api")
    tech = "python"
    for fw, lbl in (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django")):
        if any(fw == d.lower() for d in deps):
            tech = lbl
    out.append(Observation("component", svc, "middleware", collector=NAME,
                           attrs={"kind": "service", "tech": tech,
                                  "dependency_count": len(deps)},
                           confidence=0.85, evidence=_ev(root, path, excerpt=tech)))
    _saas_from_deps(root, path, deps, svc, out)


def _routes(root: str, path: str, text: str, out: List[Observation]) -> None:
    svc = _slug(os.path.basename(os.path.dirname(path)))
    pats = [
        (r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)", "python"),
        (r"(?:app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)", "node"),
    ]
    found: List[Tuple[str, str, int]] = []
    for pat, _flavour in pats:
        for m in re.finditer(pat, text):
            found.append((m.group(1).upper(), m.group(2), _line_of(text, m.start())))
    for verb, route, line in found[:60]:
        out.append(Observation("config", "route:%s %s" % (verb, route), "middleware",
                               collector=NAME,
                               attrs={"type": "http_route", "verb": verb,
                                      "path": route, "service": svc},
                               confidence=0.85,
                               evidence=_ev(root, path, line, "%s %s" % (verb, route))))


def _sql(root: str, path: str, text: str, out: List[Observation]) -> None:
    for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\((.*?)\)\s*;",
            text, re.S | re.I):
        table, body = m.group(1), m.group(2)
        line = _line_of(text, m.start())
        cols: List[Dict[str, Any]] = []
        for raw in body.split(","):
            raw = raw.strip()
            cm = re.match(
                r"[\"`]?(\w+)[\"`]?\s+([A-Za-z][A-Za-z0-9_]*(?:\s*\([^)]*\))?(?:\s*\[\])?)",
                raw)
            if cm and cm.group(1).upper() not in (
                    "PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT", "CHECK", "INDEX", "KEY"):
                cols.append({"name": cm.group(1), "type": cm.group(2).strip(),
                             "pk": "PRIMARY KEY" in raw.upper(),
                             "nullable": "NOT NULL" not in raw.upper()})
        out.append(Observation("entity", table, "data", collector=NAME,
                               attrs={"columns": cols, "source": "migration"},
                               confidence=0.9,
                               evidence=_ev(root, path, line, "CREATE TABLE %s" % table)))
        for fk in re.finditer(
                r"[\"`]?(\w+)[\"`]?[^,]*REFERENCES\s+[\"`]?(\w+)[\"`]?", body, re.I):
            out.append(Observation("relation", "%s.%s->%s" % (table, fk.group(1), fk.group(2)),
                                   "data", collector=NAME,
                                   attrs={"from": table, "column": fk.group(1),
                                          "to": fk.group(2), "cardinality": "many-to-one"},
                                   confidence=0.9,
                                   evidence=_ev(root, path, line, fk.group(0)[:80])))
    for m in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+[\"`]?(\w+)[\"`]?\s+ON\s+[\"`]?(\w+)[\"`]?\s*\(([^)]*)\)",
                         text, re.I):
        out.append(Observation("config", "index:%s" % m.group(1), "data", collector=NAME,
                               attrs={"type": "index", "table": m.group(2),
                                      "columns": [c.strip().strip('"') for c in m.group(3).split(",")]},
                               confidence=0.9,
                               evidence=_ev(root, path, _line_of(text, m.start()), m.group(0)[:90])))


def _terraform(root: str, path: str, text: str, out: List[Observation]) -> None:
    for m in re.finditer(r'resource\s+"([\w-]+)"\s+"([\w-]+)"\s*\{', text):
        rtype, rname = m.group(1), m.group(2)
        line = _line_of(text, m.start())
        block = text[m.end(): m.end() + 1400]
        attrs: Dict[str, Any] = {"tf_type": rtype, "tf_name": rname}
        for field_name in ("instance_class", "instance_type", "engine", "engine_version",
                           "allocated_storage", "desired_count", "cpu", "memory",
                           "multi_az", "backup_retention_period", "min_size", "max_size",
                           "publicly_accessible", "skip_final_snapshot"):
            fm = re.search(r'\b%s\s*=\s*"?([^"\n]+)"?' % field_name, block)
            if fm:
                attrs[field_name] = fm.group(1).strip()
        layer = "infrastructure"
        kind = "infra"
        if any(t in rtype for t in ("db_instance", "rds_cluster", "dynamodb", "elasticache",
                                    "redshift", "s3_bucket")):
            layer, kind = "data", "store"
        if any(t in rtype for t in ("ecs_service", "lambda_function", "app_runner")):
            layer, kind = "middleware", "service"
        out.append(Observation("component", _slug("%s-%s" % (rtype, rname)), layer,
                               collector=NAME,
                               attrs=dict(attrs, kind=kind, tech=rtype, declared_in="terraform"),
                               confidence=0.85,
                               evidence=_ev(root, path, line, "%s.%s" % (rtype, rname))))
        _tf_risks(root, path, rtype, rname, attrs, line, out)
    if re.search(r'backend\s+"(s3|gcs|azurerm|remote)"', text):
        out.append(Observation("config", "terraform_remote_state", "infrastructure",
                               collector=NAME, attrs={"type": "iac", "remote_state": True},
                               confidence=0.95, evidence=_ev(root, path, excerpt="remote backend")))


def _tf_risks(root: str, path: str, rtype: str, rname: str, attrs: Dict[str, Any],
              line: int, out: List[Observation]) -> None:
    """Resilience and exposure findings readable straight from the code."""
    ident = _slug("%s-%s" % (rtype, rname))
    if "db_instance" in rtype or "rds_cluster" in rtype:
        if str(attrs.get("multi_az", "")).lower() in ("false", "0"):
            out.append(Observation("risk", "rds-single-az:%s" % ident, "data", collector=NAME,
                                   attrs={"severity": "high", "category": "resilience",
                                          "detail": "%s is declared single-AZ; an availability "
                                                    "zone failure is a full outage with a "
                                                    "restore-from-backup recovery time"
                                                    % rname},
                                   confidence=0.95,
                                   evidence=_ev(root, path, line, "multi_az = false")))
        retention = attrs.get("backup_retention_period")
        try:
            if retention is not None and int(retention) < 7:
                out.append(Observation("risk", "rds-backup-window:%s" % ident, "data",
                                       collector=NAME,
                                       attrs={"severity": "high", "category": "resilience",
                                              "detail": "%s keeps %s days of backups; "
                                                        "point-in-time recovery is limited to "
                                                        "that window" % (rname, retention)},
                                       confidence=0.95,
                                       evidence=_ev(root, path, line,
                                                    "backup_retention_period = %s" % retention)))
        except (TypeError, ValueError):
            pass
        if str(attrs.get("publicly_accessible", "")).lower() in ("true", "1"):
            out.append(Observation("risk", "rds-public:%s" % ident, "data", collector=NAME,
                                   attrs={"severity": "critical", "category": "security",
                                          "detail": "%s is declared publicly accessible" % rname},
                                   confidence=0.95,
                                   evidence=_ev(root, path, line, "publicly_accessible = true")))
        if str(attrs.get("skip_final_snapshot", "")).lower() in ("true", "1"):
            out.append(Observation("risk", "rds-no-final-snapshot:%s" % ident, "data",
                                   collector=NAME,
                                   attrs={"severity": "medium", "category": "resilience",
                                          "detail": "%s destroys without a final snapshot"
                                                    % rname},
                                   confidence=0.9,
                                   evidence=_ev(root, path, line, "skip_final_snapshot = true")))
    if "s3_bucket" in rtype and "acl" in attrs and "public" in str(attrs.get("acl", "")):
        out.append(Observation("risk", "s3-public:%s" % ident, "data", collector=NAME,
                               attrs={"severity": "critical", "category": "security",
                                      "detail": "%s has a public ACL" % rname},
                               confidence=0.9, evidence=_ev(root, path, line)))


def _k8s(root: str, path: str, text: str, out: List[Observation]) -> None:
    if not re.search(r"^\s*kind:\s*(Deployment|StatefulSet|DaemonSet|CronJob|Job|HorizontalPodAutoscaler)",
                     text, re.M):
        return
    for doc in re.split(r"^---\s*$", text, flags=re.M):
        km = re.search(r"^\s*kind:\s*(\w+)", doc, re.M)
        nm = re.search(r"^\s*name:\s*([\w.-]+)", doc, re.M)
        if not km or not nm:
            continue
        kind, name = km.group(1), nm.group(1)
        line = _line_of(text, text.find(doc))
        if kind == "HorizontalPodAutoscaler":
            mn = re.search(r"minReplicas:\s*(\d+)", doc)
            mx = re.search(r"maxReplicas:\s*(\d+)", doc)
            tgt = re.search(r"averageUtilization:\s*(\d+)", doc)
            out.append(Observation("config", "hpa:%s" % _slug(name), "infrastructure",
                                   collector=NAME,
                                   attrs={"type": "autoscaling", "target": _slug(name),
                                          "min": int(mn.group(1)) if mn else None,
                                          "max": int(mx.group(1)) if mx else None,
                                          "target_utilisation": int(tgt.group(1)) if tgt else None},
                                   confidence=0.9, evidence=_ev(root, path, line, "HPA %s" % name)))
            continue
        replicas = re.search(r"^\s*replicas:\s*(\d+)", doc, re.M)
        cpu_req = re.search(r"requests:\s*\n(?:\s+\w+:.*\n)*?\s+cpu:\s*[\"']?([\w.]+)", doc)
        mem_req = re.search(r"requests:\s*\n(?:\s+\w+:.*\n)*?\s+memory:\s*[\"']?([\w.]+)", doc)
        has_limits = "limits:" in doc
        attrs = {"kind": "job" if kind in ("Job", "CronJob") else "service",
                 "tech": "kubernetes/%s" % kind,
                 "replicas": int(replicas.group(1)) if replicas else None,
                 "cpu_request": cpu_req.group(1) if cpu_req else None,
                 "mem_request": mem_req.group(1) if mem_req else None,
                 "has_limits": has_limits,
                 "workload_kind": kind}
        out.append(Observation("component", _slug(name),
                               "data" if kind == "StatefulSet" else "middleware",
                               collector=NAME, attrs=attrs, confidence=0.9,
                               evidence=_ev(root, path, line, "%s/%s" % (kind, name))))
        if not cpu_req or not has_limits:
            out.append(Observation("risk", "k8s-resources:%s" % _slug(name), "infrastructure",
                                   collector=NAME,
                                   attrs={"severity": "medium", "category": "capacity",
                                          "detail": "workload %s is missing resource %s" %
                                                    (name, "requests" if not cpu_req else "limits")},
                                   confidence=0.9, evidence=_ev(root, path, line)))


def _compose(root: str, path: str, text: str, out: List[Observation]) -> None:
    m = re.search(r"^services:\s*$", text, re.M)
    if not m:
        return
    for sm in re.finditer(r"^  ([\w.-]+):\s*$", text[m.end():], re.M):
        name = sm.group(1)
        out.append(Observation("component", _slug(name), "middleware", collector=NAME,
                               attrs={"kind": "service", "tech": "docker-compose"},
                               confidence=0.7,
                               evidence=_ev(root, path, _line_of(text, m.end() + sm.start()), name)))


def _ci(root: str, path: str, text: str, out: List[Observation]) -> None:
    triggers = []
    for t in ("push", "pull_request", "workflow_dispatch", "schedule", "release"):
        if re.search(r"^\s*%s:" % t, text, re.M):
            triggers.append(t)
    deploys = bool(re.search(r"(?i)(deploy|terraform apply|kubectl apply|vercel|helm upgrade)", text))
    out.append(Observation("config", "pipeline:%s" % os.path.basename(path), "infrastructure",
                           collector=NAME,
                           attrs={"type": "cicd", "triggers": triggers, "deploys": deploys,
                                  "mode": "git" if "push" in triggers or "pull_request" in triggers
                                          else "manual"},
                           confidence=0.9,
                           evidence=_ev(root, path, excerpt=",".join(triggers))))


def _env_refs(root: str, path: str, text: str, out: List[Observation]) -> None:
    for m in re.finditer(r"(?:process\.env\.|os\.environ(?:\.get)?[\[(]['\"]?)([A-Z][A-Z0-9_]{3,})",
                         text):
        name = m.group(1)
        low = name.lower()
        for token, (label, role) in SAAS_MAP.items():
            if token in low:
                key = _slug(label)
                out.append(Observation("component", key, "external", collector=NAME,
                                       attrs={"kind": "saas", "tech": label, "role": role},
                                       confidence=0.6,
                                       evidence=_ev(root, path, _line_of(text, m.start()), name)))
        if any(k in low for k in ("database_url", "db_host", "postgres", "mysql")):
            out.append(Observation("component", "primary-database", "data", collector=NAME,
                                   attrs={"kind": "store", "tech": "relational"},
                                   confidence=0.7,
                                   evidence=_ev(root, path, _line_of(text, m.start()), name)))


def _secrets(root: str, path: str, text: str, out: List[Observation]) -> None:
    rel = _rel(root, path).lower()
    if any(h in rel for h in SECRET_SAFE_HINTS):
        return
    for pat, label, severity in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            snippet = m.group(0)
            if any(h in snippet.lower() for h in SECRET_SAFE_HINTS):
                continue
            out.append(Observation("risk", "secret:%s:%s" % (_slug(label), _rel(root, path)),
                                   "infrastructure", collector=NAME,
                                   attrs={"severity": severity, "category": "security",
                                          "detail": "%s committed to the repository" % label},
                                   confidence=0.85,
                                   evidence=_ev(root, path, _line_of(text, m.start()),
                                                snippet[:24] + "...")))
            break


def _openapi(root: str, path: str, text: str, out: List[Observation]) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    if "paths" not in data or "openapi" not in data and "swagger" not in data:
        return
    for route, ops in (data.get("paths") or {}).items():
        for verb in ops:
            if verb.lower() in ("get", "post", "put", "patch", "delete"):
                out.append(Observation("config", "route:%s %s" % (verb.upper(), route),
                                       "middleware", collector=NAME,
                                       attrs={"type": "http_route", "verb": verb.upper(),
                                              "path": route, "service": "api",
                                              "documented": True},
                                       confidence=0.95,
                                       evidence=_ev(root, path, excerpt=route)))


# --------------------------------------------------------------------------

def collect(cfg: Dict[str, Any]) -> List[Observation]:
    root = os.path.abspath(cfg["repo"]["path"])
    ignore = cfg["repo"].get("ignore") or []
    out: List[Observation] = []
    if not os.path.isdir(root):
        raise SystemExit("repo path does not exist: %s" % root)

    files = 0
    loc = 0
    langs: Dict[str, int] = {}
    has_ci = False
    has_iac = False
    has_tests = False

    for path in _walk(root, ignore):
        base = os.path.basename(path)
        ext = os.path.splitext(base)[1].lower()
        rel = _rel(root, path)
        if ext in TEXT_EXT or base in ("Dockerfile", "Makefile"):
            files += 1
            langs[ext or base] = langs.get(ext or base, 0) + 1
        if "test" in rel.lower() or "spec" in rel.lower():
            has_tests = True
        text = _read(path)
        if text is None:
            continue
        loc += text.count("\n")

        if base == "package.json":
            _package_json(root, path, text, out)
        elif base in ("requirements.txt", "pyproject.toml", "Pipfile"):
            _python_manifest(root, path, text, out)
        if ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb"):
            _routes(root, path, text, out)
            _env_refs(root, path, text, out)
        if ext == ".sql":
            _sql(root, path, text, out)
        if ext in (".tf", ".tfvars"):
            has_iac = True
            _terraform(root, path, text, out)
        if ext in (".yml", ".yaml"):
            _k8s(root, path, text, out)
            if base.startswith("docker-compose"):
                _compose(root, path, text, out)
            if ".github/workflows" in rel or "gitlab-ci" in base or "buildkite" in rel:
                has_ci = True
                _ci(root, path, text, out)
        if base.lower() in ("openapi.json", "swagger.json"):
            _openapi(root, path, text, out)
        if ext in TEXT_EXT and ext not in (".md",):
            _secrets(root, path, text, out)

    out.append(Observation("metric", "repo.files", "infrastructure", collector=NAME,
                           attrs={"value": files, "unit": "files"}, confidence=1.0,
                           evidence=Evidence(locator="(repository root)", method="static")))
    out.append(Observation("metric", "repo.lines", "infrastructure", collector=NAME,
                           attrs={"value": loc, "unit": "lines"}, confidence=1.0,
                           evidence=Evidence(locator="(repository root)", method="static")))
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    out.append(Observation("metric", "repo.file_mix", "infrastructure", collector=NAME,
                           attrs={"value": dict(top), "unit": "files_by_ext"}, confidence=1.0,
                           evidence=Evidence(locator="(repository root)", method="static")))

    if not has_ci:
        out.append(Observation("risk", "no-ci-pipeline", "infrastructure", collector=NAME,
                               attrs={"severity": "high", "category": "delivery",
                                      "detail": "no CI/CD workflow found; deployment is manual "
                                                "and unaudited"},
                               confidence=0.7, evidence=Evidence(locator="(repository root)", method="static")))
    if not has_iac:
        out.append(Observation("risk", "no-iac", "infrastructure", collector=NAME,
                               attrs={"severity": "high", "category": "reproducibility",
                                      "detail": "no infrastructure-as-code found; the "
                                                "environment cannot be reconstructed from source"},
                               confidence=0.7, evidence=Evidence(locator="(repository root)", method="static")))
    if not has_tests:
        out.append(Observation("risk", "no-tests", "middleware", collector=NAME,
                               attrs={"severity": "medium", "category": "quality",
                                      "detail": "no test or spec files found"},
                               confidence=0.6, evidence=Evidence(locator="(repository root)", method="static")))
    return out
