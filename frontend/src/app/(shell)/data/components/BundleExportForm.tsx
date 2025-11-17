"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function BundleExportForm() {
  const [name, setName] = useState("bundle-export");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export bundle</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
          <Button type="submit">Export</Button>
        </form>
      </CardContent>
    </Card>
  );
}
