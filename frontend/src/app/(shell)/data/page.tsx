"use client";

import { useSearchParams } from "next/navigation";

import { BrowserImportSection } from "@/app/(shell)/data/components/BrowserImportSection";
import { BrowserImportSummary } from "@/app/(shell)/data/components/BrowserImportSummary";
import { BundleExportForm } from "@/app/(shell)/data/components/BundleExportForm";
import { BundleImportForm } from "@/app/(shell)/data/components/BundleImportForm";
import { BundleJobsSummary } from "@/app/(shell)/data/components/BundleJobsSummary";
import { useJobs, useOverview } from "@/lib/backend/hooks";

export default function DataPage() {
  const searchParams = useSearchParams();
  const focusTarget = searchParams.get("focus");
  const overview = useOverview();
  const bundleJobs = useJobs({ limit: 10 });
  const recentBundleJobs = (bundleJobs.data?.jobs ?? []).filter((job) => job.type?.startsWith("bundle_")).slice(0, 4);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Data</h1>
        <p className="text-sm text-muted-foreground">Bundles, imports, and browser capture.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BundleExportForm autoFocus={focusTarget === "export"} />
        <BundleImportForm autoFocus={focusTarget === "import"} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BundleJobsSummary
          jobs={recentBundleJobs}
          isLoading={bundleJobs.isLoading}
          error={bundleJobs.error?.message ?? null}
          onRetry={() => bundleJobs.refetch()}
        />
        <BrowserImportSummary
          entries={overview.data?.browser.history.entries}
          lastVisit={overview.data?.browser.history.last_visit ?? null}
        />
      </div>
      <BrowserImportSection />
    </div>
  );
}
