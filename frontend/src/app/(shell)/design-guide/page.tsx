import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const surfaceSwatches = [
  { label: "bg-app-bg", className: "bg-app-bg" },
  { label: "bg-app-subtle", className: "bg-app-subtle" },
  { label: "bg-app-card", className: "bg-app-card" },
  { label: "bg-ai-panel", className: "bg-ai-panel" },
];

const accentSwatches = [
  { label: "bg-accent", className: "bg-accent" },
  { label: "bg-accent-soft", className: "bg-accent-soft" },
];

const stateSwatches = [
  { label: "text-state-success", className: "bg-state-success/20 text-state-success" },
  { label: "text-state-warning", className: "bg-state-warning/20 text-state-warning" },
  { label: "text-state-danger", className: "bg-state-danger/20 text-state-danger" },
  { label: "text-state-info", className: "bg-state-info/20 text-state-info" },
];

function Swatch({ label, className }: { label: string; className: string }) {
  return (
    <div className="space-y-2 rounded-md border border-border-subtle bg-app-card p-4">
      <div className={cn("h-16 rounded-md border border-border-subtle", className)} />
      <code className="text-xs text-fg-muted">{label}</code>
    </div>
  );
}

function StateSwatch({ label, className }: { label: string; className: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-app-card p-4 text-sm text-fg">
      <span className={cn("inline-flex items-center justify-center rounded-full px-3 py-1 text-xs font-semibold", className)}>
        {label}
      </span>
    </div>
  );
}

export default function DesignGuidePage() {
  return (
    <div className="flex flex-1 flex-col gap-8">
      <header className="space-y-2">
        <p className="text-xs uppercase text-fg-muted">Design system</p>
        <h1 className="text-2xl font-semibold">UI kit & token guide</h1>
        <p className="text-sm text-fg-muted">
          Internal QA surface showing the semantic tokens, typography, and shared components. Use `/docs/frontend_design_system.md`
          for the written spec.
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Surfaces</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {surfaceSwatches.map((swatch) => (
            <Swatch key={swatch.label} {...swatch} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Accent</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {accentSwatches.map((swatch) => (
            <Swatch key={swatch.label} {...swatch} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">States</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {stateSwatches.map((swatch) => (
            <StateSwatch key={swatch.label} {...swatch} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Card</h2>
        <Card className="bg-app-card border-border-subtle shadow-subtle">
          <CardHeader>
            <CardTitle>Research deck</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-fg-muted">
            Cards use `bg-app-card`, `border-border-subtle`, `rounded-md`, and `shadow-subtle`. Nested blocks can rely on
            `bg-app-card-subtle`.
          </CardContent>
        </Card>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Buttons</h2>
        <div className="flex flex-wrap gap-4">
          <Button>Primary action</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Input</h2>
        <Input placeholder="bg-app-input · border-border-subtle · rounded-xs" className="max-w-md" />
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">List row</h2>
        <div className="rounded-md border border-border-subtle bg-app-card p-4 transition hover:bg-app-card-hover">
          <p className="text-sm font-medium text-fg">List row title</p>
          <p className="text-xs text-fg-muted">Uses bg-app-card + hover:bg-app-card-hover and a subtle border.</p>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Chat bubbles</h2>
        <div className="space-y-3">
          <div className="max-w-md rounded-md border border-border-subtle bg-app-card-subtle p-3 text-sm text-fg">
            <p className="text-xs uppercase text-fg-muted">User</p>
            What&apos;s the latest on the repo sync?
          </div>
          <div className="max-w-md rounded-md border border-border-subtle bg-accent-soft p-3 text-sm text-fg-on-accent">
            <p className="text-xs uppercase text-fg-on-accent/70">Assistant</p>
            Sync completed successfully · <span className="text-state-success font-semibold">All checks green</span>
          </div>
        </div>
      </section>
    </div>
  );
}
