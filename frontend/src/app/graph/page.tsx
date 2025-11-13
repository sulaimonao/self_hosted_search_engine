import { Suspense } from "react";

import { KnowledgeGraphPanel } from "@/components/KnowledgeGraphPanel";

export default function GraphHomePage() {
  return (
    <div className="h-full w-full overflow-auto">
      <div className="mx-auto max-w-6xl">
        <Suspense fallback={null}>
          <KnowledgeGraphPanel />
        </Suspense>
      </div>
    </div>
  );
}
