import { RepoAiFlow } from "@/app/(shell)/repo/components/RepoAiFlow";
import { RepoChangeDetail } from "@/app/(shell)/repo/components/RepoChangeDetail";
import { RepoChangesTable } from "@/app/(shell)/repo/components/RepoChangesTable";
import { RepoList } from "@/app/(shell)/repo/components/RepoList";
import { RepoStatusCard } from "@/app/(shell)/repo/components/RepoStatusCard";

export default function RepoPage() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Repo</h1>
        <p className="text-sm text-muted-foreground">Manage repositories with AI-driven flows.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RepoList />
        <RepoStatusCard />
      </div>
      <RepoAiFlow />
      <div className="grid gap-6 lg:grid-cols-2">
        <RepoChangesTable />
        <RepoChangeDetail />
      </div>
    </div>
  );
}
