import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import process from 'node:process';

const projectRoot = process.cwd();
const port = process.env.PORT && String(process.env.PORT).trim() ? process.env.PORT : '3100';
const env = { ...process.env, PORT: port };
if (!env.NODE_ENV) {
  env.NODE_ENV = 'production';
}

const standaloneServer = join(projectRoot, '.next', 'standalone', 'server.js');

function spawnCommand(command, args) {
  const child = spawn(command, args, {
    stdio: 'inherit',
    env,
    shell: process.platform === 'win32',
  });
  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
  child.on('error', (error) => {
    console.error('[start-next] Failed to launch Next.js server:', error);
    process.exit(1);
  });
}

if (existsSync(standaloneServer)) {
  spawnCommand('node', [standaloneServer, ...process.argv.slice(2)]);
} else {
  const nextBinary =
    process.platform === 'win32'
      ? join(projectRoot, 'node_modules', '.bin', 'next.cmd')
      : join(projectRoot, 'node_modules', '.bin', 'next');

  if (!existsSync(nextBinary)) {
    console.error('[start-next] Could not find the Next.js CLI. Did you install dependencies?');
    process.exit(1);
  }

  spawnCommand(nextBinary, ['start', '-p', port, ...process.argv.slice(2)]);
}
