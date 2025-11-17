import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function RepoAiFlow() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI flow</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>Describe → Propose patch → Apply patch → Run checks.</p>
        <Button variant="secondary">Start new flow</Button>
      </CardContent>
    </Card>
  );
}
