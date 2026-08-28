import { notFound } from 'next/navigation';
import EvidenceTable from '@/components/EvidenceTable';
import { StatTile, Tiles } from '@/components/StatTile';
import { date } from '@/lib/format';
import { loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function EvidenceTab({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await loadRun(id);
  if (!run) notFound();

  const { evidence } = run;

  return (
    <>
      <h2>Evidence</h2>
      <p className="sub">
        Every fact the collectors established, with the locator and excerpt behind it. The
        whole report is reproducible from this file alone. Findings link in here.
      </p>

      <Tiles>
        <StatTile label="Observations" value={evidence.observations.length} />
        <StatTile label="Schema" value={evidence.schema_version} />
        <StatTile label="Generated" value={<span className="mono" style={{ fontSize: 16 }}>{date(evidence.generated_at)}</span>} />
        {Object.entries(evidence.counts).map(([kind, count]) => (
          <StatTile key={kind} label={kind} value={count} />
        ))}
      </Tiles>

      <EvidenceTable observations={evidence.observations} />
    </>
  );
}
