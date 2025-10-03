const TRUTHY_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSY_VALUES = new Set(["0", "false", "no", "off"]);

function parseFlag(value: string | undefined | null, fallback: boolean): boolean {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length > 0) {
      const normalized = trimmed.toLowerCase();
      if (TRUTHY_VALUES.has(normalized)) {
        return true;
      }
      if (FALSY_VALUES.has(normalized)) {
        return false;
      }
    }
  }
  return fallback;
}

export const AGENT_ENABLED = parseFlag(process.env.NEXT_PUBLIC_AGENT_ENABLED, false);
export const IN_APP_BROWSER_ENABLED = parseFlag(process.env.NEXT_PUBLIC_IN_APP_BROWSER, true);

export { parseFlag as parseFeatureFlag };
