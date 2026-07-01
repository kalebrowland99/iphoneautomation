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

  // Allow farm dashboard (localhost:8080) to embed /automation in an iframe.
  async headers() {
    return [
      {
        source: "/automation",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'self' http://localhost:8080 http://127.0.0.1:8080",
          },
        ],
      },
    ];
  },

  // Empty turbopack config silences the "webpack config ignored" warning
  turbopack: {},
};

export default nextConfig;
