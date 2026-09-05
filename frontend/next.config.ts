import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Docker イメージを小さくするため、必要な node_modules だけを同梱した
  // スタンドアロン出力を作る (frontend/Dockerfile が .next/standalone を使う)
  output: "standalone",
};

export default nextConfig;
