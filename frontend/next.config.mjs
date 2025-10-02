const baseConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:5050/api/:path*",
      },
    ];
  },
};

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...baseConfig,
  experimental: {
    allowedDevOrigins: [
      "http://localhost:3100",
      "http://127.0.0.1:3100",
    ],
  },
};

export default nextConfig;
