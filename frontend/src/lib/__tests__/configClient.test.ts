import { describe, expect, it } from "vitest";
import { buildPatch, AppConfig } from "../../lib/configClient";

type MinimalAppConfig = Partial<Pick<AppConfig, 'models_primary' | 'models_fallback' | 'models_embedder' | 'features_shadow_mode' | 'setup_completed'>>;

describe("buildPatch", () => {
  it("applies select model fields when provided as strings", () => {
    const patch: Record<string, unknown> = { "models.chat.primary": "gemma-3" };
    const result = buildPatch(patch, undefined);
    expect(result.models_primary).toEqual({ name: "gemma-3" });
  });

  it("ignores select model when value is falsy", () => {
    const patch: Record<string, unknown> = { "models.chat.primary": "" };
  const current: MinimalAppConfig = { models_primary: { name: "old" } };
  const result = buildPatch(patch, current as unknown as AppConfig);
    expect(result.models_primary).toBeUndefined();
  });

  it("applies boolean fields normalized from strings", () => {
    const patch: Record<string, unknown> = { "features.shadow_mode": "false", "setup.completed": "true" };
    const result = buildPatch(patch, undefined);
    expect(result.features_shadow_mode).toBe(false);
    expect(result.setup_completed).toBe(true);
  });

  it("ignores unknown keys", () => {
    const patch: Record<string, unknown> = { "unknown.key": "value", "models.chat.fallback": "gpt-oss" };
    const result = buildPatch(patch, undefined);
    expect((result as Record<string, unknown>)["unknown.key"]).toBeUndefined();
    expect(result.models_fallback).toEqual({ name: "gpt-oss" });
  });
});

