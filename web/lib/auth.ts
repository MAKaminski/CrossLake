import { createHash, timingSafeEqual } from 'node:crypto';

/**
 * Constant-time bearer check for the ingest endpoint.
 *
 * Both sides are hashed to a fixed 32 bytes before comparison. Comparing the raw
 * strings would need a length check first, and that length check leaks the token
 * length through timing; hashing removes the branch entirely.
 */
export function isAuthorized(authorizationHeader: string | null): boolean {
  const expected = process.env.INGEST_TOKEN;
  if (!expected) return false; // fail closed when unconfigured

  const prefix = 'Bearer ';
  const presented =
    authorizationHeader && authorizationHeader.startsWith(prefix)
      ? authorizationHeader.slice(prefix.length)
      : '';

  const digest = (s: string) => createHash('sha256').update(s, 'utf8').digest();
  return timingSafeEqual(digest(presented), digest(expected));
}
