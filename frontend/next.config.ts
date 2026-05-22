import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
