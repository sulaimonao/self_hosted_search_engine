import { useMemo } from "react";
import type { ComponentPropsWithoutRef, MouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

import { cn } from "@/lib/utils";

type ChatMessageMarkdownProps = {
  text: string;
  className?: string;
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void;
};

function createAnchor(
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void,
) {
  const Anchor = ({ className, href, onClick, ...props }: ComponentPropsWithoutRef<"a">) => {
    const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
      if (typeof onClick === "function") {
        onClick(event);
      }
      if (!href || !onLinkClick) {
        return;
      }
      event.preventDefault();
      onLinkClick(href, event);
    };

    const targetProps = onLinkClick
      ? {}
      : { target: "_blank", rel: "noopener noreferrer" };

    return (
      <a
        className={cn(
          "font-medium text-primary underline underline-offset-2",
          className,
        )}
        href={href}
        {...targetProps}
        {...props}
        onClick={handleClick}
      />
    );
  };

  return Anchor;
}

function createComponents(
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void,
) {
  return {
    a: createAnchor(onLinkClick),
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
}

export function ChatMessageMarkdown({ text, className, onLinkClick }: ChatMessageMarkdownProps) {
  if (!text.trim()) {
    return null;
  }

  const components = useMemo(() => createComponents(onLinkClick), [onLinkClick]);

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
