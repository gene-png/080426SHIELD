"use client";

/**
 * RR-2 (for #1121), design note §3.3 and §0i. Apply is a FULL page load, so
 * nothing from the old client's mount can run after the switch.
 *
 * `replace`, not `assign`: Back leaves the page, as it always has, and the
 * entry that held the page's `leaving` lock is gone, so Back and Forward
 * cannot return to it. Their own module so vitest can mock them: jsdom's
 * `location` cannot be spied on reliably.
 */
export function leaveTo(url: string): void {
  window.location.replace(url);
}

/** For the `pageshow` handler: a page restored from the back/forward cache. */
export function reloadPage(): void {
  window.location.reload();
}
