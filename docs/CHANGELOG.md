# Changelog

## Unreleased

### Added
- Electron desktop shell now drives each tab through a sandboxed `BrowserView` and synchronises navigation state, favicons, and titles with the React UI via the new `window.browserAPI` preload bridge.
- Persistent `persist:main` Chromium partition, Chrome 129 user-agent spoof, and hardened navigator properties eliminate Cloudflare/Google bot loops while keeping cookies across restarts.
- Renderer fallback overlay for navigation failures with a retry affordance plus bounds syncing from the React layout to the active `BrowserView`.
