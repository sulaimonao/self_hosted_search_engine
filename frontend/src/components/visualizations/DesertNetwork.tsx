"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";

import { api } from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

interface NetworkNode {
  id: string;
  name?: string;
  group?: string | null;
  val?: number;
  color?: string;
}

interface NetworkLink {
  source: string;
  target: string;
  color?: string;
}

interface NetworkResponse {
  nodes: NetworkNode[];
  links: NetworkLink[];
}

const CANVAS_BACKGROUND = "#F5E6D3";

export function DesertNetwork() {
  const [data, setData] = useState<NetworkResponse>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch(api("/api/graph/network"));
        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }
        const payload = (await response.json()) as NetworkResponse;
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load network");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  const sizedData = useMemo(() => {
    return {
      nodes: data.nodes.map((node) => ({ ...node, val: node.val ?? 4 })),
      links: data.links,
    };
  }, [data]);

  return (
    <div className="rounded-xl border" style={{ borderColor: "#8D6E63", background: CANVAS_BACKGROUND }}>
      <div className="flex items-center justify-between px-4 py-2">
        <div>
          <h2 className="text-lg font-semibold" style={{ color: "#5D4037" }}>
            Living Root System
          </h2>
          <p className="text-sm" style={{ color: "#8D6E63" }}>
            Force-directed view of URLs and their link structure.
          </p>
        </div>
        {loading && <span className="text-sm" style={{ color: "#5D4037" }}>Loading...</span>}
        {error && (
          <span className="text-sm" style={{ color: "#D35400" }}>
            {error}
          </span>
        )}
      </div>
      <div className="h-[520px] w-full">
        <ForceGraph2D
          graphData={sizedData}
          backgroundColor={CANVAS_BACKGROUND}
          nodeColor={(node) => (node as NetworkNode).color || "#E67E22"}
          nodeLabel={(node) => (node as NetworkNode).name || (node as NetworkNode).id}
          nodeRelSize={6}
          linkColor={() => "#8D6E63"}
          linkDirectionalParticles={2}
          linkDirectionalParticleSpeed={0.005}
          linkDirectionalParticleWidth={2}
          linkDirectionalParticleColor={() => "#D35400"}
          width={undefined}
          height={undefined}
        />
      </div>
    </div>
  );
}
