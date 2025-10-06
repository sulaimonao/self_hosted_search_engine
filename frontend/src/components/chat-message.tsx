import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

import { cn } from "@/lib/utils";

type ChatMessageMarkdownProps = {
  text: string;
  className?: string;
};

const components = {
  a: ({ className, ...props }) => (
    <a
      className={cn(
        "font-medium text-primary underline underline-offset-2",
        className,
      )}
      {...props}
      target="_blank"
      rel="noopener noreferrer"
    />
  ),
  code: ({ inline, className, children, ...props }: ComponentPropsWithoutRef<"code"> & { inline?: boolean }) => {
    if (inline) {
      return (
        <code
          className={cn(
            "rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground/90",
            className,
          )}
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <pre
        className={cn(
          "overflow-x-auto rounded-lg bg-muted px-3 py-2 text-sm text-foreground/90",
          className,
        )}
      >
        <code className="font-mono" {...props}>
          {children}
        </code>
      </pre>
    );
  },
  p: ({ className, ...props }) => (
    <p
      {...props}
      className={cn("leading-relaxed text-foreground", className)}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      {...props}
      className={cn("ml-5 list-disc space-y-1 text-foreground", className)}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      {...props}
      className={cn("ml-5 list-decimal space-y-1 text-foreground", className)}
    />
  ),
  li: ({ className, ...props }) => (
    <li
      {...props}
      className={cn("leading-relaxed text-foreground", className)}
    />
  ),
  strong: ({ className, ...props }) => (
    <strong
      {...props}
      className={cn("font-semibold text-foreground", className)}
    />
  ),
} satisfies Components;

export function ChatMessageMarkdown({ text, className }: ChatMessageMarkdownProps) {
  if (!text.trim()) {
    return null;
  }

  return (
    <div
      className={cn(
        "space-y-3 text-sm leading-relaxed text-foreground [a]:hover:text-primary",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
