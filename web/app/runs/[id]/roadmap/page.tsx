import { notFound } from 'next/navigation';
import RoadmapList from '@/components/RoadmapList';
import { loadRun } from '@/lib/run';

export const dynamic = 'force-dynamic';

export default async function Roadmap({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await loadRun(id);
  if (!run) notFound();

  return (
    <>
      <h2>Ranked roadmap</h2>
      <p className="sub">
        <span className="mono">score = (impact × confidence) ÷ effort_days</span>. Confidence
        is inherited from the observation that raised the item, so an assumed number ranks
        below a measured one at equal impact.
      </p>
      <RoadmapList runId={id} recommendations={run.model.recommendations} />
    </>
  );
}
