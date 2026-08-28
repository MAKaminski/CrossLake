import { notFound } from 'next/navigation';
import CapacityTable from '@/components/CapacityTable';
import Markdown from '@/components/Markdown';
import { StatTile, Tiles } from '@/components/StatTile';
import { int, money, num, pct } from '@/lib/format';
import { loadDoc, loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function Capacity({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [run, doc] = await Promise.all([loadRun(id), loadDoc(id, '04_CAPACITY.md')]);
  if (!run || doc === null) notFound();

  const c = run.model.capacity;

  return (
    <>
      <h2>Scaling math</h2>
      <Tiles>
        <StatTile label="Target utilisation" value={pct(c.target_utilisation)} />
        <StatTile label="Daily events" value={int(c.total_daily_events)} />
        <StatTile
          label="Break point / day"
          value={int(c.system_break_point_per_day)}
          note={`${num(c.bottleneck.headroom_x)}x headroom at the bottleneck`}
        />
        <StatTile
          label="Monthly infra"
          value={money(c.monthly_infra_cost)}
          note={<span className="pill mute">{c.cost_basis}</span>}
        />
        <StatTile label="Cost / 1k events" value={money(c.cost_per_1k_events)} />
        <StatTile
          label="Over target"
          value={c.over_target.length}
          note={c.over_target.map((r) => r.component).join(', ') || 'none'}
        />
      </Tiles>

      {/* Rendered from model.json rather than from the prose, because this is data. */}
      <CapacityTable rows={c.rows} targetUtilisation={c.target_utilisation} />

      <Markdown>{doc}</Markdown>
    </>
  );
}
