"use client";

import { api } from "@/lib/api";

type BaseVerb = { headless?: boolean };

export type Verb =
  | ({ type: "navigate"; url: string } & BaseVerb)
  | ({ type: "reload" } & BaseVerb)
  | ({ type: "click"; selector?: string; text?: string } & BaseVerb)
  | ({ type: "type"; selector: string; text: string } & BaseVerb)
  | ({ type: "waitForStable"; ms?: number } & BaseVerb);

export type AutopilotRunOptions = {
  onHeadlessError?: (error: Error) => void;
};

export type AutopilotRunResult = {
  headlessErrors: Error[];
  headlessBatches: number;
};

function normalizeXpathText(value: string): string {
  return `//*[normalize-space(text())=${JSON.stringify(value.trim())}]`;
}

function safeClick(target: Element | null, context: string) {
  if (!target) {
    console.warn(`[autopilot] click target not found for ${context}`);
    return;
  }
  try {
    (target as HTMLElement).click();
  } catch (error) {
    console.warn(`[autopilot] click failed for ${context}`, error);
  }
}

export class AutopilotExecutor {
  private findBySelector(selector: string | undefined): Element | null {
    if (!selector || typeof document === "undefined") {
      return null;
    }
    try {
      return document.querySelector(selector);
    } catch (error) {
      console.warn(`[autopilot] invalid selector ${selector}`, error);
      return null;
    }
  }

  private findByText(text: string | undefined): Element | null {
    if (!text || typeof document === "undefined") {
      return null;
    }
    try {
      const xpath = normalizeXpathText(text);
      const result = document.evaluate(
        xpath,
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null,
      );
      const node = result.singleNodeValue;
      if (node instanceof HTMLElement) {
        return node;
      }
      return null;
    } catch (error) {
      console.warn(`[autopilot] xpath lookup failed for ${text}`, error);
      return null;
    }
  }

  private async runClient(step: Verb) {
    if (typeof window === "undefined" || typeof document === "undefined") {
      console.warn("[autopilot] client executor unavailable in this environment");
      return;
    }
    if (step.type === "reload") {
      window.location.reload();
      return;
    }
    if (step.type === "navigate" && step.url) {
      window.location.assign(step.url);
      return;
    }
    if (step.type === "click") {
      const selectorTarget = this.findBySelector(step.selector);
      if (selectorTarget) {
        safeClick(selectorTarget, step.selector ?? step.text ?? "click");
        return;
      }
      const textTarget = this.findByText(step.text);
      safeClick(textTarget, step.selector ?? step.text ?? "click");
      return;
    }
    if (step.type === "type") {
      const element = this.findBySelector(step.selector) as
        | HTMLInputElement
        | HTMLTextAreaElement
        | null;
      if (!element) {
        console.warn(`[autopilot] type target not found (${step.selector})`);
        return;
      }
      element.focus();
      element.value = step.text;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    if (step.type === "waitForStable") {
      const delay = typeof step.ms === "number" && step.ms >= 0 ? step.ms : 600;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  private async runHeadless(steps: Verb[]) {
    const response = await fetch(api("/api/self_heal/execute_headless"), {
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

  async run(directive: { steps: Verb[] }, options?: AutopilotRunOptions): Promise<AutopilotRunResult> {
    const headlessBuffer: Verb[] = [];
    const headlessErrors: Error[] = [];
    let headlessBatches = 0;

    const flushHeadless = async () => {
      if (headlessBuffer.length === 0) {
        return;
      }
      const batch = headlessBuffer.splice(0, headlessBuffer.length);
      try {
        await this.runHeadless(batch);
        headlessBatches += 1;
      } catch (error) {
        const normalized = error instanceof Error ? error : new Error(String(error ?? "headless failed"));
        console.warn("[autopilot] headless batch failed", normalized);
        headlessErrors.push(normalized);
        options?.onHeadlessError?.(normalized);
      }
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

    return { headlessErrors, headlessBatches };
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
