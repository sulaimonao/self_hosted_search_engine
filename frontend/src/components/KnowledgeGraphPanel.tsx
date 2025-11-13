"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface GraphNode {
  id: string;
  url: string;
  site: string | null;
  title: string | null;
  first_seen: string | null;
  last_seen: string | null;
  topics: string[];
  degree?: number;
}

interface GraphEdge {
  src_url: string;
  dst_url: string;
  relation: string | null;
}

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

  useEffect(() => {
    loadGraphSummary();
  }, []);

  useEffect(() => {
    if (selectedSite) {
      loadGraphData(selectedSite);
    }
  }, [selectedSite]);

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

  async function loadGraphData(site: string) {
    try {
      setLoading(true);
      const [nodesResponse, edgesResponse] = await Promise.all([
        fetch(api(`/api/browser/graph/nodes?site=${encodeURIComponent(site)}&limit=100`)),
        fetch(api(`/api/browser/graph/edges?site=${encodeURIComponent(site)}&limit=200`)),
      ]);

      if (!nodesResponse.ok || !edgesResponse.ok) {
        throw new Error("Failed to load graph data");
      }

      const nodesData = await nodesResponse.json();
      const edgesData = await edgesResponse.json();

      setNodes(nodesData.nodes || []);
      setEdges(edgesData.edges || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

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

      {summary && summary.top_sites.length > 0 && (
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
      )}

      {selectedSite && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-medium">Pages for {selectedSite}</h3>
            <button
              onClick={() => setSelectedSite(null)}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Clear selection
            </button>
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
            </div>
          ) : (
            <div className="p-4 text-center text-gray-500 text-sm">
              No pages found for this site
            </div>
          )}
        </div>
      )}
    </div>
  );
}
