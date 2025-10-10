import { z } from "zod";

export const copilotEventSchema = z.object({
  id: z.string().min(1).optional(),
  ts: z.number().int().nonnegative(),
  kind: z.enum([
    "crawl.start",
    "crawl.progress",
    "crawl.done",
    "index.added",
    "index.dup",
    "error",
    "llm.status",
    "server.health",
  ]),
  site: z.string().min(1).optional(),
  url: z.string().min(1).optional(),
  count: z.number().int().nonnegative().optional(),
  progress: z.number().min(0).max(100).optional(),
  message: z.string().optional(),
  meta: z.record(z.any()).optional(),
});

export type CopilotEvent = z.infer<typeof copilotEventSchema>;

export function parseEvent(payload: unknown): CopilotEvent | null {
  const parsed = copilotEventSchema.safeParse(payload);
  return parsed.success ? parsed.data : null;
}
