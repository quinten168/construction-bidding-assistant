import type { NextConfig } from "next";
import path from "path";
import dotenv from "dotenv";

// Next only auto-loads .env.local etc from THIS directory (apps/web). The repo's canonical
// secrets file is two levels up (../../.env, see root .env.example). dotenv.config() never
// overwrites a var that's already set, so an existing apps/web/.env.local still wins as a
// per-machine override -- this just backfills whatever isn't already in the environment.
dotenv.config({ path: path.resolve(__dirname, "../../.env") });

const nextConfig: NextConfig = {
  // NEXT_PUBLIC_GOOGLE_MAPS_API_KEY / BIDINTEL_API_URL: pulled from the root .env above. Listed
  // explicitly here because Next's build-time inlining only picks up vars from files it discovers
  // itself (the .env.local convention); a value loaded manually via dotenv still needs this `env`
  // block to reach the client bundle / route handlers.
  env: {
    NEXT_PUBLIC_GOOGLE_MAPS_API_KEY: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY,
    BIDINTEL_API_URL: process.env.BIDINTEL_API_URL,
  },
  // Next.js 16's dev server only trusts Origin: localhost by default (allowedDevOrigins) --
  // opening the app via 127.0.0.1 gets internal dev requests (HMR socket, font endpoint) silently
  // 403'd, which crashes client hydration before React ever mounts: the page renders its static
  // shell but no data ever loads (every table shows empty/"not found" with zero clues why).
  // Redirect 127.0.0.1 -> localhost at the earliest possible point, before that check ever runs.
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "127.0.0.1" }],
        destination: "http://localhost:3000/:path*",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
