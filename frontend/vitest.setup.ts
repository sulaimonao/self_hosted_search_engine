import "@testing-library/jest-dom/vitest";

// Provide a default API base for tests so code that calls `fetch('/api/...')`
// does not throw "Invalid URL" in node/JSDOM environment. Tests can override
// `globalThis.__TEST_API_BASE__` if they need to point to a different host.
const DEFAULT_TEST_API_BASE = process.env.TEST_API_BASE ?? "http://127.0.0.1:5050";

// Helper to resolve relative /api paths to a full URL during tests.
function resolveTestUrl(input: RequestInfo): RequestInfo {
	if (typeof input === "string" && input.startsWith("/api")) {
		const g = globalThis as unknown as { __TEST_API_BASE__?: string };
		const base = g.__TEST_API_BASE__ ?? DEFAULT_TEST_API_BASE;
		return `${base}${input}`;
	}
	return input;
}

// Patch global fetch once for the test environment. This keeps behavior
// predictable for code that constructs relative fetch paths.
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input: RequestInfo, init?: RequestInit) => {
	// prefer the original fetch implementation but call via globalThis.fetch fallback
	const fetchImpl = originalFetch ?? globalThis.fetch;
	return fetchImpl(resolveTestUrl(input), init);
};

// Simple ErrorBoundary component for tests to wrap components that intentionally
// throw so tests can assert logging/handling without leaking errors to JSDOM.
import React from "react";
// Return a React element that tests can use to wrap components. We avoid
// using JSX here so this .ts file doesn't need TSX parsing.
export function wrapWithTestBoundary(children: React.ReactNode) {
	return React.createElement(React.StrictMode, null, children);
}
