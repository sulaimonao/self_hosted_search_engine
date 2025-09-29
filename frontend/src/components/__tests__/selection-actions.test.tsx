import { render, screen } from "@testing-library/react";
import { AgentLog } from "../agent-log";
import { ChatPanel } from "../chat-panel";
import type { AgentLogEntry, ChatMessage, ProposedAction } from "@/lib/types";
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";
import { describe, expect, test, vi } from "vitest";

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: ReactNode }) => (
    <div data-testid="scroll-area">{children}</div>
  ),
}));

vi.mock("@/components/ui/separator", () => ({
  Separator: (props: HTMLAttributes<HTMLHRElement>) => (
    <hr data-testid="separator" {...props} />
  ),
}));

vi.mock("@/components/action-card", () => ({
  ActionCard: ({ action }: { action: ProposedAction }) => (
    <div data-testid={`action-card-${action.id}`}>{action.title}</div>
  ),
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/components/ui/card", () => {
  const Mock = ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  );
  return {
    Card: Mock,
    CardContent: Mock,
    CardHeader: Mock,
    CardTitle: Mock,
  };
});

vi.mock("@/components/ui/textarea", () => ({
  Textarea: ({ children, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
    <textarea {...props}>{children}</textarea>
  ),
}));

beforeAll(() => {
  Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
});

describe("selection action surfaces", () => {
  test("AgentLog shows spinner and preview for in-progress entries", () => {
    const entries: AgentLogEntry[] = [
      {
        id: "log-1",
        label: "Summarizing highlight",
        detail: "Working on captured text",
        status: "info",
        timestamp: new Date().toISOString(),
        meta: { inProgress: true, preview: "Short preview" },
      },
      {
        id: "log-2",
        label: "Summary ready",
        detail: "Completed",
        status: "success",
        timestamp: new Date().toISOString(),
        meta: { inProgress: false, preview: "Final summary" },
      },
    ];

    const { container } = render(<AgentLog entries={entries} isStreaming />);
    const listItems = container.querySelectorAll("ol li");
    expect(listItems.length).toBeGreaterThanOrEqual(2);
    expect(listItems[0]?.querySelector("svg.animate-spin")).not.toBeNull();
    expect(listItems[1]?.querySelector("svg.animate-spin")).toBeNull();
    expect(screen.getByText(/Short preview/)).toBeInTheDocument();
    expect(screen.getByText(/Summary ready/)).toBeInTheDocument();
  });

  test("ChatPanel surfaces progress, results, and errors for selection actions", () => {
    const now = new Date().toISOString();
    const summarizeExecuting: ProposedAction = {
      id: "act-1",
      kind: "summarize",
      title: "Summarize selection",
      description: "",
      payload: {},
      status: "executing",
      metadata: { progress: "Summarizing selection…" },
    };
    const summarizeDone: ProposedAction = {
      ...summarizeExecuting,
      id: "act-2",
      status: "done",
      metadata: { result: "Summary output" },
    };
    const extractError: ProposedAction = {
      id: "act-3",
      kind: "extract",
      title: "Extract selection",
      description: "",
      payload: {},
      status: "error",
      metadata: { error: "Extraction failed" },
    };
    const messages: ChatMessage[] = [
      {
        id: "msg-1",
        role: "assistant",
        content: "Processing",
        createdAt: now,
        proposedActions: [summarizeExecuting],
      },
      {
        id: "msg-2",
        role: "assistant",
        content: "Done",
        createdAt: now,
        proposedActions: [summarizeDone],
      },
      {
        id: "msg-3",
        role: "assistant",
        content: "Error",
        createdAt: now,
        proposedActions: [extractError],
      },
    ];

    render(
      <ChatPanel
        messages={messages}
        input=""
        onInputChange={() => undefined}
        onSend={() => undefined}
        onStopStreaming={() => undefined}
        isStreaming={false}
        onApproveAction={() => undefined}
        onEditAction={() => undefined}
        onDismissAction={() => undefined}
        modelOptions={["gpt-oss"]}
        selectedModel="gpt-oss"
        onModelChange={() => undefined}
        noModelsWarning={null}
      />
    );

    expect(screen.getByText("Summarizing selection…")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText("Summary output")).toBeInTheDocument();
    expect(screen.getByText("Extraction failed")).toBeInTheDocument();
  });
});

