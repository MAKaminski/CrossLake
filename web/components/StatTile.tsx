import type { ReactNode } from 'react';

/** The tile from the engine's index.html. */
export function StatTile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="tile">
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      {note ? <span className="note">{note}</span> : null}
    </div>
  );
}

export function Tiles({ children }: { children: ReactNode }) {
  return <div className="tiles">{children}</div>;
}
