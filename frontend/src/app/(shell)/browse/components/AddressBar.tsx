"use client";

import { FormEvent, useState } from "react";
import { CornerDownLeftIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function AddressBar() {
  const [value, setValue] = useState("https://local-first.dev");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // placeholder for navigation logic
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-3">
      <Input value={value} onChange={(event) => setValue(event.target.value)} className="flex-1" />
      <Button type="submit" variant="secondary" className="gap-2">
        Navigate
        <CornerDownLeftIcon className="size-4" />
      </Button>
    </form>
  );
}
