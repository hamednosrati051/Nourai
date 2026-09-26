/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output keeps the production Docker image small.
  output: 'standalone',
  reactStrictMode: true,
  images: {
    // Gallery and generated images are served by the API / object storage.
    // TODO: restrict hostnames in production (see README).
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
      { protocol: 'http', hostname: '**' },
    ],
  },
};

export default nextConfig;
