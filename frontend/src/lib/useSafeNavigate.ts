"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type NavigateOptions = {
  replace?: boolean;
  scroll?: boolean;
};

export function useSafeNavigate() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const current = useMemo(() => {
    const query = searchParams ? searchParams.toString() : "";
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, searchParams]);

  return useCallback(
    (href: string, options?: NavigateOptions) => {
      const target = href?.trim();
      if (!target) {
        return;
      }
      if (target === current) {
        return;
      }
      const action = options?.replace ? router.replace : router.push;
      action(target, { scroll: options?.scroll ?? false });
    },
    [current, router],
  );
}
