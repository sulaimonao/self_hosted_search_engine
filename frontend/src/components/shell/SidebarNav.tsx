"use client";

import { NAV_ITEMS } from "@/lib/navigation";
import { NavItem } from "@/components/shell/NavItem";

export function SidebarNav() {
  return (
    <aside className="hidden w-72 shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-soft backdrop-blur-sm md:flex md:flex-col">
      <div className="relative border-b border-sidebar-border px-4 py-5">
        <div className="absolute inset-0 bg-gradient-to-r from-accent/10 via-transparent to-sidebar" aria-hidden />
        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-strong text-primary-foreground shadow-subtle">
            <span className="text-lg font-semibold">S</span>
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold leading-tight">Search Engine</span>
            <span className="text-xs text-fg-muted">Desert build</span>
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-5">
        <p className="px-2 text-xs font-semibold uppercase tracking-[0.08em] text-fg-muted">Navigate</p>
        <div className="space-y-2">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.href} item={item} />
          ))}
        </div>
      </div>

      <div className="border-t border-sidebar-border px-4 py-4">
        <div className="flex items-center gap-2 rounded-md bg-sidebar-accent px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-state-success shadow-subtle animate-pulse" />
          <div className="flex flex-col leading-tight">
            <span className="text-xs font-semibold text-sidebar-foreground">System Online</span>
            <span className="text-[11px] text-fg-muted">Indexing in the dunes</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
