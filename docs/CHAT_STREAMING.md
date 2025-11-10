# Chat Streaming Implementation

This document describes the chat streaming implementation for Self-Hosted Search Engine desktop mode.

## Backend

### Health Endpoint

A new health endpoint has been added at `/api/health/ollama` to check Ollama connectivity and available models.

**Endpoint:** `GET /api/health/ollama`

**Response (Success):**
```json
{
  "ok": true,
  "host": "http://127.0.0.1:11434",
  "tags": {
    "models": [
      {"name": "gpt-oss", ...},
      {"name": "gemma3", ...}
    ]
  }
}
```

**Response (Error):**
```json
{
  "ok": false,
  "host": "http://127.0.0.1:11434",
  "error": "Connection refused"
}
```

**Usage:**
```bash
curl http://127.0.0.1:5050/api/health/ollama
```

### Chat Endpoint

The existing `/api/chat` endpoint supports NDJSON streaming. It streams responses in the following format:

**Metadata Event:**
```json
{"type": "metadata", "attempt": 1, "model": "gpt-oss", "trace_id": "..."}
```

**Delta Event:**
```json
{"type": "delta", "delta": "text chunk", "answer": "accumulated text"}
```

**Complete Event:**
```json
{"type": "complete", "payload": {...}}
```

**Error Event:**
```json
{"type": "error", "error": "error message", "trace_id": "..."}
```

## Frontend

### Chat State Reducer

A reducer-based state management pattern has been implemented to prevent React render loop issues.

**Location:** `frontend/src/state/chat.ts`

**State Type:**
```typescript
type State = { 
  messages: Msg[]; 
  streamingId?: string 
};
```

**Actions:**
- `user_sent` - Add user message
- `assistant_start` - Start streaming assistant response
- `assistant_delta` - Append chunk to assistant message
- `assistant_complete` - Mark streaming complete
- `error` - Handle errors

### Streaming Client

A simplified streaming utility has been added to `frontend/src/lib/chatClient.ts`.

**Usage:**
```typescript
import { streamChat } from "@/lib/chatClient";

await streamChat(
  {
    model: "gpt-oss",
    messages: [
      { role: "user", content: "Hello" }
    ]
  },
  (event) => {
    if (event.type === "delta") {
      // Handle delta
    } else if (event.type === "complete") {
      // Handle completion
    }
  },
  abortController.signal
);
```

### Example Component

An example component demonstrating the reducer pattern is available at:
`frontend/src/components/ChatPanelReducer.tsx`

**Features:**
- Reducer-based state management
- Abort controller for stopping streams
- Clean separation of concerns
- No render loop issues

## Testing

### Backend Health Check

```bash
# Start the backend
npm run dev:api

# In another terminal
curl http://127.0.0.1:5050/api/health/ollama
```

### Frontend Streaming

```bash
# Start desktop mode
npm run dev:desktop
```

The example ChatPanelReducer component can be imported and used in your application to test the streaming functionality.

## Benefits

1. **Rock-solid streaming**: NDJSON format with proper error handling
2. **Abort control**: Stop button to cancel in-flight requests
3. **No render loops**: Reducer pattern prevents "Maximum update depth exceeded" errors
4. **Health checks**: Preflight checks for Ollama connectivity
5. **Type safety**: Full TypeScript support

## Integration

To integrate with existing ChatPanel components:

1. Import the reducer: `import { reducer } from "@/state/chat"`
2. Replace useState with useReducer
3. Use the streamChat utility for API calls
4. Add abort controller for stop functionality

See `frontend/src/components/ChatPanelReducer.tsx` for a complete reference implementation.
