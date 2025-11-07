"use client";
import React, { useCallback, useEffect, useReducer, useRef } from "react";
import { reducer, State } from "@/state/chat";
import { streamChat } from "@/lib/chatClient";

function toOllamaMessages(msgs: State["messages"]) {
  return msgs.map((m) => ({ role: m.role, content: m.text }));
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
            ] as any),
          },
          (evt) => {
            if (evt.type === "delta") {
              const chunk = evt.data?.message?.content || evt.data?.delta || "";
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
      } catch (e: any) {
        dispatch({ type: "error", note: String(e?.message || e) });
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
