"""Live cloud collector (AWS, read-only).

Answers the question static analysis cannot: what is actually running, how big
is it, and what does it cost. Every call here is a read; the collector refuses
to import boto3 unless it is enabled.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List

from .core import Evidence, Observation

NAME = "cloud"

# Published on-demand USD/month approximations used only when Cost Explorer is
# unavailable. Every number produced this way is tagged basis="assumed".
INSTANCE_MONTHLY = {
    "db.t3.micro": 15.0, "db.t3.small": 30.0, "db.t3.medium": 60.0,
    "db.t4g.medium": 55.0, "db.m5.large": 130.0, "db.m5.xlarge": 260.0,
    "db.r5.large": 180.0, "db.r6g.large": 165.0,
    "t3.micro": 7.5, "t3.small": 15.0, "t3.medium": 30.0, "t3.large": 60.0,
    "m5.large": 70.0, "m5.xlarge": 140.0, "c5.large": 62.0, "c6i.large": 62.0,
    "g4dn.xlarge": 380.0, "g5.xlarge": 730.0, "p4d.24xlarge": 23900.0,
}


def _ev(locator: str, excerpt: str = "") -> Evidence:
    return Evidence(locator=locator, excerpt=excerpt[:200], method="api")


def collect(cfg: Dict[str, Any]) -> List[Observation]:
    conf = cfg.get("cloud") or {}
    if not conf.get("enabled"):
        return []
    if (conf.get("provider") or "aws").lower() != "aws":
        return [Observation("risk", "cloud-provider-unsupported", "infrastructure",
                            collector=NAME,
                            attrs={"severity": "low", "category": "coverage",
                                   "detail": "only AWS is implemented in v1"},
                            confidence=1.0, evidence=_ev("config"))]
    try:
        import boto3  # type: ignore
    except ImportError:
        return [Observation("risk", "cloud-collector-unavailable", "infrastructure",
                            collector=NAME,
                            attrs={"severity": "low", "category": "coverage",
                                   "detail": "boto3 not installed; cloud collector skipped"},
                            confidence=1.0, evidence=_ev("import boto3"))]

    session = boto3.Session(profile_name=conf.get("profile"),
                            region_name=conf.get("region") or "us-east-1")
    region = session.region_name
    out: List[Observation] = []

    def _slug(v: str) -> str:
        return v.replace("_", "-").replace(".", "-").lower()

    # --- RDS -------------------------------------------------------------
    try:
        rds = session.client("rds")
        for db in rds.describe_db_instances().get("DBInstances", []):
            ident = db["DBInstanceIdentifier"]
            cls = db.get("DBInstanceClass", "")
            out.append(Observation("component", _slug(ident), "data", collector=NAME,
                                   attrs={"kind": "store", "tech": "rds/%s" % db.get("Engine"),
                                          "instance_class": cls,
                                          "multi_az": db.get("MultiAZ"),
                                          "storage_gb": db.get("AllocatedStorage"),
                                          "backup_retention_days": db.get("BackupRetentionPeriod"),
                                          "public": db.get("PubliclyAccessible"),
                                          "monthly_cost": INSTANCE_MONTHLY.get(cls),
                                          "cost_basis": "list-price-estimate"},
                                   confidence=1.0,
                                   evidence=_ev(db.get("DBInstanceArn", ident), cls)))
            if not db.get("MultiAZ"):
                out.append(Observation("risk", "rds-single-az:%s" % _slug(ident), "data",
                                       collector=NAME,
                                       attrs={"severity": "high", "category": "resilience",
                                              "detail": "%s runs single-AZ; an AZ failure is a "
                                                        "full outage with restore-from-backup RTO"
                                                        % ident},
                                       confidence=1.0, evidence=_ev(db.get("DBInstanceArn", ident))))
            if (db.get("BackupRetentionPeriod") or 0) < 7:
                out.append(Observation("risk", "rds-backup-window:%s" % _slug(ident), "data",
                                       collector=NAME,
                                       attrs={"severity": "high", "category": "resilience",
                                              "detail": "backup retention is %s days"
                                                        % db.get("BackupRetentionPeriod")},
                                       confidence=1.0, evidence=_ev(db.get("DBInstanceArn", ident))))
            if db.get("PubliclyAccessible"):
                out.append(Observation("risk", "rds-public:%s" % _slug(ident), "data",
                                       collector=NAME,
                                       attrs={"severity": "critical", "category": "security",
                                              "detail": "database is publicly addressable"},
                                       confidence=1.0, evidence=_ev(db.get("DBInstanceArn", ident))))
    except Exception as exc:  # noqa: BLE001 - collectors degrade, never crash
        out.append(_degraded("rds", exc))

    # --- ECS -------------------------------------------------------------
    try:
        ecs = session.client("ecs")
        for cluster in ecs.list_clusters().get("clusterArns", []):
            for svc_arn in ecs.list_services(cluster=cluster).get("serviceArns", []):
                desc = ecs.describe_services(cluster=cluster, services=[svc_arn])["services"][0]
                name = desc["serviceName"]
                out.append(Observation("component", _slug(name), "middleware", collector=NAME,
                                       attrs={"kind": "service", "tech": "ecs",
                                              "replicas": desc.get("runningCount"),
                                              "desired": desc.get("desiredCount"),
                                              "launch_type": desc.get("launchType")},
                                       confidence=1.0, evidence=_ev(svc_arn, name)))
    except Exception as exc:  # noqa: BLE001
        out.append(_degraded("ecs", exc))

    # --- EC2 -------------------------------------------------------------
    try:
        ec2 = session.client("ec2")
        for res in ec2.describe_instances().get("Reservations", []):
            for inst in res.get("Instances", []):
                if inst.get("State", {}).get("Name") != "running":
                    continue
                itype = inst.get("InstanceType", "")
                name = next((t["Value"] for t in inst.get("Tags", [])
                             if t["Key"] == "Name"), inst["InstanceId"])
                out.append(Observation("component", _slug(name), "infrastructure",
                                       collector=NAME,
                                       attrs={"kind": "service", "tech": "ec2",
                                              "instance_type": itype,
                                              "monthly_cost": INSTANCE_MONTHLY.get(itype),
                                              "cost_basis": "list-price-estimate",
                                              "gpu": itype.startswith(("g4", "g5", "p3", "p4", "p5"))},
                                       confidence=1.0, evidence=_ev(inst["InstanceId"], itype)))
    except Exception as exc:  # noqa: BLE001
        out.append(_degraded("ec2", exc))

    # --- Actual spend ----------------------------------------------------
    try:
        ce = session.client("ce", region_name="us-east-1")
        end = _dt.date.today().replace(day=1)
        start = (end - _dt.timedelta(days=1)).replace(day=1)
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY", Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
        for grp in resp.get("ResultsByTime", [{}])[0].get("Groups", []):
            amount = float(grp["Metrics"]["UnblendedCost"]["Amount"])
            if amount < 1:
                continue
            out.append(Observation("cost", "aws:%s" % _slug(grp["Keys"][0]), "infrastructure",
                                   collector=NAME,
                                   attrs={"monthly_cost": round(amount, 2),
                                          "cost_basis": "billed",
                                          "period": start.isoformat()},
                                   confidence=1.0,
                                   evidence=_ev("cost-explorer:%s" % start.isoformat(),
                                                grp["Keys"][0])))
    except Exception as exc:  # noqa: BLE001
        out.append(_degraded("cost-explorer", exc))

    out.append(Observation("metric", "cloud.region", "infrastructure", collector=NAME,
                           attrs={"value": region, "unit": "region"}, confidence=1.0,
                           evidence=_ev("session")))
    return out


def _degraded(api: str, exc: Exception) -> Observation:
    return Observation("risk", "cloud-read-failed:%s" % api, "infrastructure", collector=NAME,
                       attrs={"severity": "low", "category": "coverage",
                              "detail": "could not read %s (%s); findings for this service are "
                                        "absent, not clean" % (api, type(exc).__name__)},
                       confidence=1.0, evidence=Evidence(locator=api, method="api"))
