import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function PageActions() {
  return (
    <Card className="h-80">
      <CardHeader>
        <CardTitle>Page actions</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Button variant="secondary">Summarize page</Button>
        <Button variant="secondary">Capture screenshot</Button>
        <Button variant="secondary">Send to AI panel</Button>
        <Button variant="secondary">Open in repo tool</Button>
      </CardContent>
    </Card>
  );
}
