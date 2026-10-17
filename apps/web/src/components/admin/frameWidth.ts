/**
 * Which width rules an admin page runs under (#1050, #1385). Shared by the
 * admin shell and the client frame's body, so the two cannot disagree about
 * where the page's padding and readable cap live.
 */

/**
 * #1050: a service workspace (`/admin/services/<id>/...`) carries wide
 * editable tables, so it runs full-width. List and form pages keep the
 * readable `max-w-6xl` cap. T6: a section of the client frame
 * (`/admin/clients/<id>/services/<slug>/<section>`) wraps that workspace, so
 * it runs full-width too.
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
 */
export function isClientFramePage(pathname: string): boolean {
  return /^\/admin\/clients\/[^/]+(\/|$)/.test(pathname);
}
