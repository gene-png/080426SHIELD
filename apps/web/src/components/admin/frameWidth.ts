/**
 * Which width rules an admin page runs under (#1050, #1385). Shared by the
 * admin shell and the client frame's body, so the two cannot disagree about
 * where the page's padding and readable cap live.
 */

/**
 * #1050: a service workspace (`/admin/services/<id>/...`) carries wide
 * editable tables, so it runs full-width. T6: a section of the client frame
 * (`/admin/clients/<id>/services/<slug>/<section>`) wraps that workspace, so
 * it runs full-width too. Inside a client's frame the other pages keep the
 * readable `max-w-6xl` cap (`ClientFrameBody`); #1385: a page with no client
 * is capped by nothing.
 */
export function isWorkspace(pathname: string): boolean {
  return (
    /^\/admin\/services\/[^/]+\/.+/.test(pathname) ||
    /^\/admin\/clients\/[^/]+\/services\/[^/]+\/[^/]+/.test(pathname)
  );
}

/**
 * #1385: a page under ONE client's frame (`/admin/clients/<id>` and below, not
 * the clients list). The client's rail is the page's left column, flush to the
 * edge under the top bar, so the shell leaves the page's own padding and cap
 * to the frame (`ClientFrameBody`) instead of applying them around the rail.
 *
 * The URL decides this here and the route structure decides it in the client
 * layout; they agree while every page under `/admin/clients/<id>` is in that
 * layout. A static page added beside `[clientId]` (say `clients/new`) would get
 * this rule without the rail, so add it here at the same time.
 */
export function isClientFramePage(pathname: string): boolean {
  return /^\/admin\/clients\/[^/]+(\/|$)/.test(pathname);
}
