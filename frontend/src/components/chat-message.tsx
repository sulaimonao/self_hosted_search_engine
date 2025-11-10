import { useMemo } from "react";
import type { ComponentPropsWithoutRef, MouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeRaw from "rehype-raw";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import type { PluggableList } from "unified";

import { cn } from "@/lib/utils";

type ChatMessageMarkdownProps = {
  text: string;
  className?: string;
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void;
};

type SanitizeSchema = Parameters<typeof rehypeSanitize>[0];

const SANITIZE_OPTIONS: SanitizeSchema = (() => {
  const schema: SanitizeSchema = (JSON.parse(JSON.stringify(defaultSchema ?? {})) as SanitizeSchema) ?? {};
  const tagList = Array.isArray(schema?.tagNames) ? schema.tagNames : [];
  const existingTags = new Set(tagList);
  existingTags.add("u");
  schema.tagNames = Array.from(existingTags);

  const baseAttributes = schema.attributes ?? {};
  const extendAttributes = (tag: string, attrs: string[]) => {
    const currentValues = baseAttributes[tag];
    const current = new Set<string>(Array.isArray(currentValues) ? (currentValues as string[]) : []);
    attrs.forEach((attr) => current.add(attr));
    baseAttributes[tag] = Array.from(current);
  };

  extendAttributes("u", ["class", "className"]);
  extendAttributes("span", ["class", "className"]);
  extendAttributes("code", ["class", "className", "data-language"]);
  extendAttributes("pre", ["class", "className"]);

  schema.attributes = baseAttributes;
  return schema;
})();

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
  const trimmed = text.trim();
  const components = useMemo(() => createComponents(onLinkClick), [onLinkClick]);
  const remarkPlugins = useMemo<PluggableList>(() => [remarkGfm, remarkMath], []);
  const rehypePlugins = useMemo<PluggableList>(
    () => [rehypeRaw, [rehypeSanitize, SANITIZE_OPTIONS], rehypeKatex, rehypeHighlight],
    [],
  );

  if (!trimmed) {
    return null;
  }

  return (
    <div
      className={cn(
        "space-y-3 text-sm leading-relaxed text-foreground [a]:hover:text-primary whitespace-pre-wrap break-words",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
