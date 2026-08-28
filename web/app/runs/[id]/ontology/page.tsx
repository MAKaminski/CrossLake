import { notFound } from 'next/navigation';
import Markdown from '@/components/Markdown';
import { StatTile, Tiles } from '@/components/StatTile';
import { int, money, num, pct } from '@/lib/format';
import { loadDoc, loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function OntologyTab({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [run, doc] = await Promise.all([loadRun(id), loadDoc(id, '05_ONTOLOGY.md')]);
  if (!run || doc === null) notFound();

  const o = run.model.ontology;
  const e = o.unit_economics;

  return (
    <>
      <h2>Unit economics</h2>
      {e.complete ? (
        <Tiles>
          <StatTile label="Billable unit" value={e.unit ?? '—'} />
          <StatTile label="Price / unit" value={money(e.price_per_unit)} />
          <StatTile
            label="Contribution / unit"
            value={money(e.contribution_per_unit)}
            note={`${num(e.contribution_margin_pct)}% margin`}
          />
          <StatTile label="Infra cost / unit" value={money(e.infra_cost_per_unit)} />
          <StatTile
            label="Break-even units"
            value={int(e.break_even_units)}
            note={`${pct(e.break_even_vs_today, 0)} of today's volume`}
          />
          <StatTile
            label="Months of headroom"
            value={num(o.scaling_link.months_of_headroom)}
            note={`bottleneck: ${o.scaling_link.bottleneck}`}
          />
        </Tiles>
      ) : (
        <div className="empty">
          Unit economics are incomplete — {e.open_questions.length} interview answers are
          missing. Nulls become open questions rather than guesses.
        </div>
      )}

      {o.open_questions.length ? (
        <>
          <h2>Open questions</h2>
          <div className="card">
            <ul style={{ marginBottom: 0 }}>
              {o.open_questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        </>
      ) : null}

      <Markdown>{doc}</Markdown>
    </>
  );
}
