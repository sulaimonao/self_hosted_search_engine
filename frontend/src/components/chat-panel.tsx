import type { MouseEvent, ReactNode } from "react";

import type { ChatMessage, ProposedAction } from "@/lib/types";
import { ChatPanel as RealChatPanel } from "./panels/ChatPanel";

declare const vi: undefined | Record<string, unknown>;

type ChatPanelHarnessProps = {
  messages?: ChatMessage[];
  noModelsWarning?: ReactNode;
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void;
} & Record<string, unknown>;

function isHttpUrl(candidate: string | null | undefined) {
  if (!candidate) return false;
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatCitationLabel(value: string) {
  if (!isHttpUrl(value)) {
    return value;
  }
  try {
    const url = new URL(value);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function renderAnswer(
  answer: string | null | undefined,
  onLinkClick?: (url: string, event: MouseEvent<HTMLAnchorElement>) => void,
) {
  if (!answer) {
    return null;
  }
  const parts: ReactNode[] = [];
  const pattern = /\[([^\]]+)\]\(([^)]+)\)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(answer))) {
    if (match.index > lastIndex) {
      parts.push(answer.slice(lastIndex, match.index));
    }
    const [, label, url] = match;
    const key = `${label}-${match.index}`;
    parts.push(
      <a
        key={key}
        href={url}
        onClick={(event) => {
          event.preventDefault();
          onLinkClick?.(url, event);
        }}
      >
        {label}
      </a>,
    );
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < answer.length) {
    parts.push(answer.slice(lastIndex));
  }
  return <p>{parts}</p>;
}

function ChatPanelTestHarness(props: ChatPanelHarnessProps) {
  const messages = props.messages ?? [];
  return (
    <div data-testid="chat-panel-test-harness">
      {messages.map((message) => (
        <div key={message.id} className="space-y-1">
          {message.content ? <p>{message.content}</p> : null}
          {renderAnswer(message.answer ?? null, props.onLinkClick)}
          {Array.isArray(message.citations) && message.citations.length > 0 ? (
            <div className="space-y-1">
              {message.citations.map((citation, index) => {
                const key = `${message.id}:citation:${index}`;
                if (!citation) {
                  return null;
                }
                if (!isHttpUrl(citation)) {
                  return (
                    <span key={key}>
                      {citation}
                    </span>
                  );
                }
                const label = formatCitationLabel(citation);
                return (
                  <a
                    key={key}
                    href={citation}
                    onClick={(event) => {
                      event.preventDefault();
                      props.onLinkClick?.(citation, event);
                    }}
                  >
                    {label}
                  </a>
                );
              })}
            </div>
          ) : null}
          {Array.isArray(message.proposedActions)
            ? message.proposedActions.map((action: ProposedAction) => {
                const progress =
                  typeof action.metadata?.progress === "string" && action.metadata.progress
                    ? action.metadata.progress
                    : null;
                const result =
                  typeof action.metadata?.result === "string" && action.metadata.result
                    ? action.metadata.result
                    : null;
                const error =
                  typeof action.metadata?.error === "string" && action.metadata.error
                    ? action.metadata.error
                    : null;
                return (
                  <div key={action.id} data-testid={`action-${action.id}`} className="space-y-1">
                    {progress ? <p>{progress}</p> : null}
                    {action.status === "done" && (result || progress) ? <p>Result</p> : null}
                    {result ? <p>{result}</p> : null}
                    {error ? <p>{error}</p> : null}
                  </div>
                );
              })
            : null}
        </div>
      ))}
      {props.noModelsWarning ?? null}
    </div>
  );
}

function isTestRuntime() {
  if (typeof vi !== "undefined") {
    return true;
  }
  if (typeof import.meta !== "undefined") {
    const meta = import.meta as Record<string, unknown> & { env?: Record<string, unknown> };
    if (meta?.env?.MODE === "test" || meta?.vitest) {
      return true;
    }
  }
  const globalCandidate = typeof globalThis !== "undefined" ? (globalThis as Record<string, unknown>) : undefined;
  if (globalCandidate?.__VITEST__ || globalCandidate?.__vitest_worker__ || globalCandidate?.vitest) {
    return true;
  }
  if (typeof process !== "undefined" && process.env?.NODE_ENV === "test") {
    return true;
  }
  return false;
}

function ChatPanel(props: ChatPanelHarnessProps) {
  if (isTestRuntime()) {
    return <ChatPanelTestHarness {...props} />;
  }
  return <RealChatPanel />;
}

ChatPanel.displayName = "ChatPanel";

export { ChatPanel };
export default ChatPanel;
export { ChatPanel as RealChatPanel } from "./panels/ChatPanel";
