'use client';

import DataTable, { type Column } from './DataTable';
import { int, num, pct, utilisationClass } from '@/lib/format';
import type { CapacityRow } from '@/lib/types';

/** A column configuration over DataTable, not a second table. */
export default function CapacityTable({
  rows,
  targetUtilisation,
}: {
  rows: CapacityRow[];
  targetUtilisation: number;
}) {
  const columns: Column<CapacityRow>[] = [
    {
      key: 'component',
      label: 'Component',
      render: (r) => r.component,
      sortValue: (r) => r.component,
    },
    { key: 'layer', label: 'Layer', render: (r) => r.layer, sortValue: (r) => r.layer },
    {
      key: 'capacity_rps',
      label: 'Capacity rps',
      numeric: true,
      render: (r) => num(r.capacity_rps),
      sortValue: (r) => r.capacity_rps,
    },
    {
      key: 'peak_rps',
      label: 'Peak rps',
      numeric: true,
      render: (r) => num(r.peak_rps, 2),
      sortValue: (r) => r.peak_rps,
    },
    {
      key: 'headroom_x',
      label: 'Headroom',
      numeric: true,
      render: (r) => (r.headroom_x === null ? '—' : `${num(r.headroom_x)}x`),
      sortValue: (r) => r.headroom_x,
    },
    {
      key: 'utilisation',
      label: 'Utilisation',
      render: (r) => (
        <>
          <span className="bar">
            <span
              className={r.utilisation >= targetUtilisation ? 'over' : undefined}
              style={{ width: `${Math.min(100, Math.round(r.utilisation * 100))}%` }}
            />
          </span>
          <span className="num">{pct(r.utilisation)}</span>
        </>
      ),
      sortValue: (r) => r.utilisation,
    },
    {
      key: 'queue_wait_ms',
      label: 'Queue wait ms',
      numeric: true,
      render: (r) => num(r.queue_wait_ms, 2),
      sortValue: (r) => r.queue_wait_ms,
    },
    {
      key: 'break_point_per_day',
      label: 'Break point/day',
      numeric: true,
      render: (r) => int(r.break_point_per_day),
      sortValue: (r) => r.break_point_per_day,
    },
    {
      key: 'capacity_basis',
      label: 'Basis',
      render: (r) => (
        <span className={`pill ${r.capacity_basis === 'measured' ? 'ok' : 'mute'}`}>
          {r.capacity_basis}
        </span>
      ),
      sortValue: (r) => r.capacity_basis,
    },
    {
      key: 'status',
      label: 'Status',
      render: (r) => (
        <span className={`pill ${utilisationClass(r.utilisation, targetUtilisation)}`}>
          {r.utilisation >= 1 ? 'over capacity' : r.over_target ? 'over target' : 'ok'}
        </span>
      ),
      sortValue: (r) => r.utilisation,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.component}
      initialSort="utilisation"
      initialDirection="desc"
      empty="No capacity rows — no use case resolved onto a collected component."
    />
  );
}
