"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { NavigationItem } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function NavItem({ item }: { item: NavigationItem }) {
  const pathname = usePathname();
  const isActive = pathname === item.href;

  return (
    <Link
      href={item.href}
      className={cn(
        "group flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-all duration-fast ease-default",
        isActive
          ? "border-sidebar-ring/70 bg-sidebar-primary/15 text-sidebar-foreground shadow-subtle"
          : "border-transparent text-fg-muted hover:border-sidebar-border hover:bg-sidebar-accent hover:text-sidebar-foreground"
      )}
      aria-current={isActive ? "page" : undefined}
    >
      <span
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-md border border-border-subtle bg-app-card-subtle text-fg-muted shadow-subtle transition-colors group-hover:text-sidebar-foreground",
          isActive && "border-sidebar-ring bg-sidebar-primary text-sidebar-primary-foreground"
        )}
      >
        <item.icon className="size-4" />
      </span>
      <div className="flex-1">
        <p className="font-semibold leading-5 text-sidebar-foreground">{item.title}</p>
        <p className="text-xs text-fg-muted">{item.description}</p>
      </div>
    </Link>
  );
}
