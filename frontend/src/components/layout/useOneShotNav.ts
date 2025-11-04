"use client";

import { useCallback, useRef } from "react";
import { useRouter } from "next/navigation";

type OneShotNavigateOptions = {
  scroll?: boolean;
  key?: string;
};

type NavigateInternalOptions = OneShotNavigateOptions & { replace?: boolean };

/**
 * Provides ref-latched navigation helpers that only invoke Next.js router
 * mutations once per distinct destination. This prevents render loops when
 * called from effects or derived state.
 */
export function useOneShotNav() {
  const router = useRouter();
  const lastKeyRef = useRef<string | null>(null);

  const navigate = useCallback(
    (href: string, options?: NavigateInternalOptions) => {
      const method = options?.replace ? "replace" : "push";
      const signature = options?.key ?? `${method}:${href}`;
      if (lastKeyRef.current === signature) {
        return;
      }
      lastKeyRef.current = signature;
      if (options?.replace) {
        router.replace(href, { scroll: options?.scroll });
      } else {
        router.push(href, { scroll: options?.scroll });
      }
    },
    [router],
  );

  const push = useCallback(
    (href: string, options?: OneShotNavigateOptions) => {
      navigate(href, options);
    },
    [navigate],
  );

  const replace = useCallback(
    (href: string, options?: OneShotNavigateOptions) => {
      navigate(href, { ...options, replace: true });
    },
    [navigate],
  );

  const reset = useCallback(() => {
    lastKeyRef.current = null;
  }, []);

  return { push, replace, reset };
}
