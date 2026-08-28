import type { Metadata } from 'next';
import { Archivo, IBM_Plex_Mono, Source_Serif_4 } from 'next/font/google';
import Link from 'next/link';
import ThemeToggle from '@/components/ThemeToggle';
import './globals.css';

// Self-hosted through next/font — no external stylesheet request, unlike the
// standalone index.html which links Google Fonts directly.
const archivo = Archivo({
  subsets: ['latin'],
  weight: ['500', '600', '700'],
  variable: '--font-archivo',
});
const sourceSerif = Source_Serif_4({
  subsets: ['latin'],
  weight: ['400', '600'],
  variable: '--font-source-serif',
});
const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-plex-mono',
});

export const metadata: Metadata = {
  title: 'Analysis Engine',
  description: 'Technical due-diligence runs: architecture, throughput, scaling math, ontology and a ranked roadmap.',
  robots: { index: false, follow: false },
};

/** Applied before paint so an explicit theme choice never flashes the other palette. */
const THEME_INIT = `try{var t=localStorage.getItem('ae-theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${sourceSerif.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <div className="wrap">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16 }}>
            <Link href="/" className="kick" style={{ textDecoration: 'none' }}>
              Analysis Engine
            </Link>
            <ThemeToggle />
          </div>
          {children}
          <footer>
            Every number traces to an evidence locator in <code>00_EVIDENCE.json</code>.
            Measured, declared, inferred and assumed are labelled wherever they appear.
          </footer>
        </div>
      </body>
    </html>
  );
}
