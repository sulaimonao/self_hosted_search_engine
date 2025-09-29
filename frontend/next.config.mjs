const toBaseUrl = (value) => {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^https?:\/\//i.test(trimmed)) return trimmed.replace(/\/$/, "");
  return `http://${trimmed.replace(/\/$/, "")}`;
};

const backendHost = process.env.BACKEND_HOST ?? process.env.FLASK_RUN_HOST ?? "127.0.0.1";
const backendPort = process.env.BACKEND_PORT ?? process.env.FLASK_RUN_PORT ?? "5050";
const configuredBase =
  toBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL) ??
  toBaseUrl(process.env.NEXT_PUBLIC_API_BASE) ??
  `http://${backendHost}:${backendPort}`;

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${configuredBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
