/**
 * Mirrors the engine's model.json and 00_EVIDENCE.json exactly.
 *
 * Derived from a real `ae analyze` run against fixtures/acme-lending, not from the
 * documentation. Fields are nullable here wherever that run proves they can be null —
 * capacity numbers are absent, not zero, when no collector established them.
 *
 * The viewer never re-derives a fact. If a number is not in this file, it is not in
 * the report.
 */

/** Every number in the engine carries one of these. A number without a basis is how a
 *  diligence report becomes a liability. */
export type Basis = 'measured' | 'declared' | 'inferred' | 'assumed' | 'stated';

export type Horizon = 'now' | 'next' | 'later';

export type Layer =
  | 'frontend'
  | 'middleware'
  | 'backend'
  | 'data'
  | 'infrastructure'
  | 'external';

// ---------------------------------------------------------------- model.json

export interface UseCase {
  name: string;
  path: string[];
  volume_per_day: number;
  peak_factor: number;
  fanout: Record<string, number>;
  revenue_per_event?: number;
  basis: Basis;
}

export interface CapacityRow {
  component: string;
  layer: Layer | string;
  kind: string;
  tech: string;
  replicas: number | null;
  p95_ms: number | null;
  /** Stored unrounded. Round in the renderer only — rounding here breaks ρ = λ/μ. */
  capacity_rps: number;
  capacity_basis: Basis;
  peak_rps: number;
  utilisation: number;
  headroom_x: number | null;
  queue_wait_ms: number | null;
  break_point_per_day: number | null;
  over_target: boolean;
  monthly_cost: number | null;
  drivers: string[];
}

export interface Capacity {
  rows: CapacityRow[];
  bottleneck: CapacityRow;
  over_target: CapacityRow[];
  target_utilisation: number;
  total_daily_events: number;
  monthly_infra_cost: number | null;
  cost_basis: Basis;
  cost_per_1k_events: number | null;
  system_break_point_per_day: number | null;
}

export interface Flow {
  edge: string;
  src: string;
  dst: string;
  protocol: string;
  mode: 'sync' | 'async' | string;
  calls_per_request: number;
  peak_rps: number;
  payload_bytes: number | null;
  throughput_bps: number | null;
  p95_ms: number | null;
  downstream_utilisation: number | null;
  basis: Basis;
}

export interface BusinessObject {
  entity: string;
  class: 'money' | 'event' | 'party' | 'operational' | string;
  row_count: number | null;
  attributes: number;
  indexed: boolean;
  source: string;
  basis: Basis;
}

export interface UnitEconomics {
  complete: boolean;
  open_questions: string[];
  unit: string | null;
  price_per_unit: number | null;
  units_per_month: number | null;
  monthly_revenue: number | null;
  infra_cost_per_unit: number | null;
  variable_cogs_per_unit: number | null;
  variable_cost_per_unit: number | null;
  contribution_per_unit: number | null;
  contribution_margin_pct: number | null;
  fixed_monthly_cost: number | null;
  monthly_contribution: number | null;
  break_even_units: number | null;
  break_even_vs_today: number | null;
}

export interface ScalingLink {
  growth_rate_monthly: number | null;
  units_per_month: number | null;
  system_break_point_per_month: number | null;
  months_of_headroom: number | null;
  bottleneck: string;
}

export interface RevenuePath {
  usecase: string;
  touches_money_objects: string[];
  volume_per_day: number;
  revenue_per_event: number;
  basis: Basis;
}

export interface Ontology {
  purpose: string | null;
  objects: BusinessObject[];
  class_counts: Record<string, number>;
  unit_economics: UnitEconomics;
  scaling_link: ScalingLink;
  revenue_paths: RevenuePath[];
  counterparties: string[];
  compliance: string[];
  sla: string | null;
  deploy_trigger: string | null;
  /** Unanswered interview questions. Never a guess — an absent answer stays absent. */
  open_questions: string[];
}

export interface ActionTrigger {
  mode: 'git' | 'manual';
  detail: string;
  gate: string;
}

export interface ActionSpec {
  agent_prompt: string;
  files: string[];
  acceptance: string;
  autonomy: string;
  trigger: ActionTrigger;
}

export interface Recommendation {
  id: string;
  title: string;
  finding: string;
  layer: Layer | string;
  category: string;
  impact: number;
  effort_days: number;
  confidence: number;
  /** score = (impact x confidence) / effort_days */
  score: number;
  action: ActionSpec;
  kpi: string;
  /** Evidence locator strings, e.g. "infra/terraform/main.tf:9". Resolve against
   *  EvidenceFile.observations to get the excerpt and method behind the claim. */
  evidence: string[];
  math: string | null;
  rank: number;
  horizon: Horizon;
}

export interface GrowthRow {
  entity: string;
  rows_now: number;
  growth_per_day: number;
  rows_at_horizon: number;
  multiple: number | null;
  horizon_months: number;
}

export interface Model {
  target: string;
  usecases: UseCase[];
  capacity: Capacity;
  flows: Flow[];
  ontology: Ontology;
  recommendations: Recommendation[];
  growth: GrowthRow[];
}

// ---------------------------------------------------------- 00_EVIDENCE.json

export interface Evidence {
  locator: string;
  excerpt: string;
  method: string;
}

export interface Observation {
  id: string;
  kind: string;
  key: string;
  layer?: string;
  attrs: Record<string, unknown>;
  confidence: number;
  collector: string;
  evidence: Evidence;
  observed_at: number;
}

export interface EvidenceFile {
  schema_version: string;
  target: Record<string, unknown>;
  /** model.json carries no timestamp — the run date comes from here. */
  generated_at: string;
  counts: Record<string, number>;
  observations: Observation[];
}

// ------------------------------------------------------------- viewer types

/** The six markdown documents, in the order the engine numbers them. */
export const DOCUMENTS = [
  '01_ARCHITECTURE.md',
  '02_FLOWS.md',
  '03_ERD.md',
  '04_CAPACITY.md',
  '05_ONTOLOGY.md',
  '06_ROADMAP.md',
] as const;

export type DocumentName = (typeof DOCUMENTS)[number];

/** The summary row written to index/<runId>.json at ingest. Everything the run index
 *  needs, so listing never has to open a model.json. */
export interface RunSummary {
  id: string;
  system: string;
  generated_at: string;
  bottleneck: string;
  bottleneck_utilisation: number;
  break_point_per_day: number | null;
  now_findings: number;
  total_findings: number;
  observations: number;
  ingested_at: string;
}

export interface Run {
  summary: RunSummary;
  model: Model;
  evidence: EvidenceFile;
}
