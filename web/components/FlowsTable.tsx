'use client';

import DataTable, { type Column } from './DataTable';
import { int, num, pct } from '@/lib/format';
import type { Flow } from '@/lib/types';

export default function FlowsTable({ flows }: { flows: Flow[] }) {
  const columns: Column<Flow>[] = [
    { key: 'edge', label: 'Transfer', render: (f) => f.edge, sortValue: (f) => f.edge },
    { key: 'protocol', label: 'Protocol', render: (f) => f.protocol, sortValue: (f) => f.protocol },
    {
      key: 'mode',
      label: 'Mode',
      render: (f) => <span className={`pill ${f.mode === 'sync' ? 'warn' : 'mute'}`}>{f.mode}</span>,
      sortValue: (f) => f.mode,
    },
    {
      key: 'calls_per_request',
      label: 'Calls/req',
      numeric: true,
      render: (f) => num(f.calls_per_request, 2),
      sortValue: (f) => f.calls_per_request,
    },
    {
      key: 'peak_rps',
      label: 'Peak rps',
      numeric: true,
      render: (f) => num(f.peak_rps, 2),
      sortValue: (f) => f.peak_rps,
    },
    {
      key: 'payload_bytes',
      label: 'Payload B',
      numeric: true,
      render: (f) => int(f.payload_bytes),
      sortValue: (f) => f.payload_bytes,
    },
    {
      key: 'throughput_bps',
      label: 'Throughput B/s',
      numeric: true,
      render: (f) => int(f.throughput_bps),
      sortValue: (f) => f.throughput_bps,
    },
    {
      key: 'p95_ms',
      label: 'p95 ms',
      numeric: true,
      render: (f) => num(f.p95_ms),
      sortValue: (f) => f.p95_ms,
    },
    {
      key: 'downstream_utilisation',
      label: 'Downstream ρ',
      numeric: true,
      render: (f) => pct(f.downstream_utilisation, 1),
      sortValue: (f) => f.downstream_utilisation,
    },
    {
      key: 'basis',
      label: 'Basis',
      render: (f) => (
        <span className={`pill ${f.basis === 'measured' ? 'ok' : 'mute'}`}>{f.basis}</span>
      ),
      sortValue: (f) => f.basis,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={flows}
      rowKey={(f) => f.edge}
      initialSort="peak_rps"
      empty="No transfers found."
    />
  );
}
