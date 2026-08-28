import { notFound } from 'next/navigation';
import Tabs from '@/components/Tabs';
import { StatTile, Tiles } from '@/components/StatTile';
import { date, int, pct } from '@/lib/format';
import { loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function RunLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const run = await loadRun(id);
  if (!run) notFound();

  const { model, evidence, summary } = run;
  const { capacity, ontology } = model;

  return (
    <>
      <span className="kick">Analysis Engine · {date(evidence.generated_at)}</span>
      <h1>{model.target}</h1>
      <p className="sub">
        Context architecture, transfer throughput, scaling math and a ranked roadmap,
        derived from {evidence.observations.length} observations. Every number traces to an
        evidence locator in <code>00_EVIDENCE.json</code>.
      </p>

      <Tiles>
        <StatTile label="Components" value={capacity.rows.length} />
        <StatTile label="Transfers" value={model.flows.length} />
        <StatTile label="Entities" value={ontology.objects.length} />
        <StatTile
          label="Findings"
          value={model.recommendations.length}
          note={`${summary.now_findings} at the now horizon`}
        />
        <StatTile
          label="Bottleneck"
          value={pct(capacity.bottleneck.utilisation)}
          note={capacity.bottleneck.component}
        />
        <StatTile
          label="Break point / day"
          value={int(capacity.system_break_point_per_day)}
          note={`vs ${int(capacity.total_daily_events)} today`}
        />
      </Tiles>

      <Tabs runId={id} />
      {children}
    </>
  );
}
