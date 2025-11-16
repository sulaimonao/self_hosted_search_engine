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
        setNodes(nodesData.nodes || []);
        setEdges(edgesData.edges || []);
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

        const siteEdges: GraphEdge[] = ((edgesData.edges as RawSiteEdge[]) || []).map((e) => ({
          src_url: e.src_site,
          dst_url: e.dst_site,
          relation: e.weight != null ? String(e.weight) : null,
        }));

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
        <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-800 text-sm">Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Knowledge Graph</h2>
        {/* Controls */}
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col">
            <label className="text-xs text-gray-600">View</label>
            <select
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value as "pages" | "sites")}
              className="border rounded px-2 py-1"
            >
              <option value="pages">Pages</option>
              <option value="sites">Sites (overview)</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
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
            <label className="text-xs text-gray-600">Min degree</label>
            <input
              type="number"
              min={0}
              value={minDegree}
              onChange={(e) => setMinDegree(Number(e.target.value) || 0)}
              className="border rounded px-2 py-1 w-28"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-600">Category</label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="topic tag"
              className="border rounded px-2 py-1 w-40"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-600">From</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </div>
          <div className="flex flex-col">
            <label className="text-xs text-gray-600">To</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </div>
          {viewMode === "pages" && (
            <label className="flex items-center gap-2 text-sm">
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
              <label className="text-xs text-gray-600">Min weight</label>
              <input
                type="number"
                min={1}
                max={10000}
                value={minWeight}
                onChange={(e) => setMinWeight(Math.max(1, Number(e.target.value) || 1))}
                className="border rounded px-2 py-1 w-28"
              />
            </div>
          )}
          <div className="flex flex-col">
            <label className="text-xs text-gray-600">Limit</label>
            <input
              type="number"
              min={10}
              max={1000}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 200)}
              className="border rounded px-2 py-1 w-24"
            />
          </div>
          <button
            onClick={() => loadGraphData(selectedSite)}
            className="ml-auto px-3 py-1.5 rounded bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            Apply
          </button>
        </div>
        
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{summary.pages}</div>
              <div className="text-sm text-gray-600">Pages</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{summary.sites}</div>
              <div className="text-sm text-gray-600">Sites</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">{summary.fresh_7d}</div>
              <div className="text-sm text-gray-600">Fresh (7d)</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">{edges.length}</div>
              <div className="text-sm text-gray-600">Connections</div>
            </div>
          </div>
        )}
      </div>

      {viewMode === "pages" && summary?.top_sites?.length ? (
        <div className="space-y-2">
          <h3 className="text-lg font-medium">Top Sites</h3>
          <div className="space-y-2">
            {summary.top_sites.map((site) => (
              <button
                key={site.site}
                onClick={() => setSelectedSite(site.site)}
                className={`w-full text-left px-4 py-2 rounded-lg border transition-colors ${
                  selectedSite === site.site
                    ? "bg-blue-50 border-blue-300"
                    : "bg-white border-gray-200 hover:bg-gray-50"
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="font-medium">{site.site}</span>
                  <span className="text-sm text-gray-500">{site.degree} connections</span>
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
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                Clear selection
              </button>
            )}
          </div>
          
          {loading ? (
            <div className="flex items-center justify-center p-4">
              <div className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : nodes.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {nodes.map((node) => (
                <div key={node.id} className="p-3 bg-white border border-gray-200 rounded-lg">
                  <div className="font-medium text-sm truncate">{node.title || "Untitled"}</div>
                  <div className="text-xs text-gray-500 truncate mt-1">{node.url}</div>
                  {viewMode === "pages" && node.indexed !== undefined && (
                    <div className="mt-1 text-xs">
                      <span className={node.indexed ? "text-green-600" : "text-gray-500"}>
                        {node.indexed ? "Indexed" : "Not indexed"}
                      </span>
                    </div>
                  )}
                  {node.topics && node.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {node.topics.map((topic, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded"
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
            <div className="p-4 text-center text-gray-500 text-sm">
              {viewMode === "sites" ? "No sites found" : "No pages found for this site"}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="mt-2 text-xs text-gray-600">
        {viewMode === "pages" ? (
          <div className="flex gap-4 items-center">
            <div className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full" style={{backgroundColor:'#22c55e'}} /> Indexed</div>
            <div className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full" style={{backgroundColor:'#9CA3AF'}} /> Not indexed</div>
          </div>
        ) : (
          <div>Sites overview: node size ~ pages and degree; link labels show cross-site link weight</div>
        )}
      </div>
    </div>
  );
}
