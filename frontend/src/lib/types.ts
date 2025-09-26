export type Role = "user" | "assistant" | "system" | "agent";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
  streaming?: boolean;
  proposedActions?: ProposedAction[];
}

export type ActionStatus = "proposed" | "approved" | "dismissed" | "executing" | "done" | "error";

export type ActionKind = "crawl" | "index" | "add_seed" | "extract" | "summarize" | "queue";

export interface ProposedAction {
  id: string;
  kind: ActionKind;
  title: string;
  description?: string;
  payload: Record<string, unknown>;
  status: ActionStatus;
  metadata?: Record<string, unknown>;
}

export interface SelectionActionPayload {
  selection: string;
  url: string;
  context?: string;
  boundingRect?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export interface AgentLogEntry {
  id: string;
  timestamp: string;
  label: string;
  detail?: string;
  status?: "info" | "success" | "warning" | "error";
  meta?: Record<string, unknown>;
}

export interface JobStatusSummary {
  jobId: string;
  state: "idle" | "queued" | "running" | "done" | "error";
  progress: number;
  etaSeconds?: number;
  error?: string;
  description?: string;
  lastUpdated: string;
}

export interface CrawlQueueItem {
  id: string;
  url: string;
  scope: CrawlScope;
  notes?: string;
}

export type CrawlScope = "page" | "domain" | "allowed-list" | "custom";

export interface ModelStatus {
  model: string;
  installed: boolean;
  available: boolean;
  isPrimary?: boolean;
  kind: "chat" | "embedding";
}

export interface OllamaStatus {
  installed: boolean;
  running: boolean;
  host: string;
}

export interface ChatStreamChunk {
  type: "token" | "done" | "error" | "action";
  content?: string;
  action?: ProposedAction;
  total_duration?: number;
  load_duration?: number;
}

export interface JobLogEvent {
  type: "log" | "status" | "error";
  message?: string;
  state?: string;
  progress?: number;
  timestamp: string;
}
