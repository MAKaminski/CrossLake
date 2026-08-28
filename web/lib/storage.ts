import { put, list, get } from '@vercel/blob';
import type {
  DocumentName,
  EvidenceFile,
  Model,
  Run,
  RunSummary,
} from './types';
import { DOCUMENTS } from './types';

/**
 * The only module that touches Blob, mirroring the engine's rule that collectors are
 * the only modules that touch the outside world.
 *
 * Every object is written with access:'private'. A public blob URL would sit outside
 * Deployment Protection entirely, so a public artifact would make the whole protection
 * posture decorative.
 *
 * There is no database. The run index is append-only: one small summary blob per run
 * under index/, never a shared mutable manifest, so two concurrent ingests cannot race.
 * Listing is O(number of runs) small reads; past roughly 200 runs, move the index into
 * a real store (Neon via the Vercel Marketplace) rather than making this cleverer.
 */

const ACCESS = 'private' as const;

export const RUN_FILES = ['model.json', '00_EVIDENCE.json', ...DOCUMENTS, 'index.html'] as const;

function runPath(id: string, file: string) {
  return `runs/${id}/${file}`;
}

function indexPath(id: string) {
  return `index/${id}.json`;
}

function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'system';
}

/** `<system>-<compact iso>-<rand4>` — readable, sortable, collision-safe. */
export function makeRunId(system: string, generatedAt: string): string {
  const compact = generatedAt.replace(/[-:]/g, '').replace(/\..*$/, '');
  const rand = Math.random().toString(16).slice(2, 6);
  return `${slug(system)}-${compact}-${rand}`;
}

/** Build the index row from the model and evidence. Pure — no derivation of new facts,
 *  only selection of ones the engine already established. */
export function summarize(
  id: string,
  model: Model,
  evidence: EvidenceFile,
  ingestedAt: string,
): RunSummary {
  const b = model.capacity.bottleneck;
  return {
    id,
    system: model.target,
    generated_at: evidence.generated_at,
    bottleneck: b.component,
    bottleneck_utilisation: b.utilisation,
    break_point_per_day: model.capacity.system_break_point_per_day,
    now_findings: model.recommendations.filter((r) => r.horizon === 'now').length,
    total_findings: model.recommendations.length,
    observations: evidence.observations.length,
    ingested_at: ingestedAt,
  };
}

export async function putRun(
  id: string,
  files: Record<string, string>,
  summary: RunSummary,
): Promise<void> {
  await Promise.all(
    Object.entries(files).map(([name, body]) =>
      put(runPath(id, name), body, {
        access: ACCESS,
        contentType: name.endsWith('.json')
          ? 'application/json'
          : name.endsWith('.html')
            ? 'text/html'
            : 'text/markdown',
        addRandomSuffix: false,
        allowOverwrite: true,
      }),
    ),
  );

  // Index row last: a run only appears once its artifacts are all readable.
  await put(indexPath(id), JSON.stringify(summary), {
    access: ACCESS,
    contentType: 'application/json',
    addRandomSuffix: false,
    allowOverwrite: true,
  });
}

async function readJson<T>(pathname: string): Promise<T | null> {
  const result = await get(pathname, { access: ACCESS });
  if (!result) return null;
  return JSON.parse(await new Response(result.stream).text()) as T;
}

async function readText(pathname: string): Promise<string | null> {
  const result = await get(pathname, { access: ACCESS });
  if (!result) return null;
  return new Response(result.stream).text();
}

/** Every run's summary row, newest first. */
export async function listRuns(): Promise<RunSummary[]> {
  const rows: RunSummary[] = [];
  let cursor: string | undefined;

  do {
    const page = await list({ prefix: 'index/', cursor, limit: 250 });
    const batch = await Promise.all(
      page.blobs.map((b) => readJson<RunSummary>(b.pathname)),
    );
    for (const row of batch) if (row) rows.push(row);
    cursor = page.cursor;
  } while (cursor);

  return rows.sort((a, b) => b.generated_at.localeCompare(a.generated_at));
}

export async function getRun(id: string): Promise<Run | null> {
  const [summary, model, evidence] = await Promise.all([
    readJson<RunSummary>(indexPath(id)),
    readJson<Model>(runPath(id, 'model.json')),
    readJson<EvidenceFile>(runPath(id, '00_EVIDENCE.json')),
  ]);
  if (!summary || !model || !evidence) return null;
  return { summary, model, evidence };
}

export async function getDoc(id: string, name: DocumentName): Promise<string | null> {
  return readText(runPath(id, name));
}

/** All six markdown documents for a run, in engine order. */
export async function getDocs(id: string): Promise<Record<DocumentName, string>> {
  const bodies = await Promise.all(DOCUMENTS.map((d) => getDoc(id, d)));
  const out = {} as Record<DocumentName, string>;
  DOCUMENTS.forEach((d, i) => {
    out[d] = bodies[i] ?? '';
  });
  return out;
}
