'use client';

import { useMemo, useState } from 'react';
import DataTable, { type Column } from './DataTable';
import { locatorAnchor } from './EvidenceLink';
import { num } from '@/lib/format';
import type { Observation } from '@/lib/types';

/**
 * The fact base. Every observation the collectors wrote, with the locator and excerpt
 * that establish it — this is what the whole report is reproducible from.
 *
 * The first row for a given locator carries that locator's anchor, so a link from a
 * finding lands on the observation behind it.
 */
export default function EvidenceTable({ observations }: { observations: Observation[] }) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return observations;
    return observations.filter((o) =>
      [o.kind, o.key, o.collector, o.evidence.locator, o.evidence.excerpt, o.evidence.method]
        .join(' ')
        .toLowerCase()
        .includes(q),
    );
  }, [observations, query]);

  // First occurrence of each locator owns the anchor.
  const anchorOwner = useMemo(() => {
    const seen = new Set<string>();
    const owner = new Set<string>();
    for (const o of observations) {
      if (!seen.has(o.evidence.locator)) {
        seen.add(o.evidence.locator);
        owner.add(o.id);
      }
    }
    return owner;
  }, [observations]);

  const columns: Column<Observation>[] = [
    { key: 'kind', label: 'Kind', render: (o) => o.kind, sortValue: (o) => o.kind },
    {
      key: 'key',
      label: 'Key',
      render: (o) => <span className="mono">{o.key}</span>,
      sortValue: (o) => o.key,
    },
    { key: 'layer', label: 'Layer', render: (o) => o.layer ?? '—', sortValue: (o) => o.layer ?? '' },
    {
      key: 'locator',
      label: 'Locator',
      render: (o) => (
        <span className="mono" id={anchorOwner.has(o.id) ? locatorAnchor(o.evidence.locator) : undefined}>
          {o.evidence.locator}
        </span>
      ),
      sortValue: (o) => o.evidence.locator,
    },
    {
      key: 'excerpt',
      label: 'Excerpt',
      render: (o) => <span className="mono">{o.evidence.excerpt}</span>,
      sortValue: (o) => o.evidence.excerpt,
    },
    {
      key: 'method',
      label: 'Method',
      render: (o) => <span className="pill mute">{o.evidence.method}</span>,
      sortValue: (o) => o.evidence.method,
    },
    {
      key: 'collector',
      label: 'Collector',
      render: (o) => o.collector,
      sortValue: (o) => o.collector,
    },
    {
      key: 'confidence',
      label: 'Confidence',
      numeric: true,
      render: (o) => num(o.confidence, 2),
      sortValue: (o) => o.confidence,
    },
  ];

  return (
    <>
      <p>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter observations…"
          className="mono"
          style={{
            width: '100%',
            maxWidth: 360,
            padding: '8px 10px',
            background: 'var(--surface)',
            border: '1px solid var(--rule)',
            color: 'var(--ink)',
          }}
        />{' '}
        <span className="kick">
          {filtered.length} of {observations.length}
        </span>
      </p>
      <DataTable
        columns={columns}
        rows={filtered}
        rowKey={(o) => o.id}
        initialSort="kind"
        initialDirection="asc"
        empty="No observations match that filter."
      />
    </>
  );
}
