import { proxyJson } from "../../../_proxy";

/**
 * POST /api/proxy/attack/deliverables/{id}/release - release a finalized
 * deliverable to the client (issue 4).
 *
 * This route did not exist. releaseAttackDeliverable() in the web client lib
 * called straight into a 404, so the release path was broken end-to-end even
 * before you consider that nothing rendered a button for it - which is why no
 * client could ever see a dashboard.
 */
export async function POST(
  _request: Request,
  props: { params: Promise<{ id: string }> },
) {
  const params = await props.params;
  return proxyJson(`/attack/deliverables/${params.id}/release`, {
    method: "POST",
  });
}
