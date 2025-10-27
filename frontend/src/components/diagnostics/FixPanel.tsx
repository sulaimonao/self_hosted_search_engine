import React from "react";

import "@/autopilot/executor";
import { IncidentBus } from "@/diagnostics/incident-bus";

export function FixPanel() {
  const busRef = React.useRef<IncidentBus>(new IncidentBus());
  const [open, setOpen] = React.useState(false);
  const [log, setLog] = React.useState<string[]>([]);
  const [planning, setPlanning] = React.useState(false);

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

  async function planOrFix(apply: boolean) {
    setPlanning(true);
    const incident = busRef.current.snapshot();
    const res = await fetch(`/api/self_heal?apply=${String(apply)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(incident),
    });
    const payload = await res.json();
    setPlanning(false);
    if (!apply) {
      setLog((l) => [...l, "Plan:\n" + JSON.stringify(payload, null, 2)]);
      return;
    }
    await window.autopilotExecutor.run(payload.directive);
    setLog((l) => [...l, "Executed directive."]);
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
          <pre style={{ maxHeight: 260, overflow: "auto" }}>{log.join("\n")}</pre>
        </div>
      ) : null}
    </div>
  );
}
