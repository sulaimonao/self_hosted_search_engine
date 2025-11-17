"use client";

import { NAV_ITEMS } from "@/lib/navigation";
import { NavItem } from "@/components/shell/NavItem";

export function SidebarNav() {
  return (
    <aside className="hidden w-72 shrink-0 border-r bg-background/60 px-3 py-6 md:block">
      <div className="space-y-2">
        {NAV_ITEMS.map((item) => (
          <NavItem key={item.href} item={item} />
        ))}
      </div>
    </aside>
  );
}
