'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { slug: '', label: 'Architecture' },
  { slug: 'flows', label: 'Flows' },
  { slug: 'erd', label: 'ERD' },
  { slug: 'capacity', label: 'Capacity' },
  { slug: 'ontology', label: 'Ontology' },
  { slug: 'roadmap', label: 'Roadmap' },
  { slug: 'evidence', label: 'Evidence' },
];

export default function Tabs({ runId }: { runId: string }) {
  const pathname = usePathname();
  const base = `/runs/${runId}`;

  return (
    <nav className="tabs">
      {TABS.map((t) => {
        const href = t.slug ? `${base}/${t.slug}` : base;
        return (
          <Link key={t.slug} href={href} aria-current={pathname === href ? 'page' : undefined}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
