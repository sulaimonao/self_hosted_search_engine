export async function* readTextStream(
  response: Response,
  options: { decoder?: TextDecoder } = {},
): AsyncGenerator<string, void, unknown> {
  const body = response.body;
  if (!body) {
    return;
  }
  const reader = body.getReader();
  const decoder = options.decoder ?? new TextDecoder();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        const finalChunk = decoder.decode();
        if (finalChunk) {
          yield finalChunk;
        }
        break;
      }
      if (!value || value.length === 0) {
        continue;
      }
      const text = decoder.decode(value, { stream: true });
      if (text) {
        yield text;
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}
