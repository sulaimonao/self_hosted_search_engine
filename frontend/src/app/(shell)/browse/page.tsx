import { AddressBar } from "@/app/(shell)/browse/components/AddressBar";
import { BrowserViewport } from "@/app/(shell)/browse/components/BrowserViewport";
import { PageActions } from "@/app/(shell)/browse/components/PageActions";
import { TabStrip } from "@/app/(shell)/browse/components/TabStrip";

export default function BrowsePage() {
  return (
    <div className="flex flex-1 flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Browse</h1>
        <p className="text-sm text-muted-foreground">Capture-aware browser tabs with AI assist.</p>
      </div>
      <TabStrip />
      <AddressBar />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <BrowserViewport />
        <PageActions />
      </div>
    </div>
  );
}
