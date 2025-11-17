import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type OverviewCardProps = {
  title: string;
  value: string;
  description: string;
};

export function OverviewCard({ title, value, description }: OverviewCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold">{value}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}
