---
name: analysis-engine
description: Point the Analysis Engine at a software system, database, repository or running service and produce the full documentation set — context architecture diagram by layer, transfer throughput and bottlenecks, scaling math tied to use cases, ERD, business and financial ontology, and a ranked roadmap of AI-implementable actions. Use whenever Michael says "analyze this system", "run the analysis engine", "document this codebase", "what's the architecture of", "where does this break", "scaling math for", "tech diligence on", "assess this repo", "map this system", or hands over a repository path, database DSN, or base URL and asks what it is and what to fix. Also use when preparing a technical due diligence read on a target company's stack. Advisory and read-only — it never writes to the analyzed system.
---

# Analysis Engine

Deterministic extraction, then interpretation. The CLI establishes facts; you
supply the judgment. Never reverse that order — do not describe an architecture
you have not run the collectors against.

Engine lives at `~/Documents/Claude/Projects/Personal/AnalysisEngine`.

## 1. Establish the target

Ask only what you cannot determine yourself:

- **What is being analyzed** — repository path, and optionally a read-only
  database DSN, AWS profile, or base URL.
- **Whose system is it** — his own, or a diligence target. This changes the
  register of the output, not the method.

Then check what access actually exists:

```bash
cd ~/Documents/Claude/Projects/Personal/AnalysisEngine
python3 -m ae doctor
```

## 2. Write the target config

Copy `target.json` and edit. Only `repo.path` is required. Enable the other
collectors when credentials exist; leave them off rather than inventing values —
a disabled collector is recorded as a coverage gap, which is honest, while a
fabricated number is not.

Use cases matter more than anything else in the file: the scaling math is
driven entirely by them. If he has not given volumes, ask for them once:
*"Roughly how many of the main event per day, and how peaky is it?"* If he does
not know, leave `usecases` empty — the engine synthesises assumed ones and
labels every downstream number `assumed`.

Secrets go in the environment as `${VAR}`, never in the file.

## 3. Run the interview

```bash
python3 -m ae interview
```

Ask the twelve questions **conversationally, in batches of three or four**, not
as a form dump. Write answers into `business.json` as they arrive — do not
batch them to the end. Leave anything he does not know as `null`; nulls become
open questions in the ontology document, which is the correct output, and a
guess is not.

The four that carry the most weight: billable unit, price per unit, units per
month, variable cost per unit. Without those the unit economics section cannot
compute and the roadmap loses its margin findings.

## 4. Run the analysis

```bash
python3 -m ae analyze --target <target.json> --business <business.json> --out <outdir>
```

Read the console summary. Then read `04_CAPACITY.md` and `06_ROADMAP.md`
yourself before saying anything about the system.

## 5. Interpret

The documents are the evidence; your response is the argument. Lead with a
recommendation, not a tour. Structure it as:

1. **What this system is** — one paragraph, layered: front end, middleware,
   back end, data, infrastructure.
2. **Where it breaks first** — the binding constraint, the utilisation, the
   break point in daily events, and how that compares to today's volume.
   Show the arithmetic.
3. **What the money looks like** — cost per unit against price per unit, and
   the capacity runway in months at the stated growth rate.
4. **The three things to do now** — from the roadmap's `now` horizon, each with
   its agent prompt and deployment trigger.

Always state which numbers are measured and which are assumed. If the cloud,
database or probe collectors did not run, say so in one sentence — an absent
finding is not a clean finding, and that distinction is the entire value of the
tool.

## 6. Deliver

Write the output directory beside the analyzed system, or into the Personal
project folder for a diligence target. Publish `index.html` as an artifact when
he will come back to it. Offer to run the top-ranked action through Claude Code
using the `agent_prompt` and `acceptance` fields verbatim — they are written to
be executable without translation.

## Re-running

The engine is idempotent. After any remediation, re-run with the same config
and diff `model.json` to show what moved. That diff is the progress report.

## Guardrails

- Read-only against every target. The probe issues `GET`/`HEAD` only.
- Never commit `business.json` or any config containing a live DSN into a
  repository.
- Never present an assumed capacity number without its label.
- If a collector fails, report the gap; do not fill it from inference.
