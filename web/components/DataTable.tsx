'use client';

import { useMemo, useState, type ReactNode } from 'react';

export interface Column<T> {
  key: string;
  label: string;
  /** Right-aligned with tabular numerals. */
  numeric?: boolean;
  render: (row: T) => ReactNode;
  /** Value used for sorting. Omit to make the column unsortable. */
  sortValue?: (row: T) => number | string | null;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Column key to sort by initially. */
  initialSort?: string;
  initialDirection?: 'asc' | 'desc';
  empty?: string;
}

/**
 * The only table in the app. Capacity, roadmap, flows, entities, evidence and the run
 * index are all column configurations over this component — not separate tables. Same
 * table everywhere is the point.
 */
export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  initialSort,
  initialDirection = 'desc',
  empty = 'Nothing to show.',
}: Props<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(initialSort);
  const [direction, setDirection] = useState<'asc' | 'desc'>(initialDirection);

  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sortKey);
    if (!column?.sortValue) return rows;
    const get = column.sortValue;
    const factor = direction === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      // Nulls are absent measurements, not zeros. They sort last either way.
      if (x === null && y === null) return 0;
      if (x === null) return 1;
      if (y === null) return -1;
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * factor;
      return String(x).localeCompare(String(y)) * factor;
    });
  }, [columns, rows, sortKey, direction]);

  function toggle(column: Column<T>) {
    if (!column.sortValue) return;
    if (column.key === sortKey) {
      setDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(column.key);
      setDirection('desc');
    }
  }

  if (!rows.length) return <div className="empty">{empty}</div>;

  return (
    <div className="tw">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={[c.numeric ? 'num' : '', c.sortValue ? 'sortable' : ''].join(' ').trim()}
                onClick={() => toggle(c)}
                aria-sort={
                  c.key === sortKey ? (direction === 'asc' ? 'ascending' : 'descending') : undefined
                }
              >
                {c.label}
                {c.key === sortKey ? (
                  <span className="arrow">{direction === 'asc' ? '▲' : '▼'}</span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? 'num' : undefined}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
