"use client";

import { Button } from "@/components/ui/button";

export function CollectionsPanel() {
  return (
    <div className="flex h-full w-80 flex-col gap-4 p-4 text-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Collections</h3>
        <Button size="sm" variant="secondary">
          New collection
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Save and organize research targets. Implementation pending.
      </p>
    </div>
  );
}
