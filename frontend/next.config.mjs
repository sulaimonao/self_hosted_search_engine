/** @type {import('next').NextConfig} */
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:5000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/api/jobs/:id/stream",
        destination: `${backendUrl}/api/jobs/:id/stream`,
      },
    ];
  },
};

export default nextConfig;
