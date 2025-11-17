import { OverviewCard, type OverviewCardProps } from "@/components/overview/OverviewCard";

export function OverviewCards({ cards }: { cards: OverviewCardProps[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <OverviewCard key={card.title} {...card} />
      ))}
    </div>
  );
}
