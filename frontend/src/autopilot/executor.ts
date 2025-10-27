export type Verb =
  | { type: "navigate"; url: string }
  | { type: "reload" }
  | { type: "click"; selector?: string; text?: string }
  | { type: "type"; selector: string; text: string }
  | { type: "waitForStable"; ms?: number };

export class AutopilotExecutor {
  async run(directive: { steps: Verb[] }) {
    for (const step of directive.steps) {
      if (step.type === "reload") {
        location.reload();
      } else if (step.type === "navigate" && step.url) {
        location.href = step.url;
      } else if (step.type === "click") {
        let el: Element | null = null;
        if (step.selector) {
          el = document.querySelector(step.selector);
        }
        if (!el && step.text) {
          const interactive = Array.from(
            document.querySelectorAll<HTMLElement>("button,a,[role='button']"),
          );
          el =
            interactive.find((node) => (node.textContent || "").includes(step.text ?? "")) || null;
        }
        if (!el) {
          throw new Error(`click: target not found (${step.selector || step.text})`);
        }
        (el as HTMLElement).click();
      } else if (step.type === "type") {
        const el = document.querySelector(step.selector) as
          | HTMLInputElement
          | HTMLTextAreaElement
          | null;
        if (!el) {
          throw new Error(`type: target not found (${step.selector})`);
        }
        el.focus();
        el.value = step.text;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else if (step.type === "waitForStable") {
        await new Promise((resolve) => setTimeout(resolve, step.ms ?? 600));
      }
    }
  }
}

declare global {
  interface Window {
    autopilotExecutor: AutopilotExecutor;
  }
}

if (typeof window !== "undefined") {
  window.autopilotExecutor = new AutopilotExecutor();
}
