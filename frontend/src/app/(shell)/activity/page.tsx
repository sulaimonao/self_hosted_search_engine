import { JobDetailDrawer } from "@/app/(shell)/activity/components/JobDetailDrawer";
import { JobsFilters } from "@/app/(shell)/activity/components/JobsFilters";
import { JobsTable } from "@/app/(shell)/activity/components/JobsTable";

export default function ActivityPage() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Activity</h1>
        <p className="text-sm text-muted-foreground">HydraFlow jobs and ongoing automation.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <JobsTable />
        <JobsFilters />
      </div>
      <JobDetailDrawer />
    </div>
  );
}
