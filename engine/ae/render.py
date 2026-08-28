"""Renderers: Mermaid diagrams, the markdown document set, and one HTML
dashboard. Presentation only -- no analysis happens in this module.
"""
from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Dict, List, Optional

LAYER_TITLES = {
    "external": "External / actors",
    "frontend": "Front end",
    "middleware": "Middleware / APIs",
    "backend": "Back end",
    "data": "Data",
    "infrastructure": "Infrastructure",
}
LAYER_ORDER = ["external", "frontend", "middleware", "backend", "data", "infrastructure"]


def _mid(key: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", key)


def _fmt(v: Any, dash: str = "--") -> str:
    if v is None or v == "":
        return dash
    if isinstance(v, float):
        return ("%.2f" % v).rstrip("0").rstrip(".")
    if isinstance(v, int):
        return format(v, ",")
    return str(v)


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    if not rows:
        return "_No rows._\n"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_fmt(c) for c in r) + " |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Mermaid
# --------------------------------------------------------------------------

def context_diagram(graph, flows: List[Dict[str, Any]]) -> str:
    lines = ["flowchart LR"]
    layers = graph.layers()
    flow_by_edge = {f["edge"]: f for f in flows}
    for ly in LAYER_ORDER:
        comps = layers.get(ly) or []
        if not comps:
            continue
        lines.append('  subgraph %s["%s"]' % (_mid(ly), LAYER_TITLES.get(ly, ly)))
        lines.append("    direction TB")
        for c in comps:
            label = c.key if not c.tech else "%s<br/><small>%s</small>" % (c.key, c.tech)
            shape = ('(["%s"])' % label if c.kind == "actor" else
                     '[("%s")]' % label if c.kind == "store" else
                     '[/"%s"/]' % label if c.kind == "job" else
                     '["%s"]' % label)
            lines.append("    %s%s" % (_mid(c.key), shape))
        lines.append("  end")
    for e in sorted(graph.edges.values(), key=lambda x: x.key):
        f = flow_by_edge.get(e.key) or {}
        bits = [e.protocol]
        if f.get("peak_rps"):
            bits.append("%.2g rps" % f["peak_rps"])
        if not e.sync:
            bits.append("async")
        arrow = "-->" if e.sync else "-.->"
        lines.append("  %s %s|%s| %s" % (_mid(e.src), arrow, " · ".join(bits), _mid(e.dst)))
    return "\n".join(lines)


def erd_diagram(entities: Dict[str, Any], limit: int = 30) -> str:
    ents = entities["entities"]
    keep = sorted(ents.values(), key=lambda e: -(e.get("row_count") or 0))[:limit]
    names = {e["name"] for e in keep}
    lines = ["erDiagram"]
    for rel in entities["relations"]:
        if rel["from"] in names and rel["to"] in names:
            lines.append('  %s ||--o{ %s : "%s"' % (
                _safe_ent(rel["to"]), _safe_ent(rel["from"]), rel.get("column") or "fk"))
    for e in keep:
        lines.append("  %s {" % _safe_ent(e["name"]))
        for c in (e.get("columns") or [])[:12]:
            t = re.sub(r"[^a-zA-Z0-9_]", "_", str(c.get("type", "text")))[:20] or "text"
            nm = re.sub(r"[^a-zA-Z0-9_]", "_", str(c.get("name", "col")))
            lines.append("    %s %s%s" % (t, nm, " PK" if c.get("pk") else ""))
        lines.append("  }")
    return "\n".join(lines)


def _safe_ent(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


# --------------------------------------------------------------------------
# Markdown documents
# --------------------------------------------------------------------------

def _header(title: str, target: Dict[str, Any], subtitle: str) -> str:
    return ("# %s\n\n**System:** %s  \n**Generated:** %s  \n**Engine:** analysis-engine 1.0\n\n"
            "%s\n\n" % (title, target.get("name", "unnamed"),
                        time.strftime("%Y-%m-%d %H:%M"), subtitle))


def architecture_md(target, graph, flows, store) -> str:
    out = [_header("01 · Context architecture", target,
                   "The context layer: every component the engine could observe, placed in the "
                   "layer it belongs to, and every transfer process between them. Components "
                   "are drawn only where evidence exists; absence on this diagram means "
                   "*not observed*, not *not present*.")]
    out.append("## Context diagram\n\n```mermaid\n%s\n```\n" % context_diagram(graph, flows))
    out.append("## Component inventory\n")
    rows = []
    for ly in LAYER_ORDER:
        for c in graph.layers().get(ly) or []:
            rows.append([LAYER_TITLES.get(ly, ly), c.key, c.kind, c.tech,
                         c.replicas, c.p95_ms, c.monthly_cost,
                         (c.evidence or ["--"])[0]])
    out.append(_table(["Layer", "Component", "Kind", "Technology", "Replicas",
                       "p95 ms", "$/month", "Evidence"], rows))
    counts = store.counts()
    out.append("\n## Evidence base\n")
    out.append(_table(["Observation kind", "Count"],
                      [[k, v] for k, v in sorted(counts.items())]))
    gaps = [o for o in store.of_kind("risk") if o.attrs.get("category") == "coverage"]
    if gaps:
        out.append("\n## Coverage gaps\n\nThese collectors did not return. "
                   "Findings in their areas are **absent, not clean**.\n\n")
        out.append(_table(["Gap", "Detail"],
                          [[g.key, g.attrs.get("detail")] for g in gaps]))
    return "\n".join(out)


def flows_md(target, flows, capacity) -> str:
    out = [_header("02 · Transfer processes", target,
                   "Every edge in the graph with its frequency, payload and measured or "
                   "assumed latency. The `basis` column is the one that matters: "
                   "`measured` came from a live probe, `assumed` came from a default.")]
    rows = [[f["edge"], f["protocol"], f["mode"], f["calls_per_request"],
             round(f["peak_rps"], 3) if f["peak_rps"] else None,
             f["payload_bytes"], f["throughput_bps"], f["p95_ms"],
             ("%.0f%%" % (f["downstream_utilisation"] * 100)
              if f["downstream_utilisation"] is not None else "--"),
             f["basis"]] for f in flows]
    out.append(_table(["Transfer", "Protocol", "Mode", "Calls/req", "Peak rps",
                       "Payload bytes", "Bytes/s", "p95 ms", "Downstream util", "Basis"], rows))
    b = capacity.get("bottleneck")
    if b:
        out.append("\n## Binding constraint\n")
        out.append("**%s** carries the highest utilisation on the critical path at "
                   "**%.0f%%** of estimated capacity (%.2f rps against %.2f rps). "
                   "Everything upstream of it can only go as fast as it does.\n"
                   % (b["component"], b["utilisation"] * 100, b["peak_rps"],
                      b["capacity_rps"]))
        if b["queue_wait_ms"]:
            out.append("\nAt that utilisation an M/M/1 approximation puts queue wait at "
                       "**%.0f ms** on top of service time. Queue wait rises as "
                       "1/(1-ρ), so the next 10 points of utilisation cost far more "
                       "latency than the last ten did.\n" % b["queue_wait_ms"])
    asyncs = [f for f in flows if f["mode"] == "async"]
    out.append("\n## Synchrony\n\n%d of %d transfers are synchronous. Each synchronous hop "
               "adds its latency and its failure probability to the caller.\n"
               % (len(flows) - len(asyncs), len(flows)))
    return "\n".join(out)


def erd_md(target, entities, growth) -> str:
    ents = entities["entities"]
    out = [_header("03 · Entity model", target,
                   "The persisted business objects, their relationships, and how fast they "
                   "grow. Row counts appear only where the database collector ran.")]
    out.append("## ERD\n\n```mermaid\n%s\n```\n" % erd_diagram(entities))
    out.append("## Data dictionary\n")
    rows = [[e["name"], len(e.get("columns") or []), e.get("row_count"),
             "yes" if e.get("money_bearing") else "", "yes" if e.get("identity_bearing") else "",
             len(e.get("indexes") or []), e.get("source"), e.get("evidence")]
            for e in sorted(ents.values(), key=lambda x: x["name"])]
    out.append(_table(["Entity", "Columns", "Rows", "Money", "Identity", "Indexes",
                       "Source", "Evidence"], rows))
    if growth:
        out.append("\n## Growth projection\n")
        out.append(_table(["Entity", "Rows now", "Rows/day", "Rows at horizon",
                           "Multiple", "Horizon (months)"],
                          [[g["entity"], g["rows_now"], g["growth_per_day"],
                            g["rows_at_horizon"], g["multiple"], g["horizon_months"]]
                           for g in growth]))
    return "\n".join(out)


def capacity_md(target, capacity, usecases, cfg) -> str:
    out = [_header("04 · Scaling math", target,
                   "Capacity, utilisation and break point for every component, driven by the "
                   "use cases below. Read the basis columns before quoting any number.")]
    out.append("## Use cases driving load\n")
    out.append(_table(["Use case", "Path", "Events/day", "Peak factor", "Basis"],
                      [[u["name"], " → ".join(u["path"]), u["volume_per_day"],
                        u["peak_factor"], u["basis"]] for u in usecases]))
    out.append("\n## Method\n\n"
               "- Peak arrival rate `λ = events per day ÷ 86,400 × peak factor`, "
               "multiplied by calls per request on each hop.\n"
               "- Component capacity `μ = replicas × concurrency ÷ service time`; "
               "stores are bounded by connection pool rather than replicas.\n"
               "- Utilisation `ρ = λ ÷ μ`. Queue wait uses the M/M/1 term "
               "`ρ ÷ (μ(1−ρ))`, which is why the target is %.0f%% and not 100%%.\n"
               "- Break point is the daily volume at which `ρ = 1` holding the traffic "
               "mix constant.\n" % (capacity["target_utilisation"] * 100))
    out.append("\n## Component capacity\n")
    rows = [[r["component"], r["layer"], r["replicas"], r["p95_ms"],
             round(r["capacity_rps"], 2), r["capacity_basis"], round(r["peak_rps"], 3),
             "%.0f%%" % (r["utilisation"] * 100),
             round(r["headroom_x"], 2) if r["headroom_x"] else None,
             round(r["queue_wait_ms"], 1) if r["queue_wait_ms"] else None,
             r["break_point_per_day"],
             "OVER" if r["over_target"] else ""]
            for r in sorted(capacity["rows"], key=lambda x: -x["utilisation"])]
    out.append(_table(["Component", "Layer", "Replicas", "p95 ms", "Capacity rps",
                       "Basis", "Peak rps", "Utilisation", "Headroom", "Queue ms",
                       "Break point/day", "Flag"], rows))
    out.append("\n## System ceiling\n")
    sb = capacity.get("system_break_point_per_day")
    out.append("- Current modelled load: **%s events/day**\n" % _fmt(capacity["total_daily_events"]))
    out.append("- First component to saturate: **%s**\n"
               % ((capacity.get("bottleneck") or {}).get("component") or "n/a"))
    out.append("- System break point: **%s events/day**%s\n" % (
        _fmt(sb),
        (" (%.1fx today's volume)" % (sb / capacity["total_daily_events"]))
        if sb and capacity["total_daily_events"] else ""))
    if capacity.get("monthly_infra_cost"):
        out.append("- Infrastructure cost (%s): **$%s/month**, "
                   "**$%s per 1,000 events**\n" % (
                       capacity.get("cost_basis", "unknown"),
                       _fmt(capacity["monthly_infra_cost"]),
                       _fmt(capacity.get("cost_per_1k_events"))))
    a = cfg["assumptions"]
    out.append("\n## Assumption ledger\n\nEvery figure above that is not marked "
               "`measured` or `declared` rests on these. Change them in `target.json` "
               "and re-run.\n\n")
    out.append(_table(["Assumption", "Value"], [[k, v] for k, v in sorted(a.items())]))
    return "\n".join(out)


def ontology_md(target, ontology) -> str:
    out = [_header("05 · Business and financial ontology", target,
                   "What the code says about the business, kept strictly apart from what a "
                   "human told us. Unanswered items are listed as open questions rather "
                   "than filled with plausible guesses.")]
    if ontology.get("purpose"):
        out.append("**Stated purpose:** %s\n" % ontology["purpose"])
    out.append("\n## Business objects\n")
    out.append(_table(["Entity", "Class", "Rows", "Attributes", "Indexed", "Basis"],
                      [[o["entity"], o["class"], o["row_count"], o["attributes"],
                        "yes" if o["indexed"] else "no", o["basis"]]
                       for o in ontology["objects"]]))
    out.append("\nClass mix: %s\n" % ", ".join(
        "%s %d" % (k, v) for k, v in sorted(ontology["class_counts"].items())))
    econ = ontology["unit_economics"]
    out.append("\n## Unit economics\n")
    if econ.get("complete"):
        out.append(_table(["Line", "Value"], [
            ["Billable unit", econ["unit"]],
            ["Price per unit", "$%s" % _fmt(econ["price_per_unit"])],
            ["Units per month", econ["units_per_month"]],
            ["Monthly revenue", "$%s" % _fmt(econ["monthly_revenue"])],
            ["Infrastructure cost per unit", "$%s" % _fmt(econ["infra_cost_per_unit"])],
            ["Other variable cost per unit", "$%s" % _fmt(econ["variable_cogs_per_unit"])],
            ["Contribution per unit", "$%s" % _fmt(econ["contribution_per_unit"])],
            ["Contribution margin", "%s%%" % _fmt(econ["contribution_margin_pct"])],
            ["Fixed monthly cost", "$%s" % _fmt(econ["fixed_monthly_cost"])],
            ["Monthly contribution", "$%s" % _fmt(econ["monthly_contribution"])],
            ["Break-even units/month", econ["break_even_units"]],
            ["Break-even vs today", "%sx" % _fmt(econ["break_even_vs_today"])],
        ]))
    else:
        out.append("_Not computable from the inputs provided._\n")
    link = ontology["scaling_link"]
    out.append("\n## Where the technology meets the plan\n")
    out.append(_table(["Line", "Value"], [
        ["Units per month today", link.get("units_per_month")],
        ["Monthly growth rate", link.get("growth_rate_monthly")],
        ["System break point per month", link.get("system_break_point_per_month")],
        ["Months of headroom", link.get("months_of_headroom")],
        ["Binding component", link.get("bottleneck")],
    ]))
    if ontology.get("counterparties"):
        out.append("\n## Counterparties\n\n%s\n"
                   % "\n".join("- %s" % c for c in ontology["counterparties"]))
    if ontology.get("compliance"):
        out.append("\n## Compliance scope\n\n%s\n"
                   % "\n".join("- %s" % c for c in ontology["compliance"]))
    if ontology.get("open_questions"):
        out.append("\n## Open questions\n\n%s\n"
                   % "\n".join("- %s" % q for q in ontology["open_questions"]))
    return "\n".join(out)


def roadmap_md(target, recs) -> str:
    out = [_header("06 · Ranked roadmap", target,
                   "Ranked by `(impact × confidence) ÷ effort`. Each item carries an action "
                   "block an agent can execute, and the deployment trigger that already "
                   "exists in this repository.")]
    out.append("## Ranking\n")
    out.append(_table(["#", "Recommendation", "Layer", "Category", "Impact",
                       "Effort (d)", "Conf.", "Score", "Horizon"],
                      [[r["rank"], r["title"], r["layer"], r["category"], r["impact"],
                        r["effort_days"], r["confidence"], r["score"], r["horizon"]]
                       for r in recs]))
    out.append("\n## Actions\n")
    for r in recs:
        a = r["action"]
        out.append("\n### %d. %s\n" % (r["rank"], r["title"]))
        out.append("**Finding.** %s\n" % r["finding"])
        if r.get("math"):
            out.append("\n**Math.** %s\n" % r["math"])
        out.append("\n**Agent action**\n\n```\n%s\n```\n" % a["agent_prompt"])
        out.append(_table(["Field", "Value"], [
            ["Files", ", ".join(a.get("files") or [])],
            ["Acceptance", a.get("acceptance")],
            ["Autonomy", a.get("autonomy")],
            ["Deploy trigger", "%s — %s" % (a["trigger"]["mode"], a["trigger"]["detail"])],
            ["Gate", a["trigger"].get("gate")],
            ["KPI", r["kpi"]],
            ["Evidence", ", ".join(r["evidence"])],
        ]))
    return "\n".join(out)


# --------------------------------------------------------------------------
# HTML dashboard
# --------------------------------------------------------------------------

def dashboard_html(target, graph, capacity, ontology, recs, flows, entities,
                   observation_count: int = 0) -> str:
    def esc(v):
        return html.escape(str(v)) if v is not None else "&mdash;"
    sev_class = {"now": "crit", "next": "warn", "later": "ok"}
    rec_rows = "".join(
        "<tr><td class='num'>%d</td><td>%s</td><td><span class='pill %s'>%s</span></td>"
        "<td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
        % (r["rank"], esc(r["title"]), sev_class.get(r["horizon"], "ok"), r["horizon"],
           esc(r["layer"]), r["impact"], r["effort_days"], r["score"])
        for r in recs)
    cap_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td><div class='bar'><span style='width:%.0f%%'></span></div>"
        "<span class='num'>%.0f%%</span></td><td class='num'>%s</td></tr>"
        % (esc(r["component"]), esc(r["layer"]), _fmt(round(r["capacity_rps"], 1)),
           _fmt(round(r["peak_rps"], 2)),
           _fmt(round(r["headroom_x"], 1) if r["headroom_x"] else None),
           min(100.0, r["utilisation"] * 100), r["utilisation"] * 100,
           _fmt(r["break_point_per_day"]))
        for r in sorted(capacity["rows"], key=lambda x: -x["utilisation"]))
    econ = ontology["unit_economics"]
    tiles = [
        ("Components", len(graph.components)),
        ("Transfers", len(graph.edges)),
        ("Entities", len(entities["entities"])),
        ("Findings", len(recs)),
        ("Break point / day", _fmt(capacity.get("system_break_point_per_day"))),
        ("Contribution margin",
         ("%s%%" % _fmt(econ.get("contribution_margin_pct"))) if econ.get("complete") else "—"),
    ]
    tile_html = "".join("<div class='tile'><span class='k'>%s</span><span class='v'>%s</span></div>"
                        % (esc(t[0]), esc(t[1])) for t in tiles)
    return """<title>%(name)s System Analysis</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400&display=swap">
<style>
:root{--paper:#F1F3F2;--surface:#FBFCFB;--surface2:#E6EAE9;--ink:#15191B;--ink2:#434C4F;
--ink3:#6D7779;--rule:#D1D8D7;--accent:#0F4C5C;--crit:#8E3B33;--warn:#8A5A12;--ok:#2E6A4F;
--mono:"IBM Plex Mono",monospace;--sans:"Archivo",Helvetica,Arial,sans-serif;
--serif:"Source Serif 4",Georgia,serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0E1214;--surface:#151B1D;
--surface2:#1C2427;--ink:#E2E8E7;--ink2:#AEB9B8;--ink3:#7E8A8A;--rule:#293337;--accent:#74BDC9;
--crit:#DE8E85;--warn:#D5A253;--ok:#7FC3A2}}
:root[data-theme="dark"]{--paper:#0E1214;--surface:#151B1D;--surface2:#1C2427;--ink:#E2E8E7;
--ink2:#AEB9B8;--ink3:#7E8A8A;--rule:#293337;--accent:#74BDC9;--crit:#DE8E85;--warn:#D5A253;--ok:#7FC3A2}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--serif);font-size:16px;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto;padding:36px 24px 80px}
.kick{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3)}
h1{font-family:var(--sans);font-size:clamp(28px,4.5vw,42px);letter-spacing:-.02em;margin:10px 0 6px}
h2{font-family:var(--sans);font-size:22px;margin:38px 0 12px;border-top:2px solid var(--ink);padding-top:12px}
.sub{color:var(--ink2);max-width:64ch;margin:0 0 24px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:8px}
.tile{background:var(--surface);border:1px solid var(--rule);padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.tile .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
.tile .v{font-family:var(--sans);font-weight:700;font-size:26px;font-variant-numeric:tabular-nums}
.tw{overflow-x:auto;border:1px solid var(--rule);background:var(--surface)}
table{border-collapse:collapse;width:100%%;min-width:640px;font-size:14.5px}
th{font-family:var(--sans);font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;
text-align:left;color:var(--ink2);border-bottom:1px solid var(--ink);padding:9px 12px}
td{border-bottom:1px solid var(--rule);padding:9px 12px;vertical-align:top}
tbody tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.pill{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
padding:2px 7px;border:1px solid currentColor}
.pill.crit{color:var(--crit)}.pill.warn{color:var(--warn)}.pill.ok{color:var(--ok)}
.bar{display:inline-block;width:90px;height:7px;background:var(--surface2);margin-right:8px;vertical-align:middle}
.bar span{display:block;height:100%%;background:var(--accent)}
pre.mermaid{background:var(--surface);border:1px solid var(--rule);padding:16px;overflow-x:auto}
footer{margin-top:44px;border-top:2px solid var(--ink);padding-top:14px;color:var(--ink3);font-size:13.5px}
</style>
<div class="wrap">
<span class="kick">Analysis Engine &middot; %(when)s</span>
<h1>%(name)s</h1>
<p class="sub">Context architecture, transfer throughput, scaling math and a ranked roadmap,
derived from %(obs)s observations. Every number traces to evidence in <code>00_EVIDENCE.json</code>.</p>
<div class="tiles">%(tiles)s</div>
<h2>Context architecture</h2>
<pre class="mermaid">%(diagram)s</pre>
<h2>Capacity and headroom</h2>
<div class="tw"><table><thead><tr><th>Component</th><th>Layer</th><th class="num">Capacity rps</th>
<th class="num">Peak rps</th><th class="num">Headroom</th><th>Utilisation</th>
<th class="num">Break point/day</th></tr></thead><tbody>%(cap)s</tbody></table></div>
<h2>Ranked roadmap</h2>
<div class="tw"><table><thead><tr><th class="num">#</th><th>Recommendation</th><th>Horizon</th>
<th>Layer</th><th class="num">Impact</th><th class="num">Effort d</th><th class="num">Score</th>
</tr></thead><tbody>%(recs)s</tbody></table></div>
<h2>Entity model</h2>
<pre class="mermaid">%(erd)s</pre>
<footer>Generated by analysis-engine 1.0. Figures marked assumed in the markdown set are model
outputs, not measurements &mdash; check <code>04_CAPACITY.md</code> before quoting them.</footer>
</div>""" % {
        "name": esc(target.get("name")), "when": time.strftime("%Y-%m-%d %H:%M"),
        "obs": format(observation_count, ","), "tiles": tile_html,
        "diagram": esc(context_diagram(graph, flows)),
        "cap": cap_rows, "recs": rec_rows,
        "erd": esc(erd_diagram(entities, limit=14)),
    }
