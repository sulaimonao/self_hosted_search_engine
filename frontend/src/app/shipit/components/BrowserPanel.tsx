"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { safeLocalStorage } from "@/utils/isomorphicStorage";
import {
  Download,
  Globe,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Star,
  Square,
  Trash2,
  X,
} from "lucide-react";

import {
  fetchShadowDomainPolicy,
  fetchShadowGlobalPolicy,
  fetchSeeds,
  requestShadowSnapshot,
  saveSeed,
  updateShadowDomainPolicy,
} from "@/lib/api";
import type {
  CrawlScope,
  ShadowArtifact,
  ShadowPolicy,
  ShadowPolicyResponse,
  ShadowSnapshotDocument,
  ShadowSnapshotResponse,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { useApp } from "@/app/shipit/store/useApp";

const TABS_STORAGE_KEY = "researcher:tabs:v1";
const HISTORY_STORAGE_KEY = "researcher:history:v1";
const BOOKMARKS_STORAGE_KEY = "researcher:bookmarks:v1";
const SESSION_STORAGE_KEY = "researcher:session";
const ALLOWED_SCOPE: CrawlScope = "allowed-list";

interface HistoryEntry {
  id: string;
  url: string;
  title: string;
  timestamp: string;
}

interface BookmarkEntry {
  id: string;
  url: string;
  title: string;
  folder: string;
  tags: string[];
  createdAt: string;
}

interface BrowserTab {
  id: string;
  title: string;
  url: string;
  status: "idle" | "loading" | "error";
  history: string[];
  historyIndex: number;
  shadowEnabled: boolean;
  downloads: ShadowArtifact[];
  snapshots: ShadowSnapshotDocument[];
  lastSnapshot: ShadowSnapshotResponse | null;
  errorMessage?: string | null;
  policy?: ShadowPolicyResponse;
}

const INITIAL_URL = "https://news.ycombinator.com";

function extractDomain(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.hostname.toLowerCase();
  } catch {
    return null;
  }
}

function normalizeUrl(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return INITIAL_URL;
  try {
    const candidate = new URL(trimmed);
    return candidate.toString();
  } catch {
    return `https://${trimmed}`;
  }
}

function createId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function loadSessionId(): string {
  if (typeof window === "undefined") {
    return createId();
  }
  const existing = safeLocalStorage.get(SESSION_STORAGE_KEY);
  if (existing && existing.trim()) {
    return existing.trim();
  }
  const created = createId();
  safeLocalStorage.set(SESSION_STORAGE_KEY, created);
  return created;
}

export default function BrowserPanel(): JSX.Element {
  const { shadow: globalShadowDefault } = useApp();
  const { toast } = useToast();
  const sessionIdRef = useRef<string>("");
  const [tabs, setTabs] = useState<BrowserTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string>("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [bookmarks, setBookmarks] = useState<BookmarkEntry[]>([]);
  const [globalPolicy, setGlobalPolicy] = useState<ShadowPolicy | null>(null);
  const [downloadsOpen, setDownloadsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [bookmarksOpen, setBookmarksOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [historyFilter, setHistoryFilter] = useState("");
  const [historyRange, setHistoryRange] = useState("all");
  const [supportsWebview, setSupportsWebview] = useState(false);
  const webviewRefs = useRef<Record<string, ElectronWebviewElement | null>>({});
  const webviewRefCallbacks = useRef<Record<string, (node: ElectronWebviewElement | null) => void>>({});
  const attachWebview = useCallback((tabId: string, node: ElectronWebviewElement | null) => {
    webviewRefs.current[tabId] = node;
  }, []);
  const getWebviewRef = useCallback(
    (tabId: string) => {
      if (!webviewRefCallbacks.current[tabId]) {
        webviewRefCallbacks.current[tabId] = (node: ElectronWebviewElement | null) => {
          attachWebview(tabId, node);
        };
      }
      return webviewRefCallbacks.current[tabId];
    },
    [attachWebview],
  );

  const activeTab = useMemo(() => tabs.find((tab) => tab.id === activeTabId) ?? null, [tabs, activeTabId]);

  useEffect(() => {
    sessionIdRef.current = loadSessionId();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const ua = window.navigator?.userAgent ?? "";
    setSupportsWebview(/Electron/i.test(ua) || Boolean(window.appBridge?.supportsWebview));
  }, []);

  useEffect(() => {
    try {
      const stored = safeLocalStorage.get(TABS_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as BrowserTab[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setTabs(parsed.map((tab) => ({ ...tab, status: "idle" })));
          setActiveTabId(parsed[0].id);
        }
      }
    } catch {
      setTabs([]);
    }
    try {
      const storedHistory = safeLocalStorage.get(HISTORY_STORAGE_KEY);
      if (storedHistory) {
        const parsed = JSON.parse(storedHistory) as HistoryEntry[];
        if (Array.isArray(parsed)) {
          setHistory(parsed);
        }
      }
    } catch {
      setHistory([]);
    }
    try {
      const storedBookmarks = safeLocalStorage.get(BOOKMARKS_STORAGE_KEY);
      if (storedBookmarks) {
        const parsed = JSON.parse(storedBookmarks) as BookmarkEntry[];
        if (Array.isArray(parsed)) {
          setBookmarks(parsed);
        }
      }
    } catch {
      setBookmarks([]);
    }
  }, []);

  useEffect(() => {
  safeLocalStorage.set(TABS_STORAGE_KEY, JSON.stringify(tabs));
  }, [tabs]);

  useEffect(() => {
    const activeIds = new Set(tabs.map((tab) => tab.id));
    for (const key of Object.keys(webviewRefCallbacks.current)) {
      if (!activeIds.has(key)) {
        delete webviewRefCallbacks.current[key];
      }
    }
  }, [tabs]);

  useEffect(() => {
  safeLocalStorage.set(HISTORY_STORAGE_KEY, JSON.stringify(history));
  }, [history]);

  useEffect(() => {
  safeLocalStorage.set(BOOKMARKS_STORAGE_KEY, JSON.stringify(bookmarks));
  }, [bookmarks]);

  useEffect(() => {
    fetchShadowGlobalPolicy()
      .then((policy) => setGlobalPolicy(policy))
      .catch((error) => {
        console.warn("Unable to load shadow policy", error);
      });
  }, []);

  // prevent repeated bootstrap writes by tracking if we've already created the initial tab
  const bootstrappedRef = useRef(false);

  // We intentionally exclude `tabs` to avoid a self-triggering bootstrap loop.
  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (bootstrappedRef.current) return;
    if (tabs.length === 0) {
      bootstrappedRef.current = true;
      const tabId = createId();
      const initialTab: BrowserTab = {
        id: tabId,
        title: "New Tab",
        url: INITIAL_URL,
        status: "idle",
        history: [INITIAL_URL],
        historyIndex: 0,
        shadowEnabled: globalShadowDefault,
        downloads: [],
        snapshots: [],
        lastSnapshot: null,
      };
      setTabs([initialTab]);
      setActiveTabId(tabId);
    }
    // intentionally do not include `tabs` in deps to avoid self-trigger; rely on the ref
  }, [globalShadowDefault, setTabs]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const setTabState = useCallback(
    (tabId: string, updater: (tab: BrowserTab) => BrowserTab) => {
      setTabs((prev) => prev.map((tab) => (tab.id === tabId ? updater(tab) : tab)));
    },
    [],
  );

  const addTab = useCallback(() => {
    const tabId = createId();
    const newTab: BrowserTab = {
      id: tabId,
      title: "New Tab",
      url: INITIAL_URL,
      status: "idle",
      history: [INITIAL_URL],
      historyIndex: 0,
      shadowEnabled: Boolean(globalPolicy?.enabled ?? globalShadowDefault),
      downloads: [],
      snapshots: [],
      lastSnapshot: null,
    };
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(tabId);
  }, [globalPolicy, globalShadowDefault]);

  const closeTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => prev.filter((tab) => tab.id !== tabId));
      setHistory((prev) => prev);
      if (activeTabId === tabId) {
        const remaining = tabs.filter((tab) => tab.id !== tabId);
        setActiveTabId(remaining[0]?.id ?? "");
      }
    },
    [activeTabId, tabs],
  );

  const persistHistory = useCallback(
    (entry: HistoryEntry) => {
    setHistory((prev) => [entry, ...prev].slice(0, 500));
    },
    [],
  );

  const handleSnapshotSuccess = useCallback((tabId: string, snapshot: ShadowSnapshotResponse) => {
    setTabState(tabId, (tab) => ({
      ...tab,
      status: "idle",
      title: snapshot.document.canonical_url ?? snapshot.document.url ?? tab.title,
      downloads: [...snapshot.artifacts, ...tab.downloads],
      snapshots: [snapshot.document, ...tab.snapshots],
      lastSnapshot: snapshot,
      errorMessage: null,
    }));
  }, [setTabState]);

  const handleSnapshotError = useCallback((tabId: string, error: unknown) => {
    const message = error instanceof Error ? error.message : String(error ?? "Snapshot failed");
    setTabState(tabId, (tab) => ({
      ...tab,
      status: "error",
      errorMessage: message,
    }));
    toast({
      title: "Shadow capture failed",
      description: message,
      variant: "destructive",
    });
  }, [setTabState, toast]);

  const ensureDomainPolicy = useCallback(async (domain: string, enabled: boolean) => {
    if (!domain) return undefined;
    try {
      const current = await fetchShadowDomainPolicy(domain);
      if (enabled && !current.policy.enabled) {
        return updateShadowDomainPolicy(domain, { enabled: true });
      }
      if (!enabled && current.policy.enabled) {
        return updateShadowDomainPolicy(domain, { enabled: false });
      }
      return current;
    } catch (error) {
      console.warn("Unable to sync domain policy", error);
      return undefined;
    }
  }, []);

  const navigateTo = useCallback(
    async (
      tabId: string,
      urlInput: string,
      options?: { replace?: boolean; shadowEnabled?: boolean },
    ) => {
      const url = normalizeUrl(urlInput);
      const domain = extractDomain(url);
      const shadowActive = Boolean(options?.shadowEnabled);
      setTabState(tabId, (tab) => ({
        ...tab,
        status: "loading",
        url,
        history: options?.replace
          ? [...tab.history.slice(0, tab.historyIndex), url]
          : [...tab.history.slice(0, tab.historyIndex + 1), url],
        historyIndex: options?.replace ? tab.historyIndex : tab.historyIndex + 1,
        errorMessage: null,
      }));

      if (domain) {
        const policy = await ensureDomainPolicy(domain, shadowActive);
        if (policy) {
          setTabState(tabId, (tab) => ({ ...tab, policy }));
        }
      }

      try {
        const snapshot = await requestShadowSnapshot({
          url,
          tabId,
          sessionId: sessionIdRef.current,
          policyId: domain ? `domain:${domain}` : undefined,
          renderJs: shadowActive,
        });
        handleSnapshotSuccess(tabId, snapshot);
        persistHistory({
          id: createId(),
          url: snapshot.document.url,
          title: snapshot.document.canonical_url ?? snapshot.document.url,
          timestamp: snapshot.document.observed_at,
        });
      } catch (error) {
        handleSnapshotError(tabId, error);
      }
    },
    [ensureDomainPolicy, handleSnapshotError, handleSnapshotSuccess, persistHistory, setTabState],
  );

  const goBack = useCallback(
    (tab: BrowserTab) => {
      if (tab.historyIndex <= 0) return;
      const previousUrl = tab.history[tab.historyIndex - 1];
      setTabState(tab.id, (current) => ({
        ...current,
        historyIndex: Math.max(0, current.historyIndex - 1),
        url: previousUrl,
      }));
      void navigateTo(tab.id, previousUrl, { replace: true, shadowEnabled: tab.shadowEnabled });
      webviewRefs.current[tab.id]?.goBack?.();
    },
    [navigateTo, setTabState],
  );

  const goForward = useCallback(
    (tab: BrowserTab) => {
      if (tab.historyIndex >= tab.history.length - 1) return;
      const nextUrl = tab.history[tab.historyIndex + 1];
      setTabState(tab.id, (current) => ({
        ...current,
        historyIndex: Math.min(current.history.length - 1, current.historyIndex + 1),
        url: nextUrl,
      }));
      void navigateTo(tab.id, nextUrl, { replace: true, shadowEnabled: tab.shadowEnabled });
      webviewRefs.current[tab.id]?.goForward?.();
    },
    [navigateTo, setTabState],
  );

  const refreshTab = useCallback(
    (tab: BrowserTab) => {
      void navigateTo(tab.id, tab.url, { replace: true, shadowEnabled: tab.shadowEnabled });
      webviewRefs.current[tab.id]?.reload?.();
    },
    [navigateTo],
  );

  const toggleTabShadow = useCallback(
    async (tab: BrowserTab, value: boolean) => {
      const domain = extractDomain(tab.url);
      setTabState(tab.id, (current) => ({ ...current, shadowEnabled: value }));
      if (domain) {
        try {
          const policy = await updateShadowDomainPolicy(domain, { enabled: value });
          setTabState(tab.id, (current) => ({ ...current, policy }));
        } catch (error) {
          console.warn("Unable to update domain policy", error);
        }
      }
    },
    [setTabState],
  );

  const activeHistory = useMemo(() => {
    if (!activeTab) return [];
    return activeTab.history.map((url, index) => ({
      id: `${activeTab.id}:${index}`,
      url,
      active: index === activeTab.historyIndex,
    }));
  }, [activeTab]);

  const addBookmark = useCallback(() => {
    if (!activeTab?.lastSnapshot) return;
    const defaultFolder = "General";
    const folderInput = typeof window !== "undefined" ? window.prompt("Folder", defaultFolder) : defaultFolder;
    const tagsInput = typeof window !== "undefined" ? window.prompt("Tags (comma separated)", "") : "";
    const folder = folderInput && folderInput.trim() ? folderInput.trim() : defaultFolder;
    const tags = (tagsInput ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0);
    const entry: BookmarkEntry = {
      id: createId(),
      url: activeTab.lastSnapshot.document.url,
      title: activeTab.lastSnapshot.document.canonical_url ?? activeTab.lastSnapshot.document.url,
      folder,
      tags,
      createdAt: new Date().toISOString(),
    };
    setBookmarks((prev) => [entry, ...prev]);
    toast({ title: "Saved bookmark", description: entry.title });
  }, [activeTab, toast]);

  const pushBookmarkToSeeds = useCallback(async (bookmark: BookmarkEntry) => {
    try {
      const registry = await fetchSeeds();
      await saveSeed({
        action: "create",
        revision: registry.revision,
        seed: {
          url: bookmark.url,
          scope: ALLOWED_SCOPE,
          notes: bookmark.title,
        },
      });
      toast({
        title: "Collection updated",
        description: "Bookmark sent to allowed-list seeds.",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error ?? "Unable to save seed");
      toast({ title: "Seed update failed", description: message, variant: "destructive" });
    }
  }, [toast]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={addTab}>
          <Plus className="h-4 w-4" />
        </Button>
        <Tabs value={activeTabId} onValueChange={(value) => setActiveTabId(value)} className="flex-1">
          <TabsList className="justify-start overflow-x-auto">
            {tabs.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id} className="flex items-center gap-2">
                <span className="text-xs">{tab.shadowEnabled ? "●" : "○"}</span>
                <Globe className="h-4 w-4" />
                <span className="max-w-[160px] truncate text-sm">{tab.title || tab.url}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  onClick={(event) => {
                    event.stopPropagation();
                    closeTab(tab.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((tab) => (
            <TabsContent key={tab.id} value={tab.id} className="border rounded-lg p-4">
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="icon" onClick={() => goBack(tab)} disabled={tab.historyIndex <= 0}>
                    <History className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => goForward(tab)}
                    disabled={tab.historyIndex >= tab.history.length - 1}
                  >
                    <Search className="h-4 w-4 rotate-180" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => refreshTab(tab)}>
                    <RefreshCw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setTabState(tab.id, (current) => ({ ...current, status: "idle" }))}
                  >
                    <Square className="h-4 w-4" />
                  </Button>
                  <Input
                    className="flex-1"
                    defaultValue={tab.url}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        const value = (event.target as HTMLInputElement).value;
                        void navigateTo(tab.id, value, { shadowEnabled: tab.shadowEnabled });
                      }
                    }}
                  />
                  <Button
                    variant="outline"
                    onClick={() => setDownloadsOpen(true)}
                    className="flex items-center gap-2"
                  >
                    <Download className="h-4 w-4" />
                    Downloads ({tab.downloads.length})
                  </Button>
                  <Button variant="outline" onClick={() => setHistoryOpen(true)}>
                    <History className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" onClick={() => setBookmarksOpen(true)}>
                    <Star className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" onClick={addBookmark}>
                    Save
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={tab.shadowEnabled}
                      onCheckedChange={(value) => toggleTabShadow(tab, value)}
                    />
                    <span className="text-sm">Shadow per tab</span>
                    {tab.policy ? (
                      <Badge variant={tab.policy.policy.enabled ? "default" : "secondary"}>
                        {tab.policy.inherited ? "Inherited" : "Override"}
                      </Badge>
                    ) : null}
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setInfoOpen(true)}>
                    <Settings2 className="h-4 w-4" /> Page info
                  </Button>
                  {tab.status === "loading" ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" /> Capturing snapshot…
                    </div>
                  ) : null}
                  {tab.status === "error" && tab.errorMessage ? (
                    <span className="text-sm text-destructive">{tab.errorMessage}</span>
                  ) : null}
                </div>
                {supportsWebview ? (
                  <webview
                    ref={getWebviewRef(tab.id)}
                    src={tab.url}
                    title={tab.title}
                    className="h-[520px] w-full rounded-md border"
                    partition="persist:main"
                    allowpopups
                  />
                ) : (
                  <div className="flex h-[520px] w-full items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                    Browser preview is available in the desktop app.
                  </div>
                )}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </div>

      <Sheet open={downloadsOpen} onOpenChange={setDownloadsOpen}>
        <SheetContent side="right" className="w-[420px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Downloads & Artifacts</SheetTitle>
            <SheetDescription>Captured files from recent shadow snapshots.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-3">
            {activeTab?.downloads.length ? (
              activeTab.downloads.map((artifact, index) => (
                <div key={`${artifact.kind}-${index}`} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium capitalize">{artifact.kind}</span>
                    <span className="text-xs text-muted-foreground">{artifact.bytes ?? 0} bytes</span>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">{artifact.path ?? artifact.local_path ?? ""}</div>
                  <div className="mt-2 flex items-center gap-2">
                    {artifact.download_url ? (
                      <Button asChild size="sm" variant="outline">
                        <a href={artifact.download_url}>Download</a>
                      </Button>
                    ) : null}
                    {artifact.local_path ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (typeof window !== "undefined" && window.omni?.openPath) {
                            window.omni.openPath(artifact.local_path);
                          }
                        }}
                      >
                        Open in Finder
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No artifacts captured yet.</p>
            )}
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" className="w-[360px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>History</SheetTitle>
            <SheetDescription>Per-tab and global navigation history.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-4">
            <div>
              <h3 className="text-sm font-semibold">Current tab</h3>
              <div className="mt-2 space-y-2">
                {activeHistory.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className={`block w-full truncate rounded-md border px-3 py-2 text-left text-sm hover:bg-muted ${entry.active ? "bg-muted" : ""}`}
                    onClick={() => {
                      if (activeTab) {
                        void navigateTo(activeTab.id, entry.url, {
                          replace: true,
                          shadowEnabled: activeTab.shadowEnabled,
                        });
                      }
                    }}
                  >
                    {entry.url}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold">Recent</h3>
              <Input
                className="mt-2"
                placeholder="Filter by domain or keyword"
                value={historyFilter}
                onChange={(event) => setHistoryFilter(event.target.value)}
              />
              <select
                className="mt-2 w-full rounded-md border px-2 py-1 text-sm"
                value={historyRange}
                onChange={(event) => setHistoryRange(event.target.value)}
              >
                <option value="all">All time</option>
                <option value="24h">Last 24 hours</option>
                <option value="7d">Last 7 days</option>
              </select>
              <div className="mt-2 space-y-2">
                {history
                  .filter((item) => {
                    if (!historyFilter.trim()) return true;
                    const value = historyFilter.trim().toLowerCase();
                    return (
                      item.url.toLowerCase().includes(value) ||
                      item.title.toLowerCase().includes(value)
                    );
                  })
                  .filter((item) => {
                    if (historyRange === "all") return true;
                    const timestamp = new Date(item.timestamp);
                    if (Number.isNaN(timestamp.getTime())) {
                      return true;
                    }
                    const now = Date.now();
                    if (historyRange === "24h") {
                      return now - timestamp.getTime() <= 24 * 60 * 60 * 1000;
                    }
                    if (historyRange === "7d") {
                      return now - timestamp.getTime() <= 7 * 24 * 60 * 60 * 1000;
                    }
                    return true;
                  })
                  .map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="block w-full truncate rounded-md border px-3 py-2 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      if (activeTab) {
                        void navigateTo(activeTab.id, item.url, { shadowEnabled: activeTab.shadowEnabled });
                      }
                    }}
                  >
                    <div className="font-medium">{item.title}</div>
                    <div className="text-xs text-muted-foreground">{item.url}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={bookmarksOpen} onOpenChange={setBookmarksOpen}>
        <SheetContent side="right" className="w-[360px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Bookmarks</SheetTitle>
            <SheetDescription>Your saved researcher pages.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-2">
            {bookmarks.map((bookmark) => (
              <div key={bookmark.id} className="rounded-md border p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{bookmark.title}</span>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setBookmarks((prev) => prev.filter((item) => item.id !== bookmark.id))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{bookmark.url}</div>
                <div className="mt-2 flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (activeTab) {
                        void navigateTo(activeTab.id, bookmark.url, {
                          shadowEnabled: activeTab.shadowEnabled,
                        });
                      }
                    }}
                  >
                    Open
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void pushBookmarkToSeeds(bookmark)}>
                    Add to seeds
                  </Button>
                  <Badge variant="secondary">{bookmark.folder}</Badge>
                  {bookmark.tags.map((tag) => (
                    <Badge key={tag} variant="outline">
                      #{tag}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
            {bookmarks.length === 0 ? (
              <p className="text-sm text-muted-foreground">No bookmarks yet.</p>
            ) : null}
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent side="bottom" className="h-[320px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Page info</SheetTitle>
            <SheetDescription>Metadata from the most recent snapshot.</SheetDescription>
          </SheetHeader>
          <div className="mt-4 space-y-3 text-sm">
            {activeTab?.lastSnapshot ? (
              <>
                <div>
                  <span className="font-medium">Document ID:</span> {activeTab.lastSnapshot.document.id}
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">Canonical URL:</span>
                  <span>{activeTab.lastSnapshot.document.canonical_url}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const canonical = activeTab.lastSnapshot?.document.canonical_url;
                      if (canonical) {
                        void navigator.clipboard.writeText(canonical);
                        toast({ title: "Copied", description: "Canonical URL copied to clipboard." });
                      }
                    }}
                  >
                    Copy
                  </Button>
                </div>
                <div>
                  <span className="font-medium">Observed:</span> {activeTab.lastSnapshot.document.observed_at}
                </div>
                <div>
                  <span className="font-medium">Robots:</span>{" "}
                  {activeTab.lastSnapshot.policy.obey_robots ? "Respected" : "Ignored"}
                </div>
                <div>
                  <span className="font-medium">RAG indexed:</span>{" "}
                  {activeTab.lastSnapshot.rag_indexed ? "Yes" : "No"}
                </div>
                <div>
                  <span className="font-medium">Training staged:</span>{" "}
                  {activeTab.lastSnapshot.training_record ? "Yes" : "No"}
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">No snapshot captured yet.</p>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
