import { NextResponse } from 'next/server';
import { getRun } from '@/lib/storage';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const run = await getRun(id);
    if (!run) return NextResponse.json({ error: 'not found' }, { status: 404 });
    return NextResponse.json(run);
  } catch (err) {
    // Distinguish "this run does not exist" (404) from "the store cannot be read"
    // (503). Collapsing the two would turn an outage into a clean negative result.
    return NextResponse.json(
      {
        error: 'run store unavailable',
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 503 },
    );
  }
}
