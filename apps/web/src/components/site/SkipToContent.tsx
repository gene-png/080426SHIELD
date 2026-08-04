import type { JSX } from "react";
/**
 * Skip-to-content link (Navigation_Spec §7). Must be the first focusable
 * element in every shell; visually hidden until focused. Targets the
 * `#main-content` landmark each shell renders on its <main>.
 */
export function SkipToContent(): JSX.Element {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-brand-500 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-ink-on-accent"
    >
      Skip to content
    </a>
  );
}
