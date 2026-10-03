/** @type {import('next').NextConfig} */
// Accepts a full URL ("https://api.example.com") or a bare host:port, which is what
// Render's `fromService` injection provides. Missing scheme defaults to https.
const RAW_BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const BACKEND_URL = /^https?:\/\//.test(RAW_BACKEND) ? RAW_BACKEND : `https://${RAW_BACKEND}`;

module.exports = {
  reactStrictMode: true,
  // Browser calls /api/* on the Next.js origin; Next.js proxies them to the FastAPI backend (no CORS needed).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};
