import { proxyJson } from "../../../../../_proxy";

/**
 * POST /api/proxy/risk/clients/{cid}/services/{sid}/archive (#896 review B2).
 *
 * The Risk Register's duplicate banner archives through here. The api
 * re-checks that the service is still one of a duplicate group and answers
 * 204, or a typed 409 `service_not_in_duplicate_group`.
 */
export async function POST(
  _request: Request,
  props: { params: Promise<{ cid: string; sid: string }> },
) {
  const params = await props.params;
  return proxyJson(
    `/risk/clients/${params.cid}/services/${params.sid}/archive`,
    { method: "POST" },
  );
}
