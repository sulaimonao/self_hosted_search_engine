import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useResearchSessionActions } from "@/hooks/useResearchSessionActions";

export function PageActions() {
  const {
    hasSession,
    linkedTab,
    tabsQuery,
    addPageToSession,
    summarizePageToNotes,
    isAddingPage,
    isSummarizingPage,
  } = useResearchSessionActions();

  const tabSummary = linkedTab
    ? {
        title: linkedTab.current_title ?? linkedTab.current_url ?? "Untitled",
        url: linkedTab.current_url ?? "Unknown URL",
      }
    : null;

  return (
    <Card className="h-80 border-border-subtle bg-app-card">
      <CardHeader>
        <CardTitle>Session-aware actions</CardTitle>
        <CardDescription>Capture the current page and synthesize structured notes.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="rounded-md border border-border-subtle bg-app-card-subtle p-3 text-sm">
          {tabsQuery.isLoading ? (
            <Skeleton className="h-12 w-full" />
          ) : tabSummary ? (
            <div>
              <p className="font-semibold text-fg">{tabSummary.title}</p>
              <p className="text-xs text-fg-muted">{tabSummary.url}</p>
            </div>
          ) : hasSession ? (
            <p className="text-sm text-fg-muted">No browser tab is currently linked to this session.</p>
          ) : (
            <p className="text-sm text-fg-muted">Start a research session to link a browser tab.</p>
          )}
        </div>
        <div className="space-y-3">
          <Button
            variant="outline"
            className="w-full justify-start border-border-subtle bg-app-subtle"
            onClick={() => addPageToSession()}
            disabled={!hasSession || !linkedTab || isAddingPage}
          >
            {isAddingPage ? "Adding page…" : "Add page to session notes"}
          </Button>
          <Button
            variant="outline"
            className="w-full justify-start border-border-subtle bg-app-subtle"
            onClick={() => summarizePageToNotes()}
            disabled={!hasSession || !linkedTab || isSummarizingPage}
          >
            {isSummarizingPage ? "Summarizing page…" : "Summarize page into notes"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
