import { OverviewCard, type OverviewCardProps } from "@/components/overview/OverviewCard";
import { Skeleton } from "@/components/ui/skeleton";

interface OverviewCardsProps {
  cards: OverviewCardProps[];
  isLoading?: boolean;
  error?: string | null;
}

export function OverviewCards({ cards, isLoading, error }: OverviewCardsProps) {
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
    return <p className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <OverviewCard key={card.title} {...card} />
      ))}
    </div>
  );
}
