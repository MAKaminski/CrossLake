'use client';

import DataTable, { type Column } from './DataTable';
import { int, num } from '@/lib/format';
import type { GrowthRow } from '@/lib/types';

export default function GrowthTable({ rows }: { rows: GrowthRow[] }) {
  const columns: Column<GrowthRow>[] = [
    { key: 'entity', label: 'Entity', render: (r) => r.entity, sortValue: (r) => r.entity },
    {
      key: 'rows_now',
      label: 'Rows now',
      numeric: true,
      render: (r) => int(r.rows_now),
      sortValue: (r) => r.rows_now,
    },
    {
      key: 'growth_per_day',
      label: 'Rows/day',
      numeric: true,
      render: (r) => int(r.growth_per_day),
      sortValue: (r) => r.growth_per_day,
    },
    {
      key: 'rows_at_horizon',
      label: 'At horizon',
      numeric: true,
      render: (r) => int(r.rows_at_horizon),
      sortValue: (r) => r.rows_at_horizon,
    },
    {
      key: 'multiple',
      label: 'Multiple',
      numeric: true,
      render: (r) => (r.multiple === null ? '—' : `${num(r.multiple)}x`),
      sortValue: (r) => r.multiple,
    },
    {
      key: 'horizon_months',
      label: 'Months',
      numeric: true,
      render: (r) => r.horizon_months,
      sortValue: (r) => r.horizon_months,
    },
  ];

  return <DataTable columns={columns} rows={rows} rowKey={(r) => r.entity} initialSort="multiple" />;
}
