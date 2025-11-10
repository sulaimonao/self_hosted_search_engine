import React, { useCallback, useEffect, useReducer, useRef } from "react";
import { reducer, State } from "@/state/chat";
import { streamChat, type StreamEvt } from "@/lib/chatClient";

function toOllamaMessages(msgs: State["messages"]) {
  return msgs.map((m) => ({ role: m.role, content: m.text }));
}

/**
 * Extract text chunk from various delta event formats
 * Handles both direct delta and nested message.content formats
 */
function extractDeltaChunk(evt: StreamEvt): string {
  if (evt.type !== "delta") {
    return "";
  }

  const data = evt.data;
  if (typeof data !== "object" || data === null || data.type !== "delta") {
    return "";
  }

  // Check for direct delta field
  if (typeof data.delta === "string" && data.delta) {
    return data.delta;
  }

  // Check for nested message.content
  if ("message" in data) {
    const msg = data.message;
    if (
      typeof msg === "object" &&
      msg !== null &&
      "content" in msg &&
      typeof msg.content === "string"
    ) {
      return msg.content;
    }
  }

  return "";
}

export default function ChatPanelReducer() {
  const [state, dispatch] = useReducer(reducer, { messages: [] });
  const ctrlRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string) => {
      const userId = crypto.randomUUID();
      const asstId = crypto.randomUUID();
      dispatch({ type: "user_sent", id: userId, text });
      dispatch({ type: "assistant_start", id: asstId });

      ctrlRef.current?.abort();
      const ac = new AbortController();
      ctrlRef.current = ac;

      try {
        await streamChat(
          {
            model: "gpt-oss", // or from settings
            messages: toOllamaMessages([
              ...state.messages,
              { id: userId, role: "user", text },
            ]),
          },
          (evt) => {
            if (evt.type === "delta") {
              const chunk = extractDeltaChunk(evt);
              if (chunk) {
                dispatch({ type: "assistant_delta", id: asstId, chunk });
              }
            } else if (evt.type === "complete") {
              dispatch({ type: "assistant_complete", id: asstId });
            } else if (evt.type === "error") {
              dispatch({ type: "error", note: evt.error });
            }
          },
          ac.signal
        );
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : String(e);
        dispatch({ type: "error", note: errorMessage });
      }
    },
    [state.messages]
  );

  const stop = useCallback(() => {
    ctrlRef.current?.abort();
  }, []);

  useEffect(() => () => ctrlRef.current?.abort(), []);

  return (
    <div className="flex flex-col h-full">
      {/* render messages */}
      <div className="flex-1 overflow-auto p-4">
        {state.messages.map((m) => (
          <div key={m.id} className="mb-2">
            <b>{m.role === "user" ? "You" : "Assistant"}:</b> {m.text}
          </div>
        ))}
      </div>
      {/* input + actions */}
      <div className="p-2 border-t flex gap-2">
        <input
          className="flex-1 border rounded px-2 py-1"
          placeholder="Type message…"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const v = (e.target as HTMLInputElement).value.trim();
              if (v) {
                (e.target as HTMLInputElement).value = "";
                send(v);
              }
            }
          }}
        />
        <button onClick={stop} className="border rounded px-3 py-1">
          Stop
        </button>
      </div>
    </div>
  );
}
