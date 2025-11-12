"use client";

import * as React from "react";
import useSWR from "swr";
import { fetchRoadmap, fetchDiagnosticsSnapshot, decorateItems, updateRoadmapItem, statusColor, statusLabel, type RoadmapStatus } from "@/lib/roadmapClient";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, RefreshCw, Pencil, Save } from "lucide-react";

export function RoadmapPanel() {
  const { data: roadmap, mutate: mutateRoadmap, isLoading: loadingRoadmap } = useSWR("roadmap", fetchRoadmap, { refreshInterval: 60000 });
  const { data: snapshot, mutate: mutateSnapshot, isLoading: loadingDiag } = useSWR("diagnostics-snapshot", () => fetchDiagnosticsSnapshot(false));
  const items = React.useMemo(() => decorateItems(roadmap?.items ?? [], snapshot ?? null), [roadmap, snapshot]);

  const [filter, setFilter] = React.useState("");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [notesDraft, setNotesDraft] = React.useState("");
  const [statusDraft, setStatusDraft] = React.useState<RoadmapStatus>("planned");
  const [saving, setSaving] = React.useState(false);

  const filtered = items.filter(i => {
    if (!filter.trim()) return true;
    const f = filter.toLowerCase();
    return i.title.toLowerCase().includes(f) || i.id.toLowerCase().includes(f) || i.category.toLowerCase().includes(f);
  });

  const handleRunDiagnostics = async () => {
    await mutateSnapshot();
    await mutateRoadmap();
  };

  const startEdit = (id: string, notes: string | null, status: RoadmapStatus) => {
    setEditingId(id);
    setNotesDraft(notes ?? "");
    setStatusDraft(status);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setNotesDraft("");
    setStatusDraft("planned");
  };

  const saveEdit = async () => {
    if (!editingId) return;
    setSaving(true);
    try {
      // For manual items allow status override; for diag-mapped items only notes should persist.
      const current = items.find(i => i.id === editingId);
      const patch: { notes?: string; status?: RoadmapStatus } = { notes: notesDraft || undefined };
      if (current?.manual) {
        patch.status = statusDraft;
      }
      await updateRoadmapItem(editingId, patch);
      await mutateRoadmap();
      cancelEdit();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Input placeholder="Filter (id, title, category)" value={filter} onChange={e => setFilter(e.target.value)} className="max-w-xs" />
        <Button onClick={handleRunDiagnostics} disabled={loadingDiag} variant="secondary">
          {loadingDiag ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />} Run Diagnostics
        </Button>
      </div>
      {loadingRoadmap && <p className="text-sm text-muted-foreground">Loading roadmap…</p>}
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map(item => {
          const effective = item.computed_status || item.status;
          const editing = editingId === item.id;
          return (
            <Card key={item.id} className="p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium truncate" title={item.title}>{item.title}</div>
                <div className={`px-2 py-0.5 text-xs rounded text-white ${statusColor(effective)}`}>{statusLabel(effective)}</div>
              </div>
              <div className="text-xs text-muted-foreground flex justify-between">
                <span>{item.category}</span>
                {item.manual ? <span className="italic">manual</span> : <span className="italic">diag-mapped</span>}
              </div>
              {item.last_evidence && (
                <div className="text-[11px] bg-muted rounded px-2 py-1 overflow-hidden" title={item.last_evidence}>{item.last_evidence}</div>
              )}
              {editing ? (
                <div className="space-y-2">
                  {item.manual && (
                    <select
                      className="w-full rounded border px-2 py-1 text-xs"
                      value={statusDraft}
                      onChange={e => setStatusDraft(e.target.value as RoadmapStatus)}
                    >
                      <option value="planned">Planned</option>
                      <option value="in_progress">In Progress</option>
                      <option value="done">Done</option>
                    </select>
                  )}
                  <Textarea value={notesDraft} onChange={e => setNotesDraft(e.target.value)} placeholder="Notes / evidence" className="text-xs" rows={3} />
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" size="sm" onClick={cancelEdit} disabled={saving}>Cancel</Button>
                    <Button size="sm" onClick={saveEdit} disabled={saving}>{saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}</Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="text-xs line-clamp-3 whitespace-pre-wrap" title={item.notes ?? "(no notes)"}>{item.notes ?? <span className="italic text-muted-foreground">No notes</span>}</div>
                  <Button variant="ghost" size="sm" onClick={() => startEdit(item.id, item.notes ?? null, item.status)}>
                    <Pencil className="size-4" />
                  </Button>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export default RoadmapPanel;
