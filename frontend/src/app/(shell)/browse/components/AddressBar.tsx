"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CornerDownLeftIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function AddressBar() {
  const [value, setValue] = useState("https://local-first.dev");
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // placeholder for navigation logic
  }

  useEffect(() => {
    function handleFocusHotkey(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key.toLowerCase() !== "l") return;
      event.preventDefault();
      inputRef.current?.focus();
      inputRef.current?.select();
    }

    window.addEventListener("keydown", handleFocusHotkey);
    return () => window.removeEventListener("keydown", handleFocusHotkey);
  }, []);

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-3">
      <Input
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="flex-1"
        aria-label="Address bar"
      />
      <Button type="submit" variant="secondary" className="gap-2">
        Navigate
        <CornerDownLeftIcon className="size-4" />
      </Button>
    </form>
  );
}
