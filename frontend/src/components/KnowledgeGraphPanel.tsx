"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import dynamic from "next/dynamic";
import { useBrowserNavigation } from "@/hooks/useBrowserNavigation";

interface GraphNode {
  id: string;
  url: string;
  site: string | null;
  title: string | null;
  first_seen: string | null;
  last_seen: string | null;
  topics: string[];
  degree?: number;
  indexed?: boolean;
  val?: number;
}

interface GraphEdge {
  src_url: string;
  dst_url: string;
  relation: string | null;
}

interface SiteNode {
  id: string;
  site: string;
  pages: number;
  degree: number;
  fresh_7d: number;
  last_seen: string | null;
}

type RawSiteEdge = { src_site: string; dst_site: string; weight?: number | null };

interface GraphSummary {
  pages: number;
  sites: number;
  fresh_7d: number;
  connections?: number;
  sample?: Array<{ url: string; title: string | null; site: string | null; last_seen: string | null }>;
  top_sites: Array<{ site: string; degree: number }>;
}

export function KnowledgeGraphPanel() {
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSite, setSelectedSite] = useState<string | null>(null);
  const [globalView, setGlobalView] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<"pages" | "sites">("pages");
  const [minDegree, setMinDegree] = useState<number>(0);
  const [category, setCategory] = useState<string>("");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [indexedOnly, setIndexedOnly] = useState<boolean>(false);
  const [limit, setLimit] = useState<number>(200);
  const [minWeight, setMinWeight] = useState<number>(1);

  const loadGraphData = useCallback(async (site?: string | null) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (viewMode === "pages") {
        if (site && !globalView) params.set("site", site);
        if (minDegree > 0) params.set("min_degree", String(minDegree));
        if (category.trim()) params.set("category", category.trim());
        if (fromDate) params.set("from", new Date(fromDate).toISOString());
        if (toDate) params.set("to", new Date(toDate).toISOString());
        if (indexedOnly) params.set("indexed", "1");
        params.set("limit", String(Math.max(1, Math.min(limit, 1000))));
      } else {
        if (minDegree > 0) params.set("min_degree", String(minDegree));
        if (fromDate) params.set("from", new Date(fromDate).toISOString());
        if (toDate) params.set("to", new Date(toDate).toISOString());
        if (minWeight > 1) params.set("min_weight", String(minWeight));
        params.set("limit", String(Math.max(1, Math.min(limit, 1000))));
      }

      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(
          api(
            viewMode === "pages"
              ? `/api/browser/graph/nodes?${params.toString()}`
              : `/api/browser/graph/sites?${params.toString()}`
          )
        ),
        fetch(
          api(
            viewMode === "pages"
              ? `/api/browser/graph/edges?${params.toString()}`
              : `/api/browser/graph/site_edges?${params.toString()}`
          )
        ),
      ]);

      if (!nodesResponse.ok || !edgesResponse.ok) {
        throw new Error("Failed to load graph data");
      }

      const nodesData = await nodesResponse.json();
      const edgesData = await edgesResponse.json();

      if (viewMode === "pages") {
        const rawNodes = Array.isArray(nodesData.nodes) ? (nodesData.nodes as GraphNode[]) : [];
        const normalizedNodes = rawNodes.map((node, index) => {
          const url = typeof node.url === "string" ? node.url.trim() : "";
          const fallbackId = node.id ? String(node.id) : `node-${index}`;
          return { ...node, id: url || fallbackId };
        });
        const nodeIds = new Set(normalizedNodes.map((node) => node.id).filter(Boolean));
        const normalizedEdges: GraphEdge[] = (Array.isArray(edgesData.edges) ? (edgesData.edges as GraphEdge[]) : [])
          .map((edge) => ({
            ...edge,
            src_url: typeof edge.src_url === "string" ? edge.src_url.trim() : "",
            dst_url: typeof edge.dst_url === "string" ? edge.dst_url.trim() : "",
          }))
          .filter((edge) => edge.src_url && edge.dst_url && nodeIds.has(edge.src_url) && nodeIds.has(edge.dst_url));
        setNodes(normalizedNodes);
        setEdges(normalizedEdges);
      } else {
        const siteNodes: GraphNode[] = ((nodesData.nodes as SiteNode[]) || []).map((n) => ({
          id: n.id,
          url: n.site,
          site: n.site,
          title: `${n.site} (${n.pages} pages)` ,
          first_seen: null,
          last_seen: n.last_seen,
          topics: [],
          degree: n.degree,
          indexed: true,
          val: Math.max(1, Math.min(12, Math.floor(Math.log2(n.pages + 1) + n.degree / 50))),
        }));

        const nodeIds = new Set(siteNodes.map((node) => node.id));
        const siteEdges: GraphEdge[] = ((edgesData.edges as RawSiteEdge[]) || [])
          .map((e) => ({
            src_url: e.src_site,
            dst_url: e.dst_site,
            relation: e.weight != null ? String(e.weight) : null,
          }))
          .filter((edge) => edge.src_url && edge.dst_url && nodeIds.has(edge.src_url) && nodeIds.has(edge.dst_url));

        setNodes(siteNodes);
        setEdges(siteEdges);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [globalView, minDegree, category, fromDate, toDate, indexedOnly, limit, viewMode, minWeight]);

  useEffect(() => {
    loadGraphSummary();
  }, []);

  useEffect(() => {
    if (!globalView && !selectedSite && viewMode === "pages") {
      loadGraphData(null);
    }
  }, [globalView, selectedSite, viewMode, loadGraphData]);

  async function loadGraphSummary() {
    try {
      setLoading(true);
      const response = await fetch(api("/api/browser/graph/summary"));
      if (!response.ok) {
        throw new Error(`Failed to load graph summary: ${response.statusText}`);
      }
      const data = await response.json();
      setSummary(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  // load when a site is selected or when toggling to global view
  useEffect(() => {
    if (selectedSite || globalView) {
      loadGraphData(selectedSite);
    }
  }, [selectedSite, globalView, loadGraphData]);

  // load when switching to Sites overview so something shows immediately
  useEffect(() => {
    if (viewMode === "sites") {
      loadGraphData(null);
    }
  }, [viewMode, loadGraphData]);

  const GraphCanvas = dynamic(() => import("@/components/GraphCanvas"), { ssr: false });
  const navigate = useBrowserNavigation();
  const handleNodeClick = useCallback((node: GraphNode) => {
    if (!node?.url) return;
    navigate(node.url, { newTab: false });
  }, [navigate]);

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-accent border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-border-subtle bg-app-card-subtle p-4">
        <p className="text-sm text-state-danger">Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 text-fg">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Knowledge Graph</h2>
        {/* Controls */}
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">View</label>
            <select
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value as "pages" | "sites")}
              className="rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <option value="pages">Pages</option>
              <option value="sites">Sites (overview)</option>
            </select>
          </div>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={globalView}
              onChange={(e) => {
                setGlobalView(e.target.checked);
                if (e.target.checked) {
                  // clear selected site and load
                  setSelectedSite(null);
                }
              }}
            />
            Global view
          </label>
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">Min degree</label>
            <input
              type="number"
              min={0}
              value={minDegree}
              onChange={(e) => setMinDegree(Number(e.target.value) || 0)}
              className="w-28 rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">Category</label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="topic tag"
              className="w-40 rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">From</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">To</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>
          {viewMode === "pages" && (
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={indexedOnly}
                onChange={(e) => setIndexedOnly(e.target.checked)}
              />
              Indexed only
            </label>
          )}
          {viewMode === "sites" && (
            <div className="flex flex-col">
              <label className="text-xs text-fg-muted">Min weight</label>
              <input
                type="number"
                min={1}
                max={10000}
                value={minWeight}
                onChange={(e) => setMinWeight(Math.max(1, Number(e.target.value) || 1))}
                className="w-28 rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              />
            </div>
          )}
          <div className="flex flex-col">
            <label className="text-xs text-fg-muted">Limit</label>
            <input
              type="number"
              min={10}
              max={1000}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 200)}
              className="w-24 rounded-xs border border-border-subtle bg-app-input px-2 py-1 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            />
          </div>
          <button
            onClick={() => loadGraphData(selectedSite)}
            className="ml-auto rounded-md border border-transparent bg-accent px-4 py-1.5 text-sm font-medium text-fg-on-accent transition hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Apply
          </button>
        </div>

        {summary && (
          <div className="grid grid-cols-2 gap-4 rounded-xl border border-border-subtle bg-app-card-subtle p-4 md:grid-cols-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-accent">{summary.pages}</div>
              <div className="text-sm text-fg-muted">Pages</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-state-success">{summary.sites}</div>
              <div className="text-sm text-fg-muted">Sites</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-accent">{summary.fresh_7d}</div>
              <div className="text-sm text-fg-muted">Fresh (7d)</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-state-info">{summary.connections ?? edges.length}</div>
              <div className="text-sm text-fg-muted">Connections</div>
            </div>
          </div>
        )}
        {summary?.sample?.length ? (
          <div className="rounded-xl border border-border-subtle bg-app-card-subtle p-4">
            <p className="mb-2 text-sm font-semibold text-foreground">Recent pages</p>
            <div className="grid gap-2 md:grid-cols-2">
              {summary.sample.map((page) => {
                const lastSeen = page.last_seen ? new Date(page.last_seen) : null;
                return (
                  <button
                    key={page.url}
                    onClick={() => navigate(page.url, { newTab: false })}
                    className="flex flex-col items-start rounded-md border border-border-subtle bg-background px-3 py-2 text-left text-sm hover:border-accent/70 hover:shadow-subtle"
                  >
                    <span className="truncate font-medium text-foreground">{page.title || page.url}</span>
                    <span className="truncate text-xs text-fg-muted">
                      {page.site || "unknown"} {lastSeen ? `· ${lastSeen.toLocaleString()}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      {viewMode === "pages" && summary?.top_sites?.length ? (
        <div className="space-y-2">
          <h3 className="text-lg font-medium">Top Sites</h3>
          <div className="space-y-2">
            {summary.top_sites.map((site) => (
              <button
                key={site.site}
                onClick={() => setSelectedSite(site.site)}
                className={`w-full rounded-lg border px-4 py-2 text-left text-sm font-medium transition ${
                  selectedSite === site.site
                    ? "border-accent bg-accent-soft text-fg"
                    : "border-border-subtle bg-app-card text-fg hover:bg-app-card-hover"
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">{site.site}</span>
                  <span className="text-xs text-fg-muted">{site.degree} connections</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {(viewMode === "sites" || selectedSite || globalView) && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-medium">
              {viewMode === "sites"
                ? "Sites overview"
                : globalView
                ? "Global Graph"
                : `Pages for ${selectedSite}`}
            </h3>
            {viewMode === "pages" && !globalView && (
              <button
                onClick={() => setSelectedSite(null)}
                className="text-sm text-accent hover:text-accent/80"
              >
                Clear selection
              </button>
            )}
          </div>
          
          {loading ? (
            <div className="flex items-center justify-center p-4">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            </div>
          ) : nodes.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {nodes.map((node) => (
                <div key={node.id} className="rounded-lg border border-border-subtle bg-app-card p-3 text-sm text-fg">
                  <div className="font-medium truncate">{node.title || "Untitled"}</div>
                  <div className="mt-1 truncate text-xs text-fg-muted">{node.url}</div>
                  {viewMode === "pages" && node.indexed !== undefined && (
                    <div className="mt-1 text-xs">
                      <span className={node.indexed ? "text-state-success" : "text-fg-muted"}>
                        {node.indexed ? "Indexed" : "Not indexed"}
                      </span>
                    </div>
                  )}
                  {node.topics && node.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {node.topics.map((topic, idx) => (
                        <span
                          key={idx}
                          className="rounded-full bg-accent-soft px-2 py-0.5 text-xs text-fg-on-accent"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div className="mt-4">
                <GraphCanvas
                  nodes={nodes.map((n) => ({ id: n.id, url: n.url, site: n.site, title: n.title, degree: n.degree, indexed: n.indexed, val: n.val }))}
                  links={edges.map((e) => ({ source: e.src_url, target: e.dst_url, relation: e.relation }))}
                  onNodeClick={handleNodeClick}
                />
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-border-subtle bg-app-card-subtle p-4 text-center text-sm text-fg-muted">
              {viewMode === "sites" ? "No sites found" : "No pages found for this site"}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="mt-2 text-xs text-fg-muted">
        {viewMode === "pages" ? (
          <div className="flex gap-4 items-center">
            <div className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-state-success" /> Indexed</div>
            <div className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full bg-fg-muted/40" /> Not indexed</div>
          </div>
        ) : (
          <div>Sites overview: node size ~ pages and degree; link labels show cross-site link weight</div>
        )}
      </div>
    </div>
  );
}
