"""Recommendation engine: findings -> ranked, executable roadmap.

Every recommendation carries an action block an agent can run without a human
translating it first: the prompt, the files it should touch, the acceptance
test, and the deployment trigger that already exists in the target repo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .core import EvidenceStore

SEVERITY_IMPACT = {"critical": 10.0, "high": 7.0, "medium": 4.0, "low": 2.0}
CATEGORY_EFFORT = {
    "security": 1.0, "capacity": 2.0, "performance": 3.0, "resilience": 3.0,
    "delivery": 5.0, "reproducibility": 8.0, "quality": 8.0, "cost": 2.0,
    "coverage": 0.5, "architecture": 10.0,
}


def _rec(rid: str, title: str, finding: str, layer: str, category: str,
         impact: float, effort_days: float, confidence: float,
         action: Dict[str, Any], kpi: str, evidence: List[str],
         math: Optional[str] = None) -> Dict[str, Any]:
    score = (impact * confidence) / max(effort_days, 0.5)
    return {
        "id": rid, "title": title, "finding": finding, "layer": layer,
        "category": category, "impact": round(impact, 1),
        "effort_days": effort_days, "confidence": round(confidence, 2),
        "score": round(score, 2), "action": action, "kpi": kpi,
        "evidence": evidence[:4], "math": math,
    }


def _trigger(store: EvidenceStore) -> Dict[str, Any]:
    """Tie every action back to how this repo actually deploys."""
    pipelines = [o for o in store.of_kind("config") if o.attrs.get("type") == "cicd"]
    deploying = [p for p in pipelines if p.attrs.get("deploys")]
    if deploying:
        p = deploying[0]
        return {"mode": p.attrs.get("mode", "git"),
                "detail": "open a PR; %s runs on %s" % (
                    p.key.split(":", 1)[-1], ", ".join(p.attrs.get("triggers") or ["push"])),
                "gate": "CI green + human approval on the PR"}
    if pipelines:
        return {"mode": "git", "detail": "CI exists but no deploy step was found; "
                                         "the change ships manually after merge",
                "gate": "human approval"}
    return {"mode": "manual", "detail": "no pipeline detected; this change must be applied "
                                        "and deployed by hand",
            "gate": "human execution and verification"}


def build(store: EvidenceStore, graph, capacity: Dict[str, Any],
          entities: Dict[str, Any], ontology: Dict[str, Any],
          growth: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trig = _trigger(store)
    recs: List[Dict[str, Any]] = []

    # ---- 1. risks recorded by collectors --------------------------------
    for o in store.of_kind("risk"):
        sev = o.attrs.get("severity", "low")
        cat = o.attrs.get("category", "quality")
        if cat == "coverage":
            continue
        impact = SEVERITY_IMPACT.get(sev, 2.0)
        effort = CATEGORY_EFFORT.get(cat, 3.0)
        detail = o.attrs.get("detail", o.key)
        recs.append(_rec(
            rid="R-%s" % o.key.split(":")[0][:24],
            title=_title_for(o.key, detail),
            finding=detail, layer=o.layer, category=cat,
            impact=impact, effort_days=effort, confidence=o.confidence,
            action=_action_for(o, detail, trig),
            kpi=_kpi_for(cat), evidence=[o.evidence.locator]))

    # ---- 2. capacity findings -------------------------------------------
    target = capacity["target_utilisation"]
    for row in capacity["rows"]:
        if not row["over_target"]:
            continue
        need = row["peak_rps"] / (target * row["capacity_rps"]) if row["capacity_rps"] else 1
        math_line = ("peak %.2f rps against %.2f rps capacity = %.0f%% utilisation; "
                     "M/M/1 queue wait %s ms. Reaching the %.0f%% target needs %.1fx "
                     "the current capacity." % (
                         row["peak_rps"], row["capacity_rps"], row["utilisation"] * 100,
                         row["queue_wait_ms"] if row["queue_wait_ms"] else "n/a",
                         target * 100, need))
        recs.append(_rec(
            rid="R-capacity-%s" % row["component"],
            title="Scale %s before it saturates" % row["component"],
            finding="%s runs at %.0f%% of estimated capacity at peak, above the %.0f%% "
                    "target. Break point is roughly %s events/day." % (
                        row["component"], row["utilisation"] * 100, target * 100,
                        format(row["break_point_per_day"], ",") if row["break_point_per_day"]
                        else "unknown"),
            layer=row["layer"], category="capacity",
            impact=9.0 if row["utilisation"] > 0.9 else 6.0,
            effort_days=2.0,
            confidence=0.6 if row["capacity_basis"] == "assumed" else 0.9,
            action={
                "agent_prompt": "Raise capacity of %s by %.1fx. If it is a Kubernetes workload, "
                                "add or widen an HPA and set resource requests from observed "
                                "usage. If it is a managed service, size up one tier. Add a "
                                "load test that drives %.1f rps and asserts p95 under 500 ms."
                                % (row["component"], need, row["peak_rps"]),
                "files": ["k8s/*%s*.yaml" % row["component"], "infra/**/*.tf"],
                "acceptance": "sustained %.1f rps with utilisation below %.0f%% and no "
                              "error-rate change" % (row["peak_rps"], target * 100),
                "trigger": trig, "autonomy": "agent-drafted, human-approved"},
            kpi="peak utilisation of %s" % row["component"],
            evidence=["capacity model"], math=math_line))

    # ---- 3. the single bottleneck ---------------------------------------
    b = capacity.get("bottleneck")
    if b and b["utilisation"] > 0.4:
        recs.append(_rec(
            rid="R-bottleneck", title="Instrument the binding constraint: %s" % b["component"],
            finding="%s is the highest-utilisation element on the critical path (%.0f%%). "
                    "Its capacity is %s, so the number that decides the system's ceiling is "
                    "currently %s." % (
                        b["component"], b["utilisation"] * 100, b["capacity_basis"],
                        "measured" if b["capacity_basis"] == "measured" else "an assumption"),
            layer=b["layer"], category="capacity", impact=7.0, effort_days=1.0,
            confidence=0.9,
            action={
                "agent_prompt": "Add request-level instrumentation to %s: p50/p95/p99 latency, "
                                "in-flight concurrency and saturation, exported to the existing "
                                "metrics backend. Then replace the assumed service time in "
                                "target.json with the measured value and re-run the analysis."
                                % b["component"],
                "files": ["**/%s/**" % b["component"], "target.json"],
                "acceptance": "capacity_basis for %s reads 'measured' on the next run"
                              % b["component"],
                "trigger": trig, "autonomy": "agent-executable"},
            kpi="measured p95 and concurrency for %s" % b["component"],
            evidence=["capacity model"],
            math="utilisation %.0f%%, headroom %.1fx" % (
                b["utilisation"] * 100, b["headroom_x"] or 0)))

    # ---- 4. data growth --------------------------------------------------
    for g in growth[:2]:
        if (g["multiple"] or 0) >= 3 and g["rows_now"] > 50_000:
            recs.append(_rec(
                rid="R-growth-%s" % g["entity"],
                title="Plan partitioning or archival for %s" % g["entity"],
                finding="%s holds %s rows and projects to %s in %d months (%.1fx). Query "
                        "plans and index maintenance degrade well before that." % (
                            g["entity"], format(g["rows_now"], ","),
                            format(g["rows_at_horizon"], ","), g["horizon_months"],
                            g["multiple"]),
                layer="data", category="performance", impact=6.0, effort_days=4.0,
                confidence=0.7,
                action={
                    "agent_prompt": "Propose a retention and partitioning strategy for %s: "
                                    "range-partition by created date, move rows older than the "
                                    "retention window to cold storage, and add the covering "
                                    "indexes the hot queries need. Produce the migration and a "
                                    "rollback." % g["entity"],
                    "files": ["**/migrations/**"],
                    "acceptance": "hot table stays under 20M rows at the 24-month projection",
                    "trigger": trig, "autonomy": "agent-drafted, DBA-reviewed"},
                kpi="row count and p95 query time on %s" % g["entity"],
                evidence=["growth projection"],
                math="%s rows + %s/day x 30 x %d = %s" % (
                    format(g["rows_now"], ","), format(g["growth_per_day"], ","),
                    g["horizon_months"], format(g["rows_at_horizon"], ","))))

    # ---- 5. unit economics ------------------------------------------------
    econ = ontology.get("unit_economics") or {}
    if econ.get("complete"):
        margin = econ.get("contribution_margin_pct")
        if margin is not None and margin < 60:
            recs.append(_rec(
                rid="R-margin", title="Contribution margin is %.0f%% -- attack variable cost"
                                      % margin,
                finding="Each %s earns $%.4f and costs $%.4f to serve, leaving $%.4f. "
                        "Infrastructure is $%.6f of that." % (
                            econ["unit"], econ["price_per_unit"],
                            econ["variable_cost_per_unit"], econ["contribution_per_unit"],
                            econ["infra_cost_per_unit"] or 0),
                layer="infrastructure", category="cost",
                impact=8.0 if margin < 40 else 5.0, effort_days=3.0, confidence=0.8,
                action={
                    "agent_prompt": "Produce a cost-per-unit teardown: allocate every "
                                    "infrastructure line to the use case that drives it, rank "
                                    "by dollars per 1,000 units, and identify the three cheapest "
                                    "reductions (right-sizing, caching, batching, tier change). "
                                    "Quantify each in dollars per month.",
                    "files": ["infra/**", "target.json"],
                    "acceptance": "contribution margin above 60% at current volume",
                    "trigger": {"mode": "manual", "detail": "analysis, not a code change",
                                "gate": "review"},
                    "autonomy": "agent-executable"},
                kpi="contribution margin per %s" % econ["unit"],
                evidence=["unit economics"],
                math="$%.4f price - $%.6f variable = $%.4f contribution (%.0f%%)" % (
                    econ["price_per_unit"], econ["variable_cost_per_unit"],
                    econ["contribution_per_unit"], margin)))

    link = ontology.get("scaling_link") or {}
    if link.get("months_of_headroom") is not None and link["months_of_headroom"] < 18:
        recs.append(_rec(
            rid="R-runway", title="Capacity runway is %.0f months at the stated growth rate"
                                  % link["months_of_headroom"],
            finding="At %.0f%% monthly growth the system reaches its break point in about "
                    "%.0f months. The binding element is %s." % (
                        (link["growth_rate_monthly"] or 0) * 100,
                        link["months_of_headroom"], link.get("bottleneck")),
            layer="infrastructure", category="capacity", impact=9.0, effort_days=5.0,
            confidence=0.7,
            action={
                "agent_prompt": "Draft a staged capacity plan for the next 24 months: for each "
                                "quarter give projected volume, the component that saturates "
                                "first, the change required, and its monthly cost delta.",
                "files": ["docs/**"], "acceptance": "24 months of headroom at plan",
                "trigger": {"mode": "manual", "detail": "planning artefact", "gate": "review"},
                "autonomy": "agent-executable"},
            kpi="months of capacity headroom",
            evidence=["ontology.scaling_link"],
            math="ln(break_point/current) / ln(1+growth) = %.1f months"
                 % link["months_of_headroom"]))

    # ---- dedupe + rank ----------------------------------------------------
    seen: Dict[str, Dict[str, Any]] = {}
    for r in recs:
        cur = seen.get(r["id"])
        if cur is None or r["score"] > cur["score"]:
            seen[r["id"]] = r
    ranked = sorted(seen.values(), key=lambda r: -r["score"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["horizon"] = ("now" if i <= 3 else "next" if i <= 8 else "later")
    return ranked


def _title_for(key: str, detail: str) -> str:
    head = key.split(":")[0]
    titles = {
        "no-ci-pipeline": "Put deployment behind a pipeline",
        "no-iac": "Codify the environment",
        "no-tests": "Establish a test baseline",
        "secret": "Remove committed credentials and rotate",
        "k8s-resources": "Set resource requests and limits",
        "rds-single-az": "Make the database multi-AZ",
        "rds-backup-window": "Extend backup retention",
        "rds-public": "Remove public database access",
        "unindexed-fk": "Index the foreign key",
        "slow-endpoint": "Fix the slow endpoint",
        "missing-security-headers": "Add security response headers",
        "no-cache-control": "Add cache headers at the edge",
        "probe-failed": "Restore the unreachable endpoint",
    }
    return titles.get(head, detail[:70])


def _kpi_for(category: str) -> str:
    return {
        "security": "open critical findings",
        "capacity": "peak utilisation",
        "performance": "p95 latency",
        "resilience": "RTO / RPO",
        "delivery": "lead time to production",
        "reproducibility": "percentage of infrastructure reconcilable from code",
        "quality": "test coverage on changed lines",
        "cost": "cost per 1,000 events",
    }.get(category, "finding closed")


def _action_for(o, detail: str, trig: Dict[str, Any]) -> Dict[str, Any]:
    head = o.key.split(":")[0]
    loc = o.evidence.locator
    library = {
        "secret": {
            "agent_prompt": "Remove the credential at %s, replace it with a reference to the "
                            "secret manager, purge it from git history, and open a rotation "
                            "ticket naming the exposed key." % loc,
            "files": [loc.split(":")[0]],
            "acceptance": "secret scanner passes on full history; key rotated",
            "autonomy": "agent-drafted, human-approved (rotation is manual)"},
        "no-ci-pipeline": {
            "agent_prompt": "Create a CI workflow that runs lint, tests and a build on every "
                            "pull request, then a deploy job gated on the default branch. Use "
                            "the existing build commands rather than inventing new ones.",
            "files": [".github/workflows/ci.yml"],
            "acceptance": "every merge to the default branch produces an audited deployment",
            "autonomy": "agent-executable"},
        "no-iac": {
            "agent_prompt": "Import the running infrastructure into Terraform: write provider "
                            "and backend configuration with remote state and locking, import "
                            "the existing resources, and prove a plan against production is "
                            "empty.",
            "files": ["infra/terraform/**"],
            "acceptance": "terraform plan against production returns no changes",
            "autonomy": "agent-drafted, human-approved"},
        "no-tests": {
            "agent_prompt": "Add a test harness and cover the highest-traffic path end to end. "
                            "Wire it into CI and fail the build on regression.",
            "files": ["tests/**"], "acceptance": "critical path covered, CI enforcing",
            "autonomy": "agent-executable"},
        "k8s-resources": {
            "agent_prompt": "Set CPU and memory requests and limits on the workload at %s using "
                            "observed usage; if no metrics exist, set requests conservatively "
                            "and add the metric first." % loc,
            "files": [loc.split(":")[0]],
            "acceptance": "no workload schedulable without requests; no OOMKills after rollout",
            "autonomy": "agent-executable"},
        "rds-single-az": {
            "agent_prompt": "Change the database to multi-AZ in Terraform, plan it, and state "
                            "the failover window and cost delta in the PR description.",
            "files": ["infra/**/*.tf"], "acceptance": "multi_az = true in state and in code",
            "autonomy": "agent-drafted, human-approved (causes failover)"},
        "rds-public": {
            "agent_prompt": "Set publicly_accessible to false, move the instance into private "
                            "subnets, and route application access through the existing VPC "
                            "path. Enumerate every client that will break first.",
            "files": ["infra/**/*.tf"], "acceptance": "no public endpoint; app connectivity intact",
            "autonomy": "agent-drafted, human-approved"},
        "unindexed-fk": {
            "agent_prompt": "Create a concurrent index on %s, measure the affected query before "
                            "and after, and include both plans in the PR." % o.key.split(":")[-1],
            "files": ["**/migrations/**"],
            "acceptance": "index present; the join drops out of sequential scan",
            "autonomy": "agent-executable"},
        "slow-endpoint": {
            "agent_prompt": "Profile the endpoint named in the finding, identify whether the "
                            "time is in query, serialisation or an upstream call, and fix the "
                            "dominant term. Add a latency regression test.",
            "files": ["**"], "acceptance": "p95 under 500 ms measured over 20 samples",
            "autonomy": "agent-executable"},
    }
    base = library.get(head, {
        "agent_prompt": "Resolve: %s. Cite the evidence at %s, make the smallest change that "
                        "closes the finding, and add the test that keeps it closed."
                        % (detail, loc),
        "files": [loc.split(":")[0] if ":" in loc else "**"],
        "acceptance": "finding no longer reported on the next run",
        "autonomy": "agent-drafted, human-approved"})
    return dict(base, trigger=trig)
