"use client";

import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/backend/apiClient";
import type {
  BundleExportResponse,
  BundleImportResponse,
  BrowserTabRecord,
  JobDetailResponse,
  JobRecord,
  MemoryRecord,
  OverviewCounters,
  RepoListResponse,
  RepoStatusSummary,
  TaskRecord,
  ThreadRecord,
} from "@/lib/backend/types";

export function useOverview() {
  return useQuery<OverviewCounters, Error>({
    queryKey: ["overview"],
    queryFn: () => apiClient.get<OverviewCounters>("/api/overview"),
  });
}

export function useThreads(limit = 5) {
  return useQuery<{ items: ThreadRecord[] }, Error>({
    queryKey: ["threads", { limit }],
    queryFn: () => apiClient.get<{ items: ThreadRecord[] }>(`/api/threads?limit=${limit}`),
  });
}

export interface JobsFilter {
  status?: string;
  type?: string;
  limit?: number;
}

export function useJobs(filter: JobsFilter = {}) {
  const params = new URLSearchParams();
  if (filter.status) params.set("status", filter.status);
  if (filter.type) params.set("type", filter.type);
  if (filter.limit) params.set("limit", String(filter.limit));
  const queryKey = ["jobs", filter];
  const queryFn = () => apiClient.get<{ jobs: JobRecord[] }>(`/api/jobs${params.size ? `?${params.toString()}` : ""}`);
  return useQuery<{ jobs: JobRecord[] }, Error>({ queryKey, queryFn });
}

export function useJobDetail(jobId: string | null) {
  return useQuery<JobDetailResponse, Error>({
    queryKey: ["job", jobId],
    queryFn: () => apiClient.get<JobDetailResponse>(`/api/jobs/${jobId}`),
    enabled: Boolean(jobId),
  });
}

export function useTasksByThread(threadId: string | null) {
  return useQuery<{ items: TaskRecord[] }, Error>({
    queryKey: ["tasks", threadId],
    queryFn: () => apiClient.get<{ items: TaskRecord[] }>(`/api/tasks?thread_id=${threadId}`),
    enabled: Boolean(threadId),
  });
}

export function useBrowserTabs(limit = 20) {
  const queryClient = useQueryClient();
  const query = useQuery<{ items: BrowserTabRecord[] }, Error>({
    queryKey: ["browser-tabs", { limit }],
    queryFn: () => apiClient.get<{ items: BrowserTabRecord[] }>(`/api/browser/tabs?limit=${limit}`),
  });

  const bindThread = useMutation({
    mutationFn: async ({ tabId, threadId, origin }: { tabId: string; threadId?: string; origin?: string }) => {
      return apiClient.post<{ thread_id: string }>(`/api/browser/tabs/${tabId}/thread`, {
        thread_id: threadId,
        origin,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["browser-tabs"] });
    },
  });

  return { ...query, bindThread };
}

export function useMemories(threadId: string | null) {
  return useQuery<{ items: MemoryRecord[] }, Error>({
    queryKey: ["memories", threadId],
    enabled: Boolean(threadId),
    queryFn: () =>
      apiClient.post<{ items: MemoryRecord[] }>("/api/memories/search", {
        scope_ref: threadId,
        limit: 10,
      }),
  });
}

export function useRepoList() {
  return useQuery<RepoListResponse, Error>({
    queryKey: ["repos"],
    queryFn: () => apiClient.get<RepoListResponse>("/api/repo/list"),
  });
}

export function useRepoStatus(repoId: string | null) {
  return useQuery<RepoStatusSummary, Error>({
    queryKey: ["repo-status", repoId],
    queryFn: () => apiClient.get<RepoStatusSummary>(`/api/repo/${repoId}/status`),
    enabled: Boolean(repoId),
  });
}

export function useBundleExport() {
  return useMutation<BundleExportResponse, Error, { components?: string[] | null }>(async (params) => {
    const search = new URLSearchParams();
    (params?.components ?? []).forEach((component) => {
      if (component) search.append("component", component);
    });
    const suffix = search.size ? `?${search.toString()}` : "";
    return apiClient.get<BundleExportResponse>(`/api/export/bundle${suffix}`);
  });
}

export function useBundleImport() {
  return useMutation<BundleImportResponse, Error, { bundle_path: string; components?: string[] | null }>((body) =>
    apiClient.post<BundleImportResponse>("/api/import/bundle", body),
  );
}

export function useJobRefetcher() {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }, [queryClient]);
}
