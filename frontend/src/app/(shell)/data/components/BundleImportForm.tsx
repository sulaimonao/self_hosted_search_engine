"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function BundleImportForm() {
  const [file, setFile] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Import bundle</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input value={file} onChange={(event) => setFile(event.target.value)} placeholder="bundle.json" />
          <Button type="submit" variant="secondary">
            Import
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
