import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ChatPanel } from "@/components/chat-panel";
import { resolveChatLinkNavigation } from "@/components/app-shell";
import type { ChatMessage } from "@/lib/types";

describe("Chat link handling", () => {
  beforeAll(() => {
    if (typeof window !== "undefined" && !window.ResizeObserver) {
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }

      Object.defineProperty(window, "ResizeObserver", {
        value: ResizeObserver,
        configurable: true,
      });
      Object.defineProperty(globalThis, "ResizeObserver", {
        value: ResizeObserver,
        configurable: true,
      });
    }

    if (typeof window !== "undefined" && !Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = () => {};
    }
  });

  const baseMessage: ChatMessage = {
    id: "msg-1",
    role: "assistant",
    content: "",
    createdAt: "",
    answer: "See the [preview](https://example.com/docs).",
    citations: ["https://example.com/source", "notes.txt"],
  };

  it("forwards markdown and citation link clicks to the provided handler", () => {
    const onLinkClick = vi.fn();
    render(
      <ChatPanel
        messages={[baseMessage]}
        input=""
        onInputChange={() => {}}
        onSend={() => {}}
        isBusy={false}
        onApproveAction={() => {}}
        onEditAction={() => {}}
        onDismissAction={() => {}}
        disableInput
        onLinkClick={onLinkClick}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "preview" }));
    fireEvent.click(screen.getByRole("link", { name: "example.com" }));

    expect(onLinkClick).toHaveBeenCalledTimes(2);
    expect(onLinkClick).toHaveBeenNthCalledWith(1, "https://example.com/docs", expect.any(Object));
    expect(onLinkClick).toHaveBeenNthCalledWith(2, "https://example.com/source", expect.any(Object));
  });

  describe("resolveChatLinkNavigation", () => {
    it("routes same-domain links through the preview navigator", () => {
      const decision = resolveChatLinkNavigation(
        "https://example.com/page",
        "https://example.com/docs",
      );
      expect(decision).toEqual({ action: "navigate", url: "https://example.com/docs" });
    });

    it("opens external domains in a new tab", () => {
      const decision = resolveChatLinkNavigation(
        "https://example.com/page",
        "https://external.test/path",
      );
      expect(decision).toEqual({ action: "external", url: "https://external.test/path" });
    });
  });
});
