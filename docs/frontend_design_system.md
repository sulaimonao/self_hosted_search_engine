# Frontend design system

## Theme overview
- **Dark research cockpit**: Every screen assumes dim environments and long working sessions. Backgrounds stay near-black while foreground elements glow softly so you can scan data without fatigue.
- **Neutral, layered surfaces**: We stack subtle neutrals (`bg-app-bg`, `bg-app-subtle`, `bg-app-card`, `bg-app-elevated`) to hint at depth without harsh lines.
- **Single accent, calm chrome**: Purple is the only interactive hue (`bg-accent`, `text-fg-on-accent`). Everything else relies on muted chrome so the accent can signal focus.

## Semantic tokens
### Surfaces
- `bg-app-bg`: Full-page background. Apply to html/body level containers.
- `bg-app-subtle`: Section fills, secondary columns, muted inputs.
- `bg-app-elevated`: Floating panels (drawers, dialogs) that sit above the shell chrome.
- `bg-app-card`: Default card body/background. Pair with `border-border-subtle` and `shadow-subtle`.
- `bg-app-card-subtle`: Softer card background for nested UI or user chat bubbles.
- `bg-app-card-hover`: Shared hover fill for list rows, cards, and shell nav interactions.
- `bg-app-input`: Inputs, address bar, token filters.
- `bg-ai-panel`: Copilot side panel background.

### Text
- `text-fg`: High-emphasis text and key numbers.
- `text-fg-muted`: Secondary labels, metadata, helper copy.
- `text-fg-subtle`: De-emphasized timestamps, placeholder text.
- `text-fg-on-accent`: Text placed on the accent or on `bg-accent-soft`.

### Borders
- `border-border-subtle`: Default strokes, card outlines, separators.
- `border-border-strong`: Draggable rails, split panes, or key focus affordances.
- `border-ai-border`: Outer edge of the AI panel and its header.

### Accent and states
- `bg-accent` + `text-fg-on-accent`: Primary buttons, toggles, selected pills.
- `bg-accent-soft`: Accent wash for highlighted regions (assistant chat bubble, AI suggestions).
- `text-state-success | warning | danger | info`: Inline status pills, charts, and progress text.
- `bg-state-*` is intentionally absent—prefer border/text to avoid noisy alerts.

### Radii, shadows, motion
- `rounded-xs`, `rounded-md`, `rounded-xl`: Use XS for pills/inputs, MD for cards, XL for modals or floating shells.
- `shadow-soft`, `shadow-subtle`: Subtle for cards and tables, soft for dialogs/panels.
- Motion uses the default easing/durations (`transition ease-default duration-normal`) and should stay understated.

## Usage rules
### Cards and panels
- Combine `bg-app-card`, `border-border-subtle`, `rounded-md`, and `shadow-subtle` for primary cards. Use `bg-app-elevated` when a card floats over other cards (drawers, modals).
- Nested blocks inside a card should use `bg-app-card-subtle` to differentiate without introducing new hues.

### Inputs
- Always use `bg-app-input border-border-subtle text-fg` with `placeholder:text-fg-subtle`. Apply `focus-visible:ring-2 focus-visible:ring-accent` for accessibility.
- Icon adornments inside inputs use `text-fg-muted`.

### List rows / tables
- Default row: `rounded-md border border-border-subtle bg-app-card transition hover:bg-app-card-hover`.
- Active/selected rows can layer `ring-1 ring-accent/30` and `bg-accent-soft` but should still keep readable text (`text-fg`).

### AI panel & bubbles
- Panel shell uses `bg-ai-panel border border-ai-border shadow-soft`.
- User message: `bg-app-card-subtle text-fg rounded-md`.
- Assistant message: `bg-accent-soft text-fg-on-accent rounded-md`. Pair with `border border-border-subtle` when needed for separation.

### Navigation states
- Sidebar and top nav rely on `text-fg-muted` for idle items. Active item uses `bg-accent-soft text-fg` with a `border-border-strong` underline or pill.
- Hover states reuse `bg-app-card-hover` so pointer feedback feels consistent.

### Status indicators
- Jobs, repo changes, and sync pills should use `text-state-success | warning | danger | info` with matching `border-border-subtle` outlines. Avoid mixing raw Tailwind greens/reds.

## Do & Don’t
- **DO** use `bg-app-card` for any card or panel. `bg-app-subtle` is reserved for gentle sections that still sit inside the app chrome.
- **DO** lean on `text-fg-muted` and `text-fg-subtle` to build hierarchy instead of inventing new opacities.
- **DO** reuse `bg-accent`, `bg-accent-soft`, and `text-fg-on-accent` for all accent-forward UI.
- **DON’T** reach for `bg-slate-900`, `text-gray-400`, or other raw Tailwind colors in new code. Map every color to a semantic token first.
- **DON’T** mix bright alerts with large blocks of saturated red/yellow backgrounds; rely on text color and borders with the provided state tokens.
