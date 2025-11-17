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
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition", 
        isActive
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      <item.icon className="size-4" />
      <div className="flex-1">
        <p className="font-medium leading-5">{item.title}</p>
        <p className="text-xs text-muted-foreground">{item.description}</p>
      </div>
    </Link>
  );
}
