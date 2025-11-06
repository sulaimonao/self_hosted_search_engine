"use client";

import React from "react";
import { sendUiLog } from "@/lib/logging";

type Props = {
  children: React.ReactNode;
};

type State = { hasError: boolean };

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    try {
      sendUiLog({
        event: "ui.error.boundary",
        level: "ERROR",
        msg: String((error as Error)?.message ?? "client error"),
        meta: { info, stack: (error as Error)?.stack ?? null },
      });
    } catch {
      // swallow
    }
  }

  render() {
    if (this.state.hasError) {
      // show nothing (UI may provide a fallback UI component elsewhere)
      return null;
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
