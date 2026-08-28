import { NextResponse } from 'next/server';
import { isAuthorized } from '@/lib/auth';
import { RUN_FILES, listRuns, makeRunId, putRun, summarize } from '@/lib/storage';
import type { EvidenceFile, Model } from '@/lib/types';

export const runtime = 'nodejs';
export const maxDuration = 60;
export const dynamic = 'force-dynamic';

/** A full run is ~90 KB. The platform allows 100 MB; this endpoint has no reason to
 *  accept anything near that, so cap it well below and reject early on Content-Length. */
const MAX_BYTES = 10 * 1024 * 1024;

const ALLOWED = new Set<string>(RUN_FILES);

interface IngestBody {
  files?: Record<string, string>;
}

export async function POST(request: Request) {
  if (!isAuthorized(request.headers.get('authorization'))) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const declared = Number(request.headers.get('content-length') ?? '0');
  if (declared > MAX_BYTES) {
    return NextResponse.json(
      { error: `payload too large: ${declared} bytes, limit ${MAX_BYTES}` },
      { status: 413 },
    );
  }

  const raw = await request.text();
  // Content-Length can lie or be absent under chunked encoding; check what arrived.
  if (Buffer.byteLength(raw) > MAX_BYTES) {
    return NextResponse.json({ error: 'payload too large' }, { status: 413 });
  }

  let body: IngestBody;
  try {
    body = JSON.parse(raw) as IngestBody;
  } catch {
    return NextResponse.json({ error: 'body is not valid json' }, { status: 400 });
  }

  const files = body.files ?? {};
  if (typeof files['model.json'] !== 'string') {
    return NextResponse.json(
      { error: 'payload must contain model.json' },
      { status: 400 },
    );
  }
  if (typeof files['00_EVIDENCE.json'] !== 'string') {
    return NextResponse.json(
      { error: 'payload must contain 00_EVIDENCE.json — the report is not reproducible without it' },
      { status: 400 },
    );
  }

  const unknown = Object.keys(files).filter((name) => !ALLOWED.has(name));
  if (unknown.length) {
    return NextResponse.json(
      { error: `unexpected files: ${unknown.join(', ')}` },
      { status: 400 },
    );
  }

  let model: Model;
  let evidence: EvidenceFile;
  try {
    model = JSON.parse(files['model.json']) as Model;
    evidence = JSON.parse(files['00_EVIDENCE.json']) as EvidenceFile;
  } catch {
    return NextResponse.json(
      { error: 'model.json or 00_EVIDENCE.json is not valid json' },
      { status: 400 },
    );
  }
  if (!model.target || !model.capacity?.bottleneck || !evidence.generated_at) {
    return NextResponse.json(
      { error: 'model.json or 00_EVIDENCE.json is not a complete engine run' },
      { status: 400 },
    );
  }

  const id = makeRunId(model.target, evidence.generated_at);
  const summary = summarize(id, model, evidence, new Date().toISOString());
  await putRun(id, files, summary);

  return NextResponse.json({ id, summary }, { status: 201 });
}

export async function GET() {
  try {
    return NextResponse.json({ runs: await listRuns() });
  } catch (err) {
    // An unreadable store is a coverage gap, not an empty index. Returning [] here
    // would let a missing finding read as a clean one.
    return NextResponse.json(
      {
        error: 'run index unavailable',
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 503 },
    );
  }
}
