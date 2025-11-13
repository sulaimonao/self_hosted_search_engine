import { describe, expect, it } from "vitest";
import { AutopilotExecutor, type Verb } from "@/autopilot/executor";

describe("AutopilotExecutor - New Verbs", () => {
  it("accepts scroll verb with selector", () => {
    const scrollVerb: Verb = {
      type: "scroll",
      selector: "#main-content",
      behavior: "smooth",
    };
    expect(scrollVerb.type).toBe("scroll");
    expect(scrollVerb.selector).toBe("#main-content");
    expect(scrollVerb.behavior).toBe("smooth");
  });

  it("accepts scroll verb with coordinates", () => {
    const scrollVerb: Verb = {
      type: "scroll",
      x: 0,
      y: 500,
      behavior: "auto",
    };
    expect(scrollVerb.type).toBe("scroll");
    expect(scrollVerb.x).toBe(0);
    expect(scrollVerb.y).toBe(500);
  });

  it("accepts hover verb with selector", () => {
    const hoverVerb: Verb = {
      type: "hover",
      selector: "button.submit",
    };
    expect(hoverVerb.type).toBe("hover");
    expect(hoverVerb.selector).toBe("button.submit");
  });

  it("accepts hover verb with text", () => {
    const hoverVerb: Verb = {
      type: "hover",
      text: "Submit",
    };
    expect(hoverVerb.type).toBe("hover");
    expect(hoverVerb.text).toBe("Submit");
  });

  it("creates executor instance", () => {
    const executor = new AutopilotExecutor();
    expect(executor).toBeInstanceOf(AutopilotExecutor);
  });

  it("accepts directive with new verbs", () => {
    const directive = {
      steps: [
        { type: "scroll" as const, selector: "#top" },
        { type: "hover" as const, selector: "button" },
        { type: "click" as const, selector: "button" },
      ],
    };
    expect(directive.steps).toHaveLength(3);
    expect(directive.steps[0].type).toBe("scroll");
    expect(directive.steps[1].type).toBe("hover");
  });
});
