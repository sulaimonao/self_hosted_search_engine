import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { SearchResultsPanel } from "../search-results-panel";
import { SystemCheckPanel } from "../system-check-panel";
import type { SearchHit, SystemCheckResponse } from "../../lib/types";

describe("Trace ID rendering", () => {
  it("shows trace id in search error banner when provided", () => {
    const hits: SearchHit[] = [];
    render(
      <SearchResultsPanel
        query="q"
        hits={hits}
        status="error"
        isLoading={false}
        error={"Something failed"}
        detail={"Details"}
        traceId={"req_123"}
        onOpenHit={() => {}}
        currentUrl={null}
      />
    );
    expect(screen.getByText(/Trace:/i)).toBeInTheDocument();
    expect(screen.getByText(/req_123/)).toBeInTheDocument();
  });

  it("shows backend trace id in system check backend section and error banner trace id when provided", () => {
    const report: SystemCheckResponse = {
      generated_at: new Date().toISOString(),
      traceId: "req_sys_1",
      backend: { status: "pass", checks: [] },
      diagnostics: { status: "pass", job_id: "job-1" },
      llm: { status: "pass" },
      summary: {},
    };

    render(
      <SystemCheckPanel
        open
        onOpenChange={() => {}}
        systemCheck={report}
        browserReport={null}
        loading={false}
        error={"bad things"}
        errorTraceId={"req_err_2"}
        blocking={false}
        skipMessage={null}
      />
    );

  expect(screen.getByText(/req_sys_1/)).toBeInTheDocument();
  expect(screen.getByText(/req_err_2/)).toBeInTheDocument();
  });
});
