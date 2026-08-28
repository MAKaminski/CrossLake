import { notFound } from 'next/navigation';
import GrowthTable from '@/components/GrowthTable';
import Markdown from '@/components/Markdown';
import { loadDoc, loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function Erd({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [run, doc] = await Promise.all([loadRun(id), loadDoc(id, '03_ERD.md')]);
  if (!run || doc === null) notFound();

  const growth = run.model.growth;

  return (
    <>
      <Markdown>{doc}</Markdown>
      <h2>Growth projection</h2>
      {growth.length ? (
        <GrowthTable rows={growth} />
      ) : (
        <div className="empty">
          No row counts were collected, so growth cannot be projected. This is a coverage
          gap, not a finding of no growth — enable the database collector to establish it.
        </div>
      )}
    </>
  );
}
