import { expect, test } from "@playwright/test";

test.setTimeout(60_000);

function resolveBaseUrl(): string {
  const fromEnv = process.env.PLAYWRIGHT_APP_URL;
  if (typeof fromEnv === "string" && fromEnv.trim()) {
    return fromEnv.trim().replace(/\/$/, "");
  }
  return "http://127.0.0.1:3100";
}

test.describe("render loop guard", () => {
  test("no render loop markers on /browser", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        errors.push(msg.text());
      }
    });

  const baseUrl = resolveBaseUrl();
  // Sanity: backend meta should respond (helps fail fast if API isn't up yet)
  const api = process.env.API_URL || "http://127.0.0.1:5050/api/__meta";
  const res = await page.request.get(api);
  expect(res.ok()).toBeTruthy();

  // In dev, WS/SSE keeps the network active, so "networkidle" may never happen.
  await page.goto(`${baseUrl}/browser`, { waitUntil: "domcontentloaded" });
  // Prove we actually landed on /browser and the shell mounted
  await page.waitForSelector("body", { timeout: 10000 });
  // If your Browser page has a stable marker, prefer it (uncomment and adjust):
  // await page.waitForSelector('[data-testid="browser-root"]', { timeout: 10000 });

  // Optional: give Next.js a moment to settle initial client work
  await page.waitForTimeout(600);

    const joined = errors.join("\n");
    expect(joined).not.toContain("[render-loop]");
  });
});

