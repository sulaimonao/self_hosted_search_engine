import { BrowserImportSection } from "@/app/(shell)/data/components/BrowserImportSection";
import { BrowserImportSummary } from "@/app/(shell)/data/components/BrowserImportSummary";
import { BundleExportForm } from "@/app/(shell)/data/components/BundleExportForm";
import { BundleImportForm } from "@/app/(shell)/data/components/BundleImportForm";
import { BundleJobsSummary } from "@/app/(shell)/data/components/BundleJobsSummary";

export default function DataPage() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Data</h1>
        <p className="text-sm text-muted-foreground">Bundles, imports, and browser capture.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BundleExportForm />
        <BundleImportForm />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <BundleJobsSummary />
        <BrowserImportSummary />
      </div>
      <BrowserImportSection />
    </div>
  );
}
