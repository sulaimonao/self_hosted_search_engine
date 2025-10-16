import crypto from 'crypto';
export default function handler(_req: any, res: any) {
  // stable per dev boot
  // @ts-ignore
  global.__BOOT_ID = global.__BOOT_ID || crypto.randomUUID();
  res.status(200).json({ ok: true, bootId: (global as any).__BOOT_ID, pid: process.pid, port: Number(process.env.PORT||3100) });
}
