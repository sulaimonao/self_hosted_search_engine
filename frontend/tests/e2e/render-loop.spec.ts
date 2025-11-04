import { expect, test } from "@playwright/test";

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
    await page.goto(`${baseUrl}/browser`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);

    const joined = errors.join("\n");
    expect(joined).not.toContain("[render-loop]");
  });
});

