import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { SearchResultsPanel } from "@/components/search-results-panel";
import type { SearchHit } from "@/lib/types";

describe("SearchResultsPanel", () => {
  const sampleHits: SearchHit[] = [
    {
      id: "1",
      title: "Example Result",
      url: "https://example.com",
      snippet: "Example snippet",
      score: 0.42,
      blendedScore: 0.58,
      lang: "en",
    },
  ];

  it("renders search hits when available", () => {
    const onOpenHit = vi.fn();
    render(
      <SearchResultsPanel
        query="example"
        hits={sampleHits}
        status="ok"
        isLoading={false}
        error={null}
        detail={null}
        onOpenHit={onOpenHit}
        currentUrl={null}
      />
    );

    expect(screen.getByText("Example Result")).toBeInTheDocument();
    expect(screen.getByText(/Example snippet/)).toBeInTheDocument();
  });

  it("shows placeholder when idle", () => {
    render(
      <SearchResultsPanel
        query=""
        hits={[]}
        status="idle"
        isLoading={false}
        error={null}
        detail={null}
        onOpenHit={() => {}}
        currentUrl={null}
      />
    );

    expect(screen.getByText(/Enter a keyword/i)).toBeInTheDocument();
  });
});
