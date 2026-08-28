'use client';

import DataTable, { type Column } from './DataTable';
import EvidenceLink from './EvidenceLink';
import { num } from '@/lib/format';
import type { Horizon, Recommendation } from '@/lib/types';

const HORIZON_CLASS: Record<Horizon, string> = {
  now: 'crit',
  next: 'warn',
  later: 'mute',
};

/**
 * The ranked roadmap: the table carries the ranking data, the cards carry the
 * agent-executable action. Both come straight from model.json.
 */
export default function RoadmapList({
  runId,
  recommendations,
}: {
  runId: string;
  recommendations: Recommendation[];
}) {
  const columns: Column<Recommendation>[] = [
    { key: 'rank', label: '#', numeric: true, render: (r) => r.rank, sortValue: (r) => r.rank },
    {
      key: 'title',
      label: 'Recommendation',
      render: (r) => <a href={`#${r.id}`}>{r.title}</a>,
      sortValue: (r) => r.title,
    },
    {
      key: 'horizon',
      label: 'Horizon',
      render: (r) => <span className={`pill ${HORIZON_CLASS[r.horizon] ?? 'mute'}`}>{r.horizon}</span>,
      sortValue: (r) => ({ now: 0, next: 1, later: 2 })[r.horizon] ?? 3,
    },
    { key: 'layer', label: 'Layer', render: (r) => r.layer, sortValue: (r) => r.layer },
    { key: 'category', label: 'Category', render: (r) => r.category, sortValue: (r) => r.category },
    {
      key: 'impact',
      label: 'Impact',
      numeric: true,
      render: (r) => num(r.impact),
      sortValue: (r) => r.impact,
    },
    {
      key: 'effort_days',
      label: 'Effort d',
      numeric: true,
      render: (r) => num(r.effort_days),
      sortValue: (r) => r.effort_days,
    },
    {
      key: 'confidence',
      label: 'Confidence',
      numeric: true,
      render: (r) => num(r.confidence, 2),
      sortValue: (r) => r.confidence,
    },
    {
      key: 'score',
      label: 'Score',
      numeric: true,
      render: (r) => num(r.score, 2),
      sortValue: (r) => r.score,
    },
  ];

  return (
    <>
      <DataTable
        columns={columns}
        rows={recommendations}
        rowKey={(r) => r.id}
        initialSort="rank"
        initialDirection="asc"
        empty="No recommendations — nothing in the fact base raised one."
      />

      <h3>Actions</h3>
      <p className="sub">
        Each item carries an agent prompt, an acceptance test and the deployment trigger
        already present in the target repository, so the roadmap is executable rather than
        advisory.
      </p>

      {recommendations.map((r) => (
        <div className="card" id={r.id} key={r.id}>
          <span className="kick">
            {r.rank} · {r.layer} · {r.category}
          </span>
          <h3 style={{ marginTop: 6 }}>
            {r.title} <span className={`pill ${HORIZON_CLASS[r.horizon] ?? 'mute'}`}>{r.horizon}</span>
          </h3>
          <p style={{ marginTop: 0 }}>{r.finding}</p>
          {r.math ? <p className="mono">{r.math}</p> : null}

          <table>
            <tbody>
              <tr>
                <th style={{ width: 150 }}>Agent prompt</th>
                <td>{r.action.agent_prompt}</td>
              </tr>
              <tr>
                <th>Files</th>
                <td className="mono">{r.action.files.join(', ') || '—'}</td>
              </tr>
              <tr>
                <th>Acceptance</th>
                <td>{r.action.acceptance}</td>
              </tr>
              <tr>
                <th>Autonomy</th>
                <td>{r.action.autonomy}</td>
              </tr>
              <tr>
                <th>Trigger</th>
                <td>
                  <span className="pill mute">{r.action.trigger.mode}</span> {r.action.trigger.detail}
                  <br />
                  <span className="kick">Gate: {r.action.trigger.gate}</span>
                </td>
              </tr>
              <tr>
                <th>KPI</th>
                <td>{r.kpi}</td>
              </tr>
              <tr>
                <th>Evidence</th>
                <td>
                  {r.evidence.length ? (
                    r.evidence.map((locator, i) => (
                      <span key={locator}>
                        {i > 0 ? ', ' : ''}
                        <EvidenceLink runId={runId} locator={locator} />
                      </span>
                    ))
                  ) : (
                    <span className="pill crit">no locator</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}
