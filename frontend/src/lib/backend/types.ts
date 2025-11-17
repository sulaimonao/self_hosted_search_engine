export interface OverviewCounters {
  browser: {
    tabs: { total: number; linked: number };
    history: { entries: number; last_visit: string | null };
  };
  knowledge: {
    documents: number;
    pages: number;
    pending_documents: number;
    pending_chunks: number;
    pending_vectors: number;
  };
  llm: {
    threads: { total: number };
    messages: { total: number };
    memories: { total: number };
  };
  tasks: {
    total: number;
    by_status: Record<string, number>;
  };
  storage?: Record<string, { path: string; bytes: number }>;
}

export type OverviewResponse = {
  ok: true;
  data: OverviewCounters;
} & OverviewCounters;

export interface ThreadRecord {
  id: string;
  title?: string | null;
  description?: string | null;
  origin?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_user_message_at?: string | null;
  last_assistant_message_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface MessageRecord {
  id: string;
  thread_id: string;
  parent_id?: string | null;
  role: string;
  content: string;
  created_at?: string | null;
  tokens?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface TaskRecord {
  id: string;
  thread_id?: string | null;
  title: string;
  description?: string | null;
  status: string;
  priority?: number | null;
  due_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  closed_at?: string | null;
  owner?: string | null;
  metadata?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
}

export interface JobRecord {
  id: string;
  type: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  task_id?: string | null;
  thread_id?: string | null;
}

export interface JobListResponse {
  jobs: JobRecord[];
}

export interface JobDetailResponse {
  job: JobRecord;
}

export interface BrowserTabHistory {
  id?: string | null;
  url?: string | null;
  title?: string | null;
  visited_at?: string | null;
}

export interface BrowserTabRecord {
  id: string;
  shadow_mode?: string | null;
  thread_id?: string | null;
  current_history_id?: string | null;
  current_url?: string | null;
  current_title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_visited_at?: string | null;
  current_history?: BrowserTabHistory | null;
}

export interface MemoryRecord {
  id: string;
  scope: string;
  scope_ref?: string | null;
  key?: string | null;
  value: string;
  metadata?: Record<string, unknown> | null;
  strength?: number | null;
  thread_id?: string | null;
  task_id?: string | null;
  source_message_id?: string | null;
}

export interface MemorySearchResponse {
  items: MemoryRecord[];
}

export interface BundleManifest {
  components: Record<string, unknown>;
  created_at?: string;
  [key: string]: unknown;
}

export interface BundleExportResponse {
  job_id: string;
  bundle_path: string;
  manifest: BundleManifest;
}

export interface BundleImportResponse {
  job_id: string;
  imported: Record<string, number>;
}

export interface RepoRecord {
  id: string;
  root_path: string;
  description?: string | null;
  allowed_ops?: string[];
}

export interface RepoListResponse {
  items: RepoRecord[];
}

export interface RepoStatusSummary {
  repo_id: string;
  root_path: string;
  branch?: string;
  dirty?: boolean;
  ahead?: number | null;
  behind?: number | null;
  changes?: string[];
  error?: string;
}
