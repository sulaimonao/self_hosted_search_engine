"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

type Node = { id: string; url: string; site?: string | null; title?: string | null; degree?: number; indexed?: boolean; val?: number };
type Link = { source: string; target: string; relation?: string | null };

// Use dynamic import to avoid SSR issues; rely on ambient module typing.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false }) as unknown as React.ComponentType<{
  graphData: { nodes: Node[]; links: { source: string; target: string; relation?: string | null }[] };
  nodeLabel?: (n: Node) => string;
  nodeCanvasObjectMode?: () => "after" | "before" | undefined;
  nodeCanvasObject?: (node: Node & { x?: number; y?: number }, ctx: CanvasRenderingContext2D, scale: number) => void;
  linkCanvasObject?: (
    link: { source: { x?: number; y?: number }; target: { x?: number; y?: number }; relation?: string | null },
    ctx: CanvasRenderingContext2D,
    scale: number
  ) => void;
  linkDirectionalParticles?: number;
  linkDirectionalParticleSpeed?: number;
  onNodeClick?: (n: Node) => void;
  nodeColor?: string | ((n: Node) => string);
  nodeRelSize?: number;
}>;

export function GraphCanvas(props: {
  nodes: Node[];
  links: Link[];
  onNodeClick?: (node: Node) => void;
}) {
  const { nodes, links, onNodeClick } = props;

  const graphData = useMemo(() => {
    return {
      nodes: nodes.map((n) => ({ ...n })),
      links: links.map((e) => ({ source: e.source, target: e.target, relation: e.relation })),
    };
  }, [nodes, links]);

  return (
    <div className="h-[480px] w-full rounded-md border">
      <ForceGraph2D
        graphData={graphData}
        nodeLabel={(n) => n.title || n.url}
        nodeCanvasObjectMode={() => "after"}
        nodeCanvasObject={(node, ctx, scale) => {
          const label = (node.title || node.site || node.url || "").slice(0, 64);
          const fontSize = 12 / Math.sqrt(scale);
          ctx.font = `${fontSize}px sans-serif`;
          ctx.fillStyle = "#111827"; // gray-900
          const nx = typeof node.x === "number" ? node.x : 0;
          const ny = typeof node.y === "number" ? node.y : 0;
          ctx.fillText(label, nx + 8 / scale, ny + 4 / scale);
        }}
        linkCanvasObject={(link, ctx, scale) => {
          if (!link.relation) return;
          const sx = typeof link.source?.x === "number" ? link.source.x : 0;
          const sy = typeof link.source?.y === "number" ? link.source.y : 0;
          const tx = typeof link.target?.x === "number" ? link.target.x : 0;
          const ty = typeof link.target?.y === "number" ? link.target.y : 0;
          const mx = (sx + tx) / 2;
          const my = (sy + ty) / 2;
          const fontSize = 10 / Math.sqrt(scale);
          ctx.font = `${fontSize}px sans-serif`;
          ctx.fillStyle = "#6B7280"; // gray-500
          const text = String(link.relation);
          ctx.fillText(text, mx, my);
        }}
        linkDirectionalParticles={1}
        linkDirectionalParticleSpeed={0.003}
        onNodeClick={(n) => {
          if (onNodeClick) onNodeClick(n);
        }}
        // color indexed nodes green, others gray
        nodeColor={(n) => (n.indexed ? "#22c55e" /* green-500 */ : "#9CA3AF" /* gray-400 */)}
        // slightly larger nodes to improve visibility
        nodeRelSize={6}
      />
    </div>
  );
}

export default GraphCanvas;
