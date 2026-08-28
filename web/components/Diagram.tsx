'use client';

import { useEffect, useId, useState } from 'react';

/**
 * Mermaid renderer.
 *
 * This component is a Client Component by construction, which is what makes the
 * mermaid import legal: `ssr: false` is not allowed with next/dynamic inside a Server
 * Component, so the library is imported here in an effect instead. Mermaid also needs
 * a DOM to measure text, so there is nothing to gain from prerendering it.
 *
 * Colours come from the live CSS variables, so the diagram follows the same palette
 * as the rest of the page in all three theme states.
 */
export default function Diagram({ chart }: { chart: string }) {
  const reactId = useId();
  const id = `mermaid-${reactId.replace(/[^a-zA-Z0-9]/g, '')}`;
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [themeTick, setThemeTick] = useState(0);

  // Re-render when the viewer flips theme, either explicitly or at the OS level.
  useEffect(() => {
    const bump = () => setThemeTick((n) => n + 1);
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', bump);
    return () => {
      observer.disconnect();
      media.removeEventListener('change', bump);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        const css = getComputedStyle(document.documentElement);
        const v = (name: string) => css.getPropertyValue(name).trim();

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'base',
          fontFamily: v('--serif') || 'Georgia, serif',
          themeVariables: {
            background: v('--surface'),
            mainBkg: v('--surface2'),
            primaryColor: v('--surface2'),
            primaryTextColor: v('--ink'),
            primaryBorderColor: v('--rule'),
            secondaryColor: v('--surface'),
            tertiaryColor: v('--surface'),
            lineColor: v('--ink3'),
            textColor: v('--ink'),
            nodeBorder: v('--rule'),
            clusterBkg: v('--paper'),
            clusterBorder: v('--rule'),
            edgeLabelBackground: v('--surface'),
          },
        });

        const { svg: rendered } = await mermaid.render(id, chart);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, id, themeTick]);

  if (error) {
    // A diagram that will not parse is a fact about the run, not something to hide.
    return (
      <div className="diagram">
        <p className="kick">Diagram failed to render</p>
        <pre className="mono" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{error}</pre>
        <details>
          <summary className="kick" style={{ cursor: 'pointer', marginTop: 8 }}>Source</summary>
          <pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>{chart}</pre>
        </details>
      </div>
    );
  }

  return (
    <div className="diagram">
      {svg ? (
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <p className="kick" style={{ margin: 0 }}>Rendering diagram…</p>
      )}
    </div>
  );
}
