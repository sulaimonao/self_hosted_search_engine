export type Msg = { id: string; role: "user" | "assistant"; text: string };
export type State = { messages: Msg[]; streamingId?: string };

type Ev =
  | { type: "user_sent"; id: string; text: string }
  | { type: "assistant_start"; id: string }
  | { type: "assistant_delta"; id: string; chunk: string }
  | { type: "assistant_complete"; id: string }
  | { type: "error"; note: string };

export function reducer(state: State, ev: Ev): State {
  switch (ev.type) {
    case "user_sent":
      return {
        ...state,
        messages: [...state.messages, { id: ev.id, role: "user", text: ev.text }],
      };
    case "assistant_start":
      return {
        ...state,
        streamingId: ev.id,
        messages: [...state.messages, { id: ev.id, role: "assistant", text: "" }],
      };
    case "assistant_delta":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === ev.id ? { ...m, text: m.text + ev.chunk } : m
        ),
      };
    case "assistant_complete":
      return { ...state, streamingId: undefined };
    case "error":
      return { ...state, streamingId: undefined };
    default:
      return state;
  }
}
