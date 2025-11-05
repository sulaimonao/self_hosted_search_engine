// Small utility to coalesce streaming token updates into batched frames.
export type Frame = { type: "delta" | "complete" | "error"; payload?: unknown };

export function coalesceStream(onFrame: (frame: Frame) => void, intervalMs = 50) {
  let buffer: Frame[] = [];
  let timer: number | null = null;

  function flush() {
    if (buffer.length === 0) {
      timer = null;
      return;
    }
    // Merge deltas into one delta frame when possible.
    const deltas = buffer.filter((f) => f.type === "delta");
    const completes = buffer.filter((f) => f.type === "complete");
    const errors = buffer.filter((f) => f.type === "error");
    if (errors.length > 0) {
      onFrame(errors[errors.length - 1]);
    } else if (completes.length > 0) {
      onFrame(completes[completes.length - 1]);
    } else if (deltas.length > 0) {
      const merged = deltas.reduce((acc, cur) => ({
          type: "delta",
          payload: String(acc.payload ?? "") + String(cur.payload ?? ""),
        }), { type: "delta", payload: "" } as Frame);
      onFrame(merged);
    }
    buffer = [];
    timer = null;
  }

  return {
    push(frame: Frame) {
      buffer.push(frame);
      if (timer === null) {
        timer = typeof window !== "undefined" ? window.setTimeout(flush, intervalMs) as unknown as number : null;
      }
    },
    flushNow() {
      if (timer !== null) {
        clearTimeout(timer);
        flush();
      } else {
        flush();
      }
    },
    dispose() {
      if (timer !== null) clearTimeout(timer);
      buffer = [];
      timer = null;
    },
  };
}
