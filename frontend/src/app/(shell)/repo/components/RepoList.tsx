import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const repos = [
  { id: "frontend", status: "In sync", path: "~/projects/frontend" },
  { id: "backend", status: "Pending jobs", path: "~/projects/backend" },
];

export function RepoList() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repositories</CardTitle>
        <CardDescription>Link status with HydraFlow repo tools.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {repos.map((repo) => (
          <div key={repo.id} className="rounded-xl border p-3 text-sm">
            <p className="font-semibold">{repo.id}</p>
            <p className="text-muted-foreground">{repo.path}</p>
            <p className="text-xs text-emerald-600">{repo.status}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
