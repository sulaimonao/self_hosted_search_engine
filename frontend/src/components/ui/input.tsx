import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-xs border border-border-subtle bg-app-subtle/90 px-3 py-2 text-sm text-fg placeholder:text-fg-muted shadow-subtle/0 outline-none transition-colors duration-fast ease-default",
        "file:inline-flex file:h-7 file:border-0 file:bg-transparent file:px-2 file:text-xs file:font-medium file:text-fg",
        "focus-visible:border-accent focus-visible:ring-0",
        "aria-invalid:border-danger aria-invalid:ring-danger/30",
        className
      )}
      {...props}
    />
  )
}

export { Input }
