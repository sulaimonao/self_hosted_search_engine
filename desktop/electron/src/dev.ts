import { spawn } from "node:child_process";
import process from "node:process";
import waitOn from "wait-on";

async function main() {
  const frontendUrl = process.env.FRONTEND_URL || "http://127.0.0.1:3100";
  const backendDev = process.env.BACKEND_DEV ?? "1";

  const tsc = spawn("tsc", ["-w"], { stdio: "inherit" });

  await waitOn({ resources: [frontendUrl], timeout: 300_000 });
  console.log("Frontend ready:", frontendUrl);

  const electron = spawn("electron", ["."], {
    stdio: "inherit",
    env: { ...process.env, FRONTEND_URL: frontendUrl, BACKEND_DEV: backendDev },
  });

  let cleaned = false;
  const cleanup = () => {
    if (cleaned) {
      return;
    }
    cleaned = true;
    if (!electron.killed) {
      try {
        electron.kill();
      } catch {}
    }
    try {
      tsc.kill();
    } catch {}
  };

  electron.on("exit", (code) => {
    cleanup();
    process.exit(code ?? 0);
  });
  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
