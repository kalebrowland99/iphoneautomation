/** @type {import('next').NextConfig} */
const nextConfig = {
  /** Native sharp binary for `/api/convert-heic` on Vercel & local Node (HEIC via libvips). */
  serverExternalPackages: ["sharp"],

  images: {
    remotePatterns: [
      { protocol: "https", hostname: "oaidalleapiprodscus.blob.core.windows.net" },
      { protocol: "https", hostname: "**" },
    ],
  },

  // MP4 ingest is proxied by app/farm-api/[[...path]]/route.js (rewrites break multipart POST).

  // Allow the farm dashboard to embed /automation in an iframe (any local/LAN origin in dev).
  async headers() {
    return [
      {
        source: "/automation",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors *",
          },
        ],
      },
      {
        source: "/automation/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors *",
          },
        ],
      },
    ];
  },

  // Empty turbopack config silences the "webpack config ignored" warning
  turbopack: {},
};

export default nextConfig;
