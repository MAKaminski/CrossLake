import RunIndexTable from '@/components/RunIndexTable';
import { listRuns } from '@/lib/storage';
import type { RunSummary } from '@/lib/types';

export const dynamic = 'force-dynamic';

export default async function Home() {
  let runs: RunSummary[] = [];
  let error: string | null = null;

  try {
    runs = await listRuns();
  } catch (err) {
    // A store that cannot be read is a coverage gap, not an empty index. Saying
    // "no runs" here would read as a clean result.
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <>
      <h1>Runs</h1>
      <p className="sub">
        Completed analyses, newest first. The engine runs where the access already is; this
        app receives finished runs and renders them. It never re-derives a fact.
      </p>

      {error ? (
        <div className="empty">
          <p className="kick">Run index unavailable</p>
          <p className="mono" style={{ marginBottom: 0 }}>{error}</p>
          <p style={{ marginBottom: 0 }}>
            This is a coverage gap, not an empty index. Check that{' '}
            <code>BLOB_READ_WRITE_TOKEN</code> is set for this environment.
          </p>
        </div>
      ) : runs.length === 0 ? (
        <div className="empty">
          <p className="kick">No runs ingested yet</p>
          <p style={{ marginBottom: 0 }}>
            Publish one with <code>engine/scripts/publish.py</code>, or dispatch the{' '}
            <code>analyze</code> workflow.
          </p>
        </div>
      ) : (
        <RunIndexTable runs={runs} />
      )}
    </>
  );
}
