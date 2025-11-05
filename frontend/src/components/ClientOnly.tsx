// ClientOnly wrapper to avoid SSR/CSR mismatches and render‑loop churn.
// Waits until the component mounts on the client before rendering children.
'use client';

import type { PropsWithChildren } from "react";
import { useEffect, useState } from "react";

export default function ClientOnly({ children }: PropsWithChildren) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return <>{children}</>;
}
