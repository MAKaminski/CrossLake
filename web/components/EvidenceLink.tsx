import Link from 'next/link';

/** Stable anchor id for a locator, shared by the link and the Evidence tab. */
export function locatorAnchor(locator: string): string {
  return `loc-${locator.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '')}`;
}

/**
 * Evidence is the product.
 *
 * A locator is a path into the analysed system ("infra/terraform/main.tf:9"), not a
 * URL — there is nothing to link out to. So the link goes inward, to the Evidence tab,
 * where that observation's excerpt, method, collector and confidence are shown. Every
 * finding gets one; a claim with no locator is not a finding.
 */
export default function EvidenceLink({
  runId,
  locator,
}: {
  runId: string;
  locator: string;
}) {
  return (
    <Link
      href={`/runs/${runId}/evidence#${locatorAnchor(locator)}`}
      className="mono"
      title={`Evidence: ${locator}`}
    >
      {locator}
    </Link>
  );
}
