import crypto from "node:crypto";
import type { NextApiRequest, NextApiResponse } from "next";

type BootMarker = {
  __BOOT_ID?: string;
};

const bootGlobal = globalThis as typeof globalThis & BootMarker;

export default function handler(_req: NextApiRequest, res: NextApiResponse) {
  if (!bootGlobal.__BOOT_ID) {
    bootGlobal.__BOOT_ID = crypto.randomUUID();
  }

  res.status(200).json({
    ok: true,
    bootId: bootGlobal.__BOOT_ID,
    pid: process.pid,
    port: Number.parseInt(process.env.PORT ?? "3100", 10),
  });
}
