import { notFound, redirect } from "next/navigation";

import { kindForSlug } from "@/components/service-shell/frameRoutes";
import { newUrlForOldService } from "@/lib/admin/client-route";

/**
 * T6: the old workspace URLs, `/admin/services/{id}/{segment}`, kept as
 * redirects into the client-scoped frame so bookmarks and every link still
 * built by `workspaceHref` keep working. The service's client and kind come
 * from the admin-only service read; a segment naming the wrong kind goes to
 * the service's real kind (it used to mount the wrong workspace).
 */
export default async function OldServicePage(props: {
  params: Promise<{ id: string; segment: string }>;
}): Promise<never> {
  const { id, segment } = await props.params;
  if (!kindForSlug(segment)) notFound();
  const to = await newUrlForOldService(id);
  console.info("[client_frame] old URL", id, segment, "->", to);
  redirect(to);
}
