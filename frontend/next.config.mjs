/** @type {import('next').NextConfig} */

// Static export. The dashboard is entirely client-side and talks to the Python API,
// so there is no Node server in production: FastAPI serves these files, which keeps
// judges on a single URL (docs/SPEC.md decision log 8).
const nextConfig = {
  output: 'export',
  // Served from a plain static directory, so no image optimisation server.
  images: { unoptimized: true },
  // Emit out/today/index.html rather than out/today.html, which is simpler for any
  // static host to serve.
  trailingSlash: true,
  // ...but do not redirect to add that slash, which would otherwise rewrite
  // /api/health to /api/health/ and break every API call in development.
  skipTrailingSlashRedirect: true,
  // We write our own AGENTS.md; do not generate one.
  agentRules: false,

  // Development only: proxy the API to the Python backend so the browser sees a
  // single origin, exactly as it will in production. A static export has no server
  // to run these, so they are only added for `next dev`.
  ...(process.env.NODE_ENV === 'development'
    ? {
        async rewrites() {
          const backend = process.env.ORBIT_API || 'http://127.0.0.1:8000'
          return ['api', 'v1', 'webhooks'].map((prefix) => ({
            source: `/${prefix}/:path*`,
            destination: `${backend}/${prefix}/:path*`,
          }))
        },
      }
    : {}),
}

export default nextConfig
