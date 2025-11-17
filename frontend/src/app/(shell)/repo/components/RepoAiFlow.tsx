"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface RepoAiFlowProps {
  repoId?: string | null;
}

export function RepoAiFlow({ repoId }: RepoAiFlowProps) {
  const [description, setDescription] = useState("");

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI flow</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p>Describe → Propose patch → Apply patch → Run checks.</p>
        <div>
          <p className="mb-2 font-medium">1. Describe the change</p>
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Fix flaky search tests by mocking the crawler response..."
          />
        </div>
        <div className="grid gap-2 text-xs text-muted-foreground">
          <p>Steps 2-4 hook into backend repo APIs once an AI plan is generated.</p>
          <Button disabled size="sm">
            Coming soon
          </Button>
        </div>
        {!repoId && <p className="text-xs text-muted-foreground">Select a repo to unlock patch actions.</p>}
      </CardContent>
    </Card>
  );
}
