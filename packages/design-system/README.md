# @shield/design-system

Round-6 Design Contract primitives for SHIELD by Kentro v2.0. Self-hosted (no external CSS frameworks beyond Tailwind); every component is keyboard-accessible and screen-reader friendly per WCAG 2.1 AA.

## What's here

| Path                            | Purpose                                                                                                                                             |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/tokens.css`                | CSS custom properties for the Round-6 palette, typography, spacing, radii, shadows, and motion tokens. Imported once at the app root.               |
| `src/tailwind-preset.ts`        | Tailwind preset exposing the same tokens as theme values (`bg-surface-canvas`, `text-ink-primary`, etc.). Apps `presets: [...]` this.               |
| `src/components/Card.tsx`       | Modular card with soft shadow, rounded corners, optional header/footer slots.                                                                       |
| `src/components/StatusPill.tsx` | Compact status badge with reserved alert colors (saturated only for status).                                                                        |
| `src/components/NumberCard.tsx` | KPI card for executive dashboards (label + big number + optional delta).                                                                            |
| `src/components/DataTable.tsx`  | Enterprise-grade dense table primitive. Sticky header, sortable columns, row selection. (Phase-1 baseline; pagination + virtualization in Phase 4.) |
| `src/components/Toast.tsx`      | `aria-live=polite` toast region + `useToast()` hook.                                                                                                |
| `src/components/Modal.tsx`      | Native `<dialog>`-backed modal with focus management and ESC-to-close.                                                                              |
| `src/components/SlideOver.tsx`  | Native `<dialog>`-backed side panel for contextual workflows.                                                                                       |
| `src/components/EmptyState.tsx` | Empty-list message with icon + action.                                                                                                              |
| `src/utils/cn.ts`               | `clsx` + `tailwind-merge` combiner.                                                                                                                 |

## Consuming the package

apps that depend on this package set up their Tailwind to scan the design-system source and apply the preset:

```ts
// apps/<app>/tailwind.config.ts
import preset from "@shield/design-system/tailwind-preset";

export default {
  presets: [preset],
  content: [
    "./src/**/*.{ts,tsx}",
    "../../packages/design-system/src/**/*.{ts,tsx}",
  ],
};
```

And import tokens once at the app root:

```ts
// apps/<app>/src/app/layout.tsx
import "@shield/design-system/tokens.css";
```

## Round-6 tenets enforced here

- **Calm + structured.** No decorative motion. Transitions ≤200 ms; only `opacity` and small `translate`.
- **Neutral enterprise palette.** Saturated colors are reserved for status (`StatusPill`).
- **Operational density.** Tables default to compact row height; cards have soft shadows but no decorative gradients.
- **Accessibility-first.** Every interactive element has visible focus, keyboard support, and an `aria-*` contract.
