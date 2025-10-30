type BaseVerb = { headless?: boolean };

export type Verb =
  | ({ type: "navigate"; url: string } & BaseVerb)
  | ({ type: "reload" } & BaseVerb)
  | ({ type: "click"; selector?: string; text?: string } & BaseVerb)
  | ({ type: "type"; selector: string; text: string } & BaseVerb)
  | ({ type: "waitForStable"; ms?: number } & BaseVerb);

export class AutopilotExecutor {
  private async runClient(step: Verb) {
    if (step.type === "reload") {
      location.reload();
      return;
    }
    if (step.type === "navigate" && step.url) {
      location.href = step.url;
      return;
    }
    if (step.type === "click") {
      let el: Element | null = null;
      if (step.selector) {
        el = document.querySelector(step.selector);
      }
      if (!el && step.text) {
        const interactive = Array.from(
          document.querySelectorAll<HTMLElement>("button,a,[role='button']"),
        );
        el = interactive.find((node) => (node.textContent || "").includes(step.text ?? "")) || null;
        if (!el) {
          const xp = `//*[normalize-space(text())=${JSON.stringify(step.text)}]`;
          el = document.evaluate(
            xp,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null,
          ).singleNodeValue as Element | null;
        }
      }
      if (!el) {
        throw new Error(`click: target not found (${step.selector || step.text})`);
      }
      (el as HTMLElement).click();
      return;
    }
    if (step.type === "type") {
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
      return;
    }
    if (step.type === "waitForStable") {
      const delay = typeof step.ms === "number" && step.ms >= 0 ? step.ms : 600;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  private async runHeadless(steps: Verb[]) {
    const response = await fetch("/api/self_heal/execute_headless", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ consent: true, directive: { steps } }),
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(text || `headless executor ${response.status}`);
    }
    return response.json().catch(() => null);
  }

  async run(directive: { steps: Verb[] }) {
    const headlessBuffer: Verb[] = [];

    const flushHeadless = async () => {
      if (headlessBuffer.length === 0) {
        return;
      }
      const batch = headlessBuffer.splice(0, headlessBuffer.length);
      await this.runHeadless(batch);
    };

    for (const step of directive.steps) {
      if (step.headless) {
        headlessBuffer.push(step);
        continue;
      }
      await flushHeadless();
      await this.runClient(step);
    }

    await flushHeadless();
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
