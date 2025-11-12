// Re-export minimal helper if not exported by configClient (internal duplication).
function apiPath(path: string): string {
  // In the existing codebase apiPath prepends API_BASE. We mirror the logic
  // inline to avoid modifying the original module export surface.
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";
  if (!path.startsWith("/")) return `${API_BASE}/${path}`;
  return `${API_BASE}${path}`;
}

export type RoadmapStatus = "done" | "in_progress" | "planned";

export interface RoadmapItem {
  id: string;
  title: string;
  category: string;
  status: RoadmapStatus;
  diag_rule_ids?: string[] | null;
  probe_url?: string | null;
  notes?: string | null;
  manual: boolean;
  updated_at?: string | null;
  // client-only computed fields
  computed_status?: RoadmapStatus;
  last_evidence?: string | null;
}

interface RoadmapResponse { items: RoadmapItem[]; count: number; }

async function parseJson<T = unknown>(response: Response): Promise<T> {
  const data: unknown = await response.json();
  if (!response.ok) {
    const err = data as { error?: unknown };
    const message = typeof err?.error === "string" ? err.error : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
}

export async function fetchRoadmap(): Promise<RoadmapResponse> {
  const response = await fetch(apiPath("/api/roadmap"), { credentials: "include" });
  return parseJson(response);
}

export async function updateRoadmapItem(id: string, patch: { status?: RoadmapStatus; notes?: string }): Promise<RoadmapItem> {
  const response = await fetch(apiPath("/api/roadmap"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, ...patch }),
  });
  const data = await parseJson<{ ok: boolean; item: RoadmapItem }>(response);
  return data.item;
}

// Diagnostics snapshot integration -------------------------------------------------
export interface DiagnosticsRule {
  id: string;
  level?: string;
  status?: string; // pass|fail|warn|error etc.
  evidence?: string;
}
export interface DiagnosticsSnapshot { rules: DiagnosticsRule[]; timestamp?: string; }

export async function fetchDiagnosticsSnapshot(): Promise<DiagnosticsSnapshot> {
  // Backend exposes POST /api/diagnostics/run returning {checks:[...]}; map to generic snapshot shape.
  const response = await fetch(apiPath("/api/diagnostics/run"), { method: "POST", credentials: "include" });
  const raw = await parseJson<{ checks?: Array<{ id: string; status?: string; detail?: string }> }>(response);
  const rules: DiagnosticsRule[] = [];
  for (const entry of raw.checks ?? []) {
    rules.push({ id: entry.id, status: entry.status, evidence: entry.detail });
  }
  return { rules, timestamp: new Date().toISOString() };
}

// Status aggregation logic matching spec ------------------------------------------
export function aggregateStatus(item: RoadmapItem, snapshot: DiagnosticsSnapshot | null): RoadmapStatus {
  if (item.manual) {
    return item.status;
  }
  const rules = item.diag_rule_ids ?? [];
  if (rules.length === 0) {
    return item.status;
  }
  const byId = new Map((snapshot?.rules ?? []).map(r => [r.id, r] as const));
  let anyFail = false;
  let allPass = true;
  for (const rid of rules) {
    const rule = byId.get(rid);
    if (!rule) {
      allPass = false;
      continue;
    }
    const st = (rule.status || rule.level || "").toLowerCase();
    if (st.includes("fail") || st.includes("error")) {
      anyFail = true;
      allPass = false;
    } else if (!st.includes("pass") && !st.includes("ok")) {
      allPass = false;
    }
  }
  if (allPass && rules.length > 0) return "done";
  if (anyFail) return "in_progress";
  return item.status || "planned";
}

export function decorateItems(items: RoadmapItem[], snapshot: DiagnosticsSnapshot | null): RoadmapItem[] {
  return items.map(item => ({
    ...item,
    computed_status: aggregateStatus(item, snapshot),
    last_evidence: (() => {
      if (!snapshot || !item.diag_rule_ids) return null;
      const rule = snapshot.rules.find(r => item.diag_rule_ids?.includes(r.id) && r.evidence);
      return rule?.evidence ?? null;
    })(),
  }));
}

export function statusColor(status: RoadmapStatus): string {
  switch (status) {
    case "done": return "bg-emerald-500";
    case "in_progress": return "bg-amber-500";
    default: return "bg-muted-foreground/60";
  }
}

export function statusLabel(status: RoadmapStatus): string {
  switch (status) {
    case "done": return "Done";
    case "in_progress": return "In Progress";
    default: return "Planned";
  }
}

export function groupByCategory(items: RoadmapItem[]): Record<string, RoadmapItem[]> {
  const map: Record<string, RoadmapItem[]> = {};
  for (const item of items) {
    (map[item.category] ||= []).push(item);
  }
  return map;
}
