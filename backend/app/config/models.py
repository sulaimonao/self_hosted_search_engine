"""Pydantic models describing persisted application configuration."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ModelRef(BaseModel):
    """Reference to an LLM or embedding model."""

    name: str


class SeedSources(BaseModel):
    """Seed discovery sources grouped by category."""

    news: List[str] = Field(default_factory=list)
    music: List[str] = Field(default_factory=list)
    tech: List[str] = Field(default_factory=list)
    art: List[str] = Field(default_factory=list)
    other: List[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """Full application configuration with sensible defaults."""

    # models
    models_primary: ModelRef = Field(default=ModelRef(name="gemma-3"))
    models_fallback: ModelRef = Field(default=ModelRef(name="gpt-oss"))
    models_embedder: ModelRef = Field(default=ModelRef(name="embeddinggemma"))

    # feature toggles
    features_shadow_mode: bool = True
    features_agent_mode: bool = True
    features_local_discovery: bool = True
    features_browsing_fallbacks: bool = True
    features_index_auto_rebuild: bool = True
    features_auth_clearance_detectors: bool = False

    # chat defaults
    chat_use_page_context_default: bool = True

    # browser/session
    browser_persist: bool = True
    browser_allow_cookies: bool = True

    # developer diagnostics
    dev_render_loop_guard: bool = True

    # seed sources
    sources_seed: SeedSources = Field(default_factory=SeedSources)

    # setup state
    setup_completed: bool = False
