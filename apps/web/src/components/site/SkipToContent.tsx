import type { JSX } from "react";

/**
 * Every `<main id="main-content">` pairs `tabIndex={-1}` with the classes
 * `focus:outline-2 focus:outline-offset-4 focus:outline-brand-500` (issue 5).
 *
 * Focus already moved programmatically on activation (WAI-ARIA skip-link
 * practice), but the shells carried a bare `outline-hidden`, so on a short page
 * the jump produced NO visible change — which reads as a broken link even
 * though it worked. The focus ring is that missing feedback.
 *
 * `outline-hidden` had to be REMOVED, not merely supplemented: it sets
 * `outline-style: none`, which cancels the ring even though the focus utilities
 * apply the width and colour (verified in-browser — computed outline-style
 * stayed "none" until it was dropped). `main` only ever receives focus via this
 * link, so the ring appears exactly when the link is used and never during
 * ordinary tabbing. Classes are inline in each shell because Tailwind's JIT
 * only scans literal strings.
 */

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
