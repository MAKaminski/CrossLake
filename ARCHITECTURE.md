# Analysis Engine — architecture

## Systems architecture

The engine is a four-stage pipeline with one shared fact base. Collectors only
write observations; analyzers only read them; renderers only read the derived
model. Nothing skips a stage, which is what makes the output reproducible from
`00_EVIDENCE.json` alone.

```mermaid
flowchart LR
  subgraph inputs["Inputs"]
    direction TB
    t["target.json<br/><small>access + use cases</small>"]
    b["business.json<br/><small>interview answers</small>"]
    sys[("Target system")]
  end
  subgraph collect["1 · Collect"]
    direction TB
    cr["repo<br/><small>static</small>"]
    cc["cloud<br/><small>AWS read-only</small>"]
    cd["database<br/><small>introspection</small>"]
    cp["probe<br/><small>GET/HEAD only</small>"]
  end
  subgraph store["2 · Fact base"]
    es[("EvidenceStore<br/><small>Observation + Evidence</small>")]
  end
  subgraph derive["3 · Derive"]
    direction TB
    g["SystemGraph<br/><small>components + edges</small>"]
    cap["Capacity model<br/><small>lambda, mu, rho, break point</small>"]
    ent["Entity model<br/><small>ERD + growth</small>"]
    ont["Ontology<br/><small>business + financial</small>"]
    rec["Recommender<br/><small>rank + action spec</small>"]
  end
  subgraph out["4 · Render"]
    direction TB
    md["Six markdown documents"]
    html["HTML dashboard"]
    mj["model.json"]
  end
  sys --> cr & cc & cd & cp
  t --> cr & cc & cd & cp
  cr & cc & cd & cp --> es
  es --> g --> cap --> rec
  es --> ent --> ont --> rec
  b --> ont
  cap --> ont
  g & cap & ent & ont & rec --> md & html & mj
```

### By layer

| Layer | In this system | Notes |
|---|---|---|
| Front end | `index.html` dashboard, the six markdown documents | Static artefacts; no server |
| Middleware | `ae.cli` — argument parsing, pipeline orchestration | The only place that knows the order of stages |
| Back end | `ae.analyze`, `ae.ontology`, `ae.recommend` | Pure functions over the fact base; no I/O |
| Data | `ae.core.EvidenceStore` and `00_EVIDENCE.json` | The single source of truth for every number |
| Infrastructure | `ae.collect_*` | The only modules that touch the outside world |

The dependency rule runs one way: infrastructure → data → back end → middleware
→ front end. An analyzer that needed a network call would be a design error.

## Entity relationship model

```mermaid
erDiagram
  TARGET_CONFIG ||--o{ USECASE : "declares"
  TARGET_CONFIG ||--|| ASSUMPTIONS : "carries"
  COLLECTOR ||--o{ OBSERVATION : "emits"
  OBSERVATION ||--|| EVIDENCE : "must cite"
  OBSERVATION ||--o| COMPONENT : "kind=component"
  OBSERVATION ||--o| EDGE : "kind=edge"
  OBSERVATION ||--o| ENTITY : "kind=entity"
  OBSERVATION ||--o| RELATION : "kind=relation"
  OBSERVATION ||--o| RISK : "kind=risk"
  COMPONENT ||--o{ EDGE : "source of"
  COMPONENT ||--o{ EDGE : "target of"
  ENTITY ||--o{ RELATION : "participates in"
  COMPONENT ||--|| CAPACITY_ROW : "sized as"
  USECASE ||--o{ CAPACITY_ROW : "drives load on"
  ENTITY ||--|| BUSINESS_OBJECT : "classified as"
  BUSINESS_OBJECT ||--o| UNIT_ECONOMICS : "money class feeds"
  INTERVIEW_ANSWER ||--o{ UNIT_ECONOMICS : "supplies"
  CAPACITY_ROW ||--o{ RECOMMENDATION : "raises"
  RISK ||--o{ RECOMMENDATION : "raises"
  UNIT_ECONOMICS ||--o{ RECOMMENDATION : "raises"
  RECOMMENDATION ||--|| ACTION_SPEC : "carries"
  ACTION_SPEC ||--|| DEPLOY_TRIGGER : "targets"

  OBSERVATION {
    string id PK
    string kind
    string key
    string layer
    json attrs
    float confidence
    string collector
  }
  EVIDENCE {
    string locator PK
    string excerpt
    string method
  }
  COMPONENT {
    string key PK
    string layer
    string kind
    string tech
    int replicas
    float capacity_rps
    float monthly_cost
  }
  EDGE {
    string key PK
    string src FK
    string dst FK
    string protocol
    bool sync
    float calls_per_request
    string basis
  }
  CAPACITY_ROW {
    string component PK
    float capacity_rps
    float peak_rps
    float utilisation
    float headroom_x
    int break_point_per_day
    string capacity_basis
  }
  RECOMMENDATION {
    string id PK
    int rank
    float impact
    float effort_days
    float confidence
    float score
    string horizon
  }
  ACTION_SPEC {
    string agent_prompt
    string acceptance
    string autonomy
  }
```

## The one repeating pattern

Everything the engine learns is an `Observation` carrying an `Evidence`.
Collectors differ only in how they produce them; analyzers differ only in what
they read. Adding a fifth collector means writing one `collect(cfg)` function
that returns observations — no other module changes.

## Capacity model

| Quantity | Formula | Basis |
|---|---|---|
| Peak arrival rate | `λ = events_per_day ÷ 86,400 × peak_factor × calls_per_request` | declared use case |
| Service capacity | `μ = replicas × concurrency ÷ service_time` | measured p95 when a probe ran, otherwise assumed |
| Store capacity | `μ = connections ÷ service_time ÷ 4` | pool-bound, not replica-bound |
| Utilisation | `ρ = λ ÷ μ` | derived |
| Queue wait | `Wq = ρ ÷ (μ(1−ρ))` — M/M/1 | derived; explodes as ρ → 1, which is why the target is 0.7 |
| Break point | daily volume where `ρ = 1`, holding traffic mix constant | derived |
| Cost per unit | `monthly_infra_cost ÷ monthly_units` | observed spend, or a declared figure |
| Capacity runway | `ln(break_point ÷ current) ÷ ln(1 + growth)` | needs the interview's growth rate |

Values are stored unrounded and rounded only by the renderer, so every derived
identity in `model.json` holds exactly.

## Recommendation ranking

`score = (impact × confidence) ÷ effort_days`

Impact comes from severity for collected risks, from utilisation for capacity
findings, and from margin for economic findings. Confidence is inherited from
the observation that raised it — an assumed capacity number produces a
lower-confidence recommendation than a measured one, and therefore ranks below
it at equal impact. Each item carries an `ACTION_SPEC` (agent prompt, files,
acceptance test, autonomy level) bound to the `DEPLOY_TRIGGER` detected in the
target repository, so the roadmap is executable rather than advisory.

## Testing

`python3 -m tests.test_smoke` runs 30 checks against `fixtures/acme-lending`,
including the arithmetic identities of the capacity model and the requirement
that every observation carries evidence.
