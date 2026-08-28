"""Live probe collector: measured latency and declared capacity from a running
system. Read-only by construction -- it will only issue GET/HEAD and refuses
anything else, because an analysis harness must never mutate a target.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .core import Evidence, Observation, env_expand

NAME = "probe"
SAFE_METHODS = ("GET", "HEAD")


def _ev(url: str, excerpt: str = "") -> Evidence:
    return Evidence(locator=url, excerpt=excerpt[:200], method="probe")


def _request(url: str, method: str, timeout: float,
             headers: Dict[str, str]) -> "tuple[Optional[int], float, int, Optional[str]]":
    req = urllib.request.Request(url, method=method, headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(200_000)
            return resp.status, (time.perf_counter() - started) * 1000.0, len(body), None
    except urllib.error.HTTPError as exc:
        return exc.code, (time.perf_counter() - started) * 1000.0, 0, None
    except Exception as exc:  # noqa: BLE001
        return None, (time.perf_counter() - started) * 1000.0, 0, type(exc).__name__


def collect(cfg: Dict[str, Any]) -> List[Observation]:
    conf = cfg.get("probe") or {}
    if not conf.get("enabled"):
        return []
    base = (env_expand(conf.get("base_url")) or "").rstrip("/")
    if not base:
        return [Observation("risk", "probe-not-configured", "middleware", collector=NAME,
                            attrs={"severity": "low", "category": "coverage",
                                   "detail": "probe enabled with no base_url"},
                            confidence=1.0, evidence=_ev("config"))]
    samples = int(conf.get("samples") or 5)
    timeout = float(conf.get("timeout_s") or 10)
    headers = {k: env_expand(v) for k, v in (conf.get("headers") or {}).items()}
    headers.setdefault("User-Agent", "analysis-engine/1.0 (read-only)")
    endpoints = conf.get("endpoints") or ["/"]
    out: List[Observation] = []

    for ep in endpoints:
        if isinstance(ep, str):
            path, method, name = ep, "GET", ep
        else:
            path = ep.get("path", "/")
            method = (ep.get("method") or "GET").upper()
            name = ep.get("name") or path
        if method not in SAFE_METHODS:
            out.append(Observation("risk", "probe-unsafe-method:%s" % path, "middleware",
                                   collector=NAME,
                                   attrs={"severity": "low", "category": "coverage",
                                          "detail": "refused %s %s; the probe only issues "
                                                    "GET/HEAD" % (method, path)},
                                   confidence=1.0, evidence=_ev(base + path)))
            continue
        url = base + path
        times: List[float] = []
        sizes: List[int] = []
        statuses: List[int] = []
        error: Optional[str] = None
        for _ in range(max(1, samples)):
            status, ms, size, err = _request(url, method, timeout, headers)
            if err:
                error = err
                break
            times.append(ms)
            sizes.append(size)
            if status is not None:
                statuses.append(status)
            time.sleep(0.05)
        if error or not times:
            out.append(Observation("risk", "probe-failed:%s" % path, "middleware",
                                   collector=NAME,
                                   attrs={"severity": "medium", "category": "availability",
                                          "detail": "%s did not respond (%s)" % (url, error)},
                                   confidence=1.0, evidence=_ev(url)))
            continue
        times.sort()
        p50 = statistics.median(times)
        p95 = times[min(len(times) - 1, int(round(0.95 * (len(times) - 1))))]
        out.append(Observation("metric", "latency:%s" % name, "middleware", collector=NAME,
                               attrs={"value": round(p95, 1), "unit": "ms", "stat": "p95",
                                      "p50_ms": round(p50, 1),
                                      "min_ms": round(times[0], 1),
                                      "max_ms": round(times[-1], 1),
                                      "samples": len(times),
                                      "status_codes": sorted(set(statuses)),
                                      "payload_bytes": int(statistics.mean(sizes)) if sizes else 0,
                                      "endpoint": path, "basis": "measured"},
                               confidence=1.0,
                               evidence=_ev(url, "p95 %.0fms over %d samples" % (p95, len(times)))))
        if p95 > 1000:
            out.append(Observation("risk", "slow-endpoint:%s" % name, "middleware",
                                   collector=NAME,
                                   attrs={"severity": "medium", "category": "performance",
                                          "detail": "%s p95 is %.0f ms measured over %d samples"
                                                    % (path, p95, len(times)),
                                          "p95_ms": round(p95, 1)},
                                   confidence=0.9, evidence=_ev(url)))

    # Headers tell you about the edge: CDN, caching, rate limits, security.
    status, _ms, _size, err = _request(base + "/", "GET", timeout, headers)
    if not err:
        try:
            req = urllib.request.Request(base + "/", method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
        except Exception:  # noqa: BLE001
            hdrs = {}
        for hdr, label in (("cf-ray", "Cloudflare"), ("x-vercel-id", "Vercel"),
                           ("x-amz-cf-id", "CloudFront"), ("x-served-by", "Fastly")):
            if hdr in hdrs:
                out.append(Observation("component", label.lower(), "infrastructure",
                                       collector=NAME,
                                       attrs={"kind": "gateway", "tech": label},
                                       confidence=0.95, evidence=_ev(base, hdr)))
        for hdr in ("x-ratelimit-limit", "ratelimit-limit"):
            if hdr in hdrs:
                out.append(Observation("metric", "ratelimit", "middleware", collector=NAME,
                                       attrs={"value": hdrs[hdr], "unit": "requests",
                                              "basis": "declared"},
                                       confidence=1.0, evidence=_ev(base, hdr)))
        missing = [h for h in ("strict-transport-security", "content-security-policy",
                               "x-content-type-options") if h not in hdrs]
        if missing:
            out.append(Observation("risk", "missing-security-headers", "frontend", collector=NAME,
                                   attrs={"severity": "low", "category": "security",
                                          "detail": "missing response headers: %s"
                                                    % ", ".join(missing)},
                                   confidence=1.0, evidence=_ev(base)))
        if "cache-control" not in hdrs:
            out.append(Observation("risk", "no-cache-control", "frontend", collector=NAME,
                                   attrs={"severity": "low", "category": "performance",
                                          "detail": "no Cache-Control on the root document; "
                                                    "every request is origin traffic"},
                                   confidence=0.8, evidence=_ev(base)))
    return out
