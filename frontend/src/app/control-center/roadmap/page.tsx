import RoadmapPanel from "@/components/roadmap/RoadmapPanel";

export const metadata = { title: "Control Center / Roadmap" };

export default function RoadmapPage() {
  return (
    <main className="p-4 space-y-4">
      <h1 className="text-lg font-semibold">Roadmap</h1>
      <p className="text-sm text-muted-foreground">Live roadmap view. Status chips auto-compute from diagnostics; manual items can be edited inline.</p>
      <RoadmapPanel />
    </main>
  );
}
