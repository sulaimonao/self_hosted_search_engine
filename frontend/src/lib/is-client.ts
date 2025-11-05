export function isClient(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

export default isClient;
