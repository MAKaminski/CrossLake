'use client';

export default function RunError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <>
      <h1>Run unavailable</h1>
      <div className="empty">
        <p className="kick">The artifact store could not be read</p>
        <p className="mono">{error.message}</p>
        <p>
          This is a coverage gap, not a finding that the run is absent. Check that{' '}
          <code>BLOB_READ_WRITE_TOKEN</code> is set for this environment.
        </p>
        <button
          type="button"
          onClick={reset}
          className="pill mute"
          style={{ background: 'none', cursor: 'pointer' }}
        >
          retry
        </button>
      </div>
    </>
  );
}
