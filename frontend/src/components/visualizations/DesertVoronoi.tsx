"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";

import { api } from "@/lib/api";

interface HierarchyNode {
  name: string;
  value?: number;
  url?: string;
  children?: HierarchyNode[];
}

const palette = ["#D35400", "#E67E22", "#A1887F", "#D7CCC8"];

export function DesertVoronoi() {
  const [root, setRoot] = useState<HierarchyNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ width: number; height: number }>({ width: 640, height: 420 });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const resp = await fetch(api("/api/graph/hierarchy"));
        if (!resp.ok) throw new Error(`Status ${resp.status}`);
        const payload = (await resp.json()) as HierarchyNode;
        if (!cancelled) {
          setRoot(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load hierarchy");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function updateSize() {
      const el = containerRef.current;
      if (!el) return;
      const { width } = el.getBoundingClientRect();
      setSize({ width: Math.max(320, width), height: 420 });
    }
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const treemapNodes = useMemo(() => {
    if (!root) return [];
    const hierarchy = d3
      .hierarchy(root)
      .sum((d) => d.value ?? 1)
      .sort((a, b) => (b.value || 0) - (a.value || 0));
    d3.treemap<HierarchyNode>().size([size.width, size.height]).padding(4)(hierarchy);
    return hierarchy.leaves();
  }, [root, size.height, size.width]);

  const colorScale = useMemo(
    () =>
      d3
        .scaleOrdinal<string, string>()
        .domain(treemapNodes.map((n) => n.parent?.data.name || "unknown"))
        .range(palette),
    [treemapNodes]
  );

  return (
    <div
      ref={containerRef}
      className="rounded-xl border p-4"
      style={{ borderColor: "#8D6E63", background: "#F5E6D3" }}
    >
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: "#5D4037" }}>
            Topic Distribution (Cracked Earth)
          </h3>
          <p className="text-sm" style={{ color: "#8D6E63" }}>
            Treemap grouped by site/topic from indexed documents.
          </p>
        </div>
        {loading && <span className="text-sm" style={{ color: "#5D4037" }}>Loading...</span>}
        {error && (
          <span className="text-sm" style={{ color: "#D35400" }}>
            {error}
          </span>
        )}
      </div>
      <svg width={size.width} height={size.height}>
        {treemapNodes.map((node, idx) => {
          const fill = colorScale(node.parent?.data.name || "unknown");
          const label = node.data.name.length > 24 ? `${node.data.name.slice(0, 24)}…` : node.data.name;
          return (
            <g key={`leaf-${idx}`} transform={`translate(${node.x0},${node.y0})`}>
              <rect
                width={Math.max(0, node.x1 - node.x0)}
                height={Math.max(0, node.y1 - node.y0)}
                fill={fill}
                stroke="#5D4037"
                rx={6}
                opacity={0.9}
              />
              <text x={8} y={18} fontSize={12} fill="#2d1e19" fontWeight={600} pointerEvents="none">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
