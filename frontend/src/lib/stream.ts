
export async function* readTextStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<string, void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) yield decoder.decode(value, { stream: true });
    }
  } finally {
    reader.releaseLock();
  }
}

export async function collectText(stream: ReadableStream<Uint8Array>): Promise<string> {
  let out = '';
  for await (const chunk of readTextStream(stream)) out += chunk;
  return out;
}
