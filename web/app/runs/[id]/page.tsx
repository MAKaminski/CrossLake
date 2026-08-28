import { notFound } from 'next/navigation';
import Markdown from '@/components/Markdown';
import { loadDoc } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function Architecture({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const doc = await loadDoc(id, '01_ARCHITECTURE.md');
  if (doc === null) notFound();
  return <Markdown>{doc}</Markdown>;
}
