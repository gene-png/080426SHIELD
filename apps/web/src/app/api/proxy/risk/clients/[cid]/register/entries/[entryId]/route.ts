import { proxyJson } from "../../../../../_proxy";

/**
 * PATCH /api/proxy/risk/clients/{cid}/register/entries/{entryId} (#844).
 *
 * The consultant's likelihood and impact for one entry. The BODY is forwarded:
 * it is the whole request, and a proxy written as `proxyJson(url, { method })`
 * would drop it and every edit would come back 422 from the api.
 */
export async function PATCH(
  request: Request,
  props: { params: Promise<{ cid: string; entryId: string }> },
) {
  const params = await props.params;
  const body: unknown = await request.json();
  return proxyJson(
    `/risk/clients/${params.cid}/register/entries/${params.entryId}`,
    { method: "PATCH", body },
  );
}
