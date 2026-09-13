/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy the FastAPI control plane so the browser sees one origin and SSE
    // streams are not subject to CORS preflight.
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.TRIADR_API_URL || 'http://127.0.0.1:8000'}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
