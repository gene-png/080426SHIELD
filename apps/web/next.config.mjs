/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Next.js standalone output keeps the prod Docker image small.
  output: "standalone",
  // typedRoutes intentionally OFF: requires `next build` to populate the
  // route manifest before `tsc --noEmit` can verify `<Link href>`. We run
  // typecheck before build as a smoke. Revisit in Phase 6 hardening.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            // Self-only: the app loads no third-party CDNs/fonts/images, so a
            // strict policy holds. 'unsafe-inline' covers Tailwind + inline
            // style props and Next's bootstrap; 'unsafe-eval' keeps the Next
            // runtime working. No remote origins are allowed.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "base-uri 'self'",
              "form-action 'self'",
              "frame-ancestors 'none'",
              "object-src 'none'",
              "img-src 'self' data: blob:",
              "style-src 'self' 'unsafe-inline'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "font-src 'self'",
              "connect-src 'self'",
              "manifest-src 'self'",
            ].join("; "),
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
