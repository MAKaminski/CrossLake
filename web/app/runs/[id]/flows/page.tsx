import { notFound } from 'next/navigation';
import FlowsTable from '@/components/FlowsTable';
import Markdown from '@/components/Markdown';
import { loadDoc, loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function Flows({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [run, doc] = await Promise.all([loadRun(id), loadDoc(id, '02_FLOWS.md')]);
  if (!run || doc === null) notFound();

  return (
    <>
      <h2>Transfer processes</h2>
      <FlowsTable flows={run.model.flows} />
      <Markdown>{doc}</Markdown>
    </>
  );
}
