Summary
- Checks: `pytest tests/backend tests/api tests/integration` (pass), `npm --prefix frontend run lint` (pass), `pytest tests/e2e/test_zero_touch.py` (timed out after backend/frontend bootstrapping), no dedicated typecheck script available.
- Result: Minor issues fixed; see notes below for remaining items.

Backend
- No contract or route changes required; existing suites cover the documented `/api/*` surface.
- Duplicate SQL snapshots live at `backend/app/db/008_app_config.sql`, `backend/app/db/20251102_app_config.sql`, and `backend/app/db/20251115_desktop_defaults.sql`; the migrator only reads the `backend/app/db/migrations/` copies, so these appear stale/background-only.

Frontend
- Moved `ChatThreadProvider` to `frontend/src/app/layout.tsx` and removed the nested wrapper in `frontend/src/components/shell/AppShell.tsx` so all routes share chat context (fixes `useChatThread` runtime errors on non-shell pages).
- Updated `frontend/src/components/UsePageContextToggle.tsx` to expose “Use current page context” as the accessible label, matching the e2e selector expectation.
- Marked unused/legacy candidates with inline comments: `frontend/src/components/PageContextChatPanel.tsx`, `frontend/src/components/local-discovery-panel.tsx`, `frontend/src/components/DocInspector.tsx`.

Config / Scripts
- Installed `pytest-playwright` from `requirements-dev.txt` locally so the `page` fixture is available; no repository changes needed.

Outstanding issues
- `pytest tests/e2e/test_zero_touch.py` still timed out after 120s while the zero-touch stack was bringing up backend/frontend; may need a longer timeout or pre-running the servers before invoking pytest.
- Confirm whether the duplicate SQL files under `backend/app/db/` can be removed or documented; the active migrator uses the versions under `backend/app/db/migrations/`.
