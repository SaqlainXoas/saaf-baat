/**
 * The demo-film recorder drives the real app inside an iframe on this same
 * origin (artifacts/demo-video/), which `frame-ancestors 'none'` forbids.
 * Only `artifacts/demo-video/dev-server.sh` sets this, and it relaxes framing
 * to SAMEORIGIN — never to a wildcard, and never by default. Production and a
 * normal `npm run dev` keep DENY.
 */
const allowSameOriginFraming = process.env.SAAF_DEMO_FILM === "1";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: allowSameOriginFraming ? "SAMEORIGIN" : "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        {
          key: "Content-Security-Policy",
          value: `frame-ancestors ${allowSameOriginFraming ? "'self'" : "'none'"}; base-uri 'self'; object-src 'none'`,
        },
      ],
    }];
  },
};

export default nextConfig;
