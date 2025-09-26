"use client";

import { useEffect, useRef } from "react";
import { Search, Share } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isProbablyUrl } from "@/lib/utils";

interface OmniboxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
}

export function Omnibox({ value, onChange, onSubmit, placeholder }: OmniboxProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "l") {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <form
      className="flex items-center gap-2 rounded-full border border-border bg-background/80 px-4 py-2 shadow-sm backdrop-blur"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(value.trim());
      }}
    >
      <Search className="h-4 w-4 text-muted-foreground" />
      <Input
        ref={inputRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder ?? "Search or enter a URL"}
        className="border-none bg-transparent text-sm focus-visible:ring-0"
      />
      {value && isProbablyUrl(value) && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          title="Copy link"
          onClick={() => navigator.clipboard.writeText(value).catch(() => {})}
        >
          <Share className="h-4 w-4" />
        </Button>
      )}
    </form>
  );
}
