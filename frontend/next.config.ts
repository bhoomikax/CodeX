import type { NextConfig } from "next";

// Hosts allowed to reach Next.js dev resources (hot reload) when the site is
// opened through a LAN address instead of localhost. Comma-separated, e.g.
// ALLOWED_DEV_ORIGINS=10.225.243.71,192.168.1.20
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "10.225.243.71")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  allowedDevOrigins,
  async rewrites() {
    const backendUrl = (
      process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000"
    ).replace(/\/$/, "");

    return [
      {
        source: "/api/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
