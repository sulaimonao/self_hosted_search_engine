import { Suspense } from "react";

import { BrowserShell } from "@/components/browser/BrowserShell";

export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <BrowserShell />
    </Suspense>
  );
}
