#!/usr/bin/env node

/* eslint-disable no-console */

const API_BASE =
  (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:5050").replace(/\/$/, "") ||
  "http://127.0.0.1:5050";
const RENDERER_URL = (() => {
  const fallback = "http://127.0.0.1:3100";
  const raw = process.env.DESKTOP_RENDERER_URL;
  if (!raw) {
    return fallback;
  }
  try {
    const normalized = new URL(raw);
    return normalized.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
})();
const EMBEDDING_DEFAULT = ["embeddinggemma"];
const CHAT_DEFAULT = ["gemma:2b"];

const MAX_ATTEMPTS = Number.parseInt(process.env.DESKTOP_PREFLIGHT_ATTEMPTS ?? "20", 10);
const POLL_INTERVAL_MS = Number.parseInt(process.env.DESKTOP_PREFLIGHT_INTERVAL ?? "1500", 10);
const HEALTH_ATTEMPTS = Number.parseInt(process.env.DESKTOP_PREFLIGHT_HEALTH_ATTEMPTS ?? "10", 10);
const HEALTH_INTERVAL_MS = Number.parseInt(
  process.env.DESKTOP_PREFLIGHT_HEALTH_INTERVAL ?? "500",
  10,
);

function parseList(value, fallback) {
  if (!value) {
    return fallback;
  }
  const parts = value
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
  return parts.length > 0 ? parts : fallback;
}

const EMBEDDING_MODELS = parseList(process.env.DESKTOP_EMBED_MODELS, EMBEDDING_DEFAULT);
const CHAT_MODELS = parseList(process.env.DESKTOP_CHAT_MODELS, CHAT_DEFAULT);

function log(message) {
  console.log(`[desktop:preflight] ${message}`);
}

async function sleep(ms) {
  await new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function fetchJson(path, init) {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      detail ? `Request ${path} failed (${response.status}): ${detail}` : `Request ${path} failed (${response.status})`,
    );
  }
  return response.json();
}

async function ensureRendererReady() {
  const target = `${RENDERER_URL.replace(/\/$/, "")}/api/__meta`;
  try {
    const response = await fetch(target, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Renderer meta check failed (${response.status})`);
    }
    const payload = await response.json();
    if (!payload?.ok || typeof payload.bootId !== "string") {
      throw new Error("Renderer meta payload invalid");
    }
    log(`Renderer ready (bootId=${payload.bootId}, pid=${payload.pid ?? "unknown"}).`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Renderer validation failed: ${message}`);
  }
}

async function ensureHealth() {
  for (let attempt = 0; attempt < HEALTH_ATTEMPTS; attempt += 1) {
    try {
      await fetchJson("/api/meta/health");
      log("Backend health check passed.");
      return;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      log(`Backend health attempt ${attempt + 1}/${HEALTH_ATTEMPTS} failed: ${message}`);
      await sleep(HEALTH_INTERVAL_MS);
    }
  }
  throw new Error("Backend health check failed after multiple attempts.");
}

async function getCapabilities() {
  return fetchJson("/api/meta/capabilities", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
}

async function installModels(kind, models) {
  const payload = {};
  payload[kind] = models;
  log(`Requesting installation for ${kind} models: ${models.join(", ")}`);
  return fetchJson("/api/admin/install_models", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
}

function describeInstallSummary(kind, response) {
  const installed = (response.installed?.[kind]) ?? [];
  const skipped = (response.skipped?.[kind]) ?? [];
  if (installed.length > 0) {
    log(`Started installation for ${kind} models: ${installed.join(", ")}`);
  }
  if (skipped.length > 0) {
    log(`Skipped ${kind} models (already installed): ${skipped.join(", ")}`);
  }
  if (response.errors && response.errors.length > 0) {
    response.errors.forEach((error) => {
      log(`Model install error: ${error}`);
    });
  }
}

async function waitForCapability(label, predicate, initialCaps) {
  let caps = initialCaps ?? (await getCapabilities());
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    if (predicate(caps)) {
      log(`${label} ready after ${attempt + 1} attempt(s).`);
      return caps;
    }
    await sleep(POLL_INTERVAL_MS);
    caps = await getCapabilities();
  }
  throw new Error(`${label} not ready after ${MAX_ATTEMPTS} attempts.`);
}

async function ensureEmbeddingReady(initialCaps) {
  if (initialCaps.search?.vector) {
    log("Vector search already available.");
    return initialCaps;
  }
  const targets = initialCaps.search?.embedding?.model
    ? [initialCaps.search.embedding.model]
    : EMBEDDING_MODELS;
  if (targets.length === 0) {
    log("No embedding models configured; skipping vector readiness check.");
    return initialCaps;
  }
  const response = await installModels("embedding", targets);
  describeInstallSummary("embedding", response);
  if (response.errors && response.errors.length > 0) {
    throw new Error(`Embedding installation failed: ${response.errors.join("; ")}`);
  }
  return waitForCapability("Embedding model", (caps) => Boolean(caps.search?.vector));
}

async function ensureChatReady(initialCaps) {
  if (initialCaps.llm?.chat) {
    log("Chat models already available.");
    return initialCaps;
  }
  const targets = CHAT_MODELS;
  if (targets.length === 0) {
    log("No chat models configured; skipping chat readiness check.");
    return initialCaps;
  }
  const response = await installModels("chat", targets);
  describeInstallSummary("chat", response);
  if (response.errors && response.errors.length > 0) {
    throw new Error(`Chat model installation failed: ${response.errors.join("; ")}`);
  }
  return waitForCapability("Chat model", (caps) => Boolean(caps.llm?.chat));
}

async function main() {
  log(`Preflight starting against renderer=${RENDERER_URL} api=${API_BASE}`);
  await ensureRendererReady();
  await ensureHealth();

  let caps = await getCapabilities();
  log(
    `Capabilities snapshot: vector=${Boolean(caps.search?.vector)}, hybrid=${Boolean(
      caps.search?.hybrid,
    )}, chat=${Boolean(caps.llm?.chat)}`,
  );

  caps = await ensureEmbeddingReady(caps);
  caps = await ensureChatReady(caps);

  if (!caps.search?.hybrid && caps.search?.bm25) {
    log("Hybrid search disabled; BM25 fallback only.");
  }

  log("Preflight complete. Backend ready.");
}

main()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[desktop:preflight] ${message}`);
    process.exit(1);
  });

