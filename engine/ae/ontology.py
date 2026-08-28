"""Business and financial ontology.

Two halves that must stay separate:
  inferred  -- what the code and schema say about the business
  stated    -- what a human told us in the structured interview

The engine never launders one into the other. Anything the interview did not
answer stays an open question in the output document.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .analyze import IDENTITY_HINTS, MONEY_HINTS

INTERVIEW = [
    {"id": "purpose", "q": "In one sentence: what does this system do, and for whom?"},
    {"id": "billable_unit", "q": "What is the billable unit? (seat, transaction, loan funded, "
                                "API call, GMV percentage, subscription month)"},
    {"id": "price_per_unit", "q": "Price per billable unit, in dollars.", "type": "number"},
    {"id": "units_per_month", "q": "Billable units per month today.", "type": "number"},
    {"id": "growth_rate_monthly", "q": "Month-over-month growth rate in units, as a decimal "
                                       "(0.08 = 8%).", "type": "number"},
    {"id": "variable_cogs_per_unit", "q": "Variable cost per unit outside infrastructure "
                                          "(data vendors, model API calls, payment fees, "
                                          "manual review).", "type": "number"},
    {"id": "fixed_monthly_cost", "q": "Fixed monthly cost carried by this system "
                                      "(team, licences, contracted minimums).", "type": "number"},
    {"id": "money_entities", "q": "Which tables or objects represent money moving? "
                                  "(comma separated)", "type": "list"},
    {"id": "counterparties", "q": "External counterparties this system depends on "
                                  "contractually.", "type": "list"},
    {"id": "sla", "q": "Uptime or latency commitments made to customers."},
    {"id": "compliance", "q": "Regulatory regimes in scope (SOC 2, PCI, GLBA, HIPAA, "
                              "GDPR, state lending).", "type": "list"},
    {"id": "deploy_trigger", "q": "How does code reach production today: git merge, tagged "
                                  "release, or a manual step? Who approves?"},
]


def blank_interview() -> Dict[str, Any]:
    return {"_instructions": "Answer what you know; leave the rest null. Nulls become "
                             "open questions in 05_ONTOLOGY.md rather than guesses.",
            **{item["id"]: None for item in INTERVIEW}}


def load_business(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _classify(name: str, cols: List[Dict[str, Any]]) -> str:
    blob = (name + " " + " ".join(c.get("name", "") for c in cols)).lower()
    if any(h in blob for h in ("event", "log", "audit", "history", "webhook")):
        return "event"
    if any(h in blob for h in MONEY_HINTS):
        return "money"
    if any(h in blob for h in IDENTITY_HINTS):
        return "party"
    if any(h in blob for h in ("config", "setting", "rule", "policy", "template", "type")):
        return "reference"
    return "operational"


def build(entities: Dict[str, Any], capacity: Dict[str, Any],
          usecases: List[Dict[str, Any]], business: Dict[str, Any]) -> Dict[str, Any]:
    objects: List[Dict[str, Any]] = []
    stated_money = {m.strip().lower() for m in (business.get("money_entities") or [])}
    for name, e in sorted(entities["entities"].items()):
        cls = _classify(name, e.get("columns") or [])
        if name.lower() in stated_money:
            cls = "money"
        objects.append({
            "entity": name, "class": cls,
            "row_count": e.get("row_count"),
            "attributes": len(e.get("columns") or []),
            "indexed": bool(e.get("indexes")),
            "source": e.get("source"),
            "basis": "stated" if name.lower() in stated_money else "inferred",
        })

    # ---- unit economics -------------------------------------------------
    price = _num(business.get("price_per_unit"))
    units = _num(business.get("units_per_month"))
    var_cogs = _num(business.get("variable_cogs_per_unit")) or 0.0
    fixed = _num(business.get("fixed_monthly_cost")) or 0.0
    infra_month = capacity.get("monthly_infra_cost")
    econ: Dict[str, Any] = {"complete": False, "open_questions": []}

    if price is not None and units:
        revenue = price * units
        infra_per_unit = (infra_month / units) if infra_month else None
        variable_total = var_cogs + (infra_per_unit or 0.0)
        contribution = price - variable_total
        econ.update({
            "complete": infra_per_unit is not None,
            "unit": business.get("billable_unit") or "billable unit",
            "price_per_unit": round(price, 4),
            "units_per_month": units,
            "monthly_revenue": round(revenue, 2),
            "infra_cost_per_unit": round(infra_per_unit, 6) if infra_per_unit else None,
            "variable_cogs_per_unit": round(var_cogs, 6),
            "variable_cost_per_unit": round(variable_total, 6),
            "contribution_per_unit": round(contribution, 6),
            "contribution_margin_pct": round(contribution / price * 100, 1) if price else None,
            "fixed_monthly_cost": fixed,
            "monthly_contribution": round(contribution * units, 2),
            "break_even_units": int(fixed / contribution) if contribution > 0 else None,
            "break_even_vs_today": (round((fixed / contribution) / units, 2)
                                    if contribution > 0 and units else None),
        })
        if infra_per_unit is None:
            econ["open_questions"].append(
                "Infrastructure cost per unit is unknown: enable the cloud collector or "
                "supply a monthly infrastructure figure.")
    else:
        for field, label in (("price_per_unit", "price per billable unit"),
                             ("units_per_month", "monthly volume")):
            if _num(business.get(field)) is None:
                econ["open_questions"].append("Unit economics blocked: %s not provided." % label)

    # ---- capacity vs commercial growth ----------------------------------
    growth = _num(business.get("growth_rate_monthly"))
    runway = None
    if growth and units and capacity.get("system_break_point_per_day"):
        monthly_break = capacity["system_break_point_per_day"] * 30
        if monthly_break > units and growth > 0:
            import math
            runway = math.log(monthly_break / units) / math.log(1 + growth)
    scaling_link = {
        "growth_rate_monthly": growth,
        "units_per_month": units,
        "system_break_point_per_month": (capacity["system_break_point_per_day"] * 30
                                         if capacity.get("system_break_point_per_day") else None),
        "months_of_headroom": round(runway, 1) if runway else None,
        "bottleneck": (capacity.get("bottleneck") or {}).get("component"),
    }

    revenue_paths = []
    money_objects = [o["entity"] for o in objects if o["class"] == "money"]
    for uc in usecases:
        revenue_paths.append({
            "usecase": uc["name"],
            "touches_money_objects": money_objects[:4],
            "volume_per_day": uc["volume_per_day"],
            "revenue_per_event": uc.get("revenue_per_event"),
            "basis": uc["basis"],
        })

    open_qs = list(econ["open_questions"])
    for item in INTERVIEW:
        if business.get(item["id"]) in (None, "", []):
            open_qs.append("Unanswered: %s" % item["q"])

    return {
        "purpose": business.get("purpose"),
        "objects": objects,
        "class_counts": _counts(objects),
        "unit_economics": econ,
        "scaling_link": scaling_link,
        "revenue_paths": revenue_paths,
        "counterparties": business.get("counterparties") or [],
        "compliance": business.get("compliance") or [],
        "sla": business.get("sla"),
        "deploy_trigger": business.get("deploy_trigger"),
        "open_questions": open_qs,
    }


def _counts(objects: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for o in objects:
        out[o["class"]] = out.get(o["class"], 0) + 1
    return out


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
