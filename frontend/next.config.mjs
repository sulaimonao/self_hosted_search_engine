const API_BASE_URL = (() => {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit && explicit.trim().length > 0) {
    return explicit;
  }

  const backendPort = process.env.BACKEND_PORT;
  if (backendPort && backendPort.trim().length > 0) {
    return `http://127.0.0.1:${backendPort}`;
  }

  return "http://127.0.0.1:5050";
})();

const normalizedApiBaseUrl = API_BASE_URL.replace(/\/$/, "");

const baseConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${normalizedApiBaseUrl}/api/:path*`,
      },
    ];
  },
};

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: [
    "http://localhost:3100",
    "http://127.0.0.1:3100",
  ],
  ...baseConfig,
};

export default nextConfig;
