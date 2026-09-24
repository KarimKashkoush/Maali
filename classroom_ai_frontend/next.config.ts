import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() { return [{source:"/sw.js",headers:[{key:"Cache-Control",value:"no-store, max-age=0"},{key:"Service-Worker-Allowed",value:"/"}]}]; },
};

export default nextConfig;
