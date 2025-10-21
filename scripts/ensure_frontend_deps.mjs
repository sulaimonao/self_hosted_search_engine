#!/usr/bin/env node
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, "..");
const frontendDir = path.join(repoRoot, "frontend");
const nodeModulesDir = path.join(frontendDir, "node_modules");

if (existsSync(nodeModulesDir)) {
  process.exit(0);
}

console.log("[postinstall] Installing frontend dependencies…");
const result = spawnSync(
  process.platform === "win32" ? "npm.cmd" : "npm",
  ["install", "--no-audit", "--no-fund"],
  {
    cwd: frontendDir,
    stdio: "inherit",
    env: { ...process.env, npm_config_loglevel: process.env.npm_config_loglevel ?? "warn" },
  },
);

if (result.status !== 0) {
  console.error("[postinstall] Failed to install frontend dependencies");
  process.exit(result.status ?? 1);
}
