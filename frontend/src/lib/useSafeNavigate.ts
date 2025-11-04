"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type NavigateOptions = {
  scroll?: boolean;
  replace?: boolean;
};

function normaliseHref(href: string): string {
  try {
    return href.trim();
  } catch {
    return href;
  }
}

export function useSafeNavigate() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const current = useMemo(() => {
    const search = searchParams?.toString();
    return search && search.length > 0 ? `${pathname}?${search}` : pathname;
  }, [pathname, searchParams]);

  const navigate = useCallback(
    (href: string, options?: NavigateOptions) => {
      const target = normaliseHref(href);
      if (!target) {
        return;
      }
      if (target === current) {
        return;
      }
      if (options?.replace) {
        router.replace(target, { scroll: options.scroll });
      } else {
        router.push(target, { scroll: options?.scroll });
      }
    },
    [current, router],
  );

  return useMemo(
    () => ({
      push: (href: string, options?: Omit<NavigateOptions, "replace">) => navigate(href, options),
      replace: (href: string, options?: Omit<NavigateOptions, "replace">) =>
        navigate(href, { ...options, replace: true }),
    }),
    [navigate],
  );
}

