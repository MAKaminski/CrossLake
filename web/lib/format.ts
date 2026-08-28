/**
 * Rounding happens here and nowhere else.
 *
 * The engine stores capacity values unrounded so the derived identities hold exactly
 * (ρ = λ/μ, headroom = μ/λ). Rounding in the model would break them, so the renderer
 * is the only place a number is allowed to lose precision.
 */

export const DASH = '—';

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return Math.round(value).toLocaleString('en-US');
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
}

export function date(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace('T', ' ');
}

/** Severity class for a utilisation against the target, matching index.html. */
export function utilisationClass(utilisation: number, target: number): 'crit' | 'warn' | 'ok' {
  if (utilisation >= 1) return 'crit';
  if (utilisation >= target) return 'warn';
  return 'ok';
}
