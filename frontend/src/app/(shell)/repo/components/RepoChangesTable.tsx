import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type RepoChange = {
  id: string;
  title: string;
  status: string;
  summary?: string;
  jobId?: string;
};

interface RepoChangesTableProps {
  changes: RepoChange[];
  selectedChangeId?: string | null;
  onSelectChange?: (change: RepoChange) => void;
}

export function RepoChangesTable({ changes, selectedChangeId, onSelectChange }: RepoChangesTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {changes.map((change) => (
          <button
            key={change.id}
            type="button"
            onClick={() => onSelectChange?.(change)}
            className={`w-full rounded-lg border p-3 text-left transition ${selectedChangeId === change.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"}`}
          >
            <p className="font-medium">{change.title}</p>
            <p className="text-xs text-muted-foreground">{change.status}</p>
            {change.summary && <p className="text-xs text-muted-foreground">{change.summary}</p>}
          </button>
        ))}
        <p className="text-xs text-muted-foreground">Repo change history wiring will surface backend data in a follow-up.</p>
      </CardContent>
    </Card>
  );
}
