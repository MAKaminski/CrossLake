'use client';

import Link from 'next/link';
import DataTable, { type Column } from './DataTable';
import { date, int, pct } from '@/lib/format';
import type { RunSummary } from '@/lib/types';

export default function RunIndexTable({ runs }: { runs: RunSummary[] }) {
  const columns: Column<RunSummary>[] = [
    {
      key: 'system',
      label: 'System',
      render: (r) => <Link href={`/runs/${r.id}`}>{r.system}</Link>,
      sortValue: (r) => r.system,
    },
    {
      key: 'generated_at',
      label: 'Run date',
      render: (r) => <span className="mono">{date(r.generated_at)}</span>,
      sortValue: (r) => r.generated_at,
    },
    {
      key: 'bottleneck',
      label: 'Bottleneck',
      render: (r) => <span className="mono">{r.bottleneck}</span>,
      sortValue: (r) => r.bottleneck,
    },
    {
      key: 'bottleneck_utilisation',
      label: 'Utilisation',
      numeric: true,
      render: (r) => (
        <span className={r.bottleneck_utilisation >= 0.7 ? 'pill warn' : undefined}>
          {pct(r.bottleneck_utilisation)}
        </span>
      ),
      sortValue: (r) => r.bottleneck_utilisation,
    },
    {
      key: 'break_point_per_day',
      label: 'Break point/day',
      numeric: true,
      render: (r) => int(r.break_point_per_day),
      sortValue: (r) => r.break_point_per_day,
    },
    {
      key: 'now_findings',
      label: 'Now',
      numeric: true,
      render: (r) => (r.now_findings ? <span className="pill crit">{r.now_findings}</span> : '0'),
      sortValue: (r) => r.now_findings,
    },
    {
      key: 'total_findings',
      label: 'Findings',
      numeric: true,
      render: (r) => r.total_findings,
      sortValue: (r) => r.total_findings,
    },
    {
      key: 'observations',
      label: 'Observations',
      numeric: true,
      render: (r) => int(r.observations),
      sortValue: (r) => r.observations,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={runs}
      rowKey={(r) => r.id}
      initialSort="generated_at"
      initialDirection="desc"
      empty="No runs yet."
    />
  );
}
