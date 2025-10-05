import { useEffect, useRef, useState } from "react";

interface ProgressEvent {
  stage: string;
  [key: string]: unknown;
}

export function useProgress(jobId: string | null | undefined) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) {
      setEvents([]);
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }
    const source = new EventSource(`/api/progress/${jobId}/stream`);
    sourceRef.current = source;
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ProgressEvent;
        setEvents((prev) => [...prev, payload]);
      } catch {
        // ignore malformed events
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [jobId]);

  return events;
}
