import type { NextApiRequest, NextApiResponse } from "next";
import { randomUUID } from "node:crypto";

type RendererGlobals = typeof globalThis & {
  __PSE_RENDERER_BOOT_ID__?: string;
};

const globalObject = globalThis as RendererGlobals;

if (!globalObject.__PSE_RENDERER_BOOT_ID__) {
  globalObject.__PSE_RENDERER_BOOT_ID__ = randomUUID();
}

const bootId = globalObject.__PSE_RENDERER_BOOT_ID__;

function resolvePort(): number | null {
  const value = process.env.PORT;
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function handler(
  req: NextApiRequest,
  res: NextApiResponse,
): void {
  if (req.method && !["GET", "HEAD"].includes(req.method.toUpperCase())) {
    res.setHeader("Allow", "GET,HEAD");
    res.status(405).end();
    return;
  }

  res.setHeader("Cache-Control", "no-store, max-age=0");

  if (req.method?.toUpperCase() === "HEAD") {
    res.status(200).end();
    return;
  }

  res.status(200).json({
    ok: true,
    bootId,
    pid: process.pid,
    port: resolvePort(),
  });
}
