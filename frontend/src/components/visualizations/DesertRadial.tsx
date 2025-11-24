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

export function DesertRadial() {
  const [root, setRoot] = useState<HierarchyNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [radius, setRadius] = useState(260);

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
      setRadius(Math.max(180, Math.min(width / 2, 360)));
    }
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const clusterData = useMemo(() => {
    if (!root) return null;
    const hierarchy = d3.hierarchy(root);
    const cluster = d3.cluster<HierarchyNode>().size([2 * Math.PI, radius - 60]);
    return cluster(hierarchy);
  }, [radius, root]);

  const linkGenerator = useMemo(
    () =>
      d3
        .linkRadial<d3.HierarchyPointNode<HierarchyNode>, d3.HierarchyPointNode<HierarchyNode>>()
        .angle((d) => d.x)
        .radius((d) => d.y),
    []
  );

  const diameter = radius * 2;

  return (
    <div
      ref={containerRef}
      className="rounded-xl border p-4"
      style={{ borderColor: "#8D6E63", background: "#F5E6D3" }}
    >
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: "#5D4037" }}>
            Crawl Depth (The Oasis)
          </h3>
          <p className="text-sm" style={{ color: "#8D6E63" }}>
            Radial hierarchy of the crawled structure.
          </p>
        </div>
        {loading && <span className="text-sm" style={{ color: "#5D4037" }}>Loading...</span>}
        {error && (
          <span className="text-sm" style={{ color: "#D35400" }}>
            {error}
          </span>
        )}
      </div>
      <svg width={diameter} height={diameter}>
        <g transform={`translate(${radius},${radius})`}>
          {clusterData?.links().map((link, idx) => (
            <path
              key={`link-${idx}`}
              d={linkGenerator(link) ?? undefined}
              fill="none"
              stroke="#8D6E63"
              strokeWidth={1}
              opacity={0.7}
            />
          ))}
          {clusterData?.descendants().map((node, idx) => {
            const isRoot = idx === 0;
            const angle = (node.x * 180) / Math.PI;
            const rotate = angle < 180 ? angle - 90 : angle + 90;
            return (
              <g key={`node-${idx}`} transform={`rotate(${(node.x * 180) / Math.PI - 90}) translate(${node.y},0)`}>
                <circle
                  r={isRoot ? 14 : 4}
                  fill={isRoot ? "#00C853" : "#D35400"}
                  stroke="#F5E6D3"
                  strokeWidth={isRoot ? 2 : 1}
                />
                {!isRoot && (
                  <text
                    dy="0.31em"
                    x={node.x < Math.PI === !node.children ? 8 : -8}
                    textAnchor={node.x < Math.PI === !node.children ? "start" : "end"}
                    transform={`rotate(${rotate})`}
                    fontSize={11}
                    fill="#4a342f"
                  >
                    {(node.data.name || "").slice(0, 30)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
