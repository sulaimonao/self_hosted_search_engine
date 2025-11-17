"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function LlmSettingsForm() {
  const [model, setModel] = useState("gpt-4o-mini");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>LLM settings</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input value={model} onChange={(event) => setModel(event.target.value)} />
          <Button type="submit">Save</Button>
        </form>
      </CardContent>
    </Card>
  );
}
