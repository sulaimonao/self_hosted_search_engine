import React from "react";

import "@/autopilot/executor";
import { IncidentBus } from "@/diagnostics/incident-bus";

type DirectiveStep = {
  headless?: boolean;
  [key: string]: unknown;
};

type Directive = {
  steps?: DirectiveStep[];
  [key: string]: unknown;
};

function isDirective(candidate: unknown): candidate is Directive {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const payload = candidate as { steps?: unknown };
  if ("steps" in payload && payload.steps !== undefined && !Array.isArray(payload.steps)) {
    return false;
  }
  return true;
}

export function FixPanel() {
  const busRef = React.useRef<IncidentBus>(new IncidentBus());
  const [open, setOpen] = React.useState(false);
  const [log, setLog] = React.useState<string[]>([]);
  const [planning, setPlanning] = React.useState(false);
  const [allowHeadless, setAllowHeadless] = React.useState(false);

  React.useEffect(() => {
    busRef.current.start();
  }, []);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    const es = new EventSource("/api/progress/__diagnostics__/stream");
    es.onmessage = (e) => setLog((l) => [...l, e.data]);
    es.onerror = () => es.close();
    return () => es.close();
  }, [open]);

  async function runHeadless(directive: Directive) {
    setLog((l) => [...l, "Running headless steps..."]);
    try {
      const res = await fetch("/api/self_heal/execute_headless", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ directive, consent: true }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        setLog((l) => [...l, `Headless run failed (${res.status}): ${JSON.stringify(payload)}`]);
        return;
      }
      setLog((l) => [...l, "Headless result:\n" + JSON.stringify(payload, null, 2)]);
    } catch (err) {
      setLog((l) => [...l, `Headless error: ${String(err)}`]);
    }
  }

  async function planOrFix(apply: boolean) {
    setPlanning(true);
    try {
      const incident = busRef.current.snapshot();
      const res = await fetch(`/api/self_heal?apply=${String(apply)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(incident),
      });
      const payload = await res.json().catch(() => ({}));
      const directive = isDirective(payload?.directive) ? payload.directive : null;
      const directiveSteps: DirectiveStep[] = directive?.steps ?? [];
      const directiveHasHeadless = directiveSteps.some((step) => step && step.headless);
      if (!directiveHasHeadless) {
        setAllowHeadless(false);
      }

      if (!res.ok) {
        setLog((l) => [...l, `Planner error (${res.status}): ${JSON.stringify(payload)}`]);
        return;
      }

      if (!apply) {
        setLog((l) => [...l, "Plan:\n" + JSON.stringify(payload, null, 2)]);
        return;
      }

      if (directive) {
        const inTabSteps = directiveSteps.filter((step) => step && !step.headless);
        if (inTabSteps.length > 0) {
          try {
            await window.autopilotExecutor.run({ steps: inTabSteps });
            setLog((l) => [...l, "Executed directive in-tab."]);
          } catch (err) {
            setLog((l) => [...l, `In-tab execution error: ${String(err)}`]);
          }
        }

        if (directiveHasHeadless) {
          if (allowHeadless) {
            const proceed = window.confirm(
              "Headless fix will run server-side scripted steps. Proceed?",
            );
            if (proceed) {
              await runHeadless(directive);
            } else {
              setLog((l) => [...l, "Headless execution cancelled by user."]);
            }
          } else {
            setLog((l) => [
              ...l,
              "Headless steps detected but skipped (consent not granted).",
            ]);
          }
        }
      } else {
        setLog((l) => [...l, "No directive returned by planner."]);
      }
    } catch (err) {
      setLog((l) => [...l, `Planner request failed: ${String(err)}`]);
    } finally {
      setPlanning(false);
    }
  }

  return (
    <div>
      <button onClick={() => setOpen((o) => !o)} title="Self-Heal">
        Fix
      </button>
      {open ? (
        <div className="diag-panel">
          <div className="actions">
            <button disabled={planning} onClick={() => planOrFix(false)}>
              Plan only
            </button>
            <button disabled={planning} onClick={() => planOrFix(true)}>
              Fix now
            </button>
          </div>
          <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={allowHeadless}
              onChange={(event) => setAllowHeadless(event.target.checked)}
            />
            <span>Run headless fix when needed</span>
          </label>
          <pre style={{ maxHeight: 260, overflow: "auto" }}>{log.join("\n")}</pre>
        </div>
      ) : null}
    </div>
  );
}
