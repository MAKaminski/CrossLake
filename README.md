# Analysis Engine

Point it at a system. Get the documentation set back.

```
python3 -m ae init                      # write target.json + business.json
python3 -m ae analyze --target target.json --business business.json --out out
```

No dependencies for the repo and probe collectors — Python 3.8+ standard library only.
`boto3` unlocks the cloud collector, `psycopg` unlocks PostgreSQL introspection.
Run `python3 -m ae doctor` to see what is available.

## What it produces

| File | Contents |
|---|---|
| `00_EVIDENCE.json` | Every observation with its evidence locator. The reproducible fact base. |
| `01_ARCHITECTURE.md` | Context diagram by layer (front end / middleware / back end / data / infrastructure) plus the component inventory. |
| `02_FLOWS.md` | Every transfer process: protocol, calls per request, peak rps, payload, throughput, latency, and the binding constraint. |
| `03_ERD.md` | Entity relationship diagram, data dictionary, growth projection. |
| `04_CAPACITY.md` | Scaling math per component — capacity, utilisation, queue wait, break point — and the assumption ledger behind it. |
| `05_ONTOLOGY.md` | Business objects, unit economics, where capacity meets the commercial plan, and open questions. |
| `06_ROADMAP.md` | Ranked recommendations, each with an agent-executable action and the deployment trigger already present in the repo. |
| `index.html` | One-page dashboard. |
| `model.json` | The derived model, for downstream tooling. |

## The four collectors

| Collector | Access needed | What it establishes |
|---|---|---|
| `repo` | a checkout | components, routes, entities, IaC, pipelines, committed secrets |
| `cloud` | AWS read-only role | what is actually running, instance sizes, real spend, resilience gaps |
| `database` | read-only DSN | true schema, row counts, index coverage, connection pressure |
| `probe` | a base URL | measured p95 latency, payload sizes, edge and cache behaviour |

Every collector degrades rather than failing: if one cannot run, its absence is
recorded as a **coverage gap** in `01_ARCHITECTURE.md`, so a missing finding is
never mistaken for a clean one. The probe issues `GET`/`HEAD` only and refuses
anything that could mutate the target.

## Configuration

`target.json` describes access and the use cases that drive the scaling math.
Secrets are referenced as `${ENV_VAR}` and read from the environment, never
stored in the file.

```json
{
  "name": "acme-lending",
  "repo": { "path": "./fixtures/acme-lending" },
  "database": { "enabled": true, "kind": "postgres", "dsn": "${ANALYSIS_DB_DSN}" },
  "usecases": [
    { "name": "submit loan application", "volume_per_day": 40000, "peak_factor": 4.0,
      "path": ["web", "api", "primary-database"], "fanout": { "primary-database": 6 } }
  ],
  "assumptions": { "peak_factor": 3.0, "target_utilisation": 0.7 }
}
```

Component names in `usecases` are matched loosely against what the collectors
actually found, so a config written against logical names still binds when the
graph comes back with `aws-db-instance-primary`.

`business.json` holds the twelve interview answers. Anything left null becomes
an open question in the ontology document rather than a guess.

## The rule this thing is built on

Measured, declared, inferred and assumed are labelled everywhere they appear.
A number without a basis is how a diligence report becomes a liability.
