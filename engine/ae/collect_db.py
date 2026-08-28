"""Database collector: schema introspection plus the numbers that make the
scaling math real (row counts, table sizes, index coverage).

Supports PostgreSQL via psycopg/psycopg2 and SQLite via the stdlib, so the
engine can be demonstrated with zero infrastructure.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .core import Evidence, Observation, env_expand

NAME = "database"


def _ev(locator: str, excerpt: str = "") -> Evidence:
    return Evidence(locator=locator, excerpt=excerpt[:200], method="query")


def collect(cfg: Dict[str, Any]) -> List[Observation]:
    conf = cfg.get("database") or {}
    if not conf.get("enabled"):
        return []
    dsn = env_expand(conf.get("dsn"))
    if not dsn:
        return [_degraded("no dsn configured")]
    kind = (conf.get("kind") or "postgres").lower()
    if kind == "sqlite" or dsn.endswith(".db") or dsn.endswith(".sqlite"):
        return _sqlite(dsn)
    return _postgres(dsn)


def _degraded(detail: str) -> Observation:
    return Observation("risk", "db-read-failed", "data", collector=NAME,
                       attrs={"severity": "low", "category": "coverage",
                              "detail": "database collector skipped: %s" % detail},
                       confidence=1.0, evidence=Evidence(locator="database", method="query"))


# --------------------------------------------------------------------------

def _emit_table(out: List[Observation], table: str, cols: List[Dict[str, Any]],
                rows: Optional[int], bytes_: Optional[int], locator: str) -> None:
    out.append(Observation("entity", table, "data", collector=NAME,
                           attrs={"columns": cols, "row_count": rows,
                                  "bytes": bytes_, "source": "introspection"},
                           confidence=1.0, evidence=_ev(locator, table)))
    if rows is not None:
        out.append(Observation("metric", "table.rows:%s" % table, "data", collector=NAME,
                               attrs={"value": rows, "unit": "rows", "table": table},
                               confidence=1.0, evidence=_ev(locator, table)))


def _postgres(dsn: str) -> List[Observation]:
    try:
        try:
            import psycopg  # type: ignore
            conn = psycopg.connect(dsn)
        except ImportError:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(dsn)
    except ImportError:
        return [_degraded("psycopg not installed")]
    except Exception as exc:  # noqa: BLE001
        return [_degraded("connection failed (%s)" % type(exc).__name__)]

    out: List[Observation] = []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position""")
        cols_by_table: Dict[str, List[Dict[str, Any]]] = {}
        for t, c, dt, nullable in cur.fetchall():
            cols_by_table.setdefault(t, []).append(
                {"name": c, "type": dt, "nullable": nullable == "YES", "pk": False})

        cur.execute("""
            SELECT relname, n_live_tup, pg_total_relation_size(relid)
            FROM pg_stat_user_tables""")
        stats = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

        for table, cols in cols_by_table.items():
            rows, size = stats.get(table, (None, None))
            _emit_table(out, table, cols, rows, size, "pg:information_schema")

        cur.execute("""
            SELECT tc.table_name, kcu.column_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'""")
        fks: List[Tuple[str, str, str]] = cur.fetchall()
        for src, col, dst in fks:
            out.append(Observation("relation", "%s.%s->%s" % (src, col, dst), "data",
                                   collector=NAME,
                                   attrs={"from": src, "column": col, "to": dst,
                                          "cardinality": "many-to-one"},
                                   confidence=1.0, evidence=_ev("pg:constraints")))

        cur.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public'")
        indexed: Dict[str, List[str]] = {}
        for tbl, iname, idef in cur.fetchall():
            cols_in = re.findall(r"\((.*?)\)", idef)
            first = cols_in[0].split(",")[0].strip() if cols_in else ""
            indexed.setdefault(tbl, []).append(first)
            out.append(Observation("config", "index:%s" % iname, "data", collector=NAME,
                                   attrs={"type": "index", "table": tbl, "definition": idef},
                                   confidence=1.0, evidence=_ev("pg:pg_indexes", iname)))

        for src, col, dst in fks:
            rows = (stats.get(src) or (0, 0))[0] or 0
            if col not in indexed.get(src, []) and rows > 10000:
                out.append(Observation("risk", "unindexed-fk:%s.%s" % (src, col), "data",
                                       collector=NAME,
                                       attrs={"severity": "high", "category": "performance",
                                              "detail": "%s.%s is a foreign key with no index on "
                                                        "a table of %s rows; joins and cascading "
                                                        "deletes degrade linearly"
                                                        % (src, col, format(rows, ",")),
                                              "rows": rows},
                                       confidence=0.9, evidence=_ev("pg:pg_indexes")))

        cur.execute("SELECT count(*) FROM pg_stat_activity")
        conns = cur.fetchone()[0]
        cur.execute("SHOW max_connections")
        maxc = int(cur.fetchone()[0])
        out.append(Observation("metric", "db.connections", "data", collector=NAME,
                               attrs={"value": conns, "max": maxc, "unit": "connections",
                                      "utilisation": round(conns / maxc, 3) if maxc else None},
                               confidence=1.0, evidence=_ev("pg:pg_stat_activity")))
        conn.close()
    except Exception as exc:  # noqa: BLE001
        out.append(_degraded("query failed (%s)" % type(exc).__name__))
    return out


def _sqlite(path: str) -> List[Observation]:
    import sqlite3
    if not os.path.exists(path):
        return [_degraded("sqlite file not found: %s" % path)]
    out: List[Observation] = []
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    indexed: Dict[str, List[str]] = {}
    for t in tables:
        for r in cur.execute("PRAGMA index_list('%s')" % t).fetchall():
            for ic in cur.execute("PRAGMA index_info('%s')" % r[1]).fetchall():
                indexed.setdefault(t, []).append(ic[2])
    for t in tables:
        cols = [{"name": r[1], "type": r[2], "nullable": not r[3], "pk": bool(r[5])}
                for r in cur.execute("PRAGMA table_info('%s')" % t).fetchall()]
        rows = cur.execute("SELECT count(*) FROM '%s'" % t).fetchone()[0]
        _emit_table(out, t, cols, rows, None, "sqlite:%s" % os.path.basename(path))
        for r in cur.execute("PRAGMA foreign_key_list('%s')" % t).fetchall():
            out.append(Observation("relation", "%s.%s->%s" % (t, r[3], r[2]), "data",
                                   collector=NAME,
                                   attrs={"from": t, "column": r[3], "to": r[2],
                                          "cardinality": "many-to-one"},
                                   confidence=1.0, evidence=_ev("sqlite:foreign_key_list")))
            if r[3] not in indexed.get(t, []) and rows > 10000:
                out.append(Observation("risk", "unindexed-fk:%s.%s" % (t, r[3]), "data",
                                       collector=NAME,
                                       attrs={"severity": "high", "category": "performance",
                                              "detail": "%s.%s is an unindexed foreign key on "
                                                        "%s rows" % (t, r[3], format(rows, ",")),
                                              "rows": rows},
                                       confidence=0.9, evidence=_ev("sqlite:index_list")))
    conn.close()
    return out
