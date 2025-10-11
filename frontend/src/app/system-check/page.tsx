'use client';

import { useSystemCheck } from "@/hooks/use-system-check";
import { SystemCheckPanel } from "@/components/system-check-panel";

export default function SystemCheckPage() {
  const controller = useSystemCheck({ autoRun: true, openInitially: true });

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      <SystemCheckPanel
        open={controller.open}
        onOpenChange={controller.setOpen}
        systemCheck={controller.backendReport}
        browserReport={controller.browserReport}
        loading={controller.loading}
        error={controller.error}
        blocking={controller.blocking}
        skipMessage={controller.skipMessage}
        onRetry={controller.rerun}
        onContinue={() => controller.setOpen(false)}
        onOpenReport={controller.openReport}
      />
      {!controller.open ? (
        <div className="mt-6 flex flex-col items-center gap-3 text-sm text-muted-foreground">
          <p>System check closed. Re-run to verify again.</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded border border-input bg-transparent px-3 py-1 text-sm font-medium"
              onClick={() => {
                controller.setOpen(true);
                controller.rerun();
              }}
            >
              Run again
            </button>
            <button
              type="button"
              className="rounded border border-transparent bg-primary px-3 py-1 text-sm font-medium text-primary-foreground"
              onClick={() => controller.setOpen(true)}
            >
              Show last result
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
