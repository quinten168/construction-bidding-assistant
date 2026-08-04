import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
