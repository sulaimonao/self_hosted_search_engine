import "@testing-library/jest-dom";
import { act, render, screen } from "@testing-library/react";

import { AgentTracePanel } from "@/components/AgentTracePanel";
import { useAgentTraceStore } from "@/state/agentTrace";
import { useUIStore } from "@/state/ui";

describe("ui reasoning toggle store", () => {
  beforeEach(() => {
    useUIStore.setState({ showReasoning: false, hydrated: false });
    window.localStorage.clear();
  });

  it("hydrates from localStorage when available", () => {
    window.localStorage.setItem("ui.showReasoning", "true");
    act(() => {
      useUIStore.getState().hydrate();
    });
    const state = useUIStore.getState();
    expect(state.showReasoning).toBe(true);
    expect(state.hydrated).toBe(true);
  });

  it("persists toggle changes to localStorage", () => {
    act(() => {
      useUIStore.getState().setShowReasoning(true);
    });
    expect(window.localStorage.getItem("ui.showReasoning")).toBe("true");
  });
});

describe("AgentTracePanel", () => {
  beforeEach(() => {
    useUIStore.setState({ showReasoning: true, hydrated: true });
    useAgentTraceStore.setState({ stepsByChat: {} });
  });

  it("renders agent steps when available", () => {
    act(() => {
      useAgentTraceStore.getState().addStep("chat-1", "__thread__", {
        tool: "browser.history",
        status: "ok",
        duration_ms: 120,
        excerpt: "visited example",
        token_in: 10,
        token_out: 4,
      });
    });

    render(<AgentTracePanel chatId="chat-1" />);

    expect(screen.getByText(/Agent steps/i)).toBeInTheDocument();
    expect(screen.getByText(/browser.history/i)).toBeInTheDocument();
    expect(screen.getByText(/visited example/i)).toBeInTheDocument();
  });
});
