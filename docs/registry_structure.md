# Seed Registry Schema

The registry stored at `seeds/registry.yaml` defines curated entrypoints for
bootstrapping discovery. The schema is intentionally data-first so that new
collections can be added without changing Python code. This document explains
how the file is structured and how defaults cascade through the hierarchy.

## Top-level keys

| Key | Required | Description |
| --- | --- | --- |
| `version` | ✅ | Schema revision. Increment when making breaking structural changes. |
| `crawl_defaults` | ✅ | Mapping of default attributes applied to every source (e.g. `strategy`, `trust`, throttling hints). |
| `directories` | ✅ | Mapping of named collections (e.g. `news`, `github_topics`). Each directory groups related sources and can set its own defaults. |
| `sources` | Optional | Legacy list of sources processed after `directories`. Use only when a collection does not fit an existing directory. |

## Default resolution order

Values are merged in the following order (later entries win and enrich the
previous ones):

1. Global `crawl_defaults`
2. Directory-level `defaults`
3. Inline directory attributes (`kind`, `strategy`, `trust`, `tags`)
4. Individual source fields
5. Automatic metadata such as `collection`

List-like `tags` are merged rather than replaced and normalized to lowercase
with duplicates removed. All other values are deep-copied so the loader never
shares mutable references between entries.

## Directory definition

Each directory entry has the following shape:

```yaml
<directory-slug>:
  description: >-
    Human-readable context for the collection (appears in docs only).
  defaults:
    kind: editorial
    strategy: feed
    trust: high
    tags:
      - news
      - rss
  sources:
    - id: news_example
      entrypoints:
        - https://example.com/feed.xml
      trust: medium  # overrides directory default
      cadence: hourly
```

* `description` (optional) documents intent.
* `defaults` (optional) overrides the global defaults for the directory.
* Inline keys `kind`, `strategy`, `trust`, and `tags` are also accepted for
  convenience and are merged into the directory defaults.
* `sources` is a list of mappings where each entry **must** specify:
  * `id` – globally unique identifier.
  * `entrypoints` – a URL string or list of URL strings (full `http(s)` paths only).

Other keys (e.g. `title`, `cadence`, `follow_sitemaps`) are preserved and exposed
through the loader as `extras`.

Every source automatically receives a `collection` extra that mirrors the
directory slug so downstream systems know the origin grouping.

## Trust level guidance

The canonical registry currently defines the following high-level directories:

* `news` — editorial RSS feeds from organizations like AP, Reuters, NPR, and BBC
  with `trust: high`.
* `wikipedia_portals` — curated encyclopedia portals with `trust: high` (or
  `medium` for broader community-maintained areas).
* `github_topics` — GitHub topic hubs with `trust: medium`.
* `awesome_lists` — maintained Awesome lists, defaulting to `trust: high`.
* `sitemap_discovery` — robots.txt seeds for sitemap enumeration with
  `trust: medium` and `follow_sitemaps: true`.

Use these trust defaults when adding new sources unless you have explicit review
signals to justify a change.

## Adding a new source

1. Pick the appropriate directory. If none exists, create a new directory with a
   descriptive slug and defaults.
2. Ensure the `id` is unique across the entire file. Prefixes such as
   `news_`, `github_topic_`, or `sitemap_` help avoid collisions.
3. Provide full absolute URLs for `entrypoints`. Avoid relative paths.
4. Set any overrides (e.g. `trust`, `strategy`, `tags`) required for the source.
5. Update documentation when introducing a new directory or schema feature.

## Validation

Running the unit tests ensures the loader can interpret the schema:

```bash
pytest tests/test_server_seeds_loader.py
```

The loader will raise `ValueError` if mandatory fields are missing, entrypoint
URLs are invalid, or duplicate IDs are introduced.
