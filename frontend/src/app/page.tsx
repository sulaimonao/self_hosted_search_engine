<<<<<<< ours
<<<<<<< ours
import { WebPreview } from "@/components/web-preview";
import { ChatPanel } from "@/components/chat-panel";

export default function Home() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 h-screen bg-background">
      <div className="col-span-1">
        <WebPreview />
      </div>
      <div className="col-span-1 flex flex-col">
        <ChatPanel />
      </div>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, Compass, Database, ShieldCheck } from "lucide-react";
import { AgentLog } from "@/components/agent-log";
import { ChatPanel } from "@/components/chat-panel";
import { CommandPalette } from "@/components/command-palette";
import { CrawlManager, type PendingCrawl } from "@/components/crawl-manager";
import { JobStatus } from "@/components/job-status";
import { Omnibox } from "@/components/omnibox";
import { SettingsModels } from "@/components/settings-models";
import { WebPreview } from "@/components/web-preview";
import { Badge } from "@/components/ui/badge";
import {
  acknowledgeAction,
  fetchLlmStatus,
  listJobs,
  optimisticActionUpdate,
  queueCrawl,
  searchIndex,
  streamChat,
  streamJob,
  type AgentAction,
  type ChatMessage,
  type CrawlScope,
  type JobEvent,
  type JobSummary,
  type LlmStatusResponse,
} from "@/lib/api";
import { isProbablyUrl, toRelativeTime } from "@/lib/utils";

const defaultScope: CrawlScope = {
  maxPages: 10,
  maxDepth: 1,
  domains: [],
};

function createAssistantMessage(): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "",
    createdAt: new Date().toISOString(),
    streaming: true,
  };
}

export default function Home() {
  const [webUrl, setWebUrl] = useState<string>("https://example.com");
  const [omniboxValue, setOmniboxValue] = useState<string>("https://example.com");
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [logEvents, setLogEvents] = useState<JobEvent[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | undefined>();
  const [pendingCrawls, setPendingCrawls] = useState<PendingCrawl[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [llmStatus, setLlmStatus] = useState<LlmStatusResponse | undefined>();
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmError, setLlmError] = useState<string | undefined>();
  const jobStreams = useRef<Record<string, { close: () => void }>>({});

  const closeAllStreams = useCallback(() => {
    Object.values(jobStreams.current).forEach((source) => source.close());
  }, []);

  const sendChat = useCallback(async () => {
    const content = chatInput.trim();
    if (!content) return;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    const assistantMessage = createAssistantMessage();

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setChatInput("");
    setStreaming(true);

    try {
      for await (const chunk of streamChat({ message: content, context: { url: webUrl } })) {
        if (chunk.token !== undefined) {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessage.id
                ? {
                    ...message,
                    content: `${message.content}${chunk.token ?? ""}`,
                    streaming: !chunk.done,
                  }
                : message,
            ),
          );
        }
        if (chunk.action) {
          setActions((prev) => {
            const existing = prev.find((item) => item.id === chunk.action!.id);
            if (existing) {
              return prev.map((item) => (item.id === chunk.action!.id ? { ...existing, ...chunk.action! } : item));
            }
            return [...prev, chunk.action!];
          });
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantMessage.id
                ? {
                    ...message,
                    pendingActions: message.pendingActions?.some((action) => action.id === chunk.action!.id)
                      ? message.pendingActions
                      : [...(message.pendingActions ?? []), chunk.action!],
                  }
                : message,
            ),
          );
        }
        if (chunk.done) {
          setStreaming(false);
        }
      }
    } catch (error) {
      const description = error instanceof Error ? error.message : "Unknown error";
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMessage.id
            ? {
                ...message,
                content: `⚠️ ${description}`,
                streaming: false,
              }
            : message,
        ),
      );
      setStreaming(false);
    }
  }, [chatInput, webUrl]);

  const subscribeToJob = useCallback(
    (jobId: string) => {
      if (jobStreams.current[jobId]) return;
      const controller = streamJob(jobId, (event) => {
        setLogEvents((prev) => {
          const next = [...prev, event];
          return next.slice(-400);
        });
        setJobs((prev) =>
          prev.map((job) =>
            job.id === jobId
              ? {
                  ...job,
                  lastEvent: event,
                  progress: typeof event.meta?.progress === "number" ? event.meta.progress : job.progress,
                  status: (event.meta?.status as JobSummary["status"]) ?? job.status,
                }
              : job,
          ),
        );
      });
      jobStreams.current[jobId] = controller;
    },
    [],
  );

  useEffect(() => closeAllStreams, [closeAllStreams]);

  useEffect(() => {
    const load = async () => {
      try {
        const status = await fetchLlmStatus().catch((error: Error) => {
          setLlmError(error.message);
          return undefined;
        });
        if (status) {
          setLlmStatus(status);
          setLlmError(undefined);
        }
        const jobsResponse = await listJobs().catch(() => []);
        setJobs(
          jobsResponse.map((job) => ({
            ...job,
            progress: Number.isFinite(job.progress) ? job.progress : 0,
          })),
        );
        jobsResponse.forEach((job) => subscribeToJob(job.id));
      } catch (error) {
        console.warn("Failed to initialize", error);
      }
    };
    setLlmLoading(true);
    load().finally(() => setLlmLoading(false));
  }, [subscribeToJob]);

  const handleApproveAction = useCallback(
    async (action: AgentAction, note?: string) => {
      try {
        optimisticActionUpdate(action.id, setActions, "approved");
        await acknowledgeAction(action.id, "approved", note);
        if (action.type === "crawl") {
          const scope: CrawlScope = {
            ...defaultScope,
            ...(action.payload.scope as Partial<CrawlScope>),
          };
          const response = await queueCrawl({
            url: String(action.payload.url ?? action.payload.target ?? action.payload.source ?? webUrl),
            scope,
            note,
          });
          const jobId = response.jobId ?? response.id ?? response.job?.id;
          if (jobId) {
            const job: JobSummary = {
              id: jobId,
              status: "queued",
              progress: 0,
              totals: {
                queued: 1,
                running: 0,
                done: 0,
                errors: 0,
              },
              lastEvent: {
                id: crypto.randomUUID(),
                type: "info",
                message: `Crawl queued for ${action.payload.url}`,
                ts: new Date().toISOString(),
                jobId,
              },
            };
            setJobs((prev) => [job, ...prev.filter((existing) => existing.id !== jobId)]);
            subscribeToJob(jobId);
            setActiveJobId(jobId);
          }
        }
      } catch (error) {
        optimisticActionUpdate(action.id, setActions, "error");
        console.error("Failed to approve action", error);
      }
    },
    [subscribeToJob, webUrl],
  );

  const handleDismissAction = useCallback(async (action: AgentAction) => {
    optimisticActionUpdate(action.id, setActions, "dismissed");
    await acknowledgeAction(action.id, "dismissed");
  }, []);

  const handleQueueUrl = useCallback((url: string) => {
    try {
      const hostname = new URL(url).hostname;
      setPendingCrawls((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          url,
          scope: {
            ...defaultScope,
            domains: hostname ? [hostname] : [],
          },
        },
      ]);
    } catch (error) {
      setLogEvents((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          type: "error",
          message: `Invalid URL dropped: ${url}`,
          ts: new Date().toISOString(),
        },
      ]);
    }
  }, []);

  const handleLaunchCrawl = useCallback(
    async (item: PendingCrawl) => {
      try {
        const response = await queueCrawl({ url: item.url, scope: item.scope, note: item.note });
        const jobId = response.jobId ?? response.id ?? response.job?.id ?? crypto.randomUUID();
        const job: JobSummary = {
          id: jobId,
          status: "queued",
          progress: 0,
          totals: { queued: 1, running: 0, done: 0, errors: 0 },
        };
        setJobs((prev) => [job, ...prev.filter((existing) => existing.id !== jobId)]);
        subscribeToJob(jobId);
        setLogEvents((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            jobId,
            type: "info",
            message: `Manual crawl queued for ${item.url}`,
            ts: new Date().toISOString(),
          },
        ]);
      } catch (error) {
        setLogEvents((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "error",
            message: `Failed to queue crawl for ${item.url}: ${error instanceof Error ? error.message : String(error)}`,
            ts: new Date().toISOString(),
          },
        ]);
      } finally {
        setPendingCrawls((prev) => prev.filter((entry) => entry.id !== item.id));
      }
    },
    [subscribeToJob],
  );

  const handleOmniboxSubmit = useCallback(
    async (value: string) => {
      if (!value) return;
      if (isProbablyUrl(value)) {
        setWebUrl(value);
        setOmniboxValue(value);
        setLogEvents((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "info",
            message: `Navigated to ${value}`,
            ts: new Date().toISOString(),
          },
        ]);
      } else {
        setChatInput(value);
        setLogEvents((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "info",
            message: `Searching local index for “${value}”`,
            ts: new Date().toISOString(),
          },
        ]);
        try {
          const results = await searchIndex(value);
          const content = results.hits
            ? results.hits
                .map((hit: { title: string; url: string; summary?: string }, index: number) =>
                  `${index + 1}. ${hit.title} — ${hit.url}\n${hit.summary ?? ""}`,
                )
                .join("\n\n")
            : JSON.stringify(results, null, 2);
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "system",
              content: `Search results for “${value}”:\n${content}`,
              createdAt: new Date().toISOString(),
            },
          ]);
        } catch (error) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "system",
              content: `Failed to search: ${error instanceof Error ? error.message : String(error)}`,
              createdAt: new Date().toISOString(),
            },
          ]);
        }
      }
    },
    [],
  );

  const handleCommand = useCallback(
    (command: string) => {
      if (command === "start crawl") {
        if (webUrl) {
          handleQueueUrl(webUrl);
        }
      } else if (command === "open settings") {
        document.getElementById("settings-panel")?.scrollIntoView({ behavior: "smooth" });
      } else if (command === "explain plan") {
        setChatInput("Explain the current crawl plan");
      }
    },
    [handleQueueUrl, webUrl],
  );

  const rightColumn = useMemo(() => {
    return (
      <div className="grid h-full grid-rows-[minmax(0,1fr)_auto] gap-4">
        <ChatPanel
          messages={messages}
          actions={actions}
          input={chatInput}
          onInputChange={setChatInput}
          onSend={sendChat}
          disabled={streaming}
          onActionApprove={handleApproveAction}
          onActionDismiss={handleDismissAction}
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <JobStatus jobs={jobs} activeJobId={activeJobId} onSelect={setActiveJobId} />
          <div id="settings-panel">
            <SettingsModels
              status={llmStatus}
              loading={llmLoading}
              error={llmError}
              onRefresh={async () => {
                setLlmLoading(true);
                try {
                  const status = await fetchLlmStatus();
                  setLlmStatus(status);
                  setLlmError(undefined);
                } catch (error) {
                  setLlmError(error instanceof Error ? error.message : String(error));
                } finally {
                  setLlmLoading(false);
                }
              }}
              onUpdateSelection={(type, model) => {
                setLogEvents((prev) => [
                  ...prev,
                  {
                    id: crypto.randomUUID(),
                    type: "info",
                    message: `Requested ${type} model change to ${model}`,
                    ts: new Date().toISOString(),
                  },
                ]);
              }}
            />
          </div>
        </div>
      </div>
    );
  }, [
    actions,
    chatInput,
    handleApproveAction,
    handleDismissAction,
    jobs,
    llmError,
    llmLoading,
    llmStatus,
    messages,
    sendChat,
    streaming,
    activeJobId,
  ]);

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-foreground">
      <header className="sticky top-0 z-30 border-b border-white/5 bg-black/40 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="secondary" className="bg-emerald-500/20 text-emerald-200">
                <ShieldCheck className="mr-1 h-3.5 w-3.5" /> Manual control
              </Badge>
              <Badge variant="secondary" className="bg-sky-500/20 text-sky-200">
                <Compass className="mr-1 h-3.5 w-3.5" /> Copilot ready
              </Badge>
              <Badge variant="secondary" className="bg-amber-400/20 text-amber-100">
                <Database className="mr-1 h-3.5 w-3.5" /> Local index
              </Badge>
            </div>
            <h1 className="text-2xl font-semibold text-white">Atlas Agent Console</h1>
            <p className="max-w-3xl text-sm text-slate-200">
              Browse the web, coordinate crawls, and approve every action. Nothing happens without your consent.
            </p>
          </div>
          <Omnibox value={omniboxValue} onChange={setOmniboxValue} onSubmit={handleOmniboxSubmit} />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col gap-6 px-6 py-6 lg:grid lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="flex min-h-[600px] flex-col gap-4">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="flex h-[60vh] flex-col overflow-hidden rounded-3xl border border-white/10 bg-black/30 shadow-xl">
            <WebPreview
              url={webUrl}
              onNavigate={(next) => {
                setWebUrl(next);
                setOmniboxValue(next);
              }}
              onQueueAction={(actionType, payload) => {
                if (actionType === "crawl" && payload.url) {
                  handleQueueUrl(payload.url);
                }
                setMessages((prev) => [
                  ...prev,
                  {
                    id: crypto.randomUUID(),
                    role: "system",
                    content: `${actionType} request staged for ${payload.url}`,
                    createdAt: new Date().toISOString(),
                  },
                ]);
              }}
            />
          </motion.div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
              <CrawlManager
                items={pendingCrawls}
                onDropUrl={handleQueueUrl}
                onScopeChange={(id, scope) =>
                  setPendingCrawls((prev) => prev.map((item) => (item.id === id ? { ...item, scope } : item)))
                }
                onLaunch={handleLaunchCrawl}
                onRemove={(id) => setPendingCrawls((prev) => prev.filter((item) => item.id !== id))}
                suggestedActions={actions.filter((action) => action.type === "crawl" && action.status === "proposed")}
              />
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
              <AgentLog events={logEvents} />
            </motion.div>
          </div>
        </section>
        <section className="flex min-h-[600px] flex-col gap-4">{rightColumn}</section>
      </main>
      <footer className="border-t border-white/5 bg-black/40 px-6 py-4 text-xs text-slate-300">
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <span>Activity updated {logEvents.length ? toRelativeTime(new Date(logEvents[logEvents.length - 1]?.ts ?? Date.now())) : "just now"}</span>
          <div className="flex items-center gap-2 text-amber-200">
            <AlertCircle className="h-4 w-4" /> Agent actions require approval before execution.
          </div>
        </div>
      </footer>
      <CommandPalette onAction={handleCommand} loading={streaming} />
    </div>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
