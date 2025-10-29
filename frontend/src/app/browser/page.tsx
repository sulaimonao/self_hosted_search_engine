import { Suspense } from "react";

import { BrowserShell } from "@/components/browser/BrowserShell";

export default function BrowserPage() {
  return (
    <Suspense fallback={null}>
      <BrowserShell />
    </Suspense>
  );
}
