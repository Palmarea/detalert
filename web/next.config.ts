import { existsSync } from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

/* El agente es un módulo local (src/agent, en .gitignore). Si no está —GitHub, Vercel— se usa la versión vacía. */
const agentDir = path.resolve(existsSync(path.join(__dirname, "src/agent")) ? "src/agent" : "src/agent-stub");

const nextConfig: NextConfig = {
  serverExternalPackages: ["pg"],
  webpack(config) {
    config.resolve.alias["@agent"] = agentDir;
    return config;
  },
  turbopack: { resolveAlias: { "@agent": "./" + path.relative(__dirname, agentDir) } },
};

export default nextConfig;
