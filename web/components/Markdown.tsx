'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Children, isValidElement, type ReactNode } from 'react';
import Diagram from './Diagram';

/** Pull the raw text out of a fenced code block's children. */
function textOf(node: ReactNode): string {
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return '';
}

/**
 * Renders the engine's markdown documents.
 *
 * ```mermaid fences are routed to the Diagram component; everything else renders as
 * markdown. The override is on `pre` rather than `code` because a <div> is not valid
 * inside <pre>.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children: preChildren, ...props }) {
            const only = Children.toArray(preChildren)[0];
            if (
              isValidElement<{ className?: string; children?: ReactNode }>(only) &&
              (only.props.className ?? '').includes('language-mermaid')
            ) {
              return <Diagram chart={textOf(only.props.children).trim()} />;
            }
            return <pre {...props}>{preChildren}</pre>;
          },
          table({ children: tableChildren, ...props }) {
            // Wide tables scroll inside their own container, never the page body.
            return (
              <div className="tw">
                <table {...props}>{tableChildren}</table>
              </div>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
