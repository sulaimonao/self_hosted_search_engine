import { DesertNetwork } from "@/components/visualizations/DesertNetwork";
import { DesertRadial } from "@/components/visualizations/DesertRadial";
import { DesertVoronoi } from "@/components/visualizations/DesertVoronoi";

export default function MissionControlPage() {
  return (
    <div className="min-h-screen w-full" style={{ background: "#FFF8F0" }}>
      <div className="mx-auto max-w-7xl px-6 py-10">
        <header className="mb-8 space-y-2 text-center md:text-left">
          <p className="text-sm font-semibold uppercase tracking-wide" style={{ color: "#D35400" }}>
            Mission Control
          </p>
          <h1 className="text-3xl font-bold" style={{ color: "#5D4037" }}>
            Crawled Data Overview
          </h1>
          <p className="max-w-3xl text-lg" style={{ color: "#8D6E63" }}>
            Visualizing the crawled index as a living network rooted in warm desert tones.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-2">
          <div className="lg:col-span-2">
            <DesertNetwork />
          </div>
          <DesertVoronoi />
          <DesertRadial />
        </div>
      </div>
    </div>
  );
}
