"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { fromDirective, type DirectivePayload } from "@/lib/io/self_heal";

type PlannerResponse = {
  directive?: unknown;
  autopilot?: { directive?: unknown; steps?: unknown } | null;
};

function extractDirective(payload: PlannerResponse): DirectivePayload | null {
  if (!payload) {
    return null;
  }
  const sources: unknown[] = [];
  if (payload.directive) {
    sources.push(payload.directive);
  }
  if (payload.autopilot?.directive) {
    sources.push(payload.autopilot.directive);
  }
  if (payload.autopilot?.steps) {
    sources.push({ steps: payload.autopilot.steps });
  }
  for (const candidate of sources) {
    try {
      const directive = fromDirective(candidate);
      if (directive) {
        return directive;
      }
    } catch {
      // ignore invalid directive candidates
    }
  }
  return null;
}

export default function SelfHealDiagnosticsPage(): JSX.Element {
  const [url, setUrl] = useState("");
  const [symptoms, setSymptoms] = useState("Banner shows an error");
  const [plan, setPlan] = useState<DirectivePayload | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [planning, setPlanning] = useState(false);

  const runSchemaCheck = async () => {
    setNotification(null);
    setError(null);
    try {
      const response = await fetch("/api/self_heal/schema");
      if (!response.ok) {
        throw new Error(`Schema fetch failed (${response.status})`);
      }
      await response.json();
      setNotification("Schema fetched successfully.");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? "Schema fetch failed");
      setError(message);
    }
  };

  const planLite = async () => {
    setPlanning(true);
    setNotification(null);
    setError(null);
    setPlan(null);
    try {
      const response = await fetch("/api/self_heal?variant=lite", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          id: "ui",
          url: url || undefined,
          symptoms: { note: symptoms },
        }),
      });
      const payload = (await response.json()) as PlannerResponse & { error?: string };
      if (!response.ok) {
        throw new Error(payload?.error || `Planner failed (${response.status})`);
      }
      const directive = extractDirective(payload);
      if (!directive) {
        throw new Error("Planner response did not include a directive.");
      }
      setPlan(directive);
      setNotification("Plan prepared. Review the directive before executing.");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? "Planner request failed");
      setError(message);
    } finally {
      setPlanning(false);
    }
  };

  const runHeadless = async () => {
    if (!plan) {
      setError("No directive prepared. Plan a fix before executing.");
      return;
    }
    setRunning(true);
    setNotification(null);
    setError(null);
    try {
      const response = await fetch(api("/api/self_heal/execute_headless"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ consent: true, directive: { steps: plan.steps } }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.error ? String(payload.error) : "Headless execution failed.";
        throw new Error(detail);
      }
      setNotification("Headless directive executed.");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? "Headless execution failed");
      setError(message);
    } finally {
      setRunning(false);
    }
  };

  const serializedPlan = (() => {
    if (!plan) {
      return null;
    }
    try {
      return JSON.stringify(plan, null, 2);
    } catch {
      return null;
    }
  })();

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 p-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Diagnostics · Self-Heal</h1>
        <p className="text-sm text-muted-foreground">
          Plan and execute self-heal directives directly from the desktop app.
        </p>
      </header>

      <section className="flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-sm">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com"
            className="flex-1"
          />
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={runSchemaCheck} disabled={planning || running}>
              Check schema
            </Button>
            <Button type="button" onClick={planLite} disabled={planning}>
              {planning ? "Planning…" : "Plan (lite)"}
            </Button>
          </div>
        </div>
        <Textarea
          rows={3}
          value={symptoms}
          onChange={(event) => setSymptoms(event.target.value)}
          placeholder="Describe the symptoms or error message visible in the UI"
        />
      </section>

      {notification ? (
        <div className="rounded-md border border-primary/30 bg-primary/10 p-3 text-sm text-primary">
          {notification}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {plan ? (
        <section className="space-y-3 rounded-lg border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Directive summary
              </h2>
              <p className="text-sm text-foreground">{plan.reason}</p>
            </div>
            <Button type="button" onClick={runHeadless} disabled={running}>
              {running ? "Running…" : "Run headless"}
            </Button>
          </div>
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>
              Steps: <span className="font-medium text-foreground">{plan.steps.length}</span>
            </p>
            {plan.plan_confidence ? (
              <p>
                Confidence: <span className="font-medium text-foreground">{plan.plan_confidence}</span>
              </p>
            ) : null}
          </div>
          {serializedPlan ? (
            <pre className="max-h-[28rem] overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-relaxed">
              {serializedPlan}
            </pre>
          ) : null}
        </section>
      ) : (
        <div className="rounded-md border border-dashed border-muted-foreground/40 bg-muted/10 p-4 text-sm text-muted-foreground">
          Plan a directive to review the proposed steps before running headless automation.
        </div>
      )}
    </main>
  );
}
