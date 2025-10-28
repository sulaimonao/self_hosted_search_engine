import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_BACKEND_PORT = process.env.BACKEND_PORT?.trim() || "5050";
const DEFAULT_API_BASE_URL = `http://127.0.0.1:${DEFAULT_BACKEND_PORT}`;

const API_BASE_URL = (() => {
  const explicit =
    process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_URL || process.env.BACKEND_URL;
  if (explicit && explicit.trim().length > 0) {
    return explicit.trim();
  }

  return DEFAULT_API_BASE_URL;
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
  output: "standalone",
  webpack(config) {
    config.resolve.alias = {
      ...(config.resolve.alias ?? {}),
      "@shared": path.resolve(__dirname, "../shared"),
    };

    return config;
  },
  ...baseConfig,
};

const configuredAssetPrefix =
  process.env.ASSET_PREFIX ?? process.env.NEXT_PUBLIC_ASSET_PREFIX ?? process.env.NEXT_ASSET_PREFIX;

if (configuredAssetPrefix && configuredAssetPrefix.trim().length > 0) {
  if (process.env.NODE_ENV === 'production') {
    nextConfig.assetPrefix = configuredAssetPrefix.trim();
  } else {
    nextConfig.assetPrefix = '';
  }
}

export default nextConfig;
