# Analysis Engine

Point it at a software system. Get a technical due-diligence documentation set back:
context architecture by layer, transfer throughput and bottlenecks, scaling math tied to
declared use cases, an ERD, a business and financial ontology, and a ranked roadmap of
agent-executable actions.

The repository has two planes, and they do not run in the same place.

| Plane | Runs where | Job |
|---|---|---|
| `engine/` | your laptop, a container, or GitHub Actions | does the analysis, where the access already is |
| `web/` | Vercel | receives finished runs, stores them, renders them, indexes them |

The web app is a viewer and a control plane. It reads `model.json` and `00_EVIDENCE.json`
and renders them. It never re-derives a fact.

---

## Run it locally

```bash
cd engine
python3 -m venv .venv && .venv/bin/pip install -e .
```

A plain `pip install -e .` fails on a Homebrew or system Python with
`externally-managed-environment` (PEP 668). Use a virtualenv, or `pipx install ./engine`.

```bash
ae init                                              # write target.json + business.json
ae analyze --target target.json --business business.json --out out
ae doctor                                            # what optional collectors are available
```

Against the bundled synthetic target, with no configuration at all:

```bash
ae analyze --target target.example.json --out out
```

The repo and probe collectors need nothing beyond the Python standard library. The core
has **zero required dependencies** on purpose — that is what lets it run inside a target's
own environment without an install. `boto3` unlocks the cloud collector, `psycopg` unlocks
PostgreSQL introspection:

```bash
pip install -e './engine[cloud,postgres]'
```

### Configuration

`target.json` describes access and the use cases that drive the scaling math. Secrets are
referenced as `${ENV_VAR}` and read from the environment, never stored in the file.
`business.json` holds the twelve interview answers; anything left null becomes an open
question rather than a guess.

Both are gitignored, because a real one carries volumes, prices and DSNs. Only
`target.example.json`, `business.example.json` and the synthetic
`fixtures/acme-lending.*.json` pair are tracked.

### Tests

```bash
cd engine
cp fixtures/acme-lending.target.json target.json
cp fixtures/acme-lending.business.json business.json
python3 -m tests.test_smoke        # 30 checks
```

The copy step is needed because the test reads `target.json` and `business.json` from the
engine root and those are gitignored. CI does the same thing.

---

## Read the output

| File | Contents |
|---|---|
| `00_EVIDENCE.json` | Every observation with its evidence locator. The reproducible fact base. |
| `01_ARCHITECTURE.md` | Context diagram by layer, plus the component inventory. |
| `02_FLOWS.md` | Every transfer: protocol, calls per request, peak rps, payload, throughput, latency, binding constraint. |
| `03_ERD.md` | Entity relationship diagram, data dictionary, growth projection. |
| `04_CAPACITY.md` | Scaling math per component — capacity, utilisation, queue wait, break point — and the assumption ledger behind it. |
| `05_ONTOLOGY.md` | Business objects, unit economics, where capacity meets the commercial plan, open questions. |
| `06_ROADMAP.md` | Ranked recommendations, each with an agent-executable action and the deployment trigger already in the repo. |
| `index.html` | One-page dashboard. |
| `model.json` | The derived model, for downstream tooling. |

Five rules govern every number in there:

1. Every fact is an `Observation` carrying an `Evidence`. The whole output is reproducible
   from `00_EVIDENCE.json` alone.
2. Capacity values are stored unrounded; rounding happens only in the renderer, so the
   derived identities hold exactly (ρ = λ/μ, headroom = μ/λ).
3. Every number carries a basis: `measured`, `declared`, `inferred` or `assumed`.
4. A collector that cannot run emits a **coverage gap**, never silence. An absent finding
   must never read as a clean finding.
5. Read-only against every target. The probe issues `GET` and `HEAD` only.

Measured, declared, inferred and assumed are labelled wherever they appear. A number
without a basis is how a diligence report becomes a liability.

---

## How the hosted viewer receives runs

A finished run is POSTed to `/api/runs` as JSON. Nothing is recomputed on arrival: the
endpoint validates the payload, writes the artifacts to Vercel Blob and appends one
summary row to the run index.

```bash
python3 engine/scripts/publish.py \
  --dir out \
  --url https://<your-deployment> \
  --token "$INGEST_TOKEN" \
  --bypass "$VERCEL_AUTOMATION_BYPASS_SECRET"
```

Or without touching a laptop: dispatch the **analyze** workflow with a target repo, a ref
and a config path. It checks the target out, installs the engine, runs `ae analyze`, and
publishes the result.

The viewer shows a run index (system, date, bottleneck, utilisation, break point,
`now`-horizon findings) and one page per run with a tab for each document. Capacity and
roadmap render from `model.json` as sortable tables rather than as prose, because they are
data. Every finding links to its evidence locator, and the Evidence tab shows the excerpt,
method, collector and confidence behind it. Evidence is the product.

### Storage

Artifacts and the index both live in **Vercel Blob**, written `access: 'private'`. There is
no second service. Vercel Postgres and Vercel KV no longer exist as first-party products,
and the index is small enough not to need a Marketplace database yet.

The index is append-only — one summary blob per run under `index/` — so two concurrent
ingests cannot race a shared manifest. Listing costs one small read per run.

> **Tripwire.** Past roughly 200 runs the index page will get slow. That is the point to
> move the index into a real store (Neon via the Vercel Marketplace), not before.

---

## Security posture

These reports name committed credentials, publicly-exposed databases and unpatched
infrastructure on real systems. Treat the deployment as carrying that data.

**The deployed app must not be publicly readable. This is a requirement, not a preference.**

- **Deployment Protection must be on before the first run carrying real data.** Vercel
  Authentication is available on every plan.
- **On the Hobby plan, never deploy to production.** Standard Protection covers preview
  deployments and generated deployment URLs, but leaves *production domains* public — and
  Vercel assigns `<project>.vercel.app` as one automatically. Set the project's production
  branch to `production` and never push it, so `main` deploys as a preview and the app is
  reached only at its protected branch alias. Do not run `vercel deploy --prod`.
  To get a protected production URL, move to Pro and set the protection scope to
  **All Deployments**.
- **Blob objects are private.** A public blob URL is served outside Deployment Protection,
  so a public artifact would defeat the protection entirely.
- **The ingest endpoint needs two secrets, and neither substitutes for the other.**
  `INGEST_TOKEN` is the app's own bearer credential, compared in constant time after both
  sides are hashed so the comparison cannot leak token length.
  `VERCEL_AUTOMATION_BYPASS_SECRET` is Vercel's Protection Bypass for Automation value —
  without it, Deployment Protection challenges the CI POST before it ever reaches the
  route.
- **Payloads are capped** at 10 MB, checked on both `Content-Length` and actual bytes, and
  filenames are restricted to the nine artifacts the engine emits.
- **No target credentials in the repository**, in any example file, or in any workflow
  file. Collector credentials are GitHub Actions secrets injected as environment variables
  and referenced from the target config as `${VAR}`.

### Environment variables

| Name | Where | Purpose |
|---|---|---|
| `INGEST_TOKEN` | Vercel project (Preview and Production separately), GitHub secret | Bearer credential for `POST /api/runs` |
| `BLOB_READ_WRITE_TOKEN` | Vercel project, set by the Blob store | Artifact storage |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Vercel project settings, GitHub secret | Lets CI through Deployment Protection |
| `WEB_URL` | GitHub Actions variable | Where `publish.py` sends the run |
