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
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-fast ease-default border-l-2",
        isActive
          ? "border-accent bg-accent-soft text-fg"
          : "border-transparent text-fg-muted hover:bg-app-card-hover hover:text-fg"
      )}
    >
      <item.icon className="size-4" />
      <div className="flex-1">
        <p className="font-medium leading-5 text-fg">{item.title}</p>
        <p className="text-xs text-fg-muted">{item.description}</p>
      </div>
    </Link>
  );
}
