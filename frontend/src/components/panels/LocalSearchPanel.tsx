"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function LocalSearchPanel() {
  const [query, setQuery] = useState("");

  return (
    <div className="flex h-full w-80 flex-col gap-3 p-4">
      <h3 className="text-sm font-semibold">Local search</h3>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          // TODO hook into local index search
        }}
      >
        <Input
          placeholder="Search indexed documents"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">Results appear here.</p>
    </div>
  );
}
