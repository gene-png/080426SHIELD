import { Children, Fragment, isValidElement, type ReactNode } from "react";

/**
 * Refusals shared by the service-shell pieces. Each piece renders caller text
 * next to approved copy, so a blank value would leave approved copy dangling
 * ("Next: " with nothing after it, a label over nothing). They throw rather
 * than render a degraded version, because nothing here can tell the reader
 * what is missing.
 *
 * There is no error boundary in apps/web yet, so a throw blanks the route.
 * Each piece's docstring says which of its throws are CALLER bugs (fixed in
 * code, never reachable once a page is written correctly) and which are
 * DATA-driven (a value from the API or an AI run), which a mounting page must
 * expect and handle until a boundary exists.
 */
export function requireText(where: string, name: string, value: unknown): void {
  // Type first: `null.trim()` would throw an unnamed TypeError instead of
  // saying which field was missing.
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${where}: a blank ${name}.`);
  }
}

/**
 * Whether `node` renders anything a reader would see. `Children.toArray`
 * drops null, undefined and booleans (so `true`, `false` and `[]` come back
 * empty), but does NOT look inside fragments, so this recurses into any
 * element whose type is Fragment. On top of that a blank string and the
 * number 0 count as nothing, because `{count && <X/>}` renders a bare "0".
 *
 * What it cannot see: a child COMPONENT that renders null. `<Rows />` is an
 * element, so it counts as content whatever it returns; only rendering it
 * would tell, and a guard that rendered children would change what renders.
 * A caller wrapping a component that may render nothing must check its data
 * before rendering the wrapper.
 */
export function hasContent(node: ReactNode): boolean {
  return Children.toArray(node).some((item) => {
    if (isValidElement(item) && item.type === Fragment) {
      return hasContent((item.props as { children?: ReactNode }).children);
    }
    return !(typeof item === "string" && !item.trim()) && item !== 0;
  });
}
