import { OverviewCard, type OverviewCardProps } from "@/components/overview/OverviewCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

interface OverviewCardsProps {
  cards: OverviewCardProps[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function OverviewCards({ cards, isLoading, error, onRetry }: OverviewCardsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-32 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        <p>{error}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <OverviewCard key={card.title} {...card} />
      ))}
    </div>
  );
}
