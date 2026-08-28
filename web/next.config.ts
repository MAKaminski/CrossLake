import path from 'node:path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // A stray package-lock.json in the home directory otherwise makes Turbopack infer a
  // workspace root above the repo. Pin it to web/.
  turbopack: { root: path.join(__dirname) },
};

export default nextConfig;
