import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  // There is a package-lock.json both here and at the repo root, so Next.js
  // would otherwise guess the repo root as the workspace root. Pin it to this
  // directory, which is where the app actually lives.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
