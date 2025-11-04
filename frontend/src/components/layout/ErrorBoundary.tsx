"use client";
import * as React from "react";

type ErrorBoundaryProps = { fallback?: React.ReactNode; children: React.ReactNode };
type ErrorBoundaryState = { hasError: boolean };

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }
  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    console.error("[UI] ErrorBoundary", error, info);
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="p-3 text-sm text-red-600">
          Chat panel crashed — see console for details.
        </div>
      );
    }
    return this.props.children;
  }
}
